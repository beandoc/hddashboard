import os
import hmac as _hmac
import hashlib as _hashlib
from typing import Optional, AsyncGenerator
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Date, DateTime, Text, ForeignKey, Index, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# PHI PSEUDONYMISATION
#
# compute_patient_id_hash returns an HMAC-SHA256 hex digest of the integer
# patient_id.  Store this on AuditLog and MLPrediction rows so analytics /
# reporting can correlate records without ever joining back to patients.id.
#
# Key priority: AUDIT_HMAC_KEY > SECRET_KEY > "" (returns None when absent).
# ─────────────────────────────────────────────────────────────────────────────

def _audit_hmac_key() -> bytes:
    raw = os.environ.get("AUDIT_HMAC_KEY") or os.environ.get("SECRET_KEY") or ""
    return raw.encode()


def compute_patient_id_hash(patient_id: Optional[int]) -> Optional[str]:
    """HMAC-SHA256(patient_id) — safe for audit/ML tables, never re-linkable to PHI by itself."""
    if patient_id is None:
        return None
    key = _audit_hmac_key()
    if not key:
        return None
    return _hmac.new(key, str(patient_id).encode(), _hashlib.sha256).hexdigest()

# Support both SQLite (local dev) and PostgreSQL (Supabase production)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./hd_dashboard.db")

# Supabase (and other providers) give postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    _connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, connect_args=_connect_args)
else:
    # Supabase requires SSL; connect_timeout handles cold-start latency
    _connect_args = {
        "sslmode": "require",
        "connect_timeout": 30,
    }
    engine = create_engine(
        DATABASE_URL,
        connect_args=_connect_args,
        pool_pre_ping=True,      # re-validate connections on checkout
        pool_recycle=300,        # recycle before Supabase's idle timeout
        pool_size=5,
        max_overflow=10,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ─────────────────────────────────────────────────────────────────────────────
# ASYNC ENGINE  (asyncpg — used by /api/v1/* analytics endpoints)
#
# Two connection pools run in parallel:
#   engine          → sync psycopg2  (Jinja2 form routes, Alembic, Celery tasks)
#   async_engine    → asyncpg        (FastAPI async routes, cohort aggregations)
#
# Read-replica support: set DATABASE_REPLICA_URL to route analytics-only
# queries to a standby.  Falls back to the primary when unset.
# ─────────────────────────────────────────────────────────────────────────────

_REPLICA_URL = os.environ.get("DATABASE_REPLICA_URL") or DATABASE_URL

if not _is_sqlite:
    _async_url = _REPLICA_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    async_engine = create_async_engine(
        _async_url,
        connect_args={"ssl": "require"},
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
    )
else:
    # SQLite dev fallback — aiosqlite would be required in practice; skip async for SQLite.
    async_engine = None  # type: ignore[assignment]

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
) if async_engine is not None else None  # type: ignore[assignment]


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async DB sessions (analytics / API routes)."""
    if AsyncSessionLocal is None:
        raise RuntimeError("Async DB not available in SQLite mode")
    async with AsyncSessionLocal() as session:
        yield session


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """Inject the tenant_id into the PostgreSQL session so RLS policies evaluate correctly.

    Must be called at the start of every async request that touches clinical tables.
    The SET LOCAL is transaction-scoped and resets automatically on commit/rollback.
    """
    from sqlalchemy import text as _text
    await session.execute(_text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))  # noqa: S608


Base = declarative_base()


# ─────────────────────────────────────────────────────────────────────────────
# PATIENT SATELLITE TABLES  (1:1 with patients.id as both PK and FK)
#
# Design rationale: the monolithic patients table had ~170 columns spanning
# auth credentials, comorbidities, viral markers, vaccination, vascular access,
# cardiac parameters, renal profile, and outcomes.  PHI reads were pulling
# hashed passwords; auth checks were pulling full clinical history; row size
# was degrading PostgreSQL buffer-cache hit rate.
#
# Each satellite uses patient_id as its PRIMARY KEY (not a surrogate) which
# enforces the 1:1 constraint at the DDL level and eliminates a B-tree index.
# ─────────────────────────────────────────────────────────────────────────────

class PatientCredentials(Base):
    """Patient portal auth — all credential fields live here, not on patients.

    login_username is the indexed lookup key for patient-portal auth.  Keeping
    it here (rather than on patients) means clinical reads never load credentials.
    reset_token is a URL-safe random token; token_expires is its UTC deadline.
    """
    __tablename__ = "patient_credentials"

    patient_id      = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    login_username  = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String)
    reset_token     = Column(String, nullable=True, index=True)
    token_expires   = Column(DateTime, nullable=True)


class PatientComorbidities(Base):
    """Structured comorbidity profile + Charlson index.  Updated on every CRUD edit."""
    __tablename__ = "patient_comorbidities"

    patient_id                = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    dm_status                 = Column(String)
    dm_end_organ_damage       = Column(Boolean)
    htn_status                = Column(Boolean)
    cad_status                = Column(Boolean)
    chf_status                = Column(Boolean)
    history_of_stroke         = Column(Boolean)
    history_of_pvd            = Column(Boolean)
    history_of_dementia       = Column(Boolean)
    history_of_cpd            = Column(Boolean)
    history_of_ctd            = Column(Boolean)
    history_of_pud            = Column(Boolean)
    liver_disease             = Column(String)
    hemiplegia                = Column(Boolean)
    solid_tumor               = Column(String)
    leukemia                  = Column(Boolean)
    lymphoma                  = Column(Boolean)
    smoking_status            = Column(String)
    alcohol_consumption       = Column(String)
    charlson_comorbidity_index = Column(Integer)
    comorbidities             = Column(Text)
    drug_allergies            = Column(String)
    clinical_background       = Column(Text)


class PatientRenalProfile(Base):
    """Primary renal diagnosis, KRT history, and KRCRw baseline parameters."""
    __tablename__ = "patient_renal_profile"

    patient_id                   = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    primary_renal_disease        = Column(String)
    native_kidney_disease        = Column(String)
    date_esrd_diagnosis          = Column(Date)
    native_kidney_biopsy         = Column(String)
    native_kidney_biopsy_date    = Column(Date)
    native_kidney_biopsy_report  = Column(Text)
    dialysis_modality            = Column(String)
    previous_dialysis_modality   = Column(String)
    previous_krt_modality        = Column(String)
    history_of_renal_transplant  = Column(Boolean)
    transplant_prospect          = Column(String)
    baseline_gcr                 = Column(Float)
    baseline_vdcr                = Column(Float)
    is_black                     = Column(Boolean, default=False)


class PatientViralMarkers(Base):
    """HBsAg, Anti-HCV, HIV serology — accessed by infection-control workflows."""
    __tablename__ = "patient_viral_markers"

    patient_id    = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    viral_markers = Column(String)   # legacy combined string
    viral_hbsag   = Column(String)
    viral_anti_hcv = Column(String)
    viral_hiv     = Column(String)


class PatientVaccination(Base):
    """Vaccination schedule and completion dates."""
    __tablename__ = "patient_vaccination"

    patient_id        = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    hep_b_status      = Column(String)
    hep_b_dose1_date  = Column(Date)
    hep_b_dose2_date  = Column(Date)
    hep_b_dose3_date  = Column(Date)
    hep_b_dose4_date  = Column(Date)
    hep_b_titer_date  = Column(Date)
    pcv13_date        = Column(Date)
    ppsv23_date       = Column(Date)
    hz_dose1_date     = Column(Date)
    hz_dose2_date     = Column(Date)
    influenza_date    = Column(Date)


class PatientVascularAccess(Base):
    """Patient-level (semi-static) vascular access record.  Per-session data is in SessionRecord."""
    __tablename__ = "patient_vascular_access"

    patient_id                    = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    access_type                   = Column(String)
    access_date                   = Column(Date)
    date_first_cannulation        = Column(Date)
    history_of_access_thrombosis  = Column(Boolean)
    access_intervention_history   = Column(Text)
    catheter_type                 = Column(String)
    catheter_insertion_site       = Column(String)


class PatientCardiac(Base):
    """Echocardiographic parameters and functional capacity markers."""
    __tablename__ = "patient_cardiac"

    patient_id           = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    ejection_fraction    = Column(Float, default=60.0)
    diastolic_dysfunction = Column(String)
    handgrip_strength    = Column(Float)
    echo_date            = Column(Date)
    echo_report          = Column(Text)


class PatientOutcomes(Base):
    """Survival status, death, transplant, withdrawal, and transfer — updated by deactivation flow."""
    __tablename__ = "patient_outcomes"

    patient_id               = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    current_survival_status  = Column(String)
    date_of_death            = Column(Date)
    primary_cause_of_death   = Column(String)
    date_of_transplant       = Column(Date)
    withdrawal_from_dialysis = Column(Boolean)
    withdrawal_date          = Column(Date)
    withdrawal_reason        = Column(String)
    withdrawal_clinician     = Column(String)
    date_facility_transfer   = Column(Date)


# ─────────────────────────────────────────────────────────────────────────────
# PATIENT  (core identity + scheduling only — ~30 columns)
# ─────────────────────────────────────────────────────────────────────────────

class Patient(Base):
    __tablename__ = "patients"

    id       = Column(Integer, primary_key=True, index=True)
    hid_no   = Column(String, unique=True, index=True, nullable=False)
    name     = Column(String, nullable=False)
    relation      = Column(String)
    relation_type = Column(String)
    sex           = Column(String)
    contact_no    = Column(String)
    email         = Column(String)
    diagnosis     = Column(String)
    hd_wef_date   = Column(Date)

    education_level    = Column(String)
    height             = Column(Float)
    blood_group        = Column(String)
    age                = Column(Integer)
    dry_weight         = Column(Float)
    healthcare_facility = Column(String)

    hd_frequency = Column(Integer, default=2)
    hd_day_1     = Column(String)
    hd_day_2     = Column(String)
    hd_day_3     = Column(String)
    hd_slot_1    = Column(String)
    hd_slot_2    = Column(String)
    hd_slot_3    = Column(String)

    whatsapp_link   = Column(String)
    whatsapp_notify = Column(Boolean, default=True)
    mail_trigger    = Column(Boolean, default=False)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── 1:1 satellite relationships ──────────────────────────────────────────
    credentials    = relationship("PatientCredentials",  uselist=False, cascade="all, delete-orphan")
    comorbidity_profile = relationship("PatientComorbidities", uselist=False, cascade="all, delete-orphan")
    renal_profile  = relationship("PatientRenalProfile",  uselist=False, cascade="all, delete-orphan")
    viral_markers_ = relationship("PatientViralMarkers",  uselist=False, cascade="all, delete-orphan")
    vaccination    = relationship("PatientVaccination",   uselist=False, cascade="all, delete-orphan")
    vascular_access = relationship("PatientVascularAccess", uselist=False, cascade="all, delete-orphan")
    cardiac        = relationship("PatientCardiac",       uselist=False, cascade="all, delete-orphan")
    outcomes       = relationship("PatientOutcomes",      uselist=False, cascade="all, delete-orphan")

    # ── 1:many relationships ─────────────────────────────────────────────────
    records              = relationship("MonthlyRecord",         back_populates="patient", cascade="all, delete-orphan")
    sessions             = relationship("SessionRecord",         back_populates="patient", cascade="all, delete-orphan")
    interim_labs         = relationship("InterimLabRecord",      back_populates="patient", cascade="all, delete-orphan")
    meal_records         = relationship("PatientMealRecord",     back_populates="patient", cascade="all, delete-orphan")
    symptom_reports      = relationship("PatientSymptomReport",  back_populates="patient", cascade="all, delete-orphan")
    reminders            = relationship("PatientReminder",       back_populates="patient", cascade="all, delete-orphan")
    dry_weight_assessments = relationship("DryWeightAssessment", back_populates="patient", cascade="all, delete-orphan")
    events               = relationship("ClinicalEvent",         back_populates="patient", cascade="all, delete-orphan")
    research_records     = relationship("ResearchRecord",        back_populates="patient", cascade="all, delete-orphan")
    hospitalisations     = relationship("HospitalisationEvent",  back_populates="patient", cascade="all, delete-orphan")

    # ── Backward-compatible property proxies ─────────────────────────────────
    # These allow all existing router / service / template code to keep using
    # patient.field notation without modification.  Setters auto-create the
    # satellite row on first write (handles both construction-time kwargs and
    # post-load attribute assignments).

    # credentials
    @hybrid_property
    def login_username(self):
        return self.credentials.login_username if self.credentials else None

    @login_username.setter
    def login_username(self, value):
        if self.credentials is None:
            self.credentials = PatientCredentials(login_username=value)
        else:
            self.credentials.login_username = value

    @login_username.expression
    def login_username(cls):
        # Correlated subquery so Patient.login_username still works in filter().
        return (
            select(PatientCredentials.login_username)
            .where(PatientCredentials.patient_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    @property
    def hashed_password(self):
        return self.credentials.hashed_password if self.credentials else None

    @hashed_password.setter
    def hashed_password(self, value):
        if self.credentials is None:
            self.credentials = PatientCredentials(hashed_password=value)
        else:
            self.credentials.hashed_password = value

    # comorbidities
    def _ensure_comorbidities(self):
        if self.comorbidity_profile is None:
            self.comorbidity_profile = PatientComorbidities()
        return self.comorbidity_profile

    @property
    def dm_status(self):
        return self.comorbidity_profile.dm_status if self.comorbidity_profile else None

    @dm_status.setter
    def dm_status(self, v):
        self._ensure_comorbidities().dm_status = v

    @property
    def dm_end_organ_damage(self):
        return self.comorbidity_profile.dm_end_organ_damage if self.comorbidity_profile else None

    @dm_end_organ_damage.setter
    def dm_end_organ_damage(self, v):
        self._ensure_comorbidities().dm_end_organ_damage = v

    @property
    def htn_status(self):
        return self.comorbidity_profile.htn_status if self.comorbidity_profile else None

    @htn_status.setter
    def htn_status(self, v):
        self._ensure_comorbidities().htn_status = v

    @property
    def cad_status(self):
        return self.comorbidity_profile.cad_status if self.comorbidity_profile else None

    @cad_status.setter
    def cad_status(self, v):
        self._ensure_comorbidities().cad_status = v

    @property
    def chf_status(self):
        return self.comorbidity_profile.chf_status if self.comorbidity_profile else None

    @chf_status.setter
    def chf_status(self, v):
        self._ensure_comorbidities().chf_status = v

    @property
    def history_of_stroke(self):
        return self.comorbidity_profile.history_of_stroke if self.comorbidity_profile else None

    @history_of_stroke.setter
    def history_of_stroke(self, v):
        self._ensure_comorbidities().history_of_stroke = v

    @property
    def history_of_pvd(self):
        return self.comorbidity_profile.history_of_pvd if self.comorbidity_profile else None

    @history_of_pvd.setter
    def history_of_pvd(self, v):
        self._ensure_comorbidities().history_of_pvd = v

    @property
    def history_of_dementia(self):
        return self.comorbidity_profile.history_of_dementia if self.comorbidity_profile else None

    @history_of_dementia.setter
    def history_of_dementia(self, v):
        self._ensure_comorbidities().history_of_dementia = v

    @property
    def history_of_cpd(self):
        return self.comorbidity_profile.history_of_cpd if self.comorbidity_profile else None

    @history_of_cpd.setter
    def history_of_cpd(self, v):
        self._ensure_comorbidities().history_of_cpd = v

    @property
    def history_of_ctd(self):
        return self.comorbidity_profile.history_of_ctd if self.comorbidity_profile else None

    @history_of_ctd.setter
    def history_of_ctd(self, v):
        self._ensure_comorbidities().history_of_ctd = v

    @property
    def history_of_pud(self):
        return self.comorbidity_profile.history_of_pud if self.comorbidity_profile else None

    @history_of_pud.setter
    def history_of_pud(self, v):
        self._ensure_comorbidities().history_of_pud = v

    @property
    def liver_disease(self):
        return self.comorbidity_profile.liver_disease if self.comorbidity_profile else None

    @liver_disease.setter
    def liver_disease(self, v):
        self._ensure_comorbidities().liver_disease = v

    @property
    def hemiplegia(self):
        return self.comorbidity_profile.hemiplegia if self.comorbidity_profile else None

    @hemiplegia.setter
    def hemiplegia(self, v):
        self._ensure_comorbidities().hemiplegia = v

    @property
    def solid_tumor(self):
        return self.comorbidity_profile.solid_tumor if self.comorbidity_profile else None

    @solid_tumor.setter
    def solid_tumor(self, v):
        self._ensure_comorbidities().solid_tumor = v

    @property
    def leukemia(self):
        return self.comorbidity_profile.leukemia if self.comorbidity_profile else None

    @leukemia.setter
    def leukemia(self, v):
        self._ensure_comorbidities().leukemia = v

    @property
    def lymphoma(self):
        return self.comorbidity_profile.lymphoma if self.comorbidity_profile else None

    @lymphoma.setter
    def lymphoma(self, v):
        self._ensure_comorbidities().lymphoma = v

    @property
    def smoking_status(self):
        return self.comorbidity_profile.smoking_status if self.comorbidity_profile else None

    @smoking_status.setter
    def smoking_status(self, v):
        self._ensure_comorbidities().smoking_status = v

    @property
    def alcohol_consumption(self):
        return self.comorbidity_profile.alcohol_consumption if self.comorbidity_profile else None

    @alcohol_consumption.setter
    def alcohol_consumption(self, v):
        self._ensure_comorbidities().alcohol_consumption = v

    @property
    def charlson_comorbidity_index(self):
        return self.comorbidity_profile.charlson_comorbidity_index if self.comorbidity_profile else None

    @charlson_comorbidity_index.setter
    def charlson_comorbidity_index(self, v):
        self._ensure_comorbidities().charlson_comorbidity_index = v

    # "comorbidities" is the legacy free-text supplementary notes field
    @property
    def comorbidities(self):
        return self.comorbidity_profile.comorbidities if self.comorbidity_profile else None

    @comorbidities.setter
    def comorbidities(self, v):
        self._ensure_comorbidities().comorbidities = v

    @property
    def drug_allergies(self):
        return self.comorbidity_profile.drug_allergies if self.comorbidity_profile else None

    @drug_allergies.setter
    def drug_allergies(self, v):
        self._ensure_comorbidities().drug_allergies = v

    @property
    def clinical_background(self):
        return self.comorbidity_profile.clinical_background if self.comorbidity_profile else None

    @clinical_background.setter
    def clinical_background(self, v):
        self._ensure_comorbidities().clinical_background = v

    # renal profile
    def _ensure_renal_profile(self):
        if self.renal_profile is None:
            self.renal_profile = PatientRenalProfile()
        return self.renal_profile

    @property
    def primary_renal_disease(self):
        return self.renal_profile.primary_renal_disease if self.renal_profile else None

    @primary_renal_disease.setter
    def primary_renal_disease(self, v):
        self._ensure_renal_profile().primary_renal_disease = v

    @property
    def native_kidney_disease(self):
        return self.renal_profile.native_kidney_disease if self.renal_profile else None

    @native_kidney_disease.setter
    def native_kidney_disease(self, v):
        self._ensure_renal_profile().native_kidney_disease = v

    @property
    def date_esrd_diagnosis(self):
        return self.renal_profile.date_esrd_diagnosis if self.renal_profile else None

    @date_esrd_diagnosis.setter
    def date_esrd_diagnosis(self, v):
        self._ensure_renal_profile().date_esrd_diagnosis = v

    @property
    def native_kidney_biopsy(self):
        return self.renal_profile.native_kidney_biopsy if self.renal_profile else None

    @native_kidney_biopsy.setter
    def native_kidney_biopsy(self, v):
        self._ensure_renal_profile().native_kidney_biopsy = v

    @property
    def native_kidney_biopsy_date(self):
        return self.renal_profile.native_kidney_biopsy_date if self.renal_profile else None

    @native_kidney_biopsy_date.setter
    def native_kidney_biopsy_date(self, v):
        self._ensure_renal_profile().native_kidney_biopsy_date = v

    @property
    def native_kidney_biopsy_report(self):
        return self.renal_profile.native_kidney_biopsy_report if self.renal_profile else None

    @native_kidney_biopsy_report.setter
    def native_kidney_biopsy_report(self, v):
        self._ensure_renal_profile().native_kidney_biopsy_report = v

    @property
    def dialysis_modality(self):
        return self.renal_profile.dialysis_modality if self.renal_profile else None

    @dialysis_modality.setter
    def dialysis_modality(self, v):
        self._ensure_renal_profile().dialysis_modality = v

    @property
    def previous_dialysis_modality(self):
        return self.renal_profile.previous_dialysis_modality if self.renal_profile else None

    @previous_dialysis_modality.setter
    def previous_dialysis_modality(self, v):
        self._ensure_renal_profile().previous_dialysis_modality = v

    @property
    def previous_krt_modality(self):
        return self.renal_profile.previous_krt_modality if self.renal_profile else None

    @previous_krt_modality.setter
    def previous_krt_modality(self, v):
        self._ensure_renal_profile().previous_krt_modality = v

    @property
    def history_of_renal_transplant(self):
        return self.renal_profile.history_of_renal_transplant if self.renal_profile else None

    @history_of_renal_transplant.setter
    def history_of_renal_transplant(self, v):
        self._ensure_renal_profile().history_of_renal_transplant = v

    @property
    def transplant_prospect(self):
        return self.renal_profile.transplant_prospect if self.renal_profile else None

    @transplant_prospect.setter
    def transplant_prospect(self, v):
        self._ensure_renal_profile().transplant_prospect = v

    @property
    def baseline_gcr(self):
        return self.renal_profile.baseline_gcr if self.renal_profile else None

    @baseline_gcr.setter
    def baseline_gcr(self, v):
        self._ensure_renal_profile().baseline_gcr = v

    @property
    def baseline_vdcr(self):
        return self.renal_profile.baseline_vdcr if self.renal_profile else None

    @baseline_vdcr.setter
    def baseline_vdcr(self, v):
        self._ensure_renal_profile().baseline_vdcr = v

    @property
    def is_black(self):
        return self.renal_profile.is_black if self.renal_profile else False

    @is_black.setter
    def is_black(self, v):
        self._ensure_renal_profile().is_black = v

    # viral markers
    def _ensure_viral(self):
        if self.viral_markers_ is None:
            self.viral_markers_ = PatientViralMarkers()
        return self.viral_markers_

    @property
    def viral_markers(self):
        return self.viral_markers_.viral_markers if self.viral_markers_ else None

    @viral_markers.setter
    def viral_markers(self, v):
        self._ensure_viral().viral_markers = v

    @property
    def viral_hbsag(self):
        return self.viral_markers_.viral_hbsag if self.viral_markers_ else None

    @viral_hbsag.setter
    def viral_hbsag(self, v):
        self._ensure_viral().viral_hbsag = v

    @property
    def viral_anti_hcv(self):
        return self.viral_markers_.viral_anti_hcv if self.viral_markers_ else None

    @viral_anti_hcv.setter
    def viral_anti_hcv(self, v):
        self._ensure_viral().viral_anti_hcv = v

    @property
    def viral_hiv(self):
        return self.viral_markers_.viral_hiv if self.viral_markers_ else None

    @viral_hiv.setter
    def viral_hiv(self, v):
        self._ensure_viral().viral_hiv = v

    # vaccination
    def _ensure_vaccination(self):
        if self.vaccination is None:
            self.vaccination = PatientVaccination()
        return self.vaccination

    @property
    def hep_b_status(self):
        return self.vaccination.hep_b_status if self.vaccination else None

    @hep_b_status.setter
    def hep_b_status(self, v):
        self._ensure_vaccination().hep_b_status = v

    @property
    def hep_b_dose1_date(self):
        return self.vaccination.hep_b_dose1_date if self.vaccination else None

    @hep_b_dose1_date.setter
    def hep_b_dose1_date(self, v):
        self._ensure_vaccination().hep_b_dose1_date = v

    @property
    def hep_b_dose2_date(self):
        return self.vaccination.hep_b_dose2_date if self.vaccination else None

    @hep_b_dose2_date.setter
    def hep_b_dose2_date(self, v):
        self._ensure_vaccination().hep_b_dose2_date = v

    @property
    def hep_b_dose3_date(self):
        return self.vaccination.hep_b_dose3_date if self.vaccination else None

    @hep_b_dose3_date.setter
    def hep_b_dose3_date(self, v):
        self._ensure_vaccination().hep_b_dose3_date = v

    @property
    def hep_b_dose4_date(self):
        return self.vaccination.hep_b_dose4_date if self.vaccination else None

    @hep_b_dose4_date.setter
    def hep_b_dose4_date(self, v):
        self._ensure_vaccination().hep_b_dose4_date = v

    @property
    def hep_b_titer_date(self):
        return self.vaccination.hep_b_titer_date if self.vaccination else None

    @hep_b_titer_date.setter
    def hep_b_titer_date(self, v):
        self._ensure_vaccination().hep_b_titer_date = v

    @property
    def pcv13_date(self):
        return self.vaccination.pcv13_date if self.vaccination else None

    @pcv13_date.setter
    def pcv13_date(self, v):
        self._ensure_vaccination().pcv13_date = v

    @property
    def ppsv23_date(self):
        return self.vaccination.ppsv23_date if self.vaccination else None

    @ppsv23_date.setter
    def ppsv23_date(self, v):
        self._ensure_vaccination().ppsv23_date = v

    @property
    def hz_dose1_date(self):
        return self.vaccination.hz_dose1_date if self.vaccination else None

    @hz_dose1_date.setter
    def hz_dose1_date(self, v):
        self._ensure_vaccination().hz_dose1_date = v

    @property
    def hz_dose2_date(self):
        return self.vaccination.hz_dose2_date if self.vaccination else None

    @hz_dose2_date.setter
    def hz_dose2_date(self, v):
        self._ensure_vaccination().hz_dose2_date = v

    @property
    def influenza_date(self):
        return self.vaccination.influenza_date if self.vaccination else None

    @influenza_date.setter
    def influenza_date(self, v):
        self._ensure_vaccination().influenza_date = v

    # vascular access
    def _ensure_vascular(self):
        if self.vascular_access is None:
            self.vascular_access = PatientVascularAccess()
        return self.vascular_access

    @property
    def access_type(self):
        return self.vascular_access.access_type if self.vascular_access else None

    @access_type.setter
    def access_type(self, v):
        self._ensure_vascular().access_type = v

    @property
    def access_date(self):
        return self.vascular_access.access_date if self.vascular_access else None

    @access_date.setter
    def access_date(self, v):
        self._ensure_vascular().access_date = v

    @property
    def date_first_cannulation(self):
        return self.vascular_access.date_first_cannulation if self.vascular_access else None

    @date_first_cannulation.setter
    def date_first_cannulation(self, v):
        self._ensure_vascular().date_first_cannulation = v

    @property
    def history_of_access_thrombosis(self):
        return self.vascular_access.history_of_access_thrombosis if self.vascular_access else None

    @history_of_access_thrombosis.setter
    def history_of_access_thrombosis(self, v):
        self._ensure_vascular().history_of_access_thrombosis = v

    @property
    def access_intervention_history(self):
        return self.vascular_access.access_intervention_history if self.vascular_access else None

    @access_intervention_history.setter
    def access_intervention_history(self, v):
        self._ensure_vascular().access_intervention_history = v

    @property
    def catheter_type(self):
        return self.vascular_access.catheter_type if self.vascular_access else None

    @catheter_type.setter
    def catheter_type(self, v):
        self._ensure_vascular().catheter_type = v

    @property
    def catheter_insertion_site(self):
        return self.vascular_access.catheter_insertion_site if self.vascular_access else None

    @catheter_insertion_site.setter
    def catheter_insertion_site(self, v):
        self._ensure_vascular().catheter_insertion_site = v

    # cardiac
    def _ensure_cardiac(self):
        if self.cardiac is None:
            self.cardiac = PatientCardiac()
        return self.cardiac

    @property
    def ejection_fraction(self):
        return self.cardiac.ejection_fraction if self.cardiac else 60.0

    @ejection_fraction.setter
    def ejection_fraction(self, v):
        self._ensure_cardiac().ejection_fraction = v

    @property
    def diastolic_dysfunction(self):
        return self.cardiac.diastolic_dysfunction if self.cardiac else None

    @diastolic_dysfunction.setter
    def diastolic_dysfunction(self, v):
        self._ensure_cardiac().diastolic_dysfunction = v

    @property
    def handgrip_strength(self):
        return self.cardiac.handgrip_strength if self.cardiac else None

    @handgrip_strength.setter
    def handgrip_strength(self, v):
        self._ensure_cardiac().handgrip_strength = v

    @property
    def echo_date(self):
        return self.cardiac.echo_date if self.cardiac else None

    @echo_date.setter
    def echo_date(self, v):
        self._ensure_cardiac().echo_date = v

    @property
    def echo_report(self):
        return self.cardiac.echo_report if self.cardiac else None

    @echo_report.setter
    def echo_report(self, v):
        self._ensure_cardiac().echo_report = v

    # outcomes
    def _ensure_outcomes(self):
        if self.outcomes is None:
            self.outcomes = PatientOutcomes()
        return self.outcomes

    @property
    def current_survival_status(self):
        return self.outcomes.current_survival_status if self.outcomes else None

    @current_survival_status.setter
    def current_survival_status(self, v):
        self._ensure_outcomes().current_survival_status = v

    @property
    def date_of_death(self):
        return self.outcomes.date_of_death if self.outcomes else None

    @date_of_death.setter
    def date_of_death(self, v):
        self._ensure_outcomes().date_of_death = v

    @property
    def primary_cause_of_death(self):
        return self.outcomes.primary_cause_of_death if self.outcomes else None

    @primary_cause_of_death.setter
    def primary_cause_of_death(self, v):
        self._ensure_outcomes().primary_cause_of_death = v

    @property
    def date_of_transplant(self):
        return self.outcomes.date_of_transplant if self.outcomes else None

    @date_of_transplant.setter
    def date_of_transplant(self, v):
        self._ensure_outcomes().date_of_transplant = v

    @property
    def withdrawal_from_dialysis(self):
        return self.outcomes.withdrawal_from_dialysis if self.outcomes else None

    @withdrawal_from_dialysis.setter
    def withdrawal_from_dialysis(self, v):
        self._ensure_outcomes().withdrawal_from_dialysis = v

    @property
    def withdrawal_date(self):
        return self.outcomes.withdrawal_date if self.outcomes else None

    @withdrawal_date.setter
    def withdrawal_date(self, v):
        self._ensure_outcomes().withdrawal_date = v

    @property
    def withdrawal_reason(self):
        return self.outcomes.withdrawal_reason if self.outcomes else None

    @withdrawal_reason.setter
    def withdrawal_reason(self, v):
        self._ensure_outcomes().withdrawal_reason = v

    @property
    def withdrawal_clinician(self):
        return self.outcomes.withdrawal_clinician if self.outcomes else None

    @withdrawal_clinician.setter
    def withdrawal_clinician(self, v):
        self._ensure_outcomes().withdrawal_clinician = v

    @property
    def date_facility_transfer(self):
        return self.outcomes.date_facility_transfer if self.outcomes else None

    @date_facility_transfer.setter
    def date_facility_transfer(self, v):
        self._ensure_outcomes().date_facility_transfer = v


class PatientReminder(Base):
    __tablename__ = "patient_reminders"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    reminder_date = Column(Date, nullable=False)
    message = Column(Text, nullable=False)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="reminders")


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String, unique=True, index=True, nullable=False)
    full_name       = Column(String)
    hashed_password = Column(String, nullable=False)
    role            = Column(String, default="staff")  # admin / doctor / staff
    is_active       = Column(Boolean, default=True)
    last_login      = Column(DateTime)
    created_at      = Column(DateTime, default=datetime.utcnow)
    # TOTP MFA — required for admin and doctor roles.
    mfa_secret      = Column(String, nullable=True)
    mfa_enabled     = Column(Boolean, default=False, nullable=False)


class MonthlyRecord(Base):
    """Monthly aggregate clinical record — one row per patient per calendar month.
    Captures laboratory results, medication prescriptions, and clinical summaries.
    Per-session procedural data lives in SessionRecord."""
    __tablename__ = "monthly_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    record_month = Column(String, nullable=False)    # YYYY-MM e.g. "2026-04"
    timestamp = Column(DateTime, default=datetime.utcnow)
    entered_by = Column(String)

    # Composite index and unique constraint for data integrity
    __table_args__ = (
        Index('ix_monthly_patient_month', 'patient_id', 'record_month'),
        UniqueConstraint('patient_id', 'record_month', name='uq_patient_month'),
    )



    # ── Fluid & Weight ────────────────────────────────────────────────────────
    idwg = Column(Float)                     # Interdialytic Weight Gain — kg (monthly worst/avg)
    target_dry_weight = Column(Float)        # kg — TargetDryWeight
    last_prehd_weight = Column(Float)        # kg — most recent pre-HD body weight this month
    residual_urine_output = Column(Float)    # mL/24h — ResidualUrineOutputVolume

    # ── Dialysis Adequacy ─────────────────────────────────────────────────────
    urr = Column(Float)                      # Urea Reduction Ratio %
    single_pool_ktv = Column(Float)          # spKt/V — SinglePoolKtV
    equilibrated_ktv = Column(Float)         # eKt/V — EquilibratedKtV
    npcr = Column(Float)                     # normalized Protein Catabolic Rate (g/kg/day)
    ufr = Column(Float)                      # Ultrafiltration Rate (mL/kg/hr)
    pre_dialysis_urea = Column(Float)        # mg/dL — PreDialysisUrea
    post_dialysis_urea = Column(Float)       # mg/dL — PostDialysisUrea
    serum_creatinine = Column(Float)         # mg/dL — SerumCreatinine
    krcrw = Column(Float)                    # mL/min — Residual Kidney Water Clearance
    krcr = Column(Float)                     # mL/min — Corrected Residual Kidney Clearance

    # ── Anemia & ESA ─────────────────────────────────────────────────────────
    hb = Column(Float)                       # g/dL — Hemoglobin
    esa_type = Column(String)                # Epoetin / Darbepoetin / Mircera / Desidustat — ESAPrescribedType
    epo_mircera_dose = Column(String)        # Dose + frequency string (e.g. "EPO 4000u TIW")
    epo_weekly_units = Column(Float)         # Computed weekly IU equivalent — ESADose
    desidustat_dose = Column(String)         # Oxemia tablet dose

    # ── Iron Panel ────────────────────────────────────────────────────────────
    serum_ferritin = Column(Float)           # ng/mL — SerumFerritin
    tsat = Column(Float)                     # % — TransferrinSaturation
    serum_iron = Column(Float)               # µg/dL — SerumIron
    tibc = Column(Float)                     # µg/dL — TotalIronBindingCapacity
    iv_iron_product = Column(String)         # Ferric Carboxymaltose / Iron Sucrose / FCM — IVIronProduct
    iv_iron_dose = Column(Float)             # mg — dose given on that date
    iv_iron_date = Column(Date)              # date IV iron was administered

    # ── Mineral Metabolism ────────────────────────────────────────────────────
    calcium = Column(Float)                  # mg/dL uncorrected — SerumCalcium
    phosphorus = Column(Float)               # mg/dL — SerumPhosphorus
    alkaline_phosphate = Column(Float)       # IU/L
    ipth = Column(Float)                     # pg/mL — IntactParathyroidHormone
    vit_d = Column(Float)                    # ng/mL — 25HydroxyvitaminD
    vitamin_d_analog_dose = Column(String)   # e.g. "Calcitriol 0.25mcg TIW" — VitaminDAnalogDose
    phosphate_binder_type = Column(String)   # Calcium Carbonate / Sevelamer / Lanthanum — PhosphateBinderType
    pb_strength = Column(Float)              # Individual tablet strength (e.g. 800)
    phosphate_binder_dose_mg = Column(Float) # Total daily mg (e.g. 2400)
    phosphate_binder_freq = Column(String)    # OD / BD / TDS / QID

    # ── Electrolytes & Acid-Base ──────────────────────────────────────────────
    serum_sodium = Column(Float)             # mEq/L — SerumSodium
    serum_potassium = Column(Float)          # mEq/L — SerumPotassium
    serum_bicarbonate = Column(Float)        # mEq/L — SerumBicarbonate
    serum_uric_acid = Column(Float)          # mg/dL — SerumUricAcid

    # ── Nutrition ─────────────────────────────────────────────────────────────
    albumin = Column(Float)                  # g/dL — SerumAlbumin
    prealbumin = Column(Float)               # mg/dL
    sga_score = Column(String)               # SGA/MIS assessment (e.g. "Severe")
    mis_score = Column(Integer)              # Malnutrition-Inflammation Score (0-30)
    av_daily_calories = Column(Float)        # kcal/day
    av_daily_protein = Column(Float)         # g/kg/day

    # ── Lipids ────────────────────────────────────────────────────────────────
    total_cholesterol = Column(Float)        # mg/dL — TotalCholesterol
    ldl_cholesterol = Column(Float)          # mg/dL — LDLCholesterol

    # ── Haematology ───────────────────────────────────────────────────────────
    wbc_count = Column(Float)                # ×10³/µL — WhiteBloodCellCount
    neutrophil_count = Column(Float)         # % or abs
    lymphocyte_count = Column(Float)         # % or abs
    platelet_count = Column(Float)           # ×10³/µL — PlateletCount
    hba1c = Column(Float)                    # % — HbA1c

    # ── Liver Function ────────────────────────────────────────────────────────
    ast = Column(Float)                      # IU/L
    alt = Column(Float)                      # IU/L

    # ── Inflammatory Marker ───────────────────────────────────────────────────
    crp = Column(Float)                      # mg/L — CReactiveProtein
    il6 = Column(Float)                      # pg/mL - Interleukin 6
    tnf_alpha = Column(Float)                # pg/mL - Tumor Necrosis Factor alpha

    # ── Medications Summary ───────────────────────────────────────────────────
    antihypertensive_count = Column(Integer) # Number of antihypertensive classes — AntihypertensiveClassCount
    antihypertensive_details = Column(Text)  # Stores JSON or formatted string of specific names, doses, freqs

    # ── Vitals (monthly representative) ──────────────────────────────────────
    bp_sys = Column(Float)                   # Systolic BP mmHg — monthly representative
    bp_dia = Column(Float)                   # Diastolic BP mmHg
    troponin_i = Column(Float)               # ng/mL
    nt_probnp = Column(Float)                # pg/mL
    ejection_fraction = Column(Float)        # %
    diastolic_dysfunction = Column(String)   # Grade I / II / III
    echo_date = Column(Date)                 # Date of Echocardiography
    access_type = Column(String)             # AVF / Permacath — monthly access status

    # ── Quality of Life ───────────────────────────────────────────────────────
    hrqol_score = Column(Float)              # KDQOL / SF-36 score — HealthRelatedQualityOfLifeScore

    # ── Hospitalisation (this month) ─────────────────────────────────────────
    hospitalization_this_month = Column(Boolean)
    hospitalization_date = Column(Date)      # DateOfHospitalAdmission
    hospitalization_diagnosis = Column(Text)   # Clinical diagnosis string
    hospitalization_icd_code = Column(String)  # ICD-10 code — ICDReasonForHospitalization
    hospitalization_icd_diagnosis = Column(Text) # Official ICD-10 diagnosis description
    hospitalization_details = Column(Text)     # JSON array of {date, diagnosis, icd_code, icd_diagnosis}

    # ── Blood Transfusion ─────────────────────────────────────────────────────
    blood_transfusion_units = Column(Integer)   # PRBC units transfused this month (1 unit ≈ +1 g/dL Hb)
    transfusion_date = Column(String)           # YYYY-MM-DD of most recent transfusion this month

    # ── Clinical Notes ────────────────────────────────────────────────────────
    issues = Column(Text)
    doctor_notes = Column(Text)
    reviewed_by = Column(String)
    reviewed_at = Column(DateTime)

    # ── Provenance ────────────────────────────────────────────────────────────
    # data_observed_at: when the labs/measurements were actually collected (clinician-supplied).
    # data_entered_at:  when this record was persisted to the DB (system-assigned).
    # The gap between these flags retrospective entry — important for ML feature freshness.
    data_observed_at = Column(DateTime, nullable=True)
    data_entered_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    # feature_vector_hash: SHA-256 of the sorted JSON feature vector at prediction time.
    # Back-filled by the ML pipeline; binds each MLPrediction to the exact input snapshot.
    feature_vector_hash = Column(String(64), nullable=True, index=True)

    # dynamic_data: JSONB payload for user-defined variables (replaces variable_values EAV table).
    # Shape: {"crp": {"v": 8.5, "by": "staff"}, "facit_fatigue": {"v": 28, "by": "staff"}}
    # Populated by migration 0004; GIN-indexed for cohort predicates.
    dynamic_data = Column(JSONB, nullable=True)

    patient = relationship("Patient", back_populates="records")


class SustainabilityRecord(Base):
    """Monthly unit-wide sustainability data for Carbon Footprint calculation."""
    __tablename__ = "sustainability_records"

    id = Column(Integer, primary_key=True, index=True)
    record_month = Column(String, unique=True, nullable=False) # YYYY-MM

    # Unit-wide inputs for the month
    electricity_kwh = Column(Float, default=0)
    water_m3 = Column(Float, default=0)
    biomedical_waste_kg = Column(Float, default=0)
    general_waste_kg = Column(Float, default=0)

    # Optional overrides if the unit wants to be more precise
    total_sessions_override = Column(Integer) # If null, use sum of MonthlyRecords
    avg_transport_dist_km = Column(Float, default=15) # Avg round trip per patient

    # Metadata
    timestamp = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String)


class DryWeightAssessment(Base):
    """Specialized assessment for determining true Dry Weight."""
    __tablename__ = "dry_weight_assessments"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    assessment_date = Column(Date, nullable=False)

    # ── Assessment Tools ──────────────────────────────────────────────────────
    ivc_diameter_max = Column(Float)         # mm
    ivc_collapsibility_index = Column(Float) # %
    bia_fluid_overload_litres = Column(Float) # Litres (+/-)
    bia_overhydration_percent = Column(Float) # %
    bia_total_body_water = Column(Float)      # Litres
    bia_phase_angle = Column(Float)          # degrees
    nt_probnp = Column(Float)                # pg/mL

    # ── Clinical Observations ─────────────────────────────────────────────────
    edema_status = Column(String)            # None / Trace / Pitting
    bp_lability = Column(String)             # Stable / High Lability / Low Lability

    # ── Decision ─────────────────────────────────────────────────────────────
    recommended_dry_weight = Column(Float)   # kg
    assessment_notes = Column(Text)

    # Metadata
    timestamp = Column(DateTime, default=datetime.utcnow)
    performed_by = Column(String)

    patient = relationship("Patient", back_populates="dry_weight_assessments")


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    alert_type = Column(String)          # email / whatsapp
    alert_reason = Column(String)        # e.g. "Hb drop alert"
    sent_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String)              # sent / failed
    message_preview = Column(Text)


class SessionRecord(Base):
    """Per-HD-session clinical record — one row per dialysis session (typically 2–3×/week).
    Linked to MonthlyRecord via record_month for monthly aggregate analytics.
    BMI is computed dynamically: weight_pre / (Patient.height/100)²."""
    __tablename__ = "session_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_date = Column(Date, nullable=False)     # Exact session date
    record_month = Column(String, nullable=False)   # YYYY-MM — joins to MonthlyRecord
    entered_by = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # ── Session Identity ──────────────────────────────────────────────────────
    provider = Column(String)            # Attending physician / nurse
    dialysis_type = Column(String)       # HD / HDF / Online-HDF for this session

    # ── Treatment Duration ────────────────────────────────────────────────────
    scheduled_treatment_duration = Column(Float)   # Prescribed minutes — ScheduledTreatmentDuration
    duration_hours = Column(Integer)               # Actual hours — ActualTreatmentDuration
    duration_minutes = Column(Integer)             # Actual minutes

    # ── Weight & Fluid Balance ────────────────────────────────────────────────
    weight_pre = Column(Float)           # kg — PreDialysisWeight
    weight_post = Column(Float)          # kg — PostDialysisWeight

    # ── Ultrafiltration ───────────────────────────────────────────────────────
    uf_volume = Column(Float)            # mL — PrescribedUltrafiltrationVolume
    actual_uf_volume = Column(Float)     # mL — ActualUltrafiltrationVolume
    uf_rate = Column(Float)              # mL/hr — UltrafiltrationRate (storable for quick query)

    # ── Blood Pressure Monitoring ─────────────────────────────────────────────
    bp_pre_sys = Column(Float)           # mmHg — Before session
    bp_pre_dia = Column(Float)
    bp_during_sys = Column(Float)        # mmHg — Representative during session
    bp_during_dia = Column(Float)
    bp_peak_sys = Column(Float)          # mmHg — Highest recorded
    bp_peak_dia = Column(Float)
    bp_nadir_sys = Column(Float)         # mmHg — Lowest recorded (IDH surveillance)
    bp_nadir_dia = Column(Float)
    bp_post_sys = Column(Float)          # mmHg — After session
    bp_post_dia = Column(Float)

    # ── Machine Prescription ─────────────────────────────────────────────────
    blood_flow_rate = Column(Float)          # mL/min — PrescribedBloodFlowRate
    actual_blood_flow_rate = Column(Float)   # mL/min — ActualBloodFlowRate
    dialysate_flow = Column(Float)           # mL/min — PrescribedDialysateFlowRate
    dialysate_flow_direction = Column(String)  # Countercurrent / Concurrent — DialysateFlowDirection
    dialyzer_type = Column(String)           # e.g. FX80 — DialyzerModel
    dialyzer_surface_area = Column(Float)    # m²
    dialyzer_membrane_flux = Column(String)  # High / Low — DialyzerMembraneFlux

    # ── Dialysate Composition ─────────────────────────────────────────────────
    dialysate_buffer = Column(String)           # Bicarbonate / Acetate — DialysateBufferType
    dialysate_sodium = Column(Float)            # mEq/L — DialysateSodiumConcentration
    dialysate_potassium = Column(Float)         # mEq/L — DialysatePotassiumConcentration
    dialysate_calcium = Column(Float)           # mEq/L — DialysateCalciumConcentration
    dialysate_bicarbonate = Column(Float)       # mEq/L — DialysateBicarbonateConcentration
    dialysate_temperature = Column(Float)       # °C — DialysateTemperature

    # ── Circuit Pressures ─────────────────────────────────────────────────────
    arterial_line_pressure = Column(Float)   # mmHg — ArterialLinePressure
    venous_line_pressure = Column(Float)     # mmHg — VenousLinePressure
    transmembrane_pressure = Column(Float)   # mmHg — TransmembranePressure

    # ── Anticoagulation ───────────────────────────────────────────────────────
    anticoagulation = Column(String)         # Heparin / Argatroban / Citrate / None — AnticoagulationType
    anticoagulation_dose = Column(Float)     # IU (heparin) or mg — AnticoagulationDose

    # ── Vascular Access (session-level) ──────────────────────────────────────
    access_location = Column(String)         # Right IJV / Left BC AVF etc. — AccessAnatomicalLocation
    access_condition = Column(String)        # Good / Fair / Poor / Infected — VascularAccessCondition
    needle_gauge = Column(String)            # 14G / 15G / 16G — NeedleGauge
    cannulation_technique = Column(String)   # Rope-ladder / Buttonhole / Area — CannulationTechnique
    vascular_interventions = Column(Text)    # Angioplasty / Declot etc. performed this session
    access_complications = Column(Text)      # e.g. "Poor thrill, haematoma"

    # ── Access Recirculation (Two-Needle Urea Method) ─────────────────────────
    urea_peripheral_s = Column(Float)
    urea_arterial_a = Column(Float)
    urea_venous_v = Column(Float)
    access_recirculation_percent = Column(Float)
    access_flow_qa = Column(Float)

    # ── Session Medications ───────────────────────────────────────────────────
    medications_administered = Column(Text)

    # ── Intradialytic Events (structured booleans for analytics) ─────────────
    idh_episode = Column(Boolean)
    idh_hypertension = Column(Boolean)

    # ── Respiratory Symptoms (Occult Overload surveillance) ──────────────────
    pre_hd_dyspnea_likert = Column(Integer)
    post_hd_dyspnea_likert = Column(Integer)

    muscle_cramps = Column(Boolean)
    nausea_vomiting = Column(Boolean)
    chest_pain = Column(Boolean)
    arrhythmia = Column(Boolean)
    early_termination = Column(Boolean)
    reason_early_termination = Column(String)
    intradialytic_exercise_mins = Column(Integer)
    intradialytic_meals_eaten = Column(Boolean)

    # ── General Complications ─────────────────────────────────────────────────
    complications_occurred = Column(Boolean, default=False)
    complications_description = Column(Text)
    complications_management = Column(Text)

    # ── Adherence & Flags ────────────────────────────────────────────────────
    dialysis_adherence = Column(String)
    doctor_concerns = Column(Text)
    next_appointment_id = Column(String)

    # ── Emergency / Extra Sessions ──────────────────────────────────────────
    is_emergency = Column(Boolean, default=False)
    reason_emergency = Column(String)

    # ── Interim Labs (Optional Session-level Labs) ──────────────────────────
    interim_hb = Column(Float)
    interim_k  = Column(Float)
    interim_ca = Column(Float)
    interim_trigger = Column(String)

    patient = relationship("Patient", back_populates="sessions")


class InterimLabRecord(Base):
    """
    Clinically-triggered or ad-hoc laboratory investigations.
    Separated from protocol-driven MonthlyRecord for better ML feature engineering.
    """
    __tablename__ = "interim_lab_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("session_records.id"), nullable=True)
    lab_date = Column(Date, nullable=False)
    record_month = Column(String)             # YYYY-MM for monthly collation

    # Lab Parameters
    parameter = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String)

    # Clinical Context (ML features)
    trigger = Column(String)
    notes = Column(Text)

    entered_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Provenance pair — mirrors MonthlyRecord semantics.
    data_observed_at = Column(DateTime, nullable=True)    # when sample was collected
    data_entered_at  = Column(DateTime, default=datetime.utcnow, nullable=False)  # when row was saved

    __table_args__ = (
        Index('ix_interim_patient_month', 'patient_id', 'record_month'),
    )

    patient = relationship("Patient", back_populates="interim_labs")
    session = relationship("SessionRecord")


class ClinicalEvent(Base):
    """
    A discrete clinical event for a patient on a specific date.
    Used to build the unit-level and per-patient clinical event timeline.
    """
    __tablename__ = "clinical_events"

    id          = Column(Integer, primary_key=True, index=True)
    patient_id  = Column(Integer, ForeignKey("patients.id"), nullable=False)
    event_date  = Column(Date, nullable=False)
    event_type  = Column(String, nullable=False)
    severity    = Column(String, default="Medium")
    notes       = Column(Text)
    created_by  = Column(String)
    created_at  = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="events")


class PatientMealRecord(Base):
    __tablename__ = "patient_meal_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    date = Column(Date, default=lambda: datetime.utcnow().date())
    calories = Column(Float)
    protein = Column(Float)
    meal_type = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="meal_records")


class PatientSymptomReport(Base):
    __tablename__ = "patient_symptom_reports"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("session_records.id"), nullable=True)
    reported_at = Column(DateTime, default=datetime.utcnow)

    # Legacy generic symptoms
    symptoms = Column(Text)
    severity = Column(Integer)
    notes = Column(Text)

    # ── Post-Dialysis Syndrome (PDS) Specifics ───────────────────────────────
    dialysis_recovery_time_mins = Column(Integer)

    # SONG-HD Fatigue Scale
    tiredness_score = Column(Integer)
    energy_level_score = Column(Integer)
    daily_activity_impact = Column(Integer)

    # Mood & Cognition (EMA)
    cognitive_alertness = Column(String)
    post_hd_mood = Column(String)
    sleepiness_severity = Column(Integer)

    # Impact Dimensions
    missed_social_or_work_event = Column(Boolean)

    patient = relationship("Patient", back_populates="symptom_reports")
    session = relationship("SessionRecord")


class ResearchProject(Base):
    __tablename__ = "research_projects"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    status = Column(String, default="Active")
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship("ResearchRecord", back_populates="project", cascade="all, delete-orphan")

class ResearchRecord(Base):
    __tablename__ = "research_records"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("research_projects.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    test_type = Column(String, nullable=False)
    test_date = Column(Date, default=lambda: datetime.utcnow().date())
    data = Column(Text) # JSON string for flexible specialized test metrics
    notes = Column(Text)
    entered_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("ResearchProject", back_populates="records")
    patient = relationship("Patient", back_populates="research_records")


class HospitalisationEvent(Base):
    """Structured longitudinal hospitalisation record — one row per admission episode."""
    __tablename__ = "hospitalisation_events"

    id              = Column(Integer, primary_key=True, index=True)
    patient_id      = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    admission_date  = Column(Date, nullable=False)
    discharge_date  = Column(Date)
    los_days        = Column(Integer)
    primary_icd     = Column(String)
    primary_diagnosis = Column(String)
    cause_category  = Column(String)
    readmission_within_30d = Column(Boolean, default=False)
    notes           = Column(Text)
    entered_by      = Column(String)
    created_at      = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="hospitalisations")


class AuditLog(Base):
    """Immutable audit trail for all PHI write operations.

    One row per create/update. Append-only — never update or delete rows here.
    actor is the session username; changes is a JSON dict of field → new value.
    patient_id_hash is HMAC-SHA256(patient_id) — use this for analytics/reporting;
    never join audit_logs back to patients via the raw patient_id FK.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String, nullable=False, index=True)
    record_id = Column(Integer, index=True)
    action = Column(String, nullable=False)     # "create" | "update"
    actor = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    changes = Column(Text)                      # JSON — only fields that changed
    patient_id_hash = Column(String(64), nullable=True, index=True)  # HMAC-SHA256(patient_id)


class MLPrediction(Base):
    """One row per model inference call.

    input_feature_hash is SHA-256 of the sorted feature vector JSON so identical
    inputs produce the same hash (dedup / reproducibility checks).
    observed_outcome is back-filled by the weekly MLOps job once the next
    monthly record is entered (hospitalization_this_month of the following month).
    patient_id_hash is HMAC-SHA256(patient_id) — use for cross-model analytics
    without joining back to the patients table.
    """
    __tablename__ = "ml_predictions"

    id                  = Column(Integer, primary_key=True, index=True)
    patient_id          = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    patient_id_hash     = Column(String(64), nullable=True, index=True)   # HMAC-SHA256(patient_id)
    model_name          = Column(String, nullable=False, index=True)   # "deterioration_v1", "mortality_1yr", …
    model_version       = Column(String, nullable=True)                # SHA-256 of .pkl, or trained_at timestamp
    input_feature_hash  = Column(String(64), nullable=False, index=True)
    features_json       = Column(Text, nullable=False)                 # JSON of feature name → value
    prediction_score    = Column(Float, nullable=False)                # raw probability in [0, 1]
    predicted_class     = Column(Integer, nullable=True)               # 1 if score >= threshold, else 0
    observed_outcome    = Column(Integer, nullable=True)               # back-filled: 1=event, 0=no event, NULL=pending
    prediction_month    = Column(String(7), nullable=True)             # "YYYY-MM" the prediction was made for
    created_at          = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    patient = relationship("Patient", foreign_keys=[patient_id])


class MLModelMetrics(Base):
    """Nightly aggregate performance metrics per model.

    Computed by the Celery MLOps task every night for the trailing 90-day window.
    calibration_slope near 1.0 means the model is well-calibrated; drift is
    flagged when |slope - 1.0| > 0.15.
    """
    __tablename__ = "ml_model_metrics"

    id                 = Column(Integer, primary_key=True, index=True)
    model_name         = Column(String, nullable=False, index=True)
    week_start         = Column(String(10), nullable=False)            # ISO date "YYYY-MM-DD" (run date)
    n_predictions      = Column(Integer, nullable=False, default=0)
    n_with_outcome     = Column(Integer, nullable=False, default=0)
    pr_auc             = Column(Float, nullable=True)
    brier_score        = Column(Float, nullable=True)
    calibration_slope  = Column(Float, nullable=True)
    calibration_intercept = Column(Float, nullable=True)
    roc_auc            = Column(Float, nullable=True)
    drift_flagged      = Column(Boolean, default=False)
    drift_detail       = Column(Text, nullable=True)                   # JSON explanation string
    computed_at        = Column(DateTime, default=datetime.utcnow, nullable=False)


class ModelArtifact(Base):
    """Registry of trained ML model artifacts.

    One row per training run.  Inference is refused when no row exists for a
    given model_name — this prevents stale or unregistered pkl files from being
    silently used in production.
    training_data_hash: SHA-256 of the sorted feature-matrix JSON used for training,
      so the exact dataset can be reconstructed for audit or retraining.
    feature_schema_json: ordered list of feature names — must match the inference
      path to catch schema drift before it produces silent prediction errors.
    """
    __tablename__ = "model_artifacts"

    id                  = Column(Integer, primary_key=True, index=True)
    model_name          = Column(String, nullable=False, index=True)   # e.g. "deterioration_v1"
    version             = Column(String, nullable=False)               # ISO timestamp of training run
    trained_at          = Column(DateTime, nullable=False)
    training_data_hash  = Column(String(64), nullable=True)            # SHA-256 of training matrix JSON
    metrics_json        = Column(Text, nullable=True)                  # JSON: cv_auc, n_samples, …
    feature_schema_json = Column(Text, nullable=True)                  # JSON array of feature names
    artifact_path       = Column(String, nullable=True)                # relative path to .joblib file
    created_at          = Column(DateTime, default=datetime.utcnow, nullable=False)


class ClinicalOverrideLog(Base):
    """Logs when a clinician disagrees with a model prediction.

    This is the single most valuable retraining signal in the system: it marks
    cases where the model and clinical judgement diverge.  Each row links back
    to the MLPrediction that was overridden and records the clinician's decision
    and free-text rationale.
    override_direction: 'higher_risk' | 'lower_risk' | 'agree_but_act_differently'
    """
    __tablename__ = "clinical_override_logs"

    id                  = Column(Integer, primary_key=True, index=True)
    patient_id          = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    ml_prediction_id    = Column(Integer, ForeignKey("ml_predictions.id"), nullable=True, index=True)
    model_name          = Column(String, nullable=False, index=True)
    predicted_score     = Column(Float, nullable=True)                 # model's raw probability
    predicted_class     = Column(Integer, nullable=True)               # 1=high risk, 0=low risk
    override_direction  = Column(String, nullable=False)               # higher_risk | lower_risk | agree_but_act_differently
    clinician_decision  = Column(String, nullable=True)                # free-text: what was actually done
    override_reason     = Column(Text, nullable=True)                  # free-text clinical rationale
    clinician_id        = Column(String, nullable=True)                # session username of submitter
    override_at         = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient        = relationship("Patient", foreign_keys=[patient_id])
    ml_prediction  = relationship("MLPrediction", foreign_keys=[ml_prediction_id])


class PatientFeatureSnapshot(Base):
    """Materialized feature store — one row per (patient, month).

    Populated nightly by task_refresh_feature_snapshots (tasks.py).
    ml_risk.py reads from here instead of recomputing features per request,
    which gives:
      • Inference latency: O(1) lookup vs O(N joins)
      • Training/serving parity: training sees the same feature_vector that
        inference used at that point in time
      • Audit surface: clinicians can see exactly what the model received
        via the /api/v1/patients/{id}/feature-history endpoint
    """
    __tablename__ = "patient_feature_snapshot"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    patient_id     = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    as_of_month    = Column(String(7), nullable=False)    # YYYY-MM
    feature_vector = Column(JSONB, nullable=False)
    feature_hash   = Column(String(64), nullable=True)    # SHA-256 of feature_vector
    model_version  = Column(String(32), nullable=True)    # matches manifest.json "version"
    stale          = Column(Boolean, nullable=False, default=False)
    computed_at    = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("patient_id", "as_of_month", name="uq_feature_snapshot_patient_month"),
    )

    patient = relationship("Patient", foreign_keys=[patient_id])


def to_dict(obj):
    """Serialize SQLAlchemy model to dictionary, skipping internal state and relationships."""
    if not obj:
        return None
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
