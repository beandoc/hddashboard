"""add reticulocyte_count to monthly_records

Revision ID: 8b92695a7472
Revises: eda57b8c4029
Create Date: 2026-06-06

Adds reticulocyte_count (%) to monthly_records for two-compartment ODE
partial observability of the reticulocyte pool state R.
"""
from alembic import op

revision = "8b92695a7472"
down_revision = "eda57b8c4029"
branch_labels = None
depends_on = None


def upgrade():
    # Use IF NOT EXISTS so this is safe to re-run if alembic_version ever
    # gets ahead of the actual schema (e.g. after a partially-applied deploy).
    op.execute(
        "ALTER TABLE monthly_records"
        " ADD COLUMN IF NOT EXISTS reticulocyte_count FLOAT"
    )


def downgrade():
    op.drop_column("monthly_records", "reticulocyte_count")
