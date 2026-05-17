
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

from database import get_db, MLModelMetrics, ClinicalOverrideLog, ModelArtifact
from config import templates
from dependencies import get_user, _require_admin
from services import validation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["admin-analytics"])


@router.get("/model-performance", response_class=HTMLResponse)
async def model_performance_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    _admin: None = Depends(_require_admin)
):
    user = get_user(request)
    metrics = validation_service.get_model_performance_metrics(db)

    # Last 30 nightly MLModelMetrics rows for the deterioration model
    recent_runs = (
        db.query(MLModelMetrics)
        .filter(MLModelMetrics.model_name == "deterioration_v1")
        .order_by(MLModelMetrics.computed_at.desc())
        .limit(30)
        .all()
    )

    # Most recent registered artifact
    latest_artifact = (
        db.query(ModelArtifact)
        .filter(ModelArtifact.model_name == "deterioration_v1")
        .order_by(ModelArtifact.trained_at.desc())
        .first()
    )

    return templates.TemplateResponse("admin_model_performance.html", {
        "request": request,
        "user": user,
        "metrics": metrics,
        "recent_runs": recent_runs,
        "latest_artifact": latest_artifact,
    })


@router.post("/clinical-override", response_class=JSONResponse)
async def log_clinical_override(
    request: Request,
    patient_id: int = Form(...),
    model_name: str = Form("deterioration_v1"),
    ml_prediction_id: Optional[int] = Form(None),
    predicted_score: Optional[float] = Form(None),
    predicted_class: Optional[int] = Form(None),
    override_direction: str = Form(...),
    clinician_decision: Optional[str] = Form(None),
    override_reason: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Record a clinician disagreement with a model prediction.

    Valid override_direction values:
      higher_risk | lower_risk | agree_but_act_differently
    """
    user = get_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    VALID_DIRECTIONS = {"higher_risk", "lower_risk", "agree_but_act_differently"}
    if override_direction not in VALID_DIRECTIONS:
        return JSONResponse(
            {"error": f"override_direction must be one of {VALID_DIRECTIONS}"},
            status_code=422,
        )

    row = ClinicalOverrideLog(
        patient_id         = patient_id,
        ml_prediction_id   = ml_prediction_id,
        model_name         = model_name,
        predicted_score    = predicted_score,
        predicted_class    = predicted_class,
        override_direction = override_direction,
        clinician_decision = clinician_decision,
        override_reason    = override_reason,
        clinician_id       = user.get("username") if isinstance(user, dict) else getattr(user, "username", None),
    )
    db.add(row)
    db.commit()
    logger.info(
        "ClinicalOverride recorded: patient=%d model=%s direction=%s by=%s",
        patient_id, model_name, override_direction, row.clinician_id,
    )
    return JSONResponse({"status": "recorded", "override_id": row.id})


@router.get("/clinical-overrides", response_class=JSONResponse)
async def list_clinical_overrides(
    model_name: str = "deterioration_v1",
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin: None = Depends(_require_admin),
):
    """Return the most recent clinical override log entries for a model."""
    rows = (
        db.query(ClinicalOverrideLog)
        .filter(ClinicalOverrideLog.model_name == model_name)
        .order_by(ClinicalOverrideLog.override_at.desc())
        .limit(limit)
        .all()
    )
    return JSONResponse([
        {
            "id":                  r.id,
            "patient_id":          r.patient_id,
            "ml_prediction_id":    r.ml_prediction_id,
            "predicted_score":     r.predicted_score,
            "predicted_class":     r.predicted_class,
            "override_direction":  r.override_direction,
            "clinician_decision":  r.clinician_decision,
            "override_reason":     r.override_reason,
            "clinician_id":        r.clinician_id,
            "override_at":         r.override_at.isoformat() if r.override_at else None,
        }
        for r in rows
    ])
