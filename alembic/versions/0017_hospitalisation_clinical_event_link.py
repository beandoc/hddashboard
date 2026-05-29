"""Link hospitalisation_events to clinical_events via optional FK.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-29

WHY THIS MIGRATION EXISTS
──────────────────────────────────────────────────────────────────────────────
Short HD-related admissions (vascular procedures, access surgery, AV fistula
creation, catheter insertion, HD complication observation stays) are routinely
logged both as a ClinicalEvent and as a HospitalisationEvent, forcing staff to
enter the same information twice.

Adding an optional clinical_event_id FK on hospitalisation_events lets a
doctor/staff member link an admission to its corresponding clinical event,
surfacing the connection in both views without merging the two record types
(they serve different structural purposes: events carry severity/type/session
context; admissions carry ICD codes, LOS, discharge diagnoses).

The column is nullable — existing records are unaffected.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0017'
down_revision: Union[str, None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'hospitalisation_events',
        sa.Column('clinical_event_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_hosp_clinical_event',
        'hospitalisation_events', 'clinical_events',
        ['clinical_event_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_hospitalisation_events_clinical_event_id',
        'hospitalisation_events',
        ['clinical_event_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_hospitalisation_events_clinical_event_id', table_name='hospitalisation_events')
    op.drop_constraint('fk_hosp_clinical_event', 'hospitalisation_events', type_='foreignkey')
    op.drop_column('hospitalisation_events', 'clinical_event_id')
