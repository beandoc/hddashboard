"""Add patient_id indexes on hot lookup tables.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-17

Without these indexes every patient-profile page and the review queue
do full sequential scans on monthly_records, session_records,
clinical_events, and interim_lab_records when filtering by patient_id,
costing ~140ms per query × many queries per page.
"""

from typing import Sequence, Union
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    ("monthly_records",       "ix_monthly_records_patient_id",       ["patient_id"]),
    ("session_records",       "ix_session_records_patient_id",        ["patient_id"]),
    ("clinical_events",       "ix_clinical_events_patient_id",        ["patient_id"]),
    ("interim_lab_records",   "ix_interim_lab_records_patient_id",    ["patient_id"]),
    # Composite for the most common join pattern
    ("monthly_records",  "ix_monthly_records_patient_month", ["patient_id", "record_month"]),
    # Speeds up review queue event-type lookups
    ("clinical_events",  "ix_clinical_events_patient_type",  ["patient_id", "event_type"]),
]


def _idx_exists(insp: Inspector, table: str, idx: str) -> bool:
    return insp.has_table(table) and any(i["name"] == idx for i in insp.get_indexes(table))


def upgrade() -> None:
    insp = Inspector.from_engine(op.get_bind())
    for table, idx_name, cols in _INDEXES:
        if not _idx_exists(insp, table, idx_name):
            op.create_index(idx_name, table, cols)


def downgrade() -> None:
    insp = Inspector.from_engine(op.get_bind())
    for table, idx_name, _ in reversed(_INDEXES):
        if _idx_exists(insp, table, idx_name):
            op.drop_index(idx_name, table_name=table)
