import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Date, DateTime, Text, ForeignKey, Index, UniqueConstraint
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
    native_kidney_biopsy_date = Column(Date)
    native_kidney_biopsy_report = Column(Text)

    # ── Structured Comorbidities ──────────────────────────────────────────────
    dm_status = Column(String)           # None / Type 1 / Type 2 / Secondary
    dm_end_organ_damage = Column(Boolean)# Diabetes with end-organ damage
    htn_status = Column(Boolean)         # HypertensionStatus
    cad_status = Column(Boolean)         # CoronaryArteryDiseaseStatus (used for MI)
    chf_status = Column(Boolean)         # CongestiveHeartFailureStatus
    history_of_stroke = Column(Boolean)  # HistoryOfStroke (used for CVA/TIA)
    history_of_pvd = Column(Boolean)     # Peripheral Vascular Disease
    history_of_dementia = Column(Boolean)# Dementia
    history_of_cpd = Column(Boolean)     # Chronic Pulmonary Disease
    history_of_ctd = Column(Boolean)     # Connective Tissue Disease
    history_of_pud = Column(Boolean)     # Peptic Ulcer Disease
    liver_disease = Column(String)       # None / Mild / Moderate to severe
    hemiplegia = Column(Boolean)         # Hemiplegia
    solid_tumor = Column(String)         # None / Localized / Metastatic
    leukemia = Column(Boolean)           # Leukemia
    lymphoma = Column(Boolean)           # Lymphoma
    smoking_status = Column(String)      # Never / Ex-smoker / Current
    alcohol_consumption = Column(String) # None / Occasional / Regular
    charlson_comorbidity_index = Column(Integer)  # Calculated CCI score
    comorbidities = Column(Text)         # Free-text supplementary comorbidity notes
    drug_allergies = Column(String)      # NIL or list of known drug allergies
    clinical_background = Column(Text)   # POMR chronological history

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
    diastolic_dysfunction = Column(String)           # Grade I / II / III or None
    handgrip_strength = Column(Float)                # kg — objective marker for frailty/sarcopenia
    echo_date = Column(Date)                 # Date of 2D Echo
    echo_report = Column(Text)               # Detailed Echo findings

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

    login_username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    records = relationship("MonthlyRecord", back_populates="patient", cascade="all, delete-orphan")
    sessions = relationship("SessionRecord", back_populates="patient", cascade="all, delete-orphan")
    interim_labs = relationship("InterimLabRecord", back_populates="patient", cascade="all, delete-orphan")
    meal_records = relationship("PatientMealRecord", back_populates="patient", cascade="all, delete-orphan")
    symptom_reports = relationship("PatientSymptomReport", back_populates="patient", cascade="all, delete-orphan")
    reminders = relationship("PatientReminder", back_populates="patient", cascade="all, delete-orphan")
    dry_weight_assessments = relationship("DryWeightAssessment", back_populates="patient", cascade="all, delete-orphan")
    events = relationship("ClinicalEvent", back_populates="patient", cascade="all, delete-orphan")

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

    # ── Clinical Notes ────────────────────────────────────────────────────────
    issues = Column(Text)

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
    
    # ── Access Recirculation (Two-Needle Urea Method) ─────────────────────────
    # Formula: R = (S-A)/(S-V) * 100
    urea_peripheral_s = Column(Float)        # S: Systemic Peripheral Urea
    urea_arterial_a = Column(Float)          # A: Predialyzer Arterial Urea
    urea_venous_v = Column(Float)            # V: Postdialyzer Venous Urea
    access_recirculation_percent = Column(Float) # Calculated result (%)
    access_flow_qa = Column(Float)           # Qa: Access Flow (mL/min) - KDOQI thresholds

    # ── Session Medications ───────────────────────────────────────────────────
    medications_administered = Column(Text)  # Free text: "EPO 4000u SC, IV Iron 100mg"

    # ── Intradialytic Events (structured booleans for analytics) ─────────────
    idh_episode = Column(Boolean)            # EpisodeOfIntradialyticHypotension (SBP drop >20 or <90)
    idh_hypertension = Column(Boolean)       # EpisodeOfIntradialyticHypertension

    # ── Respiratory Symptoms (Occult Overload surveillance) ──────────────────
    pre_hd_dyspnea_likert = Column(Integer)  # 1-5 (1=None, 5=Severe) - 1 day prior
    post_hd_dyspnea_likert = Column(Integer) # 1-5 (1=None, 5=Severe)

    muscle_cramps = Column(Boolean)          # MuscleCrampsSymptom
    nausea_vomiting = Column(Boolean)        # NauseaVomitingSymptom
    chest_pain = Column(Boolean)             # ChestPainSymptom
    arrhythmia = Column(Boolean)             # ArrhythmiaEvent
    early_termination = Column(Boolean)      # EarlySessionTerminationStatus
    reason_early_termination = Column(String)  # ReasonForEarlyTermination
    intradialytic_exercise_mins = Column(Integer)  # PDS mitigating factor
    intradialytic_meals_eaten = Column(Boolean)    # PDS mitigating factor (nutritional)

    # ── General Complications ─────────────────────────────────────────────────
    complications_occurred = Column(Boolean, default=False)
    complications_description = Column(Text)
    complications_management = Column(Text)

    # ── Adherence & Flags ────────────────────────────────────────────────────
    dialysis_adherence = Column(String)      # e.g. "Missed 1 session this month"
    doctor_concerns = Column(Text)           # Flagged for reviewing physician
    next_appointment_id = Column(String)

    # ── Emergency / Extra Sessions ──────────────────────────────────────────
    is_emergency = Column(Boolean, default=False)
    reason_emergency = Column(String)        # Fluid Overload / Hyperkalemia / Dyspnea / Other

    # ── Interim Labs (Optional Session-level Labs) ──────────────────────────
    interim_hb = Column(Float)           # g/dL — Automated promotion to InterimLabRecord
    interim_k  = Column(Float)           # mEq/L
    interim_ca = Column(Float)           # mg/dL
    interim_trigger = Column(String)     # Dropdown-matching trigger

    patient = relationship("Patient", back_populates="sessions")


class InterimLabRecord(Base):
    """
    Clinically-triggered or ad-hoc laboratory investigations.
    Separated from protocol-driven MonthlyRecord for better ML feature engineering.
    """
    __tablename__ = "interim_lab_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("session_records.id"), nullable=True) # Linked if entered via session
    lab_date = Column(Date, nullable=False)
    record_month = Column(String)             # YYYY-MM for monthly collation
    
    # Lab Parameters
    parameter = Column(String, nullable=False) # hb / potassium / calcium / phosphorus / crp
    value = Column(Float, nullable=False)
    unit = Column(String)
    
    # Clinical Context (ML features)
    trigger = Column(String)                   # Symptomatic / Post-transfusion / Post-Medication / etc.
    notes = Column(Text)
    
    entered_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Composite index for performance on interim lab lookups
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
    event_type  = Column(String, nullable=False)   # Hospitalization / Access Thrombosis / …
    severity    = Column(String, default="Medium") # Low / Medium / High / Critical
    notes       = Column(Text)
    created_by  = Column(String)
    created_at  = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="events")


class PatientMealRecord(Base):
    __tablename__ = "patient_meal_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    date = Column(Date, default=lambda: datetime.utcnow().date())
    calories = Column(Float)   # kcal
    protein = Column(Float)    # grams
    meal_type = Column(String) # Breakfast, Lunch, Dinner, Snack
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="meal_records")


class PatientSymptomReport(Base):
    __tablename__ = "patient_symptom_reports"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("session_records.id"), nullable=True) # Linked to session if EMA
    reported_at = Column(DateTime, default=datetime.utcnow)
    
    # Legacy generic symptoms
    symptoms = Column(Text)   # comma-separated list e.g. "cramping,fatigue"
    severity = Column(Integer)  # 1–5
    notes = Column(Text)
    
    # ── Post-Dialysis Syndrome (PDS) Specifics ───────────────────────────────
    dialysis_recovery_time_mins = Column(Integer)  # DRT in minutes
    
    # SONG-HD Fatigue Scale
    tiredness_score = Column(Integer)        # 1-10
    energy_level_score = Column(Integer)     # 1-10
    daily_activity_impact = Column(Integer)  # 1-5
    
    # Mood & Cognition (EMA)
    cognitive_alertness = Column(String)     # Sharp / Slight Brain Fog / Severe Brain Fog
    post_hd_mood = Column(String)            # Positive / Neutral / Negative
    sleepiness_severity = Column(Integer)    # 1-10
    
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
    
    records = relationship("ResearchRecord", back_populates="project")

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
    patient = relationship("Patient")

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
