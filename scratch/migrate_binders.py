import sqlite3
import os

db_path = 'hd_dashboard.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE monthly_records ADD COLUMN phosphate_binder_dose_mg FLOAT")
        cursor.execute("ALTER TABLE monthly_records ADD COLUMN phosphate_binder_freq VARCHAR")
        conn.commit()
        print("Migration successful: Added phosphate_binder_dose_mg and phosphate_binder_freq to monthly_records")
    except sqlite3.OperationalError as e:
        print(f"Migration skipped or failed: {e}")
    finally:
        conn.close()
else:
    print(f"Database {db_path} not found.")
