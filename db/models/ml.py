from sqlalchemy import (
    Column, Index, Integer, String, Float, Boolean, Date, DateTime, Text,
    ForeignKey, UniqueConstraint, LargeBinary,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime

from db.engine import Base


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
    patient_id_hash     = Column(String(64), nullable=True, index=True)
    model_name          = Column(String, nullable=False, index=True)
    model_version       = Column(String, nullable=True)
    input_feature_hash  = Column(String(64), nullable=False, index=True)
    features_json       = Column(Text, nullable=False)
    prediction_score    = Column(Float, nullable=False)
    predicted_class     = Column(Integer, nullable=True)
    observed_outcome    = Column(Integer, nullable=True)
    prediction_month    = Column(String(7), nullable=True)
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
    week_start         = Column(String(10), nullable=False)
    n_predictions      = Column(Integer, nullable=False, default=0)
    n_with_outcome     = Column(Integer, nullable=False, default=0)
    pr_auc             = Column(Float, nullable=True)
    brier_score        = Column(Float, nullable=True)
    calibration_slope  = Column(Float, nullable=True)
    calibration_intercept = Column(Float, nullable=True)
    roc_auc            = Column(Float, nullable=True)
    drift_flagged      = Column(Boolean, default=False)
    drift_detail       = Column(Text, nullable=True)
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
    model_name          = Column(String, nullable=False, index=True)
    version             = Column(String, nullable=False)
    trained_at          = Column(DateTime, nullable=False)
    training_data_hash  = Column(String(64), nullable=True)
    metrics_json        = Column(Text, nullable=True)
    feature_schema_json = Column(Text, nullable=True)
    artifact_path       = Column(String, nullable=True)
    # Serialised joblib bytes — survives container redeploys on ephemeral filesystems.
    model_binary        = Column(LargeBinary, nullable=True)
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
    predicted_score     = Column(Float, nullable=True)
    predicted_class     = Column(Integer, nullable=True)
    override_direction  = Column(String, nullable=False)
    clinician_decision  = Column(String, nullable=True)
    override_reason     = Column(Text, nullable=True)
    clinician_id        = Column(String, nullable=True)
    override_at         = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient        = relationship("Patient", foreign_keys=[patient_id])
    ml_prediction  = relationship("MLPrediction", foreign_keys=[ml_prediction_id])


class ACMRecommendation(Base):
    """One row per patient per month containing the ACM's recommendation.

    clinician_decision: 'accept' | 'modify' | 'reject' | None (pending)
    observed_hb_*: back-filled when subsequent monthly records arrive,
    enabling Feedback & Learning (accuracy tracking per Fig. 4, CKJ 2026).
    """
    __tablename__ = "acm_recommendations"

    id                     = Column(Integer, primary_key=True, index=True)
    patient_id             = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    recommendation_month   = Column(String(7), nullable=False, index=True)
    generated_at           = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ML outputs
    current_hb             = Column(Float, nullable=True)
    predicted_hb_1mo       = Column(Float, nullable=True)
    predicted_hb_2mo       = Column(Float, nullable=True)
    predicted_hb_3mo       = Column(Float, nullable=True)
    hb_status              = Column(String(20), nullable=True)    # on_target | low | high | ...
    confidence             = Column(String(20), nullable=True)    # model | heuristic

    # ESA recommendation
    esa_action             = Column(String(20), nullable=True)    # increase | decrease | hold | maintain
    esa_change_pct         = Column(Float, nullable=True)
    recommended_iu_sc      = Column(Float, nullable=True)
    esa_rationale          = Column(Text, nullable=True)

    # Iron recommendation
    iron_action            = Column(String(20), nullable=True)    # supplement | hold | maintain | check
    iron_rationale         = Column(Text, nullable=True)

    # Safety
    safety_flags_json      = Column(Text, nullable=True)          # JSON array

    # Clinician decision (filled by review workflow)
    clinician_decision     = Column(String(20), nullable=True, index=True)   # accept | modify | reject
    clinician_notes        = Column(Text, nullable=True)
    clinician_id           = Column(String(100), nullable=True)
    decided_at             = Column(DateTime, nullable=True)
    modified_iu_sc         = Column(Float, nullable=True)         # clinician override dose
    modified_iron_action   = Column(String(20), nullable=True)

    # Feedback — back-filled by weekly Celery task
    observed_hb_1mo        = Column(Float, nullable=True)
    observed_hb_3mo        = Column(Float, nullable=True)
    hb_prediction_mae_1mo  = Column(Float, nullable=True)         # |predicted - observed|

    patient = relationship("Patient", foreign_keys=[patient_id])

    __table_args__ = (
        UniqueConstraint("patient_id", "recommendation_month", name="uq_acm_patient_month"),
    )


class TwinSimulation(Base):
    """One row per Digital Twin scenario simulation run.

    stores the full scenario parameters and all three module outputs
    (Hb kinetics, Kt/V, IDH risk) as JSON blobs for rendering + audit.
    actual_outcomes_json is back-filled when the next session/monthly record
    arrives, enabling outcome-driven feedback loop (Fig. 6, CKJ 2026).
    """
    __tablename__ = "twin_simulations"

    id                  = Column(Integer, primary_key=True, index=True)
    patient_id          = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    created_at          = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by          = Column(String(100), nullable=True)

    # Input scenario (JSON)
    scenario_json       = Column(Text, nullable=False)            # the parameter set simulated
    baseline_session_json = Column(Text, nullable=True)           # session plan at time of sim

    # Simulation outputs (JSON)
    hb_sim_json         = Column(Text, nullable=True)             # Hb trajectory
    ktv_sim_json        = Column(Text, nullable=True)             # Kt/V comparison
    idh_sim_json        = Column(Text, nullable=True)             # IDH risk comparison
    uf_curve_json       = Column(Text, nullable=True)             # UF rate sweep

    # Clinician notes / decision to adopt scenario
    adopted             = Column(Boolean, nullable=True, default=False)
    adopted_at          = Column(DateTime, nullable=True)
    adopted_by          = Column(String(100), nullable=True)
    clinician_notes     = Column(Text, nullable=True)

    # Outcome tracking (back-filled)
    actual_outcomes_json = Column(Text, nullable=True)
    fluid_volume_params = Column(JSONB, nullable=True)

    patient = relationship("Patient", foreign_keys=[patient_id])

    __table_args__ = (
        Index("ix_twin_patient_created", "patient_id", "created_at"),
        Index("ix_twin_created_by", "created_by"),
    )


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
    as_of_month    = Column(String(7), nullable=False)
    feature_vector = Column(JSONB, nullable=False)
    feature_hash   = Column(String(64), nullable=True)
    model_version  = Column(String(32), nullable=True)
    stale          = Column(Boolean, nullable=False, default=False)
    computed_at    = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("patient_id", "as_of_month", name="uq_feature_snapshot_patient_month"),
    )

    patient = relationship("Patient", foreign_keys=[patient_id])


class DiaSenseCalibration(Base):
    """Per-session DiaSense optical-sensor calibration record.

    One row per HD session where DiaSense optical data was captured.
    Stores the measured plasma-refill coefficient (diasense_k_r), RBV nadir,
    UF target vs actual, intradialytic BP trend, post-HD symptoms, and
    post-HD BCM readings so the Digital Twin can use patient-specific
    physiology instead of the generic weight-scaled k_r estimate.

    The most recent row per patient is used by run_scenario() as k_r_override
    in simulate_fluid_volume(), replacing the default 0.006 mL/min/mmHg/kg
    population estimate with a measured, session-derived value.
    """
    __tablename__ = "diasense_calibrations"

    id                      = Column(Integer, primary_key=True, index=True)
    patient_id              = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    session_date            = Column(Date, nullable=False)
    diasense_session_id     = Column(String(64), nullable=True)   # e.g. "AGD09_HA1_213320"

    # ── k_r calibration ──────────────────────────────────────────────────────
    diasense_k_r            = Column(Float, nullable=True)        # mL/min/mmHg measured from RBV curve
    k_r_estimated           = Column(Float, nullable=True)        # weight × 0.006 at time of session

    # ── RBV nadir from optical sensor ────────────────────────────────────────
    rbv_nadir_pct           = Column(Float, nullable=True)        # max RBV drop %
    rbv_nadir_time_min      = Column(Float, nullable=True)        # session minute when nadir occurred
    rbv_breach              = Column(Boolean, default=False)      # True if nadir > 8% (Abohtyra threshold)
    plasma_refill_rate_ml_min = Column(Float, nullable=True)      # mean J_refill mL/min

    # ── UF target vs actual ──────────────────────────────────────────────────
    uf_target_ml            = Column(Float, nullable=True)        # prescribed UF volume (mL)
    uf_actual_ml            = Column(Float, nullable=True)        # weight-derived actual removal mL
    uf_rate_ml_kg_h         = Column(Float, nullable=True)        # actual UF rate mL/kg/h
    uf_achievement_pct      = Column(Float, nullable=True)        # uf_actual / uf_target × 100

    # ── Session parameters ───────────────────────────────────────────────────
    session_duration_min    = Column(Float, nullable=True)
    weight_pre_kg           = Column(Float, nullable=True)
    dry_weight_kg           = Column(Float, nullable=True)
    albumin_g_dl            = Column(Float, nullable=True)

    # ── Intradialytic BP trend ────────────────────────────────────────────────
    # JSON array: [{time_min, sbp, dbp, map, pulse}, …]
    bp_trend_json           = Column(Text, nullable=True)
    bp_nadir_sys            = Column(Float, nullable=True)
    bp_nadir_map            = Column(Float, nullable=True)
    bp_nadir_time_min       = Column(Float, nullable=True)
    idh_observed            = Column(Boolean, default=False)

    # ── Post-HD symptoms ─────────────────────────────────────────────────────
    post_hd_dyspnea_likert  = Column(Integer, nullable=True)
    post_hd_fatigue_likert  = Column(Integer, nullable=True)
    post_hd_cramps          = Column(Boolean, nullable=True)
    post_hd_nausea          = Column(Boolean, nullable=True)
    post_hd_headache        = Column(Boolean, nullable=True)

    # ── Post-HD BCM (ResearchRecord test_type ILIKE '%BCM%' / '%BIA%') ───────
    bcm_post_fluid_overload_l   = Column(Float, nullable=True)
    bcm_post_tbw_l              = Column(Float, nullable=True)
    bcm_post_phase_angle        = Column(Float, nullable=True)
    bcm_delta_overhydration_l   = Column(Float, nullable=True)   # pre minus post BCM overload

    # ── Optical sensor summary ────────────────────────────────────────────────
    he_od_mean              = Column(Float, nullable=True)
    ha_od_mean              = Column(Float, nullable=True)
    delta_od_mean           = Column(Float, nullable=True)
    he_od_slope_per_hr      = Column(Float, nullable=True)       # OD/hour hemoconcentration trend
    grade2plus_count        = Column(Integer, nullable=True)     # rows with hemoconcentration grade ≥ 2
    # Sampled RBV curve [{t_min, rbv_drop_pct}, …] — every 5th point
    rbv_curve_json          = Column(Text, nullable=True)

    # ── Audit ────────────────────────────────────────────────────────────────
    notes                   = Column(Text, nullable=True)
    created_at              = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by              = Column(String(100), nullable=True)

    patient = relationship("Patient", foreign_keys=[patient_id])

    __table_args__ = (
        Index("ix_diasense_patient_date", "patient_id", "session_date"),
    )
