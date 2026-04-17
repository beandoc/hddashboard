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
    relation = Column(String)           # Next of kin / Guardian
    relation_type = Column(String)      # Son/Daughter/Spouse
    sex = Column(String)                # Male / Female / Other
    contact_no = Column(String)
    email = Column(String)
    diagnosis = Column(String)
    hd_wef_date = Column(Date)          # HD started date
    viral_markers = Column(String)      # HBsAg/HCV/HIV status
    # Vaccination Tracking — Hepatitis B (0-1-2-6 month schedule, 1ml IM deltoid)
    hep_b_status = Column(String)       # Immune / Non-Immune / In Progress
    hep_b_dose1_date = Column(Date)     # Month 0
    hep_b_dose2_date = Column(Date)     # Month 1
    hep_b_dose3_date = Column(Date)     # Month 2
    hep_b_dose4_date = Column(Date)     # Month 6
    hep_b_titer_date = Column(Date)     # Anti-HBs titer check date
    # Pneumococcal (0.5ml SC)
    pcv13_date = Column(Date)           # PCV13 initial dose
    ppsv23_date = Column(Date)          # PPSV23 — 2 months after PCV13
    # Herpes Zoster (0.5ml SC, 2 doses 2 months apart)
    hz_dose1_date = Column(Date)
    hz_dose2_date = Column(Date)
    # Influenza (0.5ml SC, yearly)
    influenza_date = Column(Date)
    
    access_type = Column(String)        # AVF / Permacath / P-Cath / Graft
    access_date = Column(Date)
    dry_weight = Column(Float)          # kg
    hd_frequency = Column(Integer, default=2)   # Sessions per week: 2 or 3
    hd_slot_1 = Column(String)                  # "Morning" or "Afternoon"
    hd_slot_2 = Column(String)
    hd_slot_3 = Column(String)
    whatsapp_link = Column(String)      # pre-built wa.me/91XXXXXXXXXX
    whatsapp_notify = Column(Boolean, default=True)
    mail_trigger = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    records = relationship("MonthlyRecord", back_populates="patient", cascade="all, delete-orphan")


class MonthlyRecord(Base):
    __tablename__ = "monthly_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    record_month = Column(String, nullable=False)   # YYYY-MM e.g. "2025-04"
    timestamp = Column(DateTime, default=datetime.utcnow)
    entered_by = Column(String)                     # username of who entered

    # Vitals & IDWG
    idwg = Column(Float)                            # kg

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

    # Liver & Clinical Metrics
    ast = Column(Float)                             # IU/L
    alt = Column(Float)                             # IU/L
    urr = Column(Float)                             # Urea Reduction Ratio (%)
    # Vital signs & Access
    target_dry_weight = Column(Float)               # kg
    bp_sys = Column(Float)                          # Systolic BP (mmHg)
    access_type = Column(String)                    # AVF / Permacath / P-Cath / Graft
    crp = Column(Float)                             # C-Reactive Protein (mg/L)
    epo_weekly_units = Column(Float)                # total units/week

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
