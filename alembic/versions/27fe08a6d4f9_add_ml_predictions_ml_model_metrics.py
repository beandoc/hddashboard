"""add ml_predictions ml_model_metrics

Revision ID: 27fe08a6d4f9
Revises: 0003
Create Date: 2026-05-17 12:49:12.860145

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27fe08a6d4f9'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'ml_model_metrics' not in tables:
        op.create_table('ml_model_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(), nullable=False),
        sa.Column('week_start', sa.String(length=10), nullable=False),
        sa.Column('n_predictions', sa.Integer(), nullable=False),
        sa.Column('n_with_outcome', sa.Integer(), nullable=False),
        sa.Column('pr_auc', sa.Float(), nullable=True),
        sa.Column('brier_score', sa.Float(), nullable=True),
        sa.Column('calibration_slope', sa.Float(), nullable=True),
        sa.Column('calibration_intercept', sa.Float(), nullable=True),
        sa.Column('roc_auc', sa.Float(), nullable=True),
        sa.Column('drift_flagged', sa.Boolean(), nullable=True),
        sa.Column('drift_detail', sa.Text(), nullable=True),
        sa.Column('computed_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_ml_model_metrics_id'), 'ml_model_metrics', ['id'], unique=False)
        op.create_index(op.f('ix_ml_model_metrics_model_name'), 'ml_model_metrics', ['model_name'], unique=False)

    if 'ml_predictions' not in tables:
        op.create_table('ml_predictions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(), nullable=False),
        sa.Column('model_version', sa.String(), nullable=True),
        sa.Column('input_feature_hash', sa.String(length=64), nullable=False),
        sa.Column('features_json', sa.Text(), nullable=False),
        sa.Column('prediction_score', sa.Float(), nullable=False),
        sa.Column('predicted_class', sa.Integer(), nullable=True),
        sa.Column('observed_outcome', sa.Integer(), nullable=True),
        sa.Column('prediction_month', sa.String(length=7), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_ml_predictions_created_at'), 'ml_predictions', ['created_at'], unique=False)
        op.create_index(op.f('ix_ml_predictions_id'), 'ml_predictions', ['id'], unique=False)
        op.create_index(op.f('ix_ml_predictions_input_feature_hash'), 'ml_predictions', ['input_feature_hash'], unique=False)
        op.create_index(op.f('ix_ml_predictions_model_name'), 'ml_predictions', ['model_name'], unique=False)
        op.create_index(op.f('ix_ml_predictions_patient_id'), 'ml_predictions', ['patient_id'], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'ml_predictions' in tables:
        op.drop_index(op.f('ix_ml_predictions_patient_id'), table_name='ml_predictions')
        op.drop_index(op.f('ix_ml_predictions_model_name'), table_name='ml_predictions')
        op.drop_index(op.f('ix_ml_predictions_input_feature_hash'), table_name='ml_predictions')
        op.drop_index(op.f('ix_ml_predictions_id'), table_name='ml_predictions')
        op.drop_index(op.f('ix_ml_predictions_created_at'), table_name='ml_predictions')
        op.drop_table('ml_predictions')

    if 'ml_model_metrics' in tables:
        op.drop_index(op.f('ix_ml_model_metrics_model_name'), table_name='ml_model_metrics')
        op.drop_index(op.f('ix_ml_model_metrics_id'), table_name='ml_model_metrics')
        op.drop_table('ml_model_metrics')
