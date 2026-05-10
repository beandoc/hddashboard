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
    
    # Inject Core Variables that aren't already defined
    defined_names = {v.name for v in variables}
    core_vars = []
    
    # Human-readable mapping for core vars
    core_display = {
        "hb": "Hemoglobin", "albumin": "Albumin", "phosphorus": "Phosphorus",
        "calcium": "Calcium", "alkaline_phosphate": "Alk. Phos.", "ipth": "iPTH",
        "vit_d": "Vitamin D", "ferritin": "Ferritin", "tsat": "TSAT",
        "urr": "URR", "kt_v": "Kt/V", "bicarbonate": "Bicarbonate",
        "uric_acid": "Uric Acid", "creatinine": "Creatinine",
        "sodium": "Sodium", "potassium": "Potassium", "crp": "CRP",
        "systolic_bp_pre": "Systolic BP (Pre)", "idwg": "IDWG",
        "dry_weight": "Target Dry Weight", "nt_probnp": "NT-ProBNP",
        "ef": "Ejection Fraction", "wbc": "WBC Count", "platelets": "Platelet Count"
    }
    
    class VirtualVar:
        def __init__(self, id, name, display_name, category="Core", is_active=True):
            self.id = id
            self.name = name
            self.display_name = display_name
            self.category = category
            self.is_active = is_active
            self.unit = ""
            self.data_type = "number"
            self.decimal_places = 1
            self.threshold_low = None
            self.threshold_high = None
            self.target_low = None
            self.target_high = None
            self.description = "Core clinical variable from monthly records"
            self.show_in_dashboard = True
            self.show_in_timeline = True
            self.alert_direction = "both"

    for name, field in VAR_TO_MONTHLY.items():
        if name not in defined_names:
            # Use negative IDs for virtual vars to distinguish them
            v_id = - (list(VAR_TO_MONTHLY.keys()).index(name) + 1)
            core_vars.append(VirtualVar(v_id, name, core_display.get(name, name.replace("_", " ").title())))

    all_vars = variables + core_vars
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    vars_json = []
    for v in all_vars:
        vars_json.append({
            "id": v.id,
            "name": v.name,
            "display_name": v.display_name,
            "unit": getattr(v, "unit", ""),
            "category": v.category,
            "data_type": getattr(v, "data_type", "number"),
            "decimal_places": getattr(v, "decimal_places", 1),
            "threshold_low": getattr(v, "threshold_low", None),
            "threshold_high": getattr(v, "threshold_high", None),
            "target_low": getattr(v, "target_low", None),
            "target_high": getattr(v, "target_high", None),
            "description": getattr(v, "description", ""),
            "show_in_dashboard": getattr(v, "show_in_dashboard", True),
            "show_in_timeline": getattr(v, "show_in_timeline", True),
            "alert_direction": getattr(v, "alert_direction", "both"),
            "is_active": getattr(v, "is_active", True),
        })
    
    return templates.TemplateResponse("variable_manager.html", {
        "request": request, "variables": all_vars, "variables_json": vars_json,
        "patient_list_data": [{"id": p.id, "name": p.name, "hid": p.hid_no} for p in patients],
        "patients": patients,
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

    var_name = ""
    if var_id > 0:
        vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
        if not vdef: raise HTTPException(status_code=404, detail="Variable not found")
        var_name = vdef.name
    else:
        idx = abs(var_id) - 1
        core_list = list(VAR_TO_MONTHLY.keys())
        if idx >= len(core_list): raise HTTPException(status_code=404, detail="Core variable not found")
        var_name = core_list[idx]

    patients = db.query(Patient).filter(Patient.is_active == True).all()
    pid_list = [p.id for p in patients]

    result: dict = {}
    if var_id > 0:
        rows = db.query(VariableValue).filter(
            VariableValue.variable_id == var_id,
            VariableValue.patient_id.in_(pid_list),
            VariableValue.record_month >= from_m,
            VariableValue.record_month <= to_m,
        ).all()
        for r in rows:
            result.setdefault(r.patient_id, {})[r.record_month] = r.value_num

    monthly_field = VAR_TO_MONTHLY.get(var_name)
    if monthly_field:
        bridged = _monthly_field_values(db, monthly_field, pid_list, from_m, to_m)
        for pid, months in bridged.items():
            for month, val in months.items():
                result.setdefault(pid, {}).setdefault(month, val)

    return result

@router.post("/value")
async def api_upsert_value(payload: dict, db: Session = Depends(get_db)):
    patient_id = int(payload["patient_id"])
    var_id     = int(payload["variable_id"])
    val_num    = payload.get("value_num")
    month_str  = payload["record_month"]
    entered_by = payload.get("entered_by", "Variable Manager")

    vdef = None
    if var_id > 0:
        vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
        if not vdef: raise HTTPException(status_code=404, detail="Variable not found")
        
        upsert_variable_value(
            db,
            patient_id=patient_id,
            month_str=month_str,
            variable_id=var_id,
            value_num=val_num,
            value_text=payload.get("value_text"),
            entered_by=entered_by,
        )
        var_name = vdef.name
    else:
        # Virtual variable from core list
        idx = abs(var_id) - 1
        core_list = list(VAR_TO_MONTHLY.keys())
        if idx >= len(core_list): raise HTTPException(status_code=404, detail="Core variable not found")
        var_name = core_list[idx]

    # Sync to MonthlyRecord if it's a mapped core variable
    monthly_field = VAR_TO_MONTHLY.get(var_name)
    if monthly_field:
        from database import MonthlyRecord
        rec = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month == month_str
        ).first()
        if not rec:
            rec = MonthlyRecord(patient_id=patient_id, record_month=month_str, entered_by=entered_by)
            db.add(rec)
        
        if hasattr(rec, monthly_field):
            setattr(rec, monthly_field, val_num)
            db.commit()

    # Trigger Automated Alert if critical
    # (vdef might be None for virtual vars, so we use a mock if needed or skip)
    alert_vdef = vdef
    if not alert_vdef:
        # Mock for virtual vars to reuse alert logic
        class MockVdef:
            def __init__(self, name):
                self.name = name
                self.display_name = name.replace("_", " ").title()
                self.unit = ""
                self.threshold_low = None
                self.threshold_high = None
        alert_vdef = MockVdef(var_name)

    if alert_vdef and val_num is not None:
        is_critical = False
        alert_msg = ""
        t_low = getattr(alert_vdef, "threshold_low", None)
        t_high = getattr(alert_vdef, "threshold_high", None)
        
        if t_low is not None and val_num < t_low:
            is_critical = True
            alert_msg = f"Low {alert_vdef.display_name} ({val_num} {getattr(alert_vdef, 'unit', '')})"
        elif t_high is not None and val_num > t_high:
            is_critical = True
            alert_msg = f"High {alert_vdef.display_name} ({val_num} {getattr(alert_vdef, 'unit', '')})"
        
        if is_critical:
            from alerts import send_entry_alert_email
            from dashboard_logic import get_month_label
            p = db.query(Patient).filter(Patient.id == patient_id).first()
            if p:
                send_entry_alert_email(
                    patient_name=p.name,
                    hid=p.hid_no,
                    month_label=get_month_label(month_str),
                    alerts=[alert_msg],
                    labs={alert_vdef.name: val_num},
                    entered_by=entered_by
                )

    return {"ok": True}

@router.get("/{var_id}/summary")
async def api_variable_summary(var_id: int, db: Session = Depends(get_db)):
    vdef = None
    var_name = ""
    thresholds = {"low": None, "high": None, "target_low": None, "target_high": None}

    if var_id > 0:
        vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
        if not vdef: raise HTTPException(status_code=404, detail="Variable not found")
        var_name = vdef.name
        thresholds = {
            "low": vdef.threshold_low,
            "high": vdef.threshold_high,
            "target_low": vdef.target_low,
            "target_high": vdef.target_high
        }
    else:
        idx = abs(var_id) - 1
        core_list = list(VAR_TO_MONTHLY.keys())
        if idx >= len(core_list): raise HTTPException(status_code=404, detail="Core variable not found")
        var_name = core_list[idx]

    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    pid_list = [p.id for p in patients]

    all_data: dict = {}
    if var_id > 0:
        rows = db.query(VariableValue).filter(VariableValue.variable_id == var_id, VariableValue.patient_id.in_(pid_list)).all()
        for r in rows: all_data.setdefault(r.patient_id, {})[r.record_month] = r.value_num

    monthly_field = VAR_TO_MONTHLY.get(var_name)
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
        median = _pct(vals, 50)
        p25 = _pct(vals, 25)
        p75 = _pct(vals, 75)
        trend.append({
            "month": m,
            "median": round(median, 2) if median is not None else None,
            "p25":    round(p25, 2)    if p25 is not None else None,
            "p75":    round(p75, 2)    if p75 is not None else None,
        })

    return {
        "patients": patient_rows, 
        "trend": trend,
        "all_data": all_data,
        "thresholds": thresholds
    }
