
import os
import sqlite3
from import_real_data import DATA

def fix_ages():
    db_path = "hd_dashboard.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    lines = DATA.strip().split("\n")
    updated = 0
    for line in lines:
        cols = line.split("\t")
        if len(cols) < 16: continue
        
        name = cols[0]
        hid = cols[3]
        age_str = cols[15].strip()
        
        try:
            age = int(age_str)
            cursor.execute("UPDATE patients SET age = ? WHERE hid_no = ?", (age, hid))
            updated += cursor.rowcount
        except ValueError:
            print(f"Skipping {name}: invalid age '{age_str}'")

    conn.commit()
    conn.close()
    print(f"✅ Successfully updated ages for {updated} patients.")

if __name__ == "__main__":
    fix_ages()
