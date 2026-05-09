
import os
import sys
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append('/Users/sachinsrivastava/Downloads/HD Dashboard')
from ml_analytics import run_cohort_analytics

DATABASE_URL = "sqlite:///./hd_dashboard.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

data = run_cohort_analytics(db)
print(json.dumps(data, indent=2))

db.close()
