import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hd_dashboard.db")

# Fix for PostgreSQL connection strings provided by some cloud hosts (Heroku/Render)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite remains the default for local development, PostgreSQL for Production
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    hid_no = Column(String, unique=True, index=True)
    name = Column(String, nullable=False)
    relation = Column(String)
    relation_type = Column(String)
    sex = Column(String)
    contact_no = Column(String)
    email = Column(String)
    diagnosis = Column(String)
    hd_wef_date = Column(Date)
    viral_markers = Column(String)
    hep_b_status = Column(String)
    hep_b_date = Column(Date)
    pneumococcal_date = Column(Date)
    access_type = Column(String)
    access_date = Column(Date)
    dry_weight = Column(Float)
    hd_slot_1 = Column(String)
    hd_slot_2 = Column(String)
    hd_slot_3 = Column(String)
    whatsapp_link = Column(String)
    whatsapp_notify = Column(Boolean, default=False)
    mail_trigger = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(String)
    updated_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    records = relationship("MonthlyRecord", back_populates="patient")

class MonthlyRecord(Base):
    __tablename__ = "monthly_records"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    record_month = Column(String, index=True)  # YYYY-MM
    entered_by = Column(String)
    target_dry_weight = Column(Float)
    idwg = Column(Float)
    hb = Column(Float)
    serum_ferritin = Column(Float)
    tsat = Column(Float)
    serum_iron = Column(Float)
    epo_mircera_dose = Column(String)
    calcium = Column(Float)
    alkaline_phosphate = Column(Float)
    phosphorus = Column(Float)
    albumin = Column(Float)
    ast = Column(Float)
    alt = Column(Float)
    vit_d = Column(Float)
    ipth = Column(Float)
    av_daily_calories = Column(Float)
    av_daily_protein = Column(Float)
    issues = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="records")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="nurse") # admin, doctor, nurse
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class AlertLog(Base):
    __tablename__ = "alert_logs"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    alert_type = Column(String) # whatsapp, email
    alert_reason = Column(String)
    status = Column(String) # sent, failed
    message_preview = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

def create_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
