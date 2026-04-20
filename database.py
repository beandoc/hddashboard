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
    relation = Column(String)            # Next of kin / Guardian name
    relation_type = Column(String)       # Son / Daughter / Spouse / Self
    sex = Column(String)                 # Male / Female / Other
    contact_no = Column(String)
    email = Column(String)
    diagnosis = Column(String)           # Primary clinical diagnosis (legacy/general)
    hd_wef_date = Column(Date)           # HD start date → maps to DateOfDialysisInitiation

    # ── Demographics ──────────────────────────────────────────────────────────
    education_level = Column(String)     # Illiterate / Primary / Secondary / Graduate / Postgraduate
    height = Column(Float)               # cm — used to compute BMI (weight/height² stored dynamically)

    # ── Renal Disease Profile ─────────────────────────────────────────────────
    primary_renal_disease = Column(String)   # Registry canonical: IgAN / FSGS / Hypertensive Nephrosclerosis / DM Nephropathy etc.
    native_kidney_disease = Column(String)   # Alias — same concept, retained for backward compatibility
    date_esrd_diagnosis = Column(Date)       # Date ESRD was formally diagnosed
    native_kidney_biopsy = Column(String)    # Done / Not Done / Inconclusive

    # ── Structured Comorbidities ──────────────────────────────────────────────
    dm_status = Column(String)           # None / Type 1 / Type 2 / Secondary
    htn_status = Column(Boolean)         # HypertensionStatus
    cad_status = Column(Boolean)         # CoronaryArteryDiseaseStatus
    chf_status = Column(Boolean)         # CongestiveHeartFailureStatus
    history_of_stroke = Column(Boolean)  # HistoryOfStroke
    smoking_status = Column(String)      # Never / Ex-smoker / Current
    alcohol_consumption = Column(String) # None / Occasional / Regular
    charlson_comorbidity_index = Column(Integer)  # Calculated CCI score
    comorbidities = Column(Text)         # Free-text supplementary comorbidity notes
    drug_allergies = Column(String)      # NIL or list of known drug allergies

    # ── KRT History ───────────────────────────────────────────────────────────
    dialysis_modality = Column(String)           # Current: HD / HDF / Online-HDF / CAPD / APD
    previous_dialysis_modality = Column(String)  # Legacy field — kept for compatibility
    previous_krt_modality = Column(String)       # Registry standard: PreviousKRTModality (HD / PD / Transplant / None)
    history_of_renal_transplant = Column(Boolean)
    transplant_prospect = Column(String)         # Active / Inactive / Listed / Contraindicated

    # ── Viral Markers (structured — replaces the single viral_markers string) ─
    viral_markers = Column(String)       # Legacy combined string — retained
    viral_hbsag = Column(String)         # Positive / Negative / Not tested
    viral_anti_hcv = Column(String)      # Positive / Negative / Not tested
    viral_hiv = Column(String)           # Positive / Negative / Not tested

    # ── Vaccination Tracking ──────────────────────────────────────────────────
    hep_b_status = Column(String)        # Immune / Non-Immune / In Progress
    hep_b_dose1_date = Column(Date)      # Month 0
    hep_b_dose2_date = Column(Date)      # Month 1
    hep_b_dose3_date = Column(Date)      # Month 2
    hep_b_dose4_date = Column(Date)      # Month 6
    hep_b_titer_date = Column(Date)      # Anti-HBs titer check date
    pcv13_date = Column(Date)            # Pneumococcal PCV13
    ppsv23_date = Column(Date)           # PPSV23 — 2 months after PCV13
    hz_dose1_date = Column(Date)         # Herpes Zoster dose 1
    hz_dose2_date = Column(Date)         # Herpes Zoster dose 2
    influenza_date = Column(Date)        # Influenza (yearly)

    # ── Vascular Access (patient-level, semi-static) ──────────────────────────
    access_type = Column(String)             # AVF / Permacath / TCC / AV Graft
    access_date = Column(Date)               # DateOfAccessCreation
    date_first_cannulation = Column(Date)    # AVF maturation milestone
    history_of_access_thrombosis = Column(Boolean)
    access_intervention_history = Column(Text)  # Historical interventions (angioplasty, declot, etc.)
    catheter_type = Column(String)           # Permcath / Temporary / Quinton — if access is catheter
    catheter_insertion_site = Column(String) # Right IJV / Left IJV / Right Femoral etc.

    # ── Mortality Model Inputs ────────────────────────────────────────────────
    age = Column(Integer)                    # years — required for mortality prediction
    ejection_fraction = Column(Float, default=60.0)  # % — echocardiographic EF; default 60 (normal)

    # ── Weight & Facility ─────────────────────────────────────────────────────
    dry_weight = Column(Float)               # kg — baseline dry weight
    healthcare_facility = Column(String)     # e.g. Command Hospital SC

    # ── HD Schedule ───────────────────────────────────────────────────────────
    hd_frequency = Column(Integer, default=2)   # Sessions per week: 2 or 3
    hd_day_1  = Column(String)                  # Monday … Sunday
    hd_day_2  = Column(String)
    hd_day_3  = Column(String)
    hd_slot_1 = Column(String)                  # Morning / Afternoon
    hd_slot_2 = Column(String)
    hd_slot_3 = Column(String)

    # ── Demographics extras ───────────────────────────────────────────────────
    blood_group = Column(String)                # A+, B-, O+, AB+, etc.

    # ── Outcomes & Status ─────────────────────────────────────────────────────
    current_survival_status = Column(String)     # Active / Deceased / Transferred / Transplanted / Withdrawn
    date_of_death = Column(Date)
    primary_cause_of_death = Column(String)      # Cardiac / Infection / Vascular / Withdrawal / Other
    withdrawal_from_dialysis = Column(Boolean)
    date_facility_transfer = Column(Date)

    # ── Notifications ─────────────────────────────────────────────────────────
    whatsapp_link = Column(String)       # pre-built wa.me/91XXXXXXXXXX
    whatsapp_notify = Column(Boolean, default=True)
    mail_trigger = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    records = relationship("MonthlyRecord", back_populates="patient", cascade="all, delete-orphan")
    sessions = relationship("SessionRecord", back_populates="patient", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="staff")  # admin / staff
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


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

    # ── Fluid & Weight ────────────────────────────────────────────────────────
    idwg = Column(Float)                     # Interdialytic Weight Gain — kg (monthly worst/avg)
    target_dry_weight = Column(Float)        # kg — TargetDryWeight
    last_prehd_weight = Column(Float)        # kg — most recent pre-HD body weight this month
    residual_urine_output = Column(Float)    # mL/24h — ResidualUrineOutputVolume

    # ── Dialysis Adequacy ─────────────────────────────────────────────────────
    urr = Column(Float)                      # Urea Reduction Ratio %
    single_pool_ktv = Column(Float)          # spKt/V — SinglePoolKtV
    equilibrated_ktv = Column(Float)         # eKt/V — EquilibratedKtV
    pre_dialysis_urea = Column(Float)        # mg/dL — PreDialysisUrea
    post_dialysis_urea = Column(Float)       # mg/dL — PostDialysisUrea
    serum_creatinine = Column(Float)         # mg/dL — SerumCreatinine

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

    # ── Electrolytes & Acid-Base ──────────────────────────────────────────────
    serum_sodium = Column(Float)             # mEq/L — SerumSodium
    serum_potassium = Column(Float)          # mEq/L — SerumPotassium
    serum_bicarbonate = Column(Float)        # mEq/L — SerumBicarbonate
    serum_uric_acid = Column(Float)          # mg/dL — SerumUricAcid

    # ── Nutrition ─────────────────────────────────────────────────────────────
    albumin = Column(Float)                  # g/dL — SerumAlbumin
    av_daily_calories = Column(Float)        # kcal/day
    av_daily_protein = Column(Float)         # g/kg/day

    # ── Lipids ────────────────────────────────────────────────────────────────
    total_cholesterol = Column(Float)        # mg/dL — TotalCholesterol
    ldl_cholesterol = Column(Float)          # mg/dL — LDLCholesterol

    # ── Haematology ───────────────────────────────────────────────────────────
    wbc_count = Column(Float)                # ×10³/µL — WhiteBloodCellCount
    platelet_count = Column(Float)           # ×10³/µL — PlateletCount
    hba1c = Column(Float)                    # % — HbA1c

    # ── Liver Function ────────────────────────────────────────────────────────
    ast = Column(Float)                      # IU/L
    alt = Column(Float)                      # IU/L

    # ── Inflammatory Marker ───────────────────────────────────────────────────
    crp = Column(Float)                      # mg/L — CReactiveProtein

    # ── Medications Summary ───────────────────────────────────────────────────
    antihypertensive_count = Column(Integer) # Number of antihypertensive classes — AntihypertensiveClassCount

    # ── Vitals (monthly representative) ──────────────────────────────────────
    bp_sys = Column(Float)                   # Systolic BP mmHg — monthly representative
    access_type = Column(String)             # AVF / Permacath — monthly access status

    # ── Quality of Life ───────────────────────────────────────────────────────
    hrqol_score = Column(Float)              # KDQOL / SF-36 score — HealthRelatedQualityOfLifeScore

    # ── Hospitalisation (this month) ─────────────────────────────────────────
    hospitalization_this_month = Column(Boolean)
    hospitalization_date = Column(Date)      # DateOfHospitalAdmission
    hospitalization_icd_code = Column(String)  # ICD-10 code — ICDReasonForHospitalization

    # ── Clinical Notes ────────────────────────────────────────────────────────
    issues = Column(Text)

    patient = relationship("Patient", back_populates="records")


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
    # IDWG per session: weight_pre − Patient.dry_weight (computed, not stored)
    # BMI per session: weight_pre / (height_m)² (computed, not stored)

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

    # ── Session Medications ───────────────────────────────────────────────────
    medications_administered = Column(Text)  # Free text: "EPO 4000u SC, IV Iron 100mg"

    # ── Intradialytic Events (structured booleans for analytics) ─────────────
    idh_episode = Column(Boolean)            # EpisodeOfIntradialyticHypotension (SBP drop >20 or <90)
    idh_hypertension = Column(Boolean)       # EpisodeOfIntradialyticHypertension
    muscle_cramps = Column(Boolean)          # MuscleCrampsSymptom
    nausea_vomiting = Column(Boolean)        # NauseaVomitingSymptom
    chest_pain = Column(Boolean)             # ChestPainSymptom
    arrhythmia = Column(Boolean)             # ArrhythmiaEvent
    early_termination = Column(Boolean)      # EarlySessionTerminationStatus
    reason_early_termination = Column(String)  # ReasonForEarlyTermination

    # ── General Complications ─────────────────────────────────────────────────
    complications_occurred = Column(Boolean, default=False)
    complications_description = Column(Text)
    complications_management = Column(Text)

    # ── Adherence & Flags ────────────────────────────────────────────────────
    dialysis_adherence = Column(String)      # e.g. "Missed 1 session this month"
    doctor_concerns = Column(Text)           # Flagged for reviewing physician
    next_appointment_id = Column(String)

    patient = relationship("Patient", back_populates="sessions")


class ClinicalEvent(Base):
    """
    A discrete clinical event for a patient on a specific date.
    Used to build the unit-level and per-patient clinical event timeline.
    """
    __tablename__ = "clinical_events"

    id          = Column(Integer, primary_key=True, index=True)
    patient_id  = Column(Integer, ForeignKey("patients.id"), nullable=False)
    event_date  = Column(Date, nullable=False)
    event_type  = Column(String, nullable=False)   # Hospitalization / Access Thrombosis / …
    severity    = Column(String, default="Medium") # Low / Medium / High / Critical
    notes       = Column(Text)
    created_by  = Column(String)
    created_at  = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
