import sqlite3

def migrate():
    conn = sqlite3.connect('hd_dashboard.db')
    cursor = conn.cursor()
    
    # Check existing columns
    cursor.execute("PRAGMA table_info(patients)")
    columns = [column[1] for column in cursor.fetchall()]
    
    new_columns = [
        ("withdrawal_date", "DATE"),
        ("withdrawal_reason", "TEXT"),
        ("withdrawal_clinician", "TEXT")
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in columns:
            print(f"Adding column {col_name} to patients table...")
            try:
                cursor.execute(f"ALTER TABLE patients ADD COLUMN {col_name} {col_type}")
                conn.commit()
            except Exception as e:
                print(f"Error adding {col_name}: {e}")
        else:
            print(f"Column {col_name} already exists.")
            
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
