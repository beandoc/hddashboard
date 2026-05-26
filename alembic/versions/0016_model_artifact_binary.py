"""ModelArtifact — add model_binary column for persistent model storage.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-26

Adds:
  model_artifacts.model_binary  (BYTEA / LargeBinary, nullable)

Motivation: on PaaS deployments (Render, Railway) the container filesystem is
ephemeral — every redeploy wipes local .joblib files.  Storing the serialised
model in the database ensures the trained model survives redeployments without
requiring a separate object-storage bucket.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = Inspector.from_engine(op.get_bind())
    existing = [c["name"] for c in inspector.get_columns("model_artifacts")]
    if "model_binary" not in existing:
        op.add_column(
            "model_artifacts",
            sa.Column("model_binary", sa.LargeBinary, nullable=True),
        )


def downgrade() -> None:
    op.drop_column("model_artifacts", "model_binary")
