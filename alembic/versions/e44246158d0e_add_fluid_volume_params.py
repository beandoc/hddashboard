"""add_fluid_volume_params

Revision ID: e44246158d0e
Revises: e44246158d0d
Create Date: 2026-06-02 01:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.reflection import Inspector

revision: str = 'e44246158d0e'
down_revision: Union[str, None] = 'e44246158d0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(insp: Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)
    if not _col_exists(insp, "twin_simulations", "fluid_volume_params"):
        op.add_column('twin_simulations', sa.Column('fluid_volume_params', JSONB(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)
    if _col_exists(insp, "twin_simulations", "fluid_volume_params"):
        op.drop_column('twin_simulations', 'fluid_volume_params')
