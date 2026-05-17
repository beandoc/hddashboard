from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, UniqueConstraint,
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
