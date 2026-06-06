from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List
import logging
from datetime import datetime

from database import get_db
from config import templates
from dependencies import get_user
from services import protocol_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/protocols", tags=["protocols"])


@router.get("/iv-iron", response_class=HTMLResponse)
async def iv_iron_protocol_form(request: Request, db: Session = Depends(get_db)):
    user = get_user(request)
    patients = protocol_service.get_active_patients_with_iron_status(db)
    today = datetime.utcnow().date().isoformat()
    current_month = protocol_service._current_month_str()
    return templates.TemplateResponse("iv_iron_protocol.html", {
        "request":       request,
        "user":          user,
        "patients":      patients,
        "today":         today,
        "current_month": current_month,
    })


@router.post("/iv-iron")
async def iv_iron_protocol_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    # Collect per-patient entries — form fields are named:
    #   include_<pid>, product_<pid>, dose_<pid>, iron_date_<pid>
    # A global date can also be submitted as global_iron_date.
    global_date = form.get("global_iron_date", "")

    patient_ids_raw = form.getlist("patient_ids")
    included_ids    = set(form.getlist("include"))  # checkboxes

    entries = []
    for pid_str in patient_ids_raw:
        if pid_str not in included_ids:
            continue
        try:
            pid = int(pid_str)
        except ValueError:
            continue

        product  = (form.get(f"product_{pid_str}") or "").strip()
        dose_raw = form.get(f"dose_{pid_str}", "")
        date_val = form.get(f"iron_date_{pid_str}") or global_date

        entries.append({
            "patient_id": pid,
            "product":    product,
            "dose":       dose_raw,
            "date":       date_val,
        })

    result = protocol_service.bulk_save_iv_iron(db, entries)
    saved   = result["saved"]
    skipped = result["skipped"]

    return RedirectResponse(
        url=f"/protocols/iv-iron?saved={saved}&skipped={skipped}",
        status_code=303,
    )
