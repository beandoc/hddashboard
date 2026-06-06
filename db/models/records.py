from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, Text,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime

from db.engine import Base


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

    __table_args__ = (
        Index('ix_monthly_patient_month', 'patient_id', 'record_month'),
        # PERF FIX: standalone index for dashboard queries that filter by record_month
        # across ALL patients (no patient_id in WHERE clause). Without this, PostgreSQL
        # must do a full sequential table scan on every dashboard load.
        Index('ix_monthly_record_month_only', 'record_month'),
        UniqueConstraint('patient_id', 'record_month', name='uq_patient_month'),
    )

    # ── Fluid & Weight ────────────────────────────────────────────────────────
    idwg = Column(Float)
    target_dry_weight = Column(Float)
    last_prehd_weight = Column(Float)
    residual_urine_output = Column(Float)

    # ── Dialysis Adequacy ─────────────────────────────────────────────────────
    urr = Column(Float)
    single_pool_ktv = Column(Float)
    equilibrated_ktv = Column(Float)
    npcr = Column(Float)
    ufr = Column(Float)
    pre_dialysis_urea = Column(Float)
    post_dialysis_urea = Column(Float)
    serum_creatinine = Column(Float)
    post_dialysis_creatinine = Column(Float)
    krcrw = Column(Float)
    krcr = Column(Float)

    # ── Anemia & ESA ─────────────────────────────────────────────────────────
    hb = Column(Float)
    hct = Column(Float)
    esa_type = Column(String)
    epo_mircera_dose = Column(String)
    epo_weekly_units = Column(Float)
    desidustat_dose = Column(String)

    # ── Iron Panel ────────────────────────────────────────────────────────────
    serum_ferritin = Column(Float)
    tsat = Column(Float)
    serum_iron = Column(Float)
    tibc = Column(Float)
    iv_iron_product = Column(String)
    iv_iron_dose = Column(Float)
    iv_iron_date = Column(Date)

    # ── Mineral Metabolism ────────────────────────────────────────────────────
    calcium = Column(Float)
    phosphorus = Column(Float)
    alkaline_phosphate = Column(Float)
    ipth = Column(Float)
    vit_d = Column(Float)
    vitamin_d_analog_dose = Column(String)
    phosphate_binder_type = Column(String)
    pb_strength = Column(Float)
    phosphate_binder_dose_mg = Column(Float)
    phosphate_binder_freq = Column(String)
    phosphate_binder_details = Column(Text)

    # ── Electrolytes & Acid-Base ──────────────────────────────────────────────
    serum_sodium = Column(Float)
    serum_potassium = Column(Float)
    serum_bicarbonate = Column(Float)
    serum_uric_acid = Column(Float)

    # ── Nutrition ─────────────────────────────────────────────────────────────
    albumin = Column(Float)
    prealbumin = Column(Float)
    sga_score = Column(String)
    mis_score = Column(Integer)
    av_daily_calories = Column(Float)
    av_daily_protein = Column(Float)

    # ── Lipids ────────────────────────────────────────────────────────────────
    total_cholesterol = Column(Float)
    ldl_cholesterol = Column(Float)

    # ── Haematology ───────────────────────────────────────────────────────────
    wbc_count = Column(Float)
    neutrophil_count = Column(Float)
    lymphocyte_count = Column(Float)
    platelet_count = Column(Float)
    hba1c = Column(Float)
    reticulocyte_count = Column(Float)   # reticulocyte % (normal 0.5–2.5 %)

    # ── Liver Function ────────────────────────────────────────────────────────
    ast = Column(Float)
    alt = Column(Float)

    # ── Inflammatory Marker ───────────────────────────────────────────────────
    crp = Column(Float)
    il6 = Column(Float)
    tnf_alpha = Column(Float)

    # ── Medications Summary ───────────────────────────────────────────────────
    antihypertensive_count = Column(Integer)
    antihypertensive_details = Column(Text)

    # ── Vitals (monthly representative) ──────────────────────────────────────
    bp_sys = Column(Float)
    bp_dia = Column(Float)
    troponin_i = Column(Float)
    nt_probnp = Column(Float)
    ejection_fraction = Column(Float)
    diastolic_dysfunction = Column(String)
    echo_date = Column(Date)
    access_type = Column(String)

    # ── Quality of Life ───────────────────────────────────────────────────────
    hrqol_score = Column(Float)

    # ── Hospitalisation (this month) ─────────────────────────────────────────
    hospitalization_this_month = Column(Boolean)
    hospitalization_date = Column(Date)
    hospitalization_diagnosis = Column(Text)
    hospitalization_icd_code = Column(String)
    hospitalization_icd_diagnosis = Column(Text)
    hospitalization_details = Column(Text)

    # ── Blood Transfusion ─────────────────────────────────────────────────────
    blood_transfusion_units = Column(Integer)
    transfusion_date = Column(String)

    # ── Clinical Notes ────────────────────────────────────────────────────────
    issues = Column(Text)
    doctor_notes = Column(Text)
    reviewed_by = Column(String)
    reviewed_at = Column(DateTime)

    # ── Provenance ────────────────────────────────────────────────────────────
    data_observed_at = Column(DateTime, nullable=True)
    data_entered_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    feature_vector_hash = Column(String(64), nullable=True, index=True)

    # JSONB payload for user-defined variables
    dynamic_data = Column(JSONB, nullable=True)

    patient = relationship("Patient", back_populates="records")


class SustainabilityRecord(Base):
    """Monthly unit-wide sustainability data for Carbon Footprint calculation."""
    __tablename__ = "sustainability_records"

    id = Column(Integer, primary_key=True, index=True)
    record_month = Column(String, unique=True, nullable=False)

    electricity_kwh = Column(Float, default=0)
    water_m3 = Column(Float, default=0)
    biomedical_waste_kg = Column(Float, default=0)
    general_waste_kg = Column(Float, default=0)

    total_sessions_override = Column(Integer)
    avg_transport_dist_km = Column(Float, default=15)

    timestamp = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String)


class DryWeightAssessment(Base):
    """Specialized assessment for determining true Dry Weight."""
    __tablename__ = "dry_weight_assessments"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    assessment_date = Column(Date, nullable=False)

    # ── Assessment Tools ──────────────────────────────────────────────────────
    ivc_diameter_max = Column(Float)
    ivc_collapsibility_index = Column(Float)
    bia_fluid_overload_litres = Column(Float)
    bia_overhydration_percent = Column(Float)
    bia_total_body_water = Column(Float)
    bia_phase_angle = Column(Float)
    nt_probnp = Column(Float)

    # ── Clinical Observations ─────────────────────────────────────────────────
    edema_status = Column(String)
    bp_lability = Column(String)

    # ── Decision ─────────────────────────────────────────────────────────────
    recommended_dry_weight = Column(Float)
    assessment_notes = Column(Text)

    timestamp = Column(DateTime, default=datetime.utcnow)
    performed_by = Column(String)

    patient = relationship("Patient", back_populates="dry_weight_assessments")
