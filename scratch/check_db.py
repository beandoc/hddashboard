
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the project directory to sys.path to import local modules
sys.path.append('/Users/sachinsrivastava/Downloads/HD Dashboard')

from database import MonthlyRecord, Base

# Use the database URL from .env or default to sqlite
DATABASE_URL = "sqlite:///./hd_dashboard.db" # Default if not in env

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

records = db.query(MonthlyRecord).all()
print(f"Total MonthlyRecords: {len(records)}")

if records:
    print("First 5 records:")
    for r in records[:5]:
        print(f"Month: {r.record_month}, Hb: {r.hb}, Alb: {r.albumin}, Phos: {r.phosphorus}")

db.close()
