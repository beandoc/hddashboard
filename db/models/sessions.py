from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, Text,
    ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from db.engine import Base


class SessionRecord(Base):
    """Per-HD-session clinical record — one row per dialysis session (typically 2–3×/week).
    Linked to MonthlyRecord via record_month for monthly aggregate analytics.
    BMI is computed dynamically: weight_pre / (Patient.height/100)²."""
    __tablename__ = "session_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_date = Column(Date, nullable=False)
    record_month = Column(String, nullable=False)
    entered_by = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # ── Session Identity ──────────────────────────────────────────────────────
    provider = Column(String)
    dialysis_type = Column(String)

    # ── Treatment Duration ────────────────────────────────────────────────────
    scheduled_treatment_duration = Column(Float)
    duration_hours = Column(Integer)
    duration_minutes = Column(Integer)

    # ── Weight & Fluid Balance ────────────────────────────────────────────────
    weight_pre = Column(Float)
    weight_post = Column(Float)

    # ── Ultrafiltration ───────────────────────────────────────────────────────
    uf_volume = Column(Float)
    actual_uf_volume = Column(Float)
    uf_rate = Column(Float)

    # ── Blood Pressure Monitoring ─────────────────────────────────────────────
    bp_pre_sys = Column(Float)
    bp_pre_dia = Column(Float)
    bp_during_sys = Column(Float)
    bp_during_dia = Column(Float)
    bp_peak_sys = Column(Float)
    bp_peak_dia = Column(Float)
    bp_nadir_sys = Column(Float)
    bp_nadir_dia = Column(Float)
    bp_post_sys = Column(Float)
    bp_post_dia = Column(Float)

    # ── Machine Prescription ─────────────────────────────────────────────────
    blood_flow_rate = Column(Float)
    actual_blood_flow_rate = Column(Float)
    dialysate_flow = Column(Float)
    dialysate_flow_direction = Column(String)
    dialyzer_type = Column(String)
    dialyzer_surface_area = Column(Float)
    dialyzer_membrane_flux = Column(String)

    # ── Dialysate Composition ─────────────────────────────────────────────────
    dialysate_buffer = Column(String)
    dialysate_sodium = Column(Float)
    dialysate_potassium = Column(Float)
    dialysate_calcium = Column(Float)
    dialysate_bicarbonate = Column(Float)
    dialysate_temperature = Column(Float)

    # ── Circuit Pressures ─────────────────────────────────────────────────────
    arterial_line_pressure = Column(Float)
    venous_line_pressure = Column(Float)
    transmembrane_pressure = Column(Float)

    # ── Anticoagulation ───────────────────────────────────────────────────────
    anticoagulation = Column(String)
    anticoagulation_dose = Column(Float)

    # ── Vascular Access (session-level) ──────────────────────────────────────
    access_location = Column(String)
    access_condition = Column(String)
    needle_gauge = Column(String)
    cannulation_technique = Column(String)
    vascular_interventions = Column(Text)
    access_complications = Column(Text)

    # ── Access Recirculation (Two-Needle Urea Method) ─────────────────────────
    urea_peripheral_s = Column(Float)
    urea_arterial_a = Column(Float)
    urea_venous_v = Column(Float)
    access_recirculation_percent = Column(Float)
    access_flow_qa = Column(Float)

    # ── Session Medications ───────────────────────────────────────────────────
    medications_administered = Column(Text)

    # ── Intradialytic Events ──────────────────────────────────────────────────
    idh_episode = Column(Boolean)
    idh_hypertension = Column(Boolean)

    # ── Respiratory Symptoms ─────────────────────────────────────────────────
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

    # ── Vascular Access Bedside Screen (KDOQI 2019) ──────────────────────────
    # Physical exam — mandatory at every session (primary monitoring tool per KDOQI)
    # thrill_grade / bruit_grade: normal | reduced | absent
    thrill_grade            = Column(String, default="normal")
    bruit_grade             = Column(String, default="normal")
    aneurysm_flag           = Column(Boolean, default=False)
    steal_signs_flag        = Column(Boolean, default=False)

    # Cannulation quality — AVF/AVG sessions only
    cannulation_attempts    = Column(Integer)                  # 1–10, nullable
    cannulation_difficulty  = Column(String, default="routine")  # routine | difficult | failed
    needle_infiltration     = Column(Boolean, default=False)

    __table_args__ = (
        Index('ix_session_records_patient_month', 'patient_id', 'record_month'),
    )

    patient = relationship("Patient", back_populates="sessions")
    symptom_report = relationship(
        "PatientSymptomReport",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )


class InterimLabRecord(Base):
    """Clinically-triggered or ad-hoc laboratory investigations.
    Separated from protocol-driven MonthlyRecord for better ML feature engineering."""
    __tablename__ = "interim_lab_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("session_records.id"), nullable=True)
    lab_date = Column(Date, nullable=False)
    record_month = Column(String)

    parameter = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String)

    trigger = Column(String)
    notes = Column(Text)

    entered_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Provenance pair — mirrors MonthlyRecord semantics.
    data_observed_at = Column(DateTime, nullable=True)
    data_entered_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_interim_patient_month', 'patient_id', 'record_month'),
    )

    patient = relationship("Patient", back_populates="interim_labs")
    session = relationship("SessionRecord")


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    alert_type = Column(String)
    alert_reason = Column(String)
    sent_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String)
    message_preview = Column(Text)
