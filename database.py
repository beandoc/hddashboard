import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Date, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

# Support both SQLite (local dev) and PostgreSQL (Render production)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./hd_dashboard.db")

# Render gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    hid_no = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    relation_type = Column(String)      # S/O, D/O, W/O
    relation_name = Column(String)      # Guardian Name
    sex = Column(String)                # Male / Female / Other
    contact_no = Column(String)
    email = Column(String)
    diagnosis = Column(String)
    hd_wef_date = Column(Date)          # HD started date
    viral_markers = Column(String)      # HBsAg/HCV/HIV status
    access_type = Column(String)        # AVF / Permacath / P-Cath / Graft
    access_date = Column(Date)
    dry_weight = Column(Float)          # kg
    hd_slot_1 = Column(String)          # e.g. Mon Morning
    hd_slot_2 = Column(String)
    hd_slot_3 = Column(String)
    
    # Vaccination Tracking (Clinical Sentinel)
    hep_b_status = Column(String)       # Immune / Non-Immune / Unknown
    hep_b_date = Column(Date)           # Last Dose Date
    pneumococcal_date = Column(Date)    # Last Dose Date
    
    whatsapp_link = Column(String)      # pre-built wa.me/91XXXXXXXXXX
    whatsapp_notify = Column(Boolean, default=True)
    mail_trigger = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String)

    records = relationship("MonthlyRecord", back_populates="patient", cascade="all, delete-orphan")


class MonthlyRecord(Base):
    __tablename__ = "monthly_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    record_month = Column(String, nullable=False)   # YYYY-MM
    timestamp = Column(DateTime, default=datetime.utcnow)
    entered_by = Column(String)                     # username of who entered
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Vitals & IDWG
    target_dry_weight = Column(Float)               # kg
    idwg = Column(Float)                            # kg (Fluid Weight Gain)

    # Anemia / Iron Panel
    hb = Column(Float)                              # g/dL
    serum_ferritin = Column(Float)                  # ng/mL
    tsat = Column(Float)                            # %
    serum_iron = Column(Float)                      # µg/dL
    epo_mircera_dose = Column(String)               # dose + frequency

    # Mineral Metabolism
    calcium = Column(Float)                         # mg/dL (uncorrected)
    alkaline_phosphate = Column(Float)              # IU/L
    phosphorus = Column(Float)                      # mg/dL
    vit_d = Column(Float)                           # ng/mL
    ipth = Column(Float)                            # pg/mL

    # Nutrition
    albumin = Column(Float)                         # g/dL
    av_daily_calories = Column(Float)               # kcal/day
    av_daily_protein = Column(Float)                # g/kg/day

    # Liver
    ast = Column(Float)                             # IU/L
    alt = Column(Float)                             # IU/L

    # Clinical Notes
    issues = Column(Text)

    patient = relationship("Patient", back_populates="records")


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    alert_type = Column(String)         # 'email' or 'whatsapp'
    alert_reason = Column(String)       # e.g. 'Hb drop alert'
    sent_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String)             # 'sent' / 'failed'
    message_preview = Column(Text)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
