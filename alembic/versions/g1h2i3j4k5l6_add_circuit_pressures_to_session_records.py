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
    import sqlalchemy as sa
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        inspector = sa.inspect(bind)
        columns = [c['name'] for c in inspector.get_columns('session_records')]
        if 'arterial_line_pressure' not in columns:
            op.add_column('session_records', sa.Column('arterial_line_pressure', sa.Float(), nullable=True))
        if 'venous_line_pressure' not in columns:
            op.add_column('session_records', sa.Column('venous_line_pressure', sa.Float(), nullable=True))
        if 'transmembrane_pressure' not in columns:
            op.add_column('session_records', sa.Column('transmembrane_pressure', sa.Float(), nullable=True))
    else:
        op.execute(sa.text("ALTER TABLE session_records ADD COLUMN IF NOT EXISTS arterial_line_pressure FLOAT"))
        op.execute(sa.text("ALTER TABLE session_records ADD COLUMN IF NOT EXISTS venous_line_pressure FLOAT"))
        op.execute(sa.text("ALTER TABLE session_records ADD COLUMN IF NOT EXISTS transmembrane_pressure FLOAT"))


def downgrade() -> None:
    op.drop_column('session_records', 'transmembrane_pressure')
    op.drop_column('session_records', 'venous_line_pressure')
    op.drop_column('session_records', 'arterial_line_pressure')
