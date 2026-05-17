
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import logging

from database import get_db, MLModelMetrics, ModelArtifact
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


