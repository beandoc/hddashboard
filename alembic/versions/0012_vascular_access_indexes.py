"""vascular_access_indexes

Performance indexes on vascular access tables to eliminate sequential
scans during unit dashboard load (N×M query pattern).

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-24
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # AccessEpisode — most queries filter by patient_id + is_current
    op.create_index(
        "ix_access_episodes_patient_current",
        "access_episodes",
        ["patient_id", "is_current"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_access_episodes_patient_id",
        "access_episodes",
        ["patient_id"],
        if_not_exists=True,
    )

    # AccessEvent — unit dashboard filters patient_id + status + event_date
    op.create_index(
        "ix_access_events_patient_status",
        "access_events",
        ["patient_id", "status"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_access_events_episode_id",
        "access_events",
        ["episode_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_access_events_event_date",
        "access_events",
        ["event_date"],
        if_not_exists=True,
    )

    # AccessSurveillanceRecord — per-patient surveillance history
    op.create_index(
        "ix_access_surveillance_patient_date",
        "access_surveillance_records",
        ["patient_id", "surveillance_date"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_access_surveillance_episode_id",
        "access_surveillance_records",
        ["episode_id"],
        if_not_exists=True,
    )

    # SessionRecord access columns — Qa/recirculation/cannulation batch fetches
    op.create_index(
        "ix_session_records_patient_date",
        "session_records",
        ["patient_id", "session_date"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_session_records_patient_date", table_name="session_records")
    op.drop_index("ix_access_surveillance_episode_id", table_name="access_surveillance_records")
    op.drop_index("ix_access_surveillance_patient_date", table_name="access_surveillance_records")
    op.drop_index("ix_access_events_event_date", table_name="access_events")
    op.drop_index("ix_access_events_episode_id", table_name="access_events")
    op.drop_index("ix_access_events_patient_status", table_name="access_events")
    op.drop_index("ix_access_episodes_patient_id", table_name="access_episodes")
    op.drop_index("ix_access_episodes_patient_current", table_name="access_episodes")
