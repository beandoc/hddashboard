"""
pre_deploy.py — run by Render's preDeployCommand before each deploy.

Handles two cases:
  1. Fresh database (no tables yet): alembic upgrade head creates everything.
  2. Existing database (tables present, no alembic_version table):
     stamps as 0001 so alembic knows the baseline is already applied,
     then upgrades head to apply only the incremental migrations (0002+).

After alembic runs, a schema-guard pass checks that every required column
actually exists in the DB and adds any that are missing. This is a safety
net for the case where alembic_version gets ahead of the real schema (e.g.
after a partially-applied deploy on Render).
"""
import subprocess
import sys

from sqlalchemy import inspect, text

# DATABASE_URL must be set in the environment (Render injects it).
from database import engine


# Columns that must exist per table. Each entry is:
#   (column_name, DDL_type_string)
# Only add columns here that have a corresponding migration; this list is
# the fallback guard, not a replacement for migrations.
_REQUIRED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "monthly_records": [
        ("reticulocyte_count", "FLOAT"),
        ("hemostasis_time_mins", "FLOAT"),
        ("hospitalization_icu_admission", "BOOLEAN"),
        ("hospitalization_severity", "VARCHAR"),
    ],
    "hospitalisation_events": [
        ("severity", "VARCHAR"),
        ("icu_admission", "BOOLEAN"),
        ("pct", "FLOAT"),
        ("shock_on_admission", "INTEGER"),
        ("inotrope_days", "FLOAT"),
        ("ventilation_days", "FLOAT"),
        ("transfusion_units", "FLOAT"),
    ],
}


def _has_table(name: str) -> bool:
    return inspect(engine).has_table(name)


def _ensure_columns() -> None:
    """Add any missing columns using IF NOT EXISTS for each guarded table."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table_name, required_cols in _REQUIRED_COLUMNS.items():
            if not insp.has_table(table_name):
                continue
            existing = {col["name"] for col in insp.get_columns(table_name)}
            for col_name, col_type in required_cols:
                if col_name not in existing:
                    print(
                        f"[pre_deploy] Schema guard: adding missing column"
                        f" {table_name}.{col_name} ({col_type}) …"
                    )
                    conn.execute(
                        text(
                            f"ALTER TABLE {table_name}"
                            f" ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                        )
                    )
                    print(f"[pre_deploy] Schema guard: {table_name}.{col_name} added.")


def main() -> int:
    with engine.connect() as conn:  # noqa: F841 — side-effect: validates connectivity
        has_alembic = _has_table("alembic_version")
        has_patients = _has_table("patients")

    if not has_alembic and has_patients:
        # Existing DB with no migration history — stamp the baseline so
        # alembic doesn't try to re-create tables that already exist.
        print("[pre_deploy] Existing DB detected — stamping baseline (0001) …")
        result = subprocess.run(
            ["alembic", "stamp", "0001"],
            capture_output=False,
        )
        if result.returncode != 0:
            print("[pre_deploy] ERROR: alembic stamp failed.", file=sys.stderr)
            return result.returncode
        print("[pre_deploy] Stamp complete.")
    elif has_alembic:
        print("[pre_deploy] alembic_version table found — skipping stamp.")
    else:
        print("[pre_deploy] Fresh database — running full upgrade from scratch.")

    print("[pre_deploy] Running: alembic upgrade head …")
    result = subprocess.run(["alembic", "upgrade", "head"], capture_output=False)
    if result.returncode != 0:
        print("[pre_deploy] ERROR: alembic upgrade head failed.", file=sys.stderr)
        return result.returncode

    print("[pre_deploy] Migrations complete.")

    _ensure_columns()

    print("[pre_deploy] Schema guard complete. Deploy ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
