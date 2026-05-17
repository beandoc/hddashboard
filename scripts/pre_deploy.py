"""
pre_deploy.py — run by Render's preDeployCommand before each deploy.

Handles two cases:
  1. Fresh database (no tables yet): alembic upgrade head creates everything.
  2. Existing database (tables present, no alembic_version table):
     stamps as 0001 so alembic knows the baseline is already applied,
     then upgrades head to apply only the incremental migrations (0002+).
"""
import subprocess
import sys

from sqlalchemy import inspect, text

# DATABASE_URL must be set in the environment (Render injects it).
from database import engine


def _has_table(name: str) -> bool:
    return inspect(engine).has_table(name)


def main() -> int:
    with engine.connect() as conn:
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
