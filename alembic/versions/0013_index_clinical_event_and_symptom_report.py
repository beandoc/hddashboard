"""index_clinical_event_and_symptom_report

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add index to clinical_events.patient_id
    op.create_index(
        "ix_clinical_events_patient_id",
        "clinical_events",
        ["patient_id"],
        if_not_exists=True,
    )
    # Add index to patient_symptom_reports.patient_id
    op.create_index(
        "ix_patient_symptom_reports_patient_id",
        "patient_symptom_reports",
        ["patient_id"],
        if_not_exists=True,
    )
    # Add index to patient_symptom_reports.session_id
    op.create_index(
        "ix_patient_symptom_reports_session_id",
        "patient_symptom_reports",
        ["session_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_patient_symptom_reports_session_id", table_name="patient_symptom_reports")
    op.drop_index("ix_patient_symptom_reports_patient_id", table_name="patient_symptom_reports")
    op.drop_index("ix_clinical_events_patient_id", table_name="clinical_events")
