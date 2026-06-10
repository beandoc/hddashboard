"""twin_simulation_feedback

Revision ID: c3d4e5f60019
Revises: 0cec580d65c5
Create Date: 2026-06-10 00:00:00.000000

Add adoption audit columns and performance indexes to twin_simulations.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = 'c3d4e5f60019'
down_revision: Union[str, None] = '0cec580d65c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(insp: Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in insp.get_columns(table))


def _idx_exists(insp: Inspector, table: str, index_name: str) -> bool:
    return any(ix["name"] == index_name for ix in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    if not _col_exists(insp, "twin_simulations", "adopted_at"):
        op.add_column(
            "twin_simulations",
            sa.Column("adopted_at", sa.DateTime(), nullable=True),
        )
    if not _col_exists(insp, "twin_simulations", "adopted_by"):
        op.add_column(
            "twin_simulations",
            sa.Column("adopted_by", sa.String(100), nullable=True),
        )

    if not _idx_exists(insp, "twin_simulations", "ix_twin_patient_created"):
        op.create_index(
            "ix_twin_patient_created",
            "twin_simulations",
            ["patient_id", "created_at"],
        )
    if not _idx_exists(insp, "twin_simulations", "ix_twin_created_by"):
        op.create_index(
            "ix_twin_created_by",
            "twin_simulations",
            ["created_by"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    if _idx_exists(insp, "twin_simulations", "ix_twin_created_by"):
        op.drop_index("ix_twin_created_by", table_name="twin_simulations")
    if _idx_exists(insp, "twin_simulations", "ix_twin_patient_created"):
        op.drop_index("ix_twin_patient_created", table_name="twin_simulations")
    if _col_exists(insp, "twin_simulations", "adopted_by"):
        op.drop_column("twin_simulations", "adopted_by")
    if _col_exists(insp, "twin_simulations", "adopted_at"):
        op.drop_column("twin_simulations", "adopted_at")
