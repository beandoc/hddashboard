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
    patient_id  = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
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
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("session_records.id"), nullable=True, index=True)
    reported_at = Column(DateTime, default=datetime.utcnow)

    # Date of the dialysis session being reported on
    session_date = Column(Date, nullable=True)

    # Legacy generic symptoms
    symptoms = Column(Text)
    severity = Column(Integer)
    notes = Column(Text)

    # ── Post-Dialysis Syndrome (PDS) Specifics ───────────────────────────────
    dialysis_recovery_time = Column(String)  # <1 hour, 1-2 hours, 2-6 hours, etc.

    # A. Fatigue & Energy Domain (0-10)
    fatigue_physical_exhaustion = Column(Integer)
    fatigue_lack_of_energy = Column(Integer)
    fatigue_sleepiness = Column(Integer)
    fatigue_reduced_stamina = Column(Integer)
    fatigue_prolonged_rest = Column(Integer)
    fatigue_washed_out = Column(Integer)
    fatigue_motivation_loss = Column(Integer)

    # B. Cognitive Domain (0-10)
    cog_brain_fog = Column(Integer)
    cog_poor_concentration = Column(Integer)
    cog_slowed_thinking = Column(Integer)
    cog_memory_difficulty = Column(Integer)
    cog_reduced_alertness = Column(Integer)
    cog_decision_difficulty = Column(Integer)

    # C. Psychological Domain (0-10)
    psych_low_mood = Column(Integer)
    psych_anxiety = Column(Integer)
    psych_irritability = Column(Integer)
    psych_emotional_exhaustion = Column(Integer)
    psych_overwhelmed = Column(Integer)
    psych_reduced_purpose = Column(Integer)

    # D. Physical Symptom Domain (0-10)
    phys_muscle_weakness = Column(Integer)
    phys_dizziness = Column(Integer)
    phys_headache = Column(Integer)
    phys_body_pain = Column(Integer)
    phys_sob = Column(Integer)
    phys_palpitations = Column(Integer)
    phys_gait_instability = Column(Integer)
    phys_cramps = Column(Integer)

    # E. Sleep Domain (0-10)
    sleep_daytime_sleepiness = Column(Integer)
    sleep_poor_sleep_post_hd = Column(Integer)
    sleep_unrefreshing = Column(Integer)
    sleep_disturbance = Column(Integer)

    # Functional Impact Assessment (0-10)
    func_mobility = Column(Integer)
    func_household = Column(Integer)
    func_work = Column(Integer)
    func_social = Column(Integer)
    func_exercise = Column(Integer)
    func_family = Column(Integer)
    func_independence = Column(Integer)
    func_life_participation = Column(Integer)

    # Day-to-Day Symptom Variability
    symptoms_worse_time = Column(String)
    symptoms_compare_nondialysis = Column(String)

    # Associated Contributors
    associated_contributors = Column(Text)  # comma-separated string

    # Physical Activity Assessment
    activity_average_daily = Column(String)
    activity_posthd_reduction = Column(String)
    activity_exercise_tolerance = Column(String)

    # Patient Narrative Section
    narrative_most_disabling = Column(Text)
    narrative_activities_affected = Column(Text)
    narrative_helps_recovery = Column(Text)
    narrative_makes_worse = Column(Text)

    # Clinician Global Impression
    cgi_severity = Column(String)
    cgi_dominant_phenotype = Column(String)

    # Suggested Follow-up Interventions
    suggested_interventions = Column(Text)  # comma-separated string

    patient = relationship("Patient", back_populates="symptom_reports")
    session = relationship("SessionRecord", back_populates="symptom_report")


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
    # Optional link to a matching ClinicalEvent (avoids duplicate data entry)
    clinical_event_id = Column(Integer, ForeignKey("clinical_events.id"), nullable=True, index=True)

    # Severity and clinical indicators
    severity        = Column(String)
    icu_admission   = Column(Boolean, default=False)
    pct             = Column(Float)
    shock_on_admission = Column(Integer, default=0)
    inotrope_days   = Column(Float)
    ventilation_days = Column(Float)
    transfusion_units = Column(Float)

    patient        = relationship("Patient", back_populates="hospitalisations")
    clinical_event = relationship("ClinicalEvent", foreign_keys=[clinical_event_id])


# ─────────────────────────────────────────────────────────────────────────────
# VASCULAR ACCESS — KDOQI 2019 aligned models
# ─────────────────────────────────────────────────────────────────────────────

class AccessEpisode(Base):
    """One row per vascular access device per patient (multi-episode history).
    Replaces the single-record PatientVascularAccess for prospective surveillance.
    Includes ESKD Life-Plan fields per KDOQI 2019 Guidelines 1.1–1.3."""
    __tablename__ = "access_episodes"

    id                      = Column(Integer, primary_key=True, index=True)
    patient_id              = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)

    # Access classification
    access_class            = Column(String, nullable=False)   # AVF | AVG | TCC | non_tunnelled
    access_subtype          = Column(String)                   # RC AVF Rt, Lt IJV TCC, etc.

    # Dates
    creation_date           = Column(Date, nullable=False)
    first_cannulation_date  = Column(Date)                     # AVF/AVG only

    # CVC-specific fields
    insertion_site          = Column(String)
    catheter_type           = Column(String)

    # Status
    is_current              = Column(Boolean, default=True, nullable=False)
    loss_date               = Column(Date)
    loss_reason             = Column(String)
    # loss_reason values: thrombosis | infection | steal | maturation_failure |
    #   planned_upgrade | elective_removal | patient_death | transfer | unknown

    # ESKD Life-Plan (KDOQI 2019 Guidelines 1.1–1.3)
    succession_plan         = Column(Text)
    life_plan_reviewed_at   = Column(Date)
    access_reviewed_at      = Column(Date)

    notes                   = Column(Text)
    entered_by              = Column(String)
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient         = relationship("Patient", back_populates="access_episodes")
    access_events   = relationship("AccessEvent", back_populates="episode", cascade="all, delete-orphan")
    surveillance_records = relationship("AccessSurveillanceRecord", back_populates="episode", cascade="all, delete-orphan")


class AccessEvent(Base):
    """Structured coded vascular access event log with KDOQI 2019 grading.

    Event types (access_class scope):
      Cannulation: cannulation_difficulty, failed_cannulation, needle_infiltration,
                   aneurysm_new, aneurysm_enlarging, aneurysm_concerning  (AVF/AVG)
      Flow:        suboptimal_bfr, qa_decline_absolute, qa_decline_relative,
                   high_recirculation, steal_syndrome  (AVF/AVG)
      Maturation:  maturation_delay, maturation_failure, thrombosis  (AVF/AVG)
      Infection:   exit_site_infection, tunnel_infection, crbsi_suspected,
                   crbsi_confirmed, buttonhole_infection  (CVC/AVF buttonhole)

    steal_grade (KDOQI Table 18.3): grade_0 | grade_1 | grade_2 | grade_3
    cannulation_injury_grade (KDOQI Glossary): minor | major | severe
    status governance: pending_review | confirmed | ruled_out
    """
    __tablename__ = "access_events"

    id                      = Column(Integer, primary_key=True, index=True)
    patient_id              = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    episode_id              = Column(Integer, ForeignKey("access_episodes.id"), nullable=False, index=True)

    event_date              = Column(Date, nullable=False)
    event_type              = Column(String, nullable=False)
    access_class            = Column(String, nullable=False)   # denormalized for query efficiency

    severity                = Column(String)                   # mild | moderate | severe
    steal_grade             = Column(String)                   # grade_0..grade_3 (steal events only)
    cannulation_injury_grade = Column(String)                  # minor | major | severe (cannulation events only)
    affected_segment        = Column(String)                   # aneurysm/stenosis location

    action_taken            = Column(String)
    # observed | dressing_change | antibiotic_oral | antibiotic_iv |
    # angioplasty | thrombectomy | surgical_referral |
    # catheter_removed | catheter_replaced | watchful_waiting

    outcome                 = Column(String)                   # resolved | ongoing | referred | recurrent | access_lost

    status                  = Column(String, default="pending_review", nullable=False)
    # pending_review | confirmed | ruled_out

    notes                   = Column(Text)
    entered_by              = Column(String)
    reviewed_by             = Column(String)
    reviewed_at             = Column(DateTime)
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="access_events")
    episode = relationship("AccessEpisode", back_populates="access_events")


class AccessSurveillanceRecord(Base):
    """Clinically-triggered imaging/Doppler surveillance visits.

    Per KDOQI 2019 Guidelines 13.4–13.5, surveillance is triggered by clinical
    indicators (thrill/bruit change, Qa decline, cannulation difficulty) — NOT
    on a routine calendar interval. clinical_trigger is mandatory.

    finding values: normal | mild_stenosis | moderate_stenosis | severe_stenosis
                    | thrombosis | aneurysm | other
    recommendation values: routine_followup | repeat_imaging | angioplasty
                           | surgical_referral | urgent_referral
    """
    __tablename__ = "access_surveillance_records"

    id                  = Column(Integer, primary_key=True, index=True)
    patient_id          = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    episode_id          = Column(Integer, ForeignKey("access_episodes.id"), nullable=False, index=True)

    surveillance_date   = Column(Date, nullable=False)
    clinical_trigger    = Column(String, nullable=False)       # what prompted this study

    modality            = Column(String)                       # duplex_doppler | fistulogram | angiogram | physical_exam_only
    qa_by_imaging       = Column(Float)                        # mL/min
    qa_baseline_at_test = Column(Float)                        # patient's rolling baseline Qa at time of test
    psv_at_stenosis     = Column(Float)                        # peak systolic velocity cm/s
    stenosis_pct        = Column(Float)                        # % luminal reduction

    finding             = Column(String)
    recommendation      = Column(String)
    next_due_date       = Column(Date)                         # clinician-set, not auto-computed from interval

    performed_by        = Column(String)
    report_image_path   = Column(String)                       # relative path under static/uploads/surveillance/
    status              = Column(String, default="pending_review", nullable=False)
    notes               = Column(Text)
    entered_by          = Column(String)
    created_at          = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="surveillance_records")
    episode = relationship("AccessEpisode", back_populates="surveillance_records")


class AccessAlertOverride(Base):
    """Audit log for every access action-item alert that was acknowledged,
    snoozed, overridden, or acted on. Provides governance trail."""
    __tablename__ = "access_alert_overrides"

    id                  = Column(Integer, primary_key=True, index=True)
    patient_id          = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)

    alert_type          = Column(String, nullable=False)
    alert_generated_at  = Column(DateTime, nullable=False)
    alert_reason        = Column(Text)                         # computed trigger explanation

    action              = Column(String, nullable=False)
    # acknowledged | snoozed | overridden | acted_on
    override_reason     = Column(Text)                         # required when action=overridden

    actioned_by         = Column(String)
    actioned_at         = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="access_alert_overrides")
