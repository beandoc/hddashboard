"""add desidustat_modified_at and phosphate_binder_modified_at to monthly_records

Revision ID: c1d2e3f4a5b6
Revises: d486bde0fe85
Create Date: 2026-06-11

"""
from alembic import op
import sqlalchemy as sa

revision = 'c1d2e3f4a5b6'
down_revision = 'd486bde0fe85'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('monthly_records', sa.Column('desidustat_modified_at', sa.Date(), nullable=True))
    op.add_column('monthly_records', sa.Column('phosphate_binder_modified_at', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('monthly_records', 'phosphate_binder_modified_at')
    op.drop_column('monthly_records', 'desidustat_modified_at')
