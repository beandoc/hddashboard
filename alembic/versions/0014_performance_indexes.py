"""performance_indexes – standalone record_month indexes for dashboard speed

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-25

WHY THIS MIGRATION EXISTS
──────────────────────────────────────────────────────────────────────────────
The dashboard (and entry list) execute several queries that filter the
monthly_records and session_records tables by record_month ALONE — i.e. no
patient_id predicate.  Examples:

    SELECT * FROM monthly_records  WHERE record_month = '2026-05'   -- dashboard
    SELECT * FROM session_records  WHERE record_month = '2026-05'   -- adherence
    SELECT MAX(timestamp) FROM monthly_records WHERE record_month = '2026-05'  -- cache key

The existing composite indexes (patient_id, record_month) cannot be used for
these queries because the leading column (patient_id) is absent. PostgreSQL
falls back to a sequential scan of the entire table on every dashboard
navigation and every save (cache-invalidation check).

Adding dedicated single-column indexes on record_month turns those scans into
fast index seeks, dramatically reducing dashboard and save latency.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # monthly_records.record_month  — used by compute_dashboard and cache-key checks
    op.create_index(
        "ix_monthly_record_month_only",
        "monthly_records",
        ["record_month"],
        if_not_exists=True,
    )

    # session_records.record_month  — used by dashboard adherence monitor
    op.create_index(
        "ix_session_record_month_only",
        "session_records",
        ["record_month"],
        if_not_exists=True,
    )

    # interim_lab_records.record_month  — used by dashboard interim labs fetch
    op.create_index(
        "ix_interim_record_month_only",
        "interim_lab_records",
        ["record_month"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_interim_record_month_only",  table_name="interim_lab_records")
    op.drop_index("ix_session_record_month_only",  table_name="session_records")
    op.drop_index("ix_monthly_record_month_only",  table_name="monthly_records")
