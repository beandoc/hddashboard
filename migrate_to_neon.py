"""
migrate_to_neon.py
==================
Full migration from local SQLite → Render/Neon PostgreSQL.

Migrates ALL tables with data, preserving original IDs so foreign keys stay intact.
Safe to re-run: uses INSERT ... ON CONFLICT DO NOTHING.

Usage:
  DATABASE_URL="postgresql://..." python migrate_to_neon.py
"""

import os, sys, sqlite3
from datetime import datetime

local_db_path = os.path.join(os.path.dirname(__file__), "hd_dashboard.db")

NEON_URL = os.environ.get("DATABASE_URL")
if not NEON_URL:
    print("ERROR: Set DATABASE_URL env var to your Render/Neon connection string")
    sys.exit(1)
if NEON_URL.startswith("postgres://"):
    NEON_URL = NEON_URL.replace("postgres://", "postgresql://", 1)

sys.path.insert(0, os.path.dirname(__file__))
from sqlalchemy import create_engine, text, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker
from database import Base

engine = create_engine(
    NEON_URL,
    connect_args={"sslmode": "require", "connect_timeout": 30},
    pool_pre_ping=True,
)
Base.metadata.create_all(bind=engine)
print("Schema ensured on target database.\n")

conn = sqlite3.connect(local_db_path)
conn.row_factory = sqlite3.Row

inspector = sa_inspect(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Tables in dependency order (parents before children)
TABLES = [
    "users",
    "patients",
    "research_projects",
    "variable_definitions",
    "dynamic_variable_definitions",
    "monthly_records",
    "session_records",
    "research_records",
    "clinical_events",
    "dry_weight_assessments",
    "interim_lab_records",
    "patient_meal_records",
    "patient_reminders",
    "patient_symptom_reports",
    "sustainability_records",
    "alert_logs",
    "variable_values",
    "dynamic_variable_values",
]

def coerce_value(val):
    """Coerce SQLite strings to proper Python date/datetime objects for PostgreSQL."""
    if val is None or not isinstance(val, str):
        return val
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(val, fmt)
            return parsed if " " in val or "T" in val else parsed.date()
        except ValueError:
            pass
    return val

# Truncate all tables on Render in reverse order (children first) to avoid FK errors
print("Truncating existing Render data...")
with engine.connect() as pg_conn:
    for table in reversed(TABLES):
        if inspector.has_table(table):
            try:
                pg_conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
            except Exception:
                pass
    pg_conn.commit()
print("Truncate done.\n")

total_inserted = 0

for table in TABLES:
    # Check table exists in both SQLite and PostgreSQL
    sqlite_tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if table not in sqlite_tables:
        continue
    if not inspector.has_table(table):
        continue

    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        continue

    # Get columns that exist in BOTH SQLite and PostgreSQL
    sqlite_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    pg_cols = {c["name"] for c in inspector.get_columns(table)}
    cols = [c for c in sqlite_cols if c in pg_cols and c != "sqlite_sequence"]

    inserted = skipped = errors = 0
    for row in rows:
        r = dict(row)
        params = {c: coerce_value(r.get(c)) for c in cols}
        col_names = ", ".join(cols)
        placeholders = ", ".join(f":{c}" for c in cols)

        # Use primary key conflict detection to skip duplicates safely
        pk_col = "id" if "id" in cols else cols[0]
        try:
            db.execute(
                text(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT ({pk_col}) DO NOTHING"),
                params
            )
            inserted += 1
        except Exception as e:
            errors += 1
            if errors <= 2:
                print(f"  WARN [{table}] row {r.get('id', '?')}: {e}")
            db.rollback()

    db.commit()
    status = f"inserted={inserted}, skipped/existing={len(rows)-inserted-errors}"
    if errors:
        status += f", errors={errors}"
    print(f"  {table}: {len(rows)} rows → {status}")
    total_inserted += inserted

# Reset PostgreSQL sequences so new inserts get correct auto-increment IDs
print("\nResetting sequences...")
with engine.connect() as pg_conn:
    for table in TABLES:
        if not inspector.has_table(table):
            continue
        try:
            pg_conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            ))
            pg_conn.commit()
        except Exception:
            pass

conn.close()
db.close()
print(f"\nDone. Total rows inserted: {total_inserted}")
