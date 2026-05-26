"""IDH prediction model — add AF status and session-level IDH fields.

Revision ID: 0015
Revises: 28e0c191bf7a
Create Date: 2026-05-26

Adds:
  patient_comorbidities.af_status            (BOOLEAN, nullable)
  session_records.saline_bolus_count         (INTEGER, nullable)
  session_records.antihypertensive_taken_prehd (BOOLEAN, nullable)
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(inspector: Inspector, table: str, col: str) -> bool:
    return col in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # ── patient_comorbidities ─────────────────────────────────────────────────
    if not _col_exists(inspector, "patient_comorbidities", "af_status"):
        op.add_column(
            "patient_comorbidities",
            sa.Column("af_status", sa.Boolean(), nullable=True),
        )
        print("  [alembic 0015] added patient_comorbidities.af_status")
    else:
        print("  [alembic 0015] patient_comorbidities.af_status already exists — skipped")

    # ── session_records ───────────────────────────────────────────────────────
    if not _col_exists(inspector, "session_records", "saline_bolus_count"):
        op.add_column(
            "session_records",
            sa.Column("saline_bolus_count", sa.Integer(), nullable=True),
        )
        print("  [alembic 0015] added session_records.saline_bolus_count")
    else:
        print("  [alembic 0015] session_records.saline_bolus_count already exists — skipped")

    if not _col_exists(inspector, "session_records", "antihypertensive_taken_prehd"):
        op.add_column(
            "session_records",
            sa.Column("antihypertensive_taken_prehd", sa.Boolean(), nullable=True),
        )
        print("  [alembic 0015] added session_records.antihypertensive_taken_prehd")
    else:
        print("  [alembic 0015] session_records.antihypertensive_taken_prehd already exists — skipped")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if _col_exists(inspector, "session_records", "antihypertensive_taken_prehd"):
        op.drop_column("session_records", "antihypertensive_taken_prehd")

    if _col_exists(inspector, "session_records", "saline_bolus_count"):
        op.drop_column("session_records", "saline_bolus_count")

    if _col_exists(inspector, "patient_comorbidities", "af_status"):
        op.drop_column("patient_comorbidities", "af_status")
