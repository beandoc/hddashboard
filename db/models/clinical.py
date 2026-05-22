from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, Text,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from db.engine import Base


class PatientReminder(Base):
    __tablename__ = "patient_reminders"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    reminder_date = Column(Date, nullable=False)
    message = Column(Text, nullable=False)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="reminders")


class ClinicalEvent(Base):
    """A discrete clinical event for a patient on a specific date.
    Used to build the unit-level and per-patient clinical event timeline."""
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


class PatientSymptomReport(Base):
    __tablename__ = "patient_symptom_reports"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("session_records.id"), nullable=True)
    reported_at = Column(DateTime, default=datetime.utcnow)

    # Date of the dialysis session being reported on
    session_date = Column(Date, nullable=True)

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
