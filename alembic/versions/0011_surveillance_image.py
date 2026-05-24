"""surveillance_image_path

Adds report_image_path column to access_surveillance_records so that
Doppler / fistulogram report images can be uploaded and linked to a record.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "access_surveillance_records",
        sa.Column("report_image_path", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("access_surveillance_records", "report_image_path")
