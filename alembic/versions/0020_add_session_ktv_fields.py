"""add_session_ktv_fields

Revision ID: 0020
Revises: c3d4e5f60019
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision: str = '0020'
down_revision: Union[str, None] = 'c3d4e5f60019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(insp: Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    if not _col_exists(insp, "session_records", "sp_ktv"):
        op.add_column("session_records", sa.Column("sp_ktv", sa.Float(), nullable=True))
    if not _col_exists(insp, "session_records", "e_ktv"):
        op.add_column("session_records", sa.Column("e_ktv", sa.Float(), nullable=True))
    if not _col_exists(insp, "session_records", "urr"):
        op.add_column("session_records", sa.Column("urr", sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    if _col_exists(insp, "session_records", "urr"):
        op.drop_column("session_records", "urr")
    if _col_exists(insp, "session_records", "e_ktv"):
        op.drop_column("session_records", "e_ktv")
    if _col_exists(insp, "session_records", "sp_ktv"):
        op.drop_column("session_records", "sp_ktv")
