"""Add ACMRecommendation and TwinSimulation tables

Revision ID: 0018
Revises: e44246158d0d
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = 'e44246158d0d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'acm_recommendations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('recommendation_month', sa.String(7), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),

        sa.Column('current_hb',        sa.Float(), nullable=True),
        sa.Column('predicted_hb_1mo',  sa.Float(), nullable=True),
        sa.Column('predicted_hb_2mo',  sa.Float(), nullable=True),
        sa.Column('predicted_hb_3mo',  sa.Float(), nullable=True),
        sa.Column('hb_status',         sa.String(20), nullable=True),
        sa.Column('confidence',        sa.String(20), nullable=True),

        sa.Column('esa_action',           sa.String(20), nullable=True),
        sa.Column('esa_change_pct',       sa.Float(), nullable=True),
        sa.Column('recommended_iu_sc',    sa.Float(), nullable=True),
        sa.Column('esa_rationale',        sa.Text(), nullable=True),

        sa.Column('iron_action',    sa.String(20), nullable=True),
        sa.Column('iron_rationale', sa.Text(), nullable=True),

        sa.Column('safety_flags_json', sa.Text(), nullable=True),

        sa.Column('clinician_decision',   sa.String(20), nullable=True),
        sa.Column('clinician_notes',      sa.Text(), nullable=True),
        sa.Column('clinician_id',         sa.String(100), nullable=True),
        sa.Column('decided_at',           sa.DateTime(), nullable=True),
        sa.Column('modified_iu_sc',       sa.Float(), nullable=True),
        sa.Column('modified_iron_action', sa.String(20), nullable=True),

        sa.Column('observed_hb_1mo',       sa.Float(), nullable=True),
        sa.Column('observed_hb_3mo',       sa.Float(), nullable=True),
        sa.Column('hb_prediction_mae_1mo', sa.Float(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('patient_id', 'recommendation_month', name='uq_acm_patient_month'),
    )
    op.create_index('ix_acm_patient_id', 'acm_recommendations', ['patient_id'])
    op.create_index('ix_acm_rec_month',  'acm_recommendations', ['recommendation_month'])
    op.create_index('ix_acm_decision',   'acm_recommendations', ['clinician_decision'])

    op.create_table(
        'twin_simulations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(100), nullable=True),

        sa.Column('scenario_json',          sa.Text(), nullable=False),
        sa.Column('baseline_session_json',  sa.Text(), nullable=True),
        sa.Column('hb_sim_json',            sa.Text(), nullable=True),
        sa.Column('ktv_sim_json',           sa.Text(), nullable=True),
        sa.Column('idh_sim_json',           sa.Text(), nullable=True),
        sa.Column('uf_curve_json',          sa.Text(), nullable=True),

        sa.Column('adopted',            sa.Boolean(), nullable=True, default=False),
        sa.Column('clinician_notes',    sa.Text(), nullable=True),
        sa.Column('actual_outcomes_json', sa.Text(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_twin_patient_id', 'twin_simulations', ['patient_id'])
    op.create_index('ix_twin_created_at', 'twin_simulations', ['created_at'])


def downgrade() -> None:
    op.drop_table('twin_simulations')
    op.drop_table('acm_recommendations')
