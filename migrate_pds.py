# migrate_pds.py
from sqlalchemy import text
from database import engine

def migrate():
    print("🚀 Starting PDS Schema Migration...")
    
    # Columns to add to session_records
    session_cols = [
        ("intradialytic_exercise_mins", "INTEGER"),
        ("intradialytic_meals_eaten", "BOOLEAN DEFAULT FALSE")
    ]
    
    # Columns to add to patient_symptom_reports
    symptom_cols = [
        ("session_id", "INTEGER"),
        ("dialysis_recovery_time_mins", "INTEGER"),
        ("tiredness_score", "INTEGER"),
        ("energy_level_score", "INTEGER"),
        ("daily_activity_impact", "INTEGER"),
        ("cognitive_alertness", "VARCHAR"),
        ("post_hd_mood", "VARCHAR"),
        ("sleepiness_severity", "INTEGER"),
        ("missed_social_or_work_event", "BOOLEAN DEFAULT FALSE")
    ]

    with engine.connect() as conn:
        # 1. Update session_records
        for col, col_type in session_cols:
            try:
                conn.execute(text(f"ALTER TABLE session_records ADD COLUMN {col} {col_type}"))
                conn.commit()
                print(f"✅ Added {col} to session_records")
            except Exception as e:
                print(f"⚠️ Could not add {col} (it might already exist): {e}")

        # 2. Update patient_symptom_reports
        for col, col_type in symptom_cols:
            try:
                conn.execute(text(f"ALTER TABLE patient_symptom_reports ADD COLUMN {col} {col_type}"))
                conn.commit()
                print(f"✅ Added {col} to patient_symptom_reports")
            except Exception as e:
                print(f"⚠️ Could not add {col}: {e}")

    print("🏁 Migration finished.")

if __name__ == "__main__":
    migrate()
