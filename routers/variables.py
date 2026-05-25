from __future__ import annotations

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import csv
import io

from database import get_db, Patient, MonthlyRecord
from dynamic_vars import (
    VariableDefinition,
    get_all_variables,
    get_all_variable_values_for_cohort,
    upsert_variable_value,
)
from config import templates
from dependencies import get_user
from dashboard_logic import get_current_month_str
from constants import VAR_TO_MONTHLY
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/variables", tags=["variables"])


def _monthly_field_values(db: Session, field: str, patient_ids: list[int], from_m: str, to_m: str) -> dict:
    """Pull {patient_id: {month: value}} from MonthlyRecord for a core column."""
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


# ── Variable manager UI ───────────────────────────────────────────────────────

@router.get("/manager", response_class=HTMLResponse)
async def variable_manager(request: Request, db: Session = Depends(get_db)):
    variables = get_all_variables(db, active_only=False)

    defined_names = {v.name for v in variables}

    class VirtualVar:
        def __init__(self, id, name, display_name):
            self.id = id; self.name = name; self.display_name = display_name
            self.category = "Core"; self.is_active = True; self.unit = ""
            self.data_type = "number"; self.decimal_places = 1
            self.threshold_low = None; self.threshold_high = None
            self.target_low = None; self.target_high = None
            self.description = "Core clinical variable from monthly records"
            self.show_in_dashboard = True; self.show_in_timeline = True
            self.alert_direction = "both"

    core_display = {
        "hb": "Hemoglobin", "albumin": "Albumin", "phosphorus": "Phosphorus",
        "calcium": "Calcium", "alkaline_phosphate": "Alk. Phos.", "ipth": "iPTH",
        "vit_d": "Vitamin D", "ferritin": "Ferritin", "tsat": "TSAT",
        "serum_iron": "Serum Iron", "tibc": "TIBC", "urr": "URR", "kt_v": "Kt/V",
        "bicarbonate": "Bicarbonate", "uric_acid": "Uric Acid", "creatinine": "Creatinine",
        "sodium": "Sodium", "potassium": "Potassium", "crp": "CRP",
        "systolic_bp_pre": "Systolic BP (Pre)", "idwg": "IDWG",
        "dry_weight": "Target Dry Weight", "nt_probnp": "NT-ProBNP",
        "ef": "Ejection Fraction", "wbc": "WBC Count", "platelets": "Platelet Count",
    }

    core_keys = list(VAR_TO_MONTHLY.keys())
    core_vars = [
        VirtualVar(-(i + 1), name, core_display.get(name, name.replace("_", " ").title()))
        for i, name in enumerate(core_keys)
        if name not in defined_names
    ]

    all_vars = variables + core_vars
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()

    vars_json = [
        {
            "id": v.id, "name": v.name, "display_name": v.display_name,
            "unit": getattr(v, "unit", ""), "category": v.category,
            "data_type": getattr(v, "data_type", "number"),
            "decimal_places": getattr(v, "decimal_places", 1),
            "threshold_low": getattr(v, "threshold_low", None),
            "threshold_high": getattr(v, "threshold_high", None),
            "target_low": getattr(v, "target_low", None),
            "target_high": getattr(v, "target_high", None),
            "description": getattr(v, "description", ""),
            "normal_range": getattr(v, "normal_range", None),
            "clinical_significance": getattr(v, "clinical_significance", None),
            "show_in_dashboard": getattr(v, "show_in_dashboard", True),
            "show_in_timeline": getattr(v, "show_in_timeline", True),
            "alert_direction": getattr(v, "alert_direction", "both"),
            "is_active": getattr(v, "is_active", True),
        }
        for v in all_vars
    ]

    return templates.TemplateResponse("variable_manager.html", {
        "request": request, "variables": all_vars, "variables_json": vars_json,
        "patient_list_data": [{"id": p.id, "name": p.name, "hid": p.hid_no} for p in patients],
        "patients": patients,
        "default_from": "2023-01", "default_to": get_current_month_str(),
        "user": get_user(request),
    })


# ── Export endpoints ─────────────────────────────────────────────────────────

@router.get("/export/definitions")
async def export_definitions(
    request: Request,
    format: str = Query("json"),
    db: Session = Depends(get_db)
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    custom_vars = db.query(VariableDefinition).order_by(VariableDefinition.category, VariableDefinition.display_name).all()

    core_display = {
        "hb": "Hemoglobin", "albumin": "Albumin", "phosphorus": "Phosphorus",
        "calcium": "Calcium", "alkaline_phosphate": "Alk. Phos.", "ipth": "iPTH",
        "vit_d": "Vitamin D", "ferritin": "Ferritin", "tsat": "TSAT",
        "serum_iron": "Serum Iron", "tibc": "TIBC", "urr": "URR", "kt_v": "Kt/V",
        "bicarbonate": "Bicarbonate", "uric_acid": "Uric Acid", "creatinine": "Creatinine",
        "sodium": "Sodium", "potassium": "Potassium", "crp": "CRP",
        "systolic_bp_pre": "Systolic BP (Pre)", "idwg": "IDWG",
        "dry_weight": "Target Dry Weight", "nt_probnp": "NT-ProBNP",
        "ef": "Ejection Fraction", "wbc": "WBC Count", "platelets": "Platelet Count",
    }

    defined_names = {v.name for v in custom_vars}

    defs_list = []
    # Custom definitions first
    for v in custom_vars:
        defs_list.append({
            "name": v.name,
            "display_name": v.display_name,
            "unit": v.unit or "",
            "category": v.category,
            "data_type": v.data_type,
            "threshold_low": v.threshold_low,
            "threshold_high": v.threshold_high,
            "target_low": v.target_low,
            "target_high": v.target_high,
            "description": v.description or "",
            "normal_range": v.normal_range or "",
            "clinical_significance": v.clinical_significance or "",
            "is_active": v.is_active,
            "source": "Custom"
        })

    # Virtual core definitions next
    for name, disp in core_display.items():
        if name not in defined_names:
            defs_list.append({
                "name": name,
                "display_name": disp,
                "unit": "",
                "category": "Core",
                "data_type": "number",
                "threshold_low": None,
                "threshold_high": None,
                "target_low": None,
                "target_high": None,
                "description": "Core clinical variable from monthly records",
                "normal_range": "",
                "clinical_significance": "",
                "is_active": True,
                "source": "Core"
            })

    if format == "csv":
        output = io.StringIO()
        headers = ["name", "display_name", "unit", "category", "data_type", "threshold_low",
                   "threshold_high", "target_low", "target_high", "description",
                   "normal_range", "clinical_significance", "is_active", "source"]
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        for row in defs_list:
            row_clean = {k: ("" if v is None else str(v)) for k, v in row.items()}
            writer.writerow(row_clean)
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=clinical_variable_definitions.csv"}
        )

    return defs_list


@router.get("/export/values")
async def export_values(
    request: Request,
    format: str = Query("json"),
    db: Session = Depends(get_db)
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    custom_vars = db.query(VariableDefinition).all()
    custom_var_names = [v.name for v in custom_vars]

    patients = db.query(Patient).all()
    patient_map = {p.id: p for p in patients}

    records = db.query(MonthlyRecord).order_by(MonthlyRecord.record_month.desc(), MonthlyRecord.patient_id).all()

    export_data = []
    for r in records:
        p = patient_map.get(r.patient_id)
        if not p:
            continue

        row = {
            "patient_id": p.id,
            "patient_name": p.name,
            "hid_no": p.hid_no,
            "record_month": r.record_month,
            "entered_by": r.entered_by or "",
        }

        # Add core variables
        for var_name, db_col in VAR_TO_MONTHLY.items():
            val = getattr(r, db_col, None)
            if val is None and r.dynamic_data:
                entry = r.dynamic_data.get(var_name)
                if isinstance(entry, dict):
                    val = entry.get("v") if entry.get("v") is not None else entry.get("t")
            row[var_name] = val

        # Add custom dynamic variables
        dynamic_data = r.dynamic_data or {}
        for var_name in custom_var_names:
            if var_name in VAR_TO_MONTHLY:
                continue
            entry = dynamic_data.get(var_name)
            val = None
            if entry and isinstance(entry, dict):
                val = entry.get("v") if entry.get("v") is not None else entry.get("t")
            row[var_name] = val

        export_data.append(row)

    if format == "csv":
        output = io.StringIO()
        headers = ["patient_id", "patient_name", "hid_no", "record_month", "entered_by"]
        headers.extend(list(VAR_TO_MONTHLY.keys()))
        for name in custom_var_names:
            if name not in VAR_TO_MONTHLY:
                headers.append(name)

        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        for row in export_data:
            row_clean = {k: ("" if v is None else str(v)) for k, v in row.items()}
            writer.writerow(row_clean)
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=patient_variables_data.csv"}
        )

    return export_data


# ── Variable definition CRUD ──────────────────────────────────────────────────

@router.post("")
async def api_create_variable(payload: dict, db: Session = Depends(get_db)):
    if db.query(VariableDefinition).filter(VariableDefinition.name == payload.get("name")).first():
        raise HTTPException(status_code=400, detail="Variable name already exists")
    vdef = VariableDefinition(**{k: v for k, v in payload.items() if hasattr(VariableDefinition, k)})
    db.add(vdef)
    db.commit()
    db.refresh(vdef)
    return {"id": vdef.id, "name": vdef.name}


@router.put("/{var_id}")
async def api_update_variable(var_id: int, payload: dict, db: Session = Depends(get_db)):
    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
    if not vdef:
        raise HTTPException(status_code=404, detail="Variable not found")
    for k, v in payload.items():
        if hasattr(vdef, k) and k not in ("id", "created_at"):
            setattr(vdef, k, v)
    db.commit()
    return {"ok": True}


@router.post("/{var_id}/toggle")
async def api_toggle_variable(var_id: int, db: Session = Depends(get_db)):
    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
    if not vdef:
        raise HTTPException(status_code=404, detail="Variable not found")
    vdef.is_active = not vdef.is_active
    db.commit()
    return {"is_active": vdef.is_active}


# ── Variable data reads ───────────────────────────────────────────────────────

def _resolve_var(db: Session, var_id: int) -> tuple[str, Optional[VariableDefinition]]:
    """Return (var_name, vdef_or_None). Handles positive IDs (defined) and negative (core)."""
    if var_id > 0:
        vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
        if not vdef:
            raise HTTPException(status_code=404, detail="Variable not found")
        return vdef.name, vdef
    idx = abs(var_id) - 1
    core_list = list(VAR_TO_MONTHLY.keys())
    if idx >= len(core_list):
        raise HTTPException(status_code=404, detail="Core variable not found")
    return core_list[idx], None


def _get_var_data(
    db: Session, var_id: int, patient_ids: list[int] | None = None,
    from_m: str = "2020-01", to_m: str | None = None,
) -> tuple[dict, dict, str, str]:
    """Unified data fetch for a variable (dynamic JSONB or core MonthlyRecord column).

    Returns: (all_data, thresholds, var_name, unit)
    all_data shape: {patient_id: {month: float}}
    """
    to_m = to_m or get_current_month_str()
    var_name, vdef = _resolve_var(db, var_id)
    thresholds = {
        "low": vdef.threshold_low if vdef else None,
        "high": vdef.threshold_high if vdef else None,
        "target_low": vdef.target_low if vdef else None,
        "target_high": vdef.target_high if vdef else None,
    }
    unit = vdef.unit if vdef else ""

    if patient_ids is None:
        patient_ids = [p.id for p in db.query(Patient).filter(Patient.is_active == True).all()]

    all_data: dict = {}

    # Dynamic variable: read from JSONB
    if var_id > 0:
        all_data = get_all_variable_values_for_cohort(db, var_name, patient_ids, from_m, to_m)

    # Core variable: read from MonthlyRecord column, fill gaps
    monthly_field = VAR_TO_MONTHLY.get(var_name)
    if monthly_field:
        bridged = _monthly_field_values(db, monthly_field, patient_ids, from_m, to_m)
        for pid, months in bridged.items():
            for month, val in months.items():
                all_data.setdefault(pid, {}).setdefault(month, val)

    return all_data, thresholds, var_name, unit


@router.get("/{var_id}/values")
async def api_get_variable_values(var_id: int, request: Request, db: Session = Depends(get_db)):
    from_m = request.query_params.get("from", "2023-01")
    to_m   = request.query_params.get("to", get_current_month_str())
    patient_ids = [p.id for p in db.query(Patient).filter(Patient.is_active == True).all()]
    all_data, _, _, _ = _get_var_data(db, var_id, patient_ids, from_m, to_m)
    return all_data


# ── Variable value write ──────────────────────────────────────────────────────

@router.post("/value")
async def api_upsert_value(payload: dict, db: Session = Depends(get_db)):
    patient_id = int(payload["patient_id"])
    var_id     = int(payload["variable_id"])
    val_num    = payload.get("value_num")
    month_str  = payload["record_month"]
    entered_by = payload.get("entered_by", "Variable Manager")

    var_name, vdef = _resolve_var(db, var_id)

    if var_id > 0:
        upsert_variable_value(
            db, patient_id=patient_id, month_str=month_str,
            variable_id=var_id, value_num=val_num,
            value_text=payload.get("value_text"), entered_by=entered_by,
        )

    # Sync to MonthlyRecord core column when it's a mapped core variable
    monthly_field = VAR_TO_MONTHLY.get(var_name)
    if monthly_field:
        rec = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month == month_str,
        ).first()
        if not rec:
            rec = MonthlyRecord(patient_id=patient_id, record_month=month_str, entered_by=entered_by)
            db.add(rec)
        if hasattr(rec, monthly_field):
            setattr(rec, monthly_field, val_num)
            db.commit()

    # Fire critical alert if threshold breached
    if val_num is not None and vdef is not None:
        _maybe_send_alert(db, patient_id, month_str, vdef, val_num, entered_by)

    return {"ok": True}


def _maybe_send_alert(db, patient_id, month_str, vdef, val_num, entered_by):
    t_low  = getattr(vdef, "threshold_low", None)
    t_high = getattr(vdef, "threshold_high", None)
    alert_msg = None
    if t_low is not None and val_num < t_low:
        alert_msg = f"Low {vdef.display_name} ({val_num} {vdef.unit or ''})"
    elif t_high is not None and val_num > t_high:
        alert_msg = f"High {vdef.display_name} ({val_num} {vdef.unit or ''})"
    if not alert_msg:
        return
    from alerts import send_entry_alert_email
    from dashboard_logic import get_month_label
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if p:
        send_entry_alert_email(
            patient_name=p.name, hid=p.hid_no,
            month_label=get_month_label(month_str),
            alerts=[alert_msg], labs={vdef.name: val_num},
            entered_by=entered_by,
        )


# ── Summary endpoint (used by variable manager charts) ───────────────────────

@router.get("/{var_id}/summary")
async def api_variable_summary(
    var_id: int,
    var2_id: Optional[int] = None,
    var3_id: Optional[int] = None,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    patient_filter: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    patients_q = db.query(Patient).filter(Patient.is_active == True)
    if patient_filter:
        patients_q = patients_q.filter(Patient.name.ilike(f"%{patient_filter}%"))
    patients_q = patients_q.order_by(Patient.name)
    patients = patients_q.all()
    patient_ids = [p.id for p in patients]

    from_m = date_from or "2020-01"
    to_m   = date_to   or get_current_month_str()
    all_data, thresholds, var_name, unit = _get_var_data(db, var_id, patient_ids, from_m=from_m, to_m=to_m)

    patient_rows = [
        {
            "id": p.id, "name": p.name, "hid": p.hid_no,
            "latest_value": (lambda m: m[max(m)] if m else None)(all_data.get(p.id, {})),
            "gender": p.sex, "age": p.age,
            "access_type": p.access_type, "shift": p.hd_slot_1 or "N/A",
        }
        for p in patients
    ]

    # Trend (monthly median + IQR)
    month_buckets: dict = {}
    for pid, months in all_data.items():
        for m, v in months.items():
            if v is not None:
                month_buckets.setdefault(m, []).append(v)

    def _pct(vals, p):
        n = len(vals)
        if not n:
            return None
        i = (p / 100) * (n - 1)
        lo, hi = int(i), min(int(i) + 1, n - 1)
        return vals[lo] + (vals[hi] - vals[lo]) * (i - lo)

    trend = [
        {
            "month": m,
            "median": round(v50, 2) if (v50 := _pct(sorted(month_buckets[m]), 50)) is not None else None,
            "p25":    round(v25, 2) if (v25 := _pct(sorted(month_buckets[m]), 25)) is not None else None,
            "p75":    round(v75, 2) if (v75 := _pct(sorted(month_buckets[m]), 75)) is not None else None,
        }
        for m in sorted(month_buckets)
    ]

    res = {
        "var_name": var_name, "unit": unit,
        "patients": patient_rows, "trend": trend,
        "all_data": all_data, "thresholds": thresholds,
    }

    for extra_id, key in [(var2_id, "var2"), (var3_id, "var3")]:
        if extra_id:
            d, t, n, u = _get_var_data(db, extra_id, patient_ids)
            if d is not None:
                res[key] = {"name": n, "unit": u, "all_data": d, "thresholds": t}

    months_with_data = sorted(month_buckets.keys(), reverse=True)
    if len(months_with_data) >= 2:
        curr_m, prev_m = months_with_data[0], months_with_data[1]
        res["trajectory"] = [
            {"name": p["name"], "prev": p_m.get(prev_m), "curr": p_m.get(curr_m),
             "month_prev": prev_m, "month_curr": curr_m}
            for p in patient_rows
            if (p_m := all_data.get(p["id"], {})) and p_m.get(curr_m) is not None and p_m.get(prev_m) is not None
        ]

    return res
