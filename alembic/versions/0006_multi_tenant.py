"""Add multi-tenancy: tenant_id + PostgreSQL Row-Level Security.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-17

What this migration does
────────────────────────
1. Add tenant_id VARCHAR(64) NOT NULL DEFAULT 'default' to every
   clinical table:  patients, monthly_records, interim_lab_records,
   session_records, clinical_events, audit_log, variable_definitions,
   patient_feature_snapshot, users.

2. Backfill existing rows with tenant_id = 'default' (the current
   single-tenant implicit tenant).

3. Create a PostgreSQL Row-Level Security policy on each table:
     POLICY tenant_isolation
       USING (tenant_id = current_setting('app.tenant_id', true))
   The setting is injected by the connection middleware on every request.

4. Create an index on tenant_id for every table — needed because RLS
   filters are not automatically indexed.

5. Enable RLS on each table (ALTER TABLE ... ENABLE ROW LEVEL SECURITY).
   The superuser / migration role bypasses RLS (FORCE ROW LEVEL SECURITY
   is deliberately NOT set so migrations and admin scripts still work).

Application-layer contract
──────────────────────────
• Before executing any query the async middleware must run:
    SET LOCAL app.tenant_id = '<tenant_id>'
  This is scoped to the current transaction.
• The 'default' tenant ID continues to work for the existing clinic
  installation with no code changes on day 1.
• New tenants are onboarded by inserting a row into a future
  tenants registry table (not in scope for this migration).
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that carry PHI and must be tenant-isolated.
# patient_credentials / satellite tables are covered transitively via
# CASCADE from patients, so only top-level clinical tables need RLS.
_TENANT_TABLES = [
    "patients",
    "monthly_records",
    "interim_lab_records",
    "session_records",
    "clinical_events",
    "audit_log",
    "variable_definitions",
    "patient_feature_snapshot",
    "users",
]


def _col_exists(insp: Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in insp.get_columns(table))


def _table_exists(insp: Inspector, table: str) -> bool:
    return table in insp.get_table_names()


def _idx_exists(insp: Inspector, table: str, index: str) -> bool:
    return any(i["name"] == index for i in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)

    # Detect whether we are on PostgreSQL — SQLite dev env skips RLS steps.
    is_pg = bind.dialect.name == "postgresql"

    for table in _TENANT_TABLES:
        if not _table_exists(insp, table):
            continue

        # ── 1. Add tenant_id column ───────────────────────────────────────────
        if not _col_exists(insp, table, "tenant_id"):
            op.add_column(
                table,
                sa.Column(
                    "tenant_id",
                    sa.String(64),
                    nullable=False,
                    server_default=sa.text("'default'"),
                ),
            )

        # ── 2. Backfill (server_default handles new rows; existing rows need UPDATE)
        bind.execute(
            sa.text(f"UPDATE {table} SET tenant_id = 'default' WHERE tenant_id IS NULL OR tenant_id = ''")  # noqa: S608
        )

        # ── 3. Index on tenant_id ─────────────────────────────────────────────
        idx_name = f"ix_{table}_tenant_id"
        if not _idx_exists(insp, table, idx_name):
            op.create_index(idx_name, table, ["tenant_id"])

        if not is_pg:
            continue

        # ── 4. Enable RLS + create isolation policy (PostgreSQL only) ─────────
        bind.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))  # noqa: S608

        # Drop existing policy if re-running (idempotent)
        bind.execute(
            sa.text(
                f"DROP POLICY IF EXISTS tenant_isolation ON {table}"  # noqa: S608
            )
        )
        bind.execute(
            sa.text(
                f"""
                CREATE POLICY tenant_isolation ON {table}
                  USING (
                    tenant_id = COALESCE(
                      current_setting('app.tenant_id', true),
                      'default'
                    )
                  )
                  WITH CHECK (
                    tenant_id = COALESCE(
                      current_setting('app.tenant_id', true),
                      'default'
                    )
                  )
                """  # noqa: S608
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)
    is_pg = bind.dialect.name == "postgresql"

    for table in reversed(_TENANT_TABLES):
        if not _table_exists(insp, table):
            continue

        if is_pg:
            bind.execute(
                sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")  # noqa: S608
            )
            bind.execute(
                sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")  # noqa: S608
            )

        idx_name = f"ix_{table}_tenant_id"
        if _idx_exists(insp, table, idx_name):
            op.drop_index(idx_name, table_name=table)

        if _col_exists(insp, table, "tenant_id"):
            op.drop_column(table, "tenant_id")
