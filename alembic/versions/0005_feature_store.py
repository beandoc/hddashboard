"""Add patient_feature_snapshot table (feature store).

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-17

What this migration does
────────────────────────
Creates patient_feature_snapshot — a materialized feature store that
decouples feature engineering from inference and training.

Design
──────
• One row per (patient_id, as_of_month).
• feature_vector JSONB stores every engineered feature the model sees:
    {"hb": 9.2, "albumin": 3.4, "hb_trend_3m": -0.8, "cci": 5, ...}
• model_version VARCHAR links the snapshot to the model artifact that
  consumed it (matches manifest.json "version" field).
• feature_hash SHA-256 of feature_vector — lets audit queries find
  "what did model v2.1 see for patient 42 on 2025-11?" without
  re-running feature engineering.
• stale BOOLEAN — set TRUE by a Celery beat task when upstream
  MonthlyRecord changes; cleared after Celery recomputes.

Indexes
───────
• (patient_id, as_of_month) UNIQUE — one canonical snapshot per period.
• GIN on feature_vector — supports @> queries for cohort-level
  "which patients had hb < 9 when model ran?" audits.
• (model_version, stale) — Celery recompute query hits this index.
"""

from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(insp: Inspector, table: str) -> bool:
    return table in insp.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    if not _table_exists(insp, "patient_feature_snapshot"):
        op.create_table(
            "patient_feature_snapshot",
            sa.Column("id",            sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("patient_id",    sa.Integer(), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
            sa.Column("as_of_month",   sa.String(7), nullable=False),          # YYYY-MM
            sa.Column("feature_vector", JSONB(),     nullable=False),
            sa.Column("feature_hash",  sa.String(64), nullable=True),           # SHA-256 hex
            sa.Column("model_version", sa.String(32), nullable=True),
            sa.Column("stale",         sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("computed_at",   sa.DateTime(), nullable=True),
            sa.UniqueConstraint("patient_id", "as_of_month", name="uq_feature_snapshot_patient_month"),
        )
        op.create_index(
            "ix_feature_snapshot_patient_month",
            "patient_feature_snapshot",
            ["patient_id", "as_of_month"],
        )
        op.create_index(
            "ix_feature_snapshot_feature_vector_gin",
            "patient_feature_snapshot",
            ["feature_vector"],
            postgresql_using="gin",
        )
        op.create_index(
            "ix_feature_snapshot_model_stale",
            "patient_feature_snapshot",
            ["model_version", "stale"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    if _table_exists(insp, "patient_feature_snapshot"):
        op.drop_index("ix_feature_snapshot_model_stale", table_name="patient_feature_snapshot")
        op.drop_index("ix_feature_snapshot_feature_vector_gin", table_name="patient_feature_snapshot")
        op.drop_index("ix_feature_snapshot_patient_month", table_name="patient_feature_snapshot")
        op.drop_table("patient_feature_snapshot")
