"""vascular_access_kdoqi_2019

Adds KDOQI 2019 aligned vascular access surveillance tables and session fields.

New tables:
  access_episodes          — multi-episode access history + ESKD Life-Plan fields
  access_events            — structured coded event log (steal grades, cannulation grades)
  access_surveillance_records — clinically-triggered imaging/Doppler records
  access_alert_overrides   — governance audit trail for alert actions

New columns on session_records:
  thrill_grade, bruit_grade, aneurysm_flag, steal_signs_flag (bedside exam)
  cannulation_attempts, cannulation_difficulty, needle_infiltration (AVF/AVG)

Revision ID: 0010
Revises: 28e0c191bf7a
Create Date: 2026-05-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "28e0c191bf7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── access_episodes ───────────────────────────────────────────────────────
    op.create_table(
        "access_episodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("access_class", sa.String(), nullable=False),
        sa.Column("access_subtype", sa.String(), nullable=True),
        sa.Column("creation_date", sa.Date(), nullable=False),
        sa.Column("first_cannulation_date", sa.Date(), nullable=True),
        sa.Column("insertion_site", sa.String(), nullable=True),
        sa.Column("catheter_type", sa.String(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("loss_date", sa.Date(), nullable=True),
        sa.Column("loss_reason", sa.String(), nullable=True),
        sa.Column("succession_plan", sa.Text(), nullable=True),
        sa.Column("life_plan_reviewed_at", sa.Date(), nullable=True),
        sa.Column("access_reviewed_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("entered_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_episodes_patient_id", "access_episodes", ["patient_id"])

    # ── access_events ─────────────────────────────────────────────────────────
    op.create_table(
        "access_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("access_class", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("steal_grade", sa.String(), nullable=True),
        sa.Column("cannulation_injury_grade", sa.String(), nullable=True),
        sa.Column("affected_segment", sa.String(), nullable=True),
        sa.Column("action_taken", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending_review"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("entered_by", sa.String(), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["episode_id"], ["access_episodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_events_patient_id", "access_events", ["patient_id"])
    op.create_index("ix_access_events_episode_id", "access_events", ["episode_id"])

    # ── access_surveillance_records ───────────────────────────────────────────
    op.create_table(
        "access_surveillance_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("surveillance_date", sa.Date(), nullable=False),
        sa.Column("clinical_trigger", sa.String(), nullable=False),
        sa.Column("modality", sa.String(), nullable=True),
        sa.Column("qa_by_imaging", sa.Float(), nullable=True),
        sa.Column("qa_baseline_at_test", sa.Float(), nullable=True),
        sa.Column("psv_at_stenosis", sa.Float(), nullable=True),
        sa.Column("stenosis_pct", sa.Float(), nullable=True),
        sa.Column("finding", sa.String(), nullable=True),
        sa.Column("recommendation", sa.String(), nullable=True),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("performed_by", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending_review"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("entered_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["episode_id"], ["access_episodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_surveillance_patient_id", "access_surveillance_records", ["patient_id"])
    op.create_index("ix_access_surveillance_episode_id", "access_surveillance_records", ["episode_id"])

    # ── access_alert_overrides ────────────────────────────────────────────────
    op.create_table(
        "access_alert_overrides",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("alert_type", sa.String(), nullable=False),
        sa.Column("alert_generated_at", sa.DateTime(), nullable=False),
        sa.Column("alert_reason", sa.Text(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("actioned_by", sa.String(), nullable=True),
        sa.Column("actioned_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_alert_overrides_patient_id", "access_alert_overrides", ["patient_id"])

    # ── session_records — bedside screen + cannulation fields ─────────────────
    op.add_column("session_records", sa.Column("thrill_grade", sa.String(), nullable=True, server_default="normal"))
    op.add_column("session_records", sa.Column("bruit_grade", sa.String(), nullable=True, server_default="normal"))
    op.add_column("session_records", sa.Column("aneurysm_flag", sa.Boolean(), nullable=True, server_default=sa.text("FALSE")))
    op.add_column("session_records", sa.Column("steal_signs_flag", sa.Boolean(), nullable=True, server_default=sa.text("FALSE")))
    op.add_column("session_records", sa.Column("cannulation_attempts", sa.Integer(), nullable=True))
    op.add_column("session_records", sa.Column("cannulation_difficulty", sa.String(), nullable=True, server_default="routine"))
    op.add_column("session_records", sa.Column("needle_infiltration", sa.Boolean(), nullable=True, server_default=sa.text("FALSE")))


def downgrade() -> None:
    # Remove session_records columns
    op.drop_column("session_records", "needle_infiltration")
    op.drop_column("session_records", "cannulation_difficulty")
    op.drop_column("session_records", "cannulation_attempts")
    op.drop_column("session_records", "steal_signs_flag")
    op.drop_column("session_records", "aneurysm_flag")
    op.drop_column("session_records", "bruit_grade")
    op.drop_column("session_records", "thrill_grade")

    # Drop tables in reverse FK order
    op.drop_index("ix_access_alert_overrides_patient_id", "access_alert_overrides")
    op.drop_table("access_alert_overrides")

    op.drop_index("ix_access_surveillance_episode_id", "access_surveillance_records")
    op.drop_index("ix_access_surveillance_patient_id", "access_surveillance_records")
    op.drop_table("access_surveillance_records")

    op.drop_index("ix_access_events_episode_id", "access_events")
    op.drop_index("ix_access_events_patient_id", "access_events")
    op.drop_table("access_events")

    op.drop_index("ix_access_episodes_patient_id", "access_episodes")
    op.drop_table("access_episodes")
