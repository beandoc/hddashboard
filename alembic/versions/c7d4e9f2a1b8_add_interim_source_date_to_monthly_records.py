"""add interim_source_date to monthly_records

Revision ID: c7d4e9f2a1b8
Revises: eda57b8c4029
Create Date: 2026-06-07

When an interim lab is saved, the system auto-merges the value into the
monthly_records row for the same calendar month.  interim_source_date
records the actual lab collection date for those merged fields, so
audit logs can distinguish a comprehensive monthly review entry from a
spot-check interim update.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d4e9f2a1b8'
down_revision: Union[str, None] = 'eda57b8c4029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'monthly_records',
        sa.Column('interim_source_date', sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('monthly_records', 'interim_source_date')
