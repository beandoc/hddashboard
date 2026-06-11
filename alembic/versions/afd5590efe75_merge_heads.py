"""merge heads

Revision ID: afd5590efe75
Revises: 0020, a2b3c4d5e6f7
Create Date: 2026-06-11 06:59:19.329501

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'afd5590efe75'
down_revision: Union[str, None] = ('0020', 'a2b3c4d5e6f7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
