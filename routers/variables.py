from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

from database import get_db, Patient, MonthlyRecord
from dynamic_vars import VariableDefinition, VariableValue, get_all_variables, upsert_variable_value
from config import templates
from dependencies import get_user
from dashboard_logic import get_current_month_str
from constants import VAR_TO_MONTHLY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/variables", tags=["variables"])

def _monthly_field_values(db: Session, field: str, patient_ids: list[int], from_m: str, to_m: str) -> dict:
    """Pull {patient_id: {month: value}} from MonthlyRecord for a given column."""
    rows = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id.in_(patient_ids),
        MonthlyRecord.record_month >= from_m,
        MonthlyRecord.record_month <= to_m,
    ).all()
    out: dict = {}
    for r in rows:
        v = getattr(r, field, None)
        if v is not None:
            out.setdefault(r.patient_id, {})[r.record_month] = v
    return out

@router.get("/manager", response_class=HTMLResponse)
async def variable_manager(request: Request, db: Session = Depends(get_db)):
    variables = get_all_variables(db, active_only=False)
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    vars_json = [{"id": v.id, "name": v.name, "display_name": v.display_name, "unit": v.unit} for v in variables]
    return templates.TemplateResponse("variable_manager.html", {
        "request": request, "variables": variables, "variables_json": vars_json,
        "patients": [{"id": p.id, "name": p.name} for p in patients],
        "default_from": "2023-01", "default_to": get_current_month_str(),
        "user": get_user(request),
    })

@router.post("")
async def api_create_variable(payload: dict, db: Session = Depends(get_db)):
    existing = db.query(VariableDefinition).filter(VariableDefinition.name == payload.get("name")).first()
    if existing: raise HTTPException(status_code=400, detail="Variable name already exists")
    vdef = VariableDefinition(**{k: v for k, v in payload.items() if hasattr(VariableDefinition, k)})
    db.add(vdef)
    db.commit()
    db.refresh(vdef)
    return {"id": vdef.id, "name": vdef.name}

@router.put("/{var_id}")
async def api_update_variable(var_id: int, payload: dict, db: Session = Depends(get_db)):
    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
    if not vdef: raise HTTPException(status_code=404, detail="Variable not found")
    for k, v in payload.items():
        if hasattr(vdef, k) and k not in ("id", "created_at"): setattr(vdef, k, v)
    db.commit()
    return {"ok": True}

@router.post("/{var_id}/toggle")
async def api_toggle_variable(var_id: int, db: Session = Depends(get_db)):
    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
    if not vdef: raise HTTPException(status_code=404, detail="Variable not found")
    vdef.is_active = not vdef.is_active
    db.commit()
    return {"is_active": vdef.is_active}

@router.get("/{var_id}/values")
async def api_get_variable_values(var_id: int, request: Request, db: Session = Depends(get_db)):
    from_m = request.query_params.get("from", "2023-01")
    to_m   = request.query_params.get("to", get_current_month_str())

    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
    if not vdef: raise HTTPException(status_code=404, detail="Variable not found")

    patients = db.query(Patient).filter(Patient.is_active == True).all()
    pid_list = [p.id for p in patients]

    rows = db.query(VariableValue).filter(
        VariableValue.variable_id == var_id,
        VariableValue.patient_id.in_(pid_list),
        VariableValue.record_month >= from_m,
        VariableValue.record_month <= to_m,
    ).all()
    result: dict = {}
    for r in rows:
        result.setdefault(r.patient_id, {})[r.record_month] = r.value_num

    monthly_field = VAR_TO_MONTHLY.get(vdef.name)
    if monthly_field:
        bridged = _monthly_field_values(db, monthly_field, pid_list, from_m, to_m)
        for pid, months in bridged.items():
            for month, val in months.items():
                result.setdefault(pid, {}).setdefault(month, val)

    return result

@router.post("/value")
async def api_upsert_value(payload: dict, db: Session = Depends(get_db)):
    upsert_variable_value(
        db,
        patient_id=int(payload["patient_id"]),
        month_str=payload["record_month"],
        variable_id=int(payload["variable_id"]),
        value_num=payload.get("value_num"),
        value_text=payload.get("value_text"),
        entered_by=payload.get("entered_by", ""),
    )
    return {"ok": True}

@router.get("/{var_id}/summary")
async def api_variable_summary(var_id: int, db: Session = Depends(get_db)):
    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
    if not vdef: raise HTTPException(status_code=404, detail="Variable not found")

    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    pid_list = [p.id for p in patients]

    all_data: dict = {}
    rows = db.query(VariableValue).filter(VariableValue.variable_id == var_id, VariableValue.patient_id.in_(pid_list)).all()
    for r in rows: all_data.setdefault(r.patient_id, {})[r.record_month] = r.value_num

    monthly_field = VAR_TO_MONTHLY.get(vdef.name)
    if monthly_field:
        bridged = _monthly_field_values(db, monthly_field, pid_list, "2020-01", get_current_month_str())
        for pid, months in bridged.items():
            for month, val in months.items(): all_data.setdefault(pid, {}).setdefault(month, val)

    patient_rows = []
    for p in patients:
        months = all_data.get(p.id, {})
        latest = months[max(months)] if months else None
        patient_rows.append({"id": p.id, "name": p.name, "hid": p.hid_no, "latest_value": latest})

    month_buckets: dict = {}
    for pid, months in all_data.items():
        for m, v in months.items():
            if v is not None: month_buckets.setdefault(m, []).append(v)

    def _pct(sorted_vals, p):
        n = len(sorted_vals)
        if n == 0: return None
        idx = (p / 100) * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)

    trend = []
    for m in sorted(month_buckets):
        vals = sorted(month_buckets[m])
        trend.append({
            "month": m,
            "median": round(_pct(vals, 50), 2),
            "p25":    round(_pct(vals, 25), 2),
            "p75":    round(_pct(vals, 75), 2),
        })

    return {
        "patients": patient_rows, 
        "trend": trend,
        "all_data": all_data,
        "thresholds": {
            "low": vdef.threshold_low,
            "high": vdef.threshold_high,
            "target_low": vdef.target_low,
            "target_high": vdef.target_high
        }
    }
