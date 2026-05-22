"""add_post_dialysis_creatinine

Revision ID: 28e0c191bf7a
Revises: 0009
Create Date: 2026-05-22 08:31:33.848937

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '28e0c191bf7a'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('monthly_records', sa.Column('post_dialysis_creatinine', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('monthly_records', 'post_dialysis_creatinine')
