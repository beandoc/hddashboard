"""add hemostasis_time_mins to session_records

Revision ID: f2a1b3c4d5e6
Revises: eda57b8c4029
Create Date: 2026-06-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a1b3c4d5e6'
down_revision: Union[str, None] = 'c7d4e9f2a1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'session_records',
        sa.Column('hemostasis_time_mins', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('session_records', 'hemostasis_time_mins')
