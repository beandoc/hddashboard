"""Replace EAV variable_values with JSONB on monthly_records.

Revision ID: 0004
Revises: 27fe08a6d4f9
Create Date: 2026-05-17

What this migration does
────────────────────────
1. monthly_records
     + dynamic_data  JSONB  NULL DEFAULT '{}'
     + GIN index on dynamic_data  (enables @>, ?, ?& operators for cohort queries)

2. Migrate existing variable_values rows into monthly_records.dynamic_data
     Shape: {"<variable_name>": {"v": <float>, "t": "<text>", "by": "<entered_by>"}}
     Key is variable_definition.name so the payload is self-describing.

3. Drop variable_values table.

4. Keep variable_definitions table unchanged — it stays as the schema registry.

Performance rationale
─────────────────────
The EAV layout required N table rows + N joins per cohort query.
JSONB with GIN allows single-row scans with jsonpath predicates:
  WHERE dynamic_data @> '{"crp": {}}'   -- patients with CRP recorded
  WHERE (dynamic_data->>'crp')::float > 10  -- cohort filter

Downgrade path
──────────────
Recreates variable_values from the JSONB data (best-effort; text values
mapped through variable_definitions by name→id lookup).
"""

from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0004"
down_revision: Union[str, None] = "27fe08a6d4f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(insp: Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in insp.get_columns(table))


def _table_exists(insp: Inspector, table: str) -> bool:
    return table in insp.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    # ── 1. Add dynamic_data JSONB column to monthly_records ───────────────────
    if _table_exists(insp, "monthly_records") and not _col_exists(insp, "monthly_records", "dynamic_data"):
        op.add_column(
            "monthly_records",
            sa.Column(
                "dynamic_data",
                JSONB(),
                nullable=True,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
        op.create_index(
            "ix_monthly_records_dynamic_data_gin",
            "monthly_records",
            ["dynamic_data"],
            postgresql_using="gin",
        )

    # ── 2. Migrate variable_values → dynamic_data ─────────────────────────────
    # Only runs when variable_values table still exists (idempotent on re-run).
    if _table_exists(insp, "variable_values") and _table_exists(insp, "variable_definitions"):
        # Build name lookup: variable_id → variable_name
        rows = bind.execute(
            sa.text("SELECT id, name FROM variable_definitions")
        ).fetchall()
        id_to_name = {r[0]: r[1] for r in rows}

        if id_to_name:
            # Fetch all variable_values
            vv_rows = bind.execute(
                sa.text(
                    "SELECT patient_id, record_month, variable_id, value_num, value_text, entered_by "
                    "FROM variable_values ORDER BY patient_id, record_month"
                )
            ).fetchall()

            # Group by (patient_id, record_month) and build patch dicts
            patches: dict = {}
            for patient_id, record_month, variable_id, value_num, value_text, entered_by in vv_rows:
                var_name = id_to_name.get(variable_id)
                if not var_name:
                    continue
                key = (patient_id, record_month)
                if key not in patches:
                    patches[key] = {}
                entry: dict = {}
                if value_num is not None:
                    entry["v"] = value_num
                if value_text is not None:
                    entry["t"] = value_text
                if entered_by:
                    entry["by"] = entered_by
                patches[key][var_name] = entry

            # Upsert into monthly_records — insert row if missing, then patch
            import json
            for (patient_id, record_month), patch in patches.items():
                existing = bind.execute(
                    sa.text(
                        "SELECT id FROM monthly_records WHERE patient_id = :pid AND record_month = :m"
                    ),
                    {"pid": patient_id, "m": record_month},
                ).fetchone()

                if existing:
                    bind.execute(
                        sa.text(
                            "UPDATE monthly_records "
                            "SET dynamic_data = COALESCE(dynamic_data, '{}'::jsonb) || :patch::jsonb "
                            "WHERE patient_id = :pid AND record_month = :m"
                        ),
                        {"patch": json.dumps(patch), "pid": patient_id, "m": record_month},
                    )
                else:
                    bind.execute(
                        sa.text(
                            "INSERT INTO monthly_records (patient_id, record_month, dynamic_data) "
                            "VALUES (:pid, :m, :patch::jsonb)"
                        ),
                        {"pid": patient_id, "m": record_month, "patch": json.dumps(patch)},
                    )

        # ── 3. Drop variable_values ───────────────────────────────────────────
        op.drop_table("variable_values")


def downgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    # Recreate variable_values table
    if not _table_exists(insp, "variable_values"):
        op.create_table(
            "variable_values",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
            sa.Column("record_month", sa.String(), nullable=False),
            sa.Column("variable_id", sa.Integer(), sa.ForeignKey("variable_definitions.id"), nullable=False),
            sa.Column("value_num", sa.Float(), nullable=True),
            sa.Column("value_text", sa.String(), nullable=True),
            sa.Column("entered_by", sa.String(), nullable=True),
            sa.Column("entered_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("patient_id", "record_month", "variable_id", name="uq_patient_month_variable"),
        )

    # Re-populate from dynamic_data (best-effort)
    if _table_exists(insp, "monthly_records") and _col_exists(insp, "monthly_records", "dynamic_data"):
        rows = bind.execute(
            sa.text("SELECT id, name FROM variable_definitions")
        ).fetchall()
        name_to_id = {r[1]: r[0] for r in rows}

        mr_rows = bind.execute(
            sa.text(
                "SELECT patient_id, record_month, dynamic_data FROM monthly_records "
                "WHERE dynamic_data IS NOT NULL AND dynamic_data != '{}'::jsonb"
            )
        ).fetchall()

        import json
        from datetime import datetime
        for patient_id, record_month, dynamic_data in mr_rows:
            if isinstance(dynamic_data, str):
                dynamic_data = json.loads(dynamic_data)
            if not dynamic_data:
                continue
            for var_name, entry in dynamic_data.items():
                var_id = name_to_id.get(var_name)
                if not var_id:
                    continue
                bind.execute(
                    sa.text(
                        "INSERT INTO variable_values "
                        "(patient_id, record_month, variable_id, value_num, value_text, entered_by, entered_at) "
                        "VALUES (:pid, :m, :vid, :vn, :vt, :by, :at) "
                        "ON CONFLICT (patient_id, record_month, variable_id) DO NOTHING"
                    ),
                    {
                        "pid": patient_id,
                        "m": record_month,
                        "vid": var_id,
                        "vn": entry.get("v"),
                        "vt": entry.get("t"),
                        "by": entry.get("by", "migration_downgrade"),
                        "at": datetime.utcnow(),
                    },
                )

    # Drop JSONB column
    if _table_exists(insp, "monthly_records") and _col_exists(insp, "monthly_records", "dynamic_data"):
        op.drop_index("ix_monthly_records_dynamic_data_gin", table_name="monthly_records")
        op.drop_column("monthly_records", "dynamic_data")
