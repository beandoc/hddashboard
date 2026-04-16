from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Date, DateTime, Text, ForeignKey, Index
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
    created_by = Column(String)
    clinical_remarks = Column(Text)

    # Research Baseline Context (Intelligence 5.0)
    dialysis_vintage_months = Column(Integer, default=0)
    primary_diagnosis = Column(String)      # DM, HTN, GN
    comorbidity_cvd = Column(Boolean, default=False)   # Cardiovascular
    comorbidity_cvsd = Column(Boolean, default=False)  # Cerebrovascular
    hyperparathyroidism = Column(Boolean, default=False) # 2o Hyperparathyroidism

    records = relationship("MonthlyRecord", back_populates="patient", cascade="all, delete-orphan")
    transfusions = relationship("BloodTransfusion", back_populates="patient", cascade="all, delete-orphan")


class BloodTransfusion(Base):
    __tablename__ = "blood_transfusions"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    transfusion_date = Column(Date, nullable=False)
    units = Column(Integer, default=1)
    reason = Column(String, nullable=True) # e.g. "Acute Hb drop", "Pre-op"
    timestamp = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="transfusions")


class MonthlyRecord(Base):
    __tablename__ = "monthly_records"
    __table_args__ = (
        Index('idx_patient_month', 'patient_id', 'record_month'),
    )

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
    epo_mircera_dose = Column(String)               # text description
    epo_weekly_units = Column(Float)                # numeric weekly units (e.g. 4000)

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

    # Intelligence 5.0 Baseline Extras
    bp_sys = Column(Integer)
    bp_dia = Column(Integer)
    crp = Column(Float)         # C-Reactive Protein (Inflammation)
    urr = Column(Float)         # Urea Reduction Rate (Adequacy)
    mcv = Column(Float)         # Mean Corpuscular Volume
    hb_hematocrit = Column(Float) # Hematocrit (%)
    iron_iv_supplement = Column(Boolean, default=False)

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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(String, default="nurse") # admin, doctor, nurse
    is_active = Column(Boolean, default=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
