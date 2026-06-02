"""merge heads

Revision ID: eda57b8c4029
Revises: 6dd7f3136974, e44246158d0e
Create Date: 2026-06-02 06:55:51.245443

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'eda57b8c4029'
down_revision: Union[str, None] = ('6dd7f3136974', 'e44246158d0e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
