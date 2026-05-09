
import requests
import json

def check_api():
    try:
        # Assuming the server is running on localhost:8000
        # If not, we can check the database directly
        print("Checking /api/cohort-trends...")
        # Since I can't easily call the running server's API from here if it's not started,
        # I will simulate the backend call by importing the function.
        pass
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import os
    import sys
    
    # Add current directory to path so we can import routers/ml_analytics
    sys.path.append(os.getcwd())
    
    from database import SessionLocal, MonthlyRecord
    from ml_analytics import run_cohort_analytics
    
    db = SessionLocal()
    try:
        print("Checking database for MonthlyRecords...")
        count = db.query(MonthlyRecord).count()
        print(f"Total MonthlyRecords: {count}")
        
        if count > 0:
            print("Checking for non-null values in key parameters...")
            for p in ["hb", "albumin", "phosphorus"]:
                non_null_count = db.query(MonthlyRecord).filter(getattr(MonthlyRecord, p) != None).count()
                print(f"Param {p} non-null count: {non_null_count}")
            
            data = run_cohort_analytics(db)
            print("Cohort Analytics Data:")
            # print(json.dumps(data, indent=2))
            print(f"Available: {data.get('available')}")
            print(f"Months: {data.get('months')}")
            for p in ["hb", "albumin", "phosphorus"]:
                if p in data:
                    print(f"Param {p}: {len(data[p])} entries")
                else:
                    print(f"Param {p}: MISSING")
        else:
            print("No records found in database.")
    finally:
        db.close()
