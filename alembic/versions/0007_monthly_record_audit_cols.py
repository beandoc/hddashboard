"""Add audit/ML columns missing from monthly_records in production.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-17

Columns added
─────────────
monthly_records:
  data_observed_at  TIMESTAMP NULL        — when labs were actually collected
  data_entered_at   TIMESTAMP NOT NULL DEFAULT now() — when row was persisted
  feature_vector_hash VARCHAR(64) NULL    — SHA-256 of ML feature vector at predict time
  dynamic_data      JSONB NULL DEFAULT '{}' + GIN index — user-defined variable store

interim_lab_records:
  data_observed_at  TIMESTAMP NULL
  data_entered_at   TIMESTAMP NOT NULL DEFAULT now()

These columns exist in the ORM model (database.py) but were never landed
in a migration, causing `column does not exist` errors on startup.
All additions are idempotent (if-not-exists guarded).
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(insp: Inspector, table: str, col: str) -> bool:
    if not insp.has_table(table):
        return False
    return any(c["name"] == col for c in insp.get_columns(table))


def _idx_exists(insp: Inspector, table: str, idx: str) -> bool:
    if not insp.has_table(table):
        return False
    return any(i["name"] == idx for i in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)
    is_pg = bind.dialect.name == "postgresql"

    # ── monthly_records ───────────────────────────────────────────────────────

    if not _col_exists(insp, "monthly_records", "data_observed_at"):
        op.add_column("monthly_records", sa.Column("data_observed_at", sa.DateTime, nullable=True))

    if not _col_exists(insp, "monthly_records", "data_entered_at"):
        op.add_column(
            "monthly_records",
            sa.Column(
                "data_entered_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.text("now()" if is_pg else "CURRENT_TIMESTAMP"),
            ),
        )

    if not _col_exists(insp, "monthly_records", "feature_vector_hash"):
        op.add_column(
            "monthly_records",
            sa.Column("feature_vector_hash", sa.String(64), nullable=True),
        )
        op.create_index(
            "ix_monthly_records_feature_vector_hash",
            "monthly_records",
            ["feature_vector_hash"],
        )

    if not _col_exists(insp, "monthly_records", "dynamic_data"):
        if is_pg:
            from sqlalchemy.dialects.postgresql import JSONB
            op.add_column(
                "monthly_records",
                sa.Column("dynamic_data", JSONB, nullable=True, server_default=sa.text("'{}'")),
            )
            if not _idx_exists(insp, "monthly_records", "ix_monthly_records_dynamic_data_gin"):
                bind.execute(
                    sa.text(
                        "CREATE INDEX ix_monthly_records_dynamic_data_gin "
                        "ON monthly_records USING GIN (dynamic_data)"
                    )
                )
        else:
            op.add_column("monthly_records", sa.Column("dynamic_data", sa.Text, nullable=True))

    # ── interim_lab_records ───────────────────────────────────────────────────

    if not _col_exists(insp, "interim_lab_records", "data_observed_at"):
        op.add_column("interim_lab_records", sa.Column("data_observed_at", sa.DateTime, nullable=True))

    if not _col_exists(insp, "interim_lab_records", "data_entered_at"):
        op.add_column(
            "interim_lab_records",
            sa.Column(
                "data_entered_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.text("now()" if is_pg else "CURRENT_TIMESTAMP"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    for col in ["data_observed_at", "data_entered_at"]:
        if _col_exists(insp, "interim_lab_records", col):
            op.drop_column("interim_lab_records", col)

    for col in ["dynamic_data", "feature_vector_hash", "data_entered_at", "data_observed_at"]:
        if col == "dynamic_data" and _idx_exists(insp, "monthly_records", "ix_monthly_records_dynamic_data_gin"):
            op.drop_index("ix_monthly_records_dynamic_data_gin", table_name="monthly_records")
        if col == "feature_vector_hash" and _idx_exists(insp, "monthly_records", "ix_monthly_records_feature_vector_hash"):
            op.drop_index("ix_monthly_records_feature_vector_hash", table_name="monthly_records")
        if _col_exists(insp, "monthly_records", col):
            op.drop_column("monthly_records", col)
