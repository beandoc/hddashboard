"""merge reticulocyte and hemostasis heads

Revision ID: a1b2c3d4e5f6
Revises: 8b92695a7472, f2a1b3c4d5e6
Create Date: 2026-06-07 00:00:00.000000

Merge the reticulocyte_count branch (8b92695a7472) with the
hemostasis_time_mins branch (f2a1b3c4d5e6) into a single head.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = ('8b92695a7472', 'f2a1b3c4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
