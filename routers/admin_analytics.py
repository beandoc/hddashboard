
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from database import get_db
from config import templates
from dependencies import get_user, _require_admin
from services import validation_service

router = APIRouter(prefix="/analytics", tags=["admin-analytics"])

@router.get("/model-performance", response_class=HTMLResponse)
async def model_performance_dashboard(
    request: Request, 
    db: Session = Depends(get_db),
    _admin: None = Depends(_require_admin)
):
    user = get_user(request)
    metrics = validation_service.get_model_performance_metrics(db)
    
    return templates.TemplateResponse("admin_model_performance.html", {
        "request": request,
        "user": user,
        "metrics": metrics
    })
