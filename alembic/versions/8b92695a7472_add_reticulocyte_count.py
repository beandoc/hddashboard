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


import sqlalchemy as sa

def upgrade():
    # Use IF NOT EXISTS for PostgreSQL, and check before adding for SQLite.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        from sqlalchemy import inspect
        inspector = inspect(bind)
        columns = [col['name'] for col in inspector.get_columns('monthly_records')]
        if 'reticulocyte_count' not in columns:
            op.add_column('monthly_records', sa.Column('reticulocyte_count', sa.Float(), nullable=True))
    else:
        op.execute(
            "ALTER TABLE monthly_records"
            " ADD COLUMN IF NOT EXISTS reticulocyte_count FLOAT"
        )


def downgrade():
    op.drop_column("monthly_records", "reticulocyte_count")
