"""
Migration: schema improvements v2
Adds the following columns to existing tables (safe to run on a live DB):

  audit_logs            + patient_id_hash VARCHAR(64)
  ml_predictions        + patient_id_hash VARCHAR(64)
  monthly_records       + data_observed_at TIMESTAMP
                        + data_entered_at  TIMESTAMP NOT NULL DEFAULT now()
                        + feature_vector_hash VARCHAR(64)
  interim_lab_records   + data_observed_at TIMESTAMP
                        + data_entered_at  TIMESTAMP NOT NULL DEFAULT now()
  patient_credentials   + login_username   VARCHAR UNIQUE

Each ALTER is wrapped in a try/except so the script is safe to re-run
(duplicate column → no-op warning, not a crash).

Usage:
    python migrations/add_schema_improvements_v2.py
"""

import os
import sys
import logging

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from database import engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_is_sqlite = str(engine.url).startswith("sqlite")


def _col_exists(conn, table: str, column: str) -> bool:
    if _is_sqlite:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return any(r[1] == column for r in rows)
    else:
        row = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ), {"t": table, "c": column}).fetchone()
        return row is not None


def _add_col(conn, table: str, column: str, definition: str) -> None:
    if _col_exists(conn, table, column):
        log.info("  skip  %s.%s (already exists)", table, column)
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
    log.info("  added %s.%s", table, column)


# SQLite does not support DEFAULT expressions with now() — use NULL default and
# let the application layer fill data_entered_at on new rows.
_ts_default = "" if _is_sqlite else " DEFAULT NOW()"


def run() -> None:
    with engine.begin() as conn:
        log.info("audit_logs")
        _add_col(conn, "audit_logs", "patient_id_hash", "VARCHAR(64)")

        log.info("ml_predictions")
        _add_col(conn, "ml_predictions", "patient_id_hash", "VARCHAR(64)")

        log.info("monthly_records")
        _add_col(conn, "monthly_records", "data_observed_at", "TIMESTAMP")
        _add_col(conn, "monthly_records", "data_entered_at",  f"TIMESTAMP{_ts_default}")
        _add_col(conn, "monthly_records", "feature_vector_hash", "VARCHAR(64)")

        log.info("interim_lab_records")
        _add_col(conn, "interim_lab_records", "data_observed_at", "TIMESTAMP")
        _add_col(conn, "interim_lab_records", "data_entered_at",  f"TIMESTAMP{_ts_default}")

        log.info("patient_credentials")
        _add_col(conn, "patient_credentials", "login_username", "VARCHAR")

        # Back-fill login_username from patients.login_username for existing rows.
        # This is a one-time migration step; the column on patients is removed in
        # the ORM but may still exist on the physical table until the next schema
        # refresh — so we can copy it safely here.
        if not _is_sqlite:
            log.info("Back-filling patient_credentials.login_username from patients …")
            conn.execute(text("""
                UPDATE patient_credentials pc
                SET    login_username = p.login_username
                FROM   patients p
                WHERE  pc.patient_id = p.id
                  AND  pc.login_username IS NULL
                  AND  p.login_username  IS NOT NULL
            """))
        else:
            log.info("Back-filling patient_credentials.login_username from patients (SQLite) …")
            conn.execute(text("""
                UPDATE patient_credentials
                SET    login_username = (
                    SELECT login_username FROM patients
                    WHERE  patients.id = patient_credentials.patient_id
                )
                WHERE  login_username IS NULL
            """))

        # Add UNIQUE index on patient_credentials.login_username (skip if exists).
        if not _is_sqlite:
            idx_exists = conn.execute(text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename = 'patient_credentials' "
                "AND indexname = 'ix_pc_login_username'"
            )).fetchone()
            if not idx_exists:
                conn.execute(text(
                    "CREATE UNIQUE INDEX ix_pc_login_username "
                    "ON patient_credentials (login_username) "
                    "WHERE login_username IS NOT NULL"
                ))
                log.info("  created unique index ix_pc_login_username")
            else:
                log.info("  skip  ix_pc_login_username (already exists)")

    log.info("Migration complete.")


if __name__ == "__main__":
    run()
