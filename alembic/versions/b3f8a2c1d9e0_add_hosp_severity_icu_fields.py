"""add hospitalization_icu_admission and hospitalization_severity to monthly_records

Revision ID: b3f8a2c1d9e0
Revises: a1b2c3d4e5f6
Create Date: 2026-06-08

Adds two new fields to monthly_records to capture admission severity per
hospitalisation episode:

  hospitalization_icu_admission (Boolean)
    True when the patient required an ICU/HDU level of care for this admission.

  hospitalization_severity (String)
    Clinician-selected severity tier:
      "Life Threatening" — ICU, ventilation, inotropes, septic shock, etc.
      "Critical"         — High-dependency / step-down care, significant organ
                           involvement, complex presentation.
      "Moderate"         — Ward admission, acute but not immediately life-threatening.
      "Routine"          — Planned procedure, elective admission, day-case
                           intervention (e.g. AV fistula, catheter exchange).

These fields are stored on the flat MonthlyRecord row (populated from the first
admission in hospitalization_details JSON) and are used by the ML deterioration
model to:
  1. Exclude "Routine" admissions from the positive training label (so planned
     access procedures do not pollute the hospitalization outcome signal).
  2. Weight the num_recent_hospitalizations feature by clinical severity rather
     than raw admission count.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3f8a2c1d9e0'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'monthly_records',
        sa.Column('hospitalization_icu_admission', sa.Boolean(), nullable=True),
    )
    op.add_column(
        'monthly_records',
        sa.Column('hospitalization_severity', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('monthly_records', 'hospitalization_severity')
    op.drop_column('monthly_records', 'hospitalization_icu_admission')
