"""add diasense_calibrations table

Revision ID: a2b3c4d5e6f7
Revises: f2a1b3c4d5e6
Create Date: 2026-06-10

Adds diasense_calibrations — one row per HD session where DiaSense optical
data was captured.  Stores the patient-specific plasma-refill coefficient
(diasense_k_r), RBV nadir, UF target vs actual, intradialytic BP trend,
post-HD symptoms, and post-HD BCM readings so the Digital Twin can use
measured physiology instead of the population-level weight-scaled estimate.
"""
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f2a1b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diasense_calibrations",
        sa.Column("id",                       sa.Integer,  primary_key=True),
        sa.Column("patient_id",               sa.Integer,  sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("session_date",             sa.Date,     nullable=False),
        sa.Column("diasense_session_id",      sa.String(64), nullable=True),

        # k_r calibration
        sa.Column("diasense_k_r",             sa.Float,    nullable=True),
        sa.Column("k_r_estimated",            sa.Float,    nullable=True),

        # RBV nadir
        sa.Column("rbv_nadir_pct",            sa.Float,    nullable=True),
        sa.Column("rbv_nadir_time_min",       sa.Float,    nullable=True),
        sa.Column("rbv_breach",               sa.Boolean,  nullable=True, server_default="false"),
        sa.Column("plasma_refill_rate_ml_min", sa.Float,   nullable=True),

        # UF target vs actual
        sa.Column("uf_target_ml",             sa.Float,    nullable=True),
        sa.Column("uf_actual_ml",             sa.Float,    nullable=True),
        sa.Column("uf_rate_ml_kg_h",          sa.Float,    nullable=True),
        sa.Column("uf_achievement_pct",       sa.Float,    nullable=True),

        # Session parameters
        sa.Column("session_duration_min",     sa.Float,    nullable=True),
        sa.Column("weight_pre_kg",            sa.Float,    nullable=True),
        sa.Column("dry_weight_kg",            sa.Float,    nullable=True),
        sa.Column("albumin_g_dl",             sa.Float,    nullable=True),

        # BP trend
        sa.Column("bp_trend_json",            sa.Text,     nullable=True),
        sa.Column("bp_nadir_sys",             sa.Float,    nullable=True),
        sa.Column("bp_nadir_map",             sa.Float,    nullable=True),
        sa.Column("bp_nadir_time_min",        sa.Float,    nullable=True),
        sa.Column("idh_observed",             sa.Boolean,  nullable=True, server_default="false"),

        # Post-HD symptoms
        sa.Column("post_hd_dyspnea_likert",   sa.Integer,  nullable=True),
        sa.Column("post_hd_fatigue_likert",   sa.Integer,  nullable=True),
        sa.Column("post_hd_cramps",           sa.Boolean,  nullable=True),
        sa.Column("post_hd_nausea",           sa.Boolean,  nullable=True),
        sa.Column("post_hd_headache",         sa.Boolean,  nullable=True),

        # Post-HD BCM
        sa.Column("bcm_post_fluid_overload_l",  sa.Float,  nullable=True),
        sa.Column("bcm_post_tbw_l",             sa.Float,  nullable=True),
        sa.Column("bcm_post_phase_angle",       sa.Float,  nullable=True),
        sa.Column("bcm_delta_overhydration_l",  sa.Float,  nullable=True),

        # Optical sensor summary
        sa.Column("he_od_mean",               sa.Float,    nullable=True),
        sa.Column("ha_od_mean",               sa.Float,    nullable=True),
        sa.Column("delta_od_mean",            sa.Float,    nullable=True),
        sa.Column("he_od_slope_per_hr",       sa.Float,    nullable=True),
        sa.Column("grade2plus_count",         sa.Integer,  nullable=True),
        sa.Column("rbv_curve_json",           sa.Text,     nullable=True),

        # Audit
        sa.Column("notes",                    sa.Text,     nullable=True),
        sa.Column("created_at",               sa.DateTime, nullable=False,
                  server_default=sa.func.now()),
        sa.Column("created_by",               sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_diasense_patient_date",
        "diasense_calibrations",
        ["patient_id", "session_date"],
    )
    op.create_index(
        "ix_diasense_patient_id",
        "diasense_calibrations",
        ["patient_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_diasense_patient_date", table_name="diasense_calibrations")
    op.drop_index("ix_diasense_patient_id",   table_name="diasense_calibrations")
    op.drop_table("diasense_calibrations")
