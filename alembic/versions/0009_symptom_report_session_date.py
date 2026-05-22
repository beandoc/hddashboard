"""Add session_date column to patient_symptom_reports.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-22

Adds a nullable Date column so patients can specify which dialysis session
they are reporting post-dialysis symptoms for, independently of the
auto-set reported_at timestamp.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = Inspector.from_engine(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("patient_symptom_reports")]
    if "session_date" not in cols:
        op.add_column(
            "patient_symptom_reports",
            sa.Column("session_date", sa.Date(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("patient_symptom_reports", "session_date")
