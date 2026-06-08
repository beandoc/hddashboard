"""add_severity_to_hospitalisation_events

Revision ID: 0cec580d65c5
Revises: b3f8a2c1d9e0
Create Date: 2026-06-08 13:22:14.110907

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0cec580d65c5'
down_revision: Union[str, None] = 'b3f8a2c1d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'hospitalisation_events',
        sa.Column('severity', sa.String(), nullable=True),
    )
    op.add_column(
        'hospitalisation_events',
        sa.Column('icu_admission', sa.Boolean(), nullable=True),
    )
    op.add_column(
        'hospitalisation_events',
        sa.Column('pct', sa.Float(), nullable=True),
    )
    op.add_column(
        'hospitalisation_events',
        sa.Column('shock_on_admission', sa.Integer(), nullable=True),
    )
    op.add_column(
        'hospitalisation_events',
        sa.Column('inotrope_days', sa.Float(), nullable=True),
    )
    op.add_column(
        'hospitalisation_events',
        sa.Column('ventilation_days', sa.Float(), nullable=True),
    )
    op.add_column(
        'hospitalisation_events',
        sa.Column('transfusion_units', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('hospitalisation_events', 'transfusion_units')
    op.drop_column('hospitalisation_events', 'ventilation_days')
    op.drop_column('hospitalisation_events', 'inotrope_days')
    op.drop_column('hospitalisation_events', 'shock_on_admission')
    op.drop_column('hospitalisation_events', 'pct')
    op.drop_column('hospitalisation_events', 'icu_admission')
    op.drop_column('hospitalisation_events', 'severity')

