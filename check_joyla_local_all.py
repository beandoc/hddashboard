import sqlite3
import os

db_files = [f for f in os.listdir(".") if f.endswith(".db")]
print("Found DB files:", db_files)

for db_file in db_files:
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        if "patients" in tables:
            cursor.execute("SELECT id, name, hid_no FROM patients WHERE name LIKE '%Joyla%' OR hid_no = '202939012216';")
            rows = cursor.fetchall()
            if rows:
                print(f"Found in {db_file}:", rows)
                for r in rows:
                    pid = r[0]
                    if "monthly_records" in tables:
                        cursor.execute(f"SELECT record_month, hb FROM monthly_records WHERE patient_id = {pid} ORDER BY record_month DESC;")
                        print("  Monthly:", cursor.fetchall())
                    if "interim_lab_records" in tables:
                        cursor.execute(f"SELECT record_month, lab_date, parameter, value FROM interim_lab_records WHERE patient_id = {pid} AND parameter = 'hb' ORDER BY lab_date DESC;")
                        print("  Interim:", cursor.fetchall())
        conn.close()
    except Exception as e:
        print(f"Error reading {db_file}: {e}")
