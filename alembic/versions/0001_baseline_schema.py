"""Baseline schema — full HD Dashboard table set.

Revision ID: 0001
Revises:
Create Date: 2026-05-17

IMPORTANT — existing production databases (Supabase):
  Do NOT run `alembic upgrade head`.
  Instead, run once to record that the DB is already at this state:
      alembic stamp 0001
  All future migrations will then apply incrementally on top of this baseline.

New / empty databases:
  Run normally:
      alembic upgrade head
  This will create all tables via SQLAlchemy's metadata.
"""

from typing import Sequence, Union
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Import Base here to avoid circular issues at module load time.
    from database import Base  # noqa: F401

    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = set(inspector.get_table_names())

    # create_all with checkfirst=True creates only tables that are missing.
    # On the existing Supabase production database (stamped at 0001), this
    # block is never reached — Alembic skips stamped revisions.
    # On a fresh database it creates the full schema.
    Base.metadata.create_all(bind=bind, checkfirst=True)

    # Log which tables were new vs already present for operator visibility.
    after_tables = set(Inspector.from_engine(bind).get_table_names())
    created = after_tables - existing_tables
    if created:
        for t in sorted(created):
            print(f"  [alembic 0001] created table: {t}")
    else:
        print("  [alembic 0001] all tables already present — no DDL executed")


def downgrade() -> None:
    # Dropping all tables in a downgrade is intentionally not implemented.
    # A baseline migration cannot be safely reversed in production.
    raise NotImplementedError(
        "Downgrade from baseline is not supported. "
        "Restore from a database backup if needed."
    )
