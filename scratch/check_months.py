
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from collections import Counter

sys.path.append('/Users/sachinsrivastava/Downloads/HD Dashboard')
from database import MonthlyRecord

DATABASE_URL = "sqlite:///./hd_dashboard.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

records = db.query(MonthlyRecord).all()
months = [r.record_month for r in records]
month_counts = Counter(months)

print("Months found in DB:")
for m in sorted(month_counts.keys()):
    print(f"{m}: {month_counts[m]} records")

db.close()
