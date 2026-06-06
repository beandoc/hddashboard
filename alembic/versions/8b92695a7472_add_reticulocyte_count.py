"""add reticulocyte_count to monthly_records

Revision ID: 8b92695a7472
Revises: eda57b8c4029
Create Date: 2026-06-06

Adds reticulocyte_count (%) to monthly_records for two-compartment ODE
partial observability of the reticulocyte pool state R.
"""
from alembic import op
import sqlalchemy as sa

revision = "8b92695a7472"
down_revision = "eda57b8c4029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monthly_records",
        sa.Column("reticulocyte_count", sa.Float(), nullable=True),
    )


def downgrade():
    op.drop_column("monthly_records", "reticulocyte_count")
