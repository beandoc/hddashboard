"""add arterial_line_pressure, venous_line_pressure, transmembrane_pressure to session_records

Revision ID: g1h2i3j4k5l6
Revises: c1d2e3f4a5b6
Create Date: 2026-06-27

"""
from alembic import op

revision = 'g1h2i3j4k5l6'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import text
    op.execute(text("ALTER TABLE session_records ADD COLUMN IF NOT EXISTS arterial_line_pressure FLOAT"))
    op.execute(text("ALTER TABLE session_records ADD COLUMN IF NOT EXISTS venous_line_pressure FLOAT"))
    op.execute(text("ALTER TABLE session_records ADD COLUMN IF NOT EXISTS transmembrane_pressure FLOAT"))


def downgrade() -> None:
    op.drop_column('session_records', 'transmembrane_pressure')
    op.drop_column('session_records', 'venous_line_pressure')
    op.drop_column('session_records', 'arterial_line_pressure')
