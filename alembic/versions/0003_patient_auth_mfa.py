"""Add reset-token columns to patient_credentials and MFA columns to users.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-17

What this migration does
────────────────────────
1. patient_credentials
     + reset_token   VARCHAR  (nullable, indexed)
     + token_expires TIMESTAMP (nullable)

2. users
     + mfa_secret    VARCHAR  (nullable)
     + mfa_enabled   BOOLEAN  NOT NULL DEFAULT FALSE

Safe to run on existing production DB — all new columns are nullable or have
a server-side default, so no row-level back-fill is required.
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(inspector: Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspector.get_columns(table))


def _idx_exists(inspector: Inspector, table: str, index: str) -> bool:
    return any(i["name"] == index for i in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    # ── patient_credentials ───────────────────────────────────────────────────
    if "patient_credentials" in insp.get_table_names():
        if not _col_exists(insp, "patient_credentials", "reset_token"):
            op.add_column(
                "patient_credentials",
                sa.Column("reset_token", sa.String(), nullable=True),
            )
            if not _idx_exists(insp, "patient_credentials", "ix_patient_credentials_reset_token"):
                op.create_index(
                    "ix_patient_credentials_reset_token",
                    "patient_credentials",
                    ["reset_token"],
                    unique=False,
                )
        if not _col_exists(insp, "patient_credentials", "token_expires"):
            op.add_column(
                "patient_credentials",
                sa.Column("token_expires", sa.DateTime(), nullable=True),
            )

    # ── users ─────────────────────────────────────────────────────────────────
    if "users" in insp.get_table_names():
        if not _col_exists(insp, "users", "mfa_secret"):
            op.add_column(
                "users",
                sa.Column("mfa_secret", sa.String(), nullable=True),
            )
        if not _col_exists(insp, "users", "mfa_enabled"):
            op.add_column(
                "users",
                sa.Column(
                    "mfa_enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    if "users" in insp.get_table_names():
        if _col_exists(insp, "users", "mfa_enabled"):
            op.drop_column("users", "mfa_enabled")
        if _col_exists(insp, "users", "mfa_secret"):
            op.drop_column("users", "mfa_secret")

    if "patient_credentials" in insp.get_table_names():
        if _idx_exists(insp, "patient_credentials", "ix_patient_credentials_reset_token"):
            op.drop_index("ix_patient_credentials_reset_token", table_name="patient_credentials")
        if _col_exists(insp, "patient_credentials", "reset_token"):
            op.drop_column("patient_credentials", "reset_token")
        if _col_exists(insp, "patient_credentials", "token_expires"):
            op.drop_column("patient_credentials", "token_expires")
