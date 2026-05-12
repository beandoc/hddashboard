from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date as date_type, datetime
from collections import defaultdict
import json
import numpy as np
from scipy import stats as scipy_stats

from database import get_db, Patient, ResearchProject, ResearchRecord, MonthlyRecord, SessionRecord
from config import templates
from dependencies import get_user, _require_admin_role, _require_researcher_role

# ── Statistical Testing Module ─────────────────────────────────────────────────

STAT_VARS = {
    "hb": ("Hemoglobin", "g/dL"),
    "albumin": ("Albumin", "g/dL"),
    "phosphorus": ("Phosphorus", "mg/dL"),
    "calcium": ("Calcium", "mg/dL"),
    "single_pool_ktv": ("Kt/V (spKt/V)", ""),
    "urr": ("URR", "%"),
    "serum_creatinine": ("Creatinine", "mg/dL"),
    "serum_ferritin": ("Ferritin", "ng/mL"),
    "tsat": ("TSAT", "%"),
    "ipth": ("iPTH", "pg/mL"),
    "vit_d": ("Vitamin D", "ng/mL"),
    "serum_potassium": ("Potassium", "mEq/L"),
    "serum_sodium": ("Sodium", "mEq/L"),
    "serum_bicarbonate": ("Bicarbonate", "mEq/L"),
    "serum_uric_acid": ("Uric Acid", "mg/dL"),
    "crp": ("CRP", "mg/L"),
    "bp_sys": ("Systolic BP", "mmHg"),
    "bp_dia": ("Diastolic BP", "mmHg"),
    "idwg": ("IDWG", "kg"),
    "target_dry_weight": ("Target Dry Weight", "kg"),
    "nt_probnp": ("NT-ProBNP", "pg/mL"),
    "ejection_fraction": ("Ejection Fraction", "%"),
    "wbc_count": ("WBC Count", "×10³/μL"),
    "platelet_count": ("Platelet Count", "×10³/μL"),
    "total_cholesterol": ("Total Cholesterol", "mg/dL"),
    "ldl_cholesterol": ("LDL Cholesterol", "mg/dL"),
    "npcr": ("nPCR", "g/kg/day"),
    "ufr": ("UFR", "mL/h/kg"),
    "prealbumin": ("Prealbumin", "mg/dL"),
    "hba1c": ("HbA1c", "%"),
    "ast": ("AST", "IU/L"),
    "alt": ("ALT", "IU/L"),
    "troponin_i": ("Troponin I", "ng/mL"),
    "il6": ("IL-6", "pg/mL"),
    "tnf_alpha": ("TNF-α", "pg/mL"),
    "hrqol_score": ("HRQoL Score", ""),
    "mis_score": ("MIS Score", ""),
}

# (label, source) — source is "patient" (Patient model) or "monthly" (MonthlyRecord)
STAT_GROUPS = {
    "sex": ("Sex", "patient"),
    "dm_status": ("Diabetes Status", "patient"),
    "htn_status": ("Hypertension", "patient"),
    "cad_status": ("Coronary Artery Disease", "patient"),
    "chf_status": ("Congestive Heart Failure", "patient"),
    "history_of_stroke": ("History of Stroke", "patient"),
    "smoking_status": ("Smoking Status", "patient"),
    "access_type": ("Vascular Access Type", "monthly"),
    "primary_renal_disease": ("Primary Renal Disease", "patient"),
}


def _group_label(val):
    if val is None or val == "" or str(val).lower() in ("none", "nan"):
        return None
    if isinstance(val, bool):
        return "Yes" if val else "No"
    return str(val)


def _get_per_patient_values(records, variable, patients, group_source=None, group_field=None):
    vals = defaultdict(list)
    monthly_groups = defaultdict(list)

    for r in records:
        v = getattr(r, variable, None)
        if v is not None:
            try:
                vals[r.patient_id].append(float(v))
            except (TypeError, ValueError):
                pass
        if group_source == "monthly" and group_field:
            gv = getattr(r, group_field, None)
            lbl = _group_label(gv)
            if lbl:
                monthly_groups[r.patient_id].append(lbl)

    result = []
    for pid, vs in vals.items():
        if not vs:
            continue
        p = patients.get(pid)
        group = None
        if group_field:
            if group_source == "patient" and p:
                group = _group_label(getattr(p, group_field, None))
            elif group_source == "monthly":
                mg = monthly_groups.get(pid, [])
                group = max(set(mg), key=mg.count) if mg else None
        result.append({
            "patient_id": pid,
            "value": sum(vs) / len(vs),
            "n_obs": len(vs),
            "group": group,
            "name": p.name if p else f"Patient {pid}",
        })
    return result


def _descriptive_stats(values):
    arr = np.array(values, dtype=float)
    n = len(arr)
    if n == 0:
        return {}
    q1, q3 = np.percentile(arr, [25, 75])
    result = {
        "n": n,
        "mean": round(float(np.mean(arr)), 3),
        "sd": round(float(np.std(arr, ddof=1)), 3) if n > 1 else 0.0,
        "median": round(float(np.median(arr)), 3),
        "q1": round(float(q1), 3),
        "q3": round(float(q3), 3),
        "min": round(float(np.min(arr)), 3),
        "max": round(float(np.max(arr)), 3),
    }
    if 3 <= n <= 5000:
        stat, p = scipy_stats.shapiro(arr)
        result["shapiro_w"] = round(float(stat), 4)
        result["shapiro_p"] = float(p)
        result["is_normal"] = bool(p > 0.05)
    hist, edges = np.histogram(arr, bins=min(20, max(5, n // 3)))
    result["hist_counts"] = hist.tolist()
    result["hist_edges"] = [round(float(e), 3) for e in edges.tolist()]
    return result

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/stats", response_class=HTMLResponse)
async def stats_module(request: Request, db: Session = Depends(get_db)):
    user = get_user(request)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)
    role = user.get("role") if isinstance(user, dict) else getattr(user, "role", "")
    if role not in ("admin", "doctor", "staff"):
        raise HTTPException(status_code=403, detail="Access denied")
    patient_count = db.query(Patient).filter(Patient.is_active == True).count()
    return templates.TemplateResponse("research_stats.html", {
        "request": request,
        "user": user,
        "patient_count": patient_count,
        "stat_vars": STAT_VARS,
        "stat_groups": STAT_GROUPS,
    })


@router.post("/stats/run")
async def run_stat_test(request: Request, db: Session = Depends(get_db)):
    _require_admin_role(request)
    body = await request.json()

    test_type = body.get("test_type", "descriptive")
    variable = body.get("variable", "hb")
    variable2 = body.get("variable2")
    group_by = body.get("group_by")
    date_from = body.get("date_from", "2020-01")
    date_to = body.get("date_to", "2099-12")

    if variable not in STAT_VARS:
        raise HTTPException(status_code=400, detail=f"Unknown variable: {variable}")

    var_label, var_unit = STAT_VARS[variable]

    records = db.query(MonthlyRecord).filter(
        MonthlyRecord.record_month >= date_from,
        MonthlyRecord.record_month <= date_to,
    ).all()

    patients = {p.id: p for p in db.query(Patient).all()}

    # ── Descriptive ───────────────────────────────────────────────────────────
    if test_type == "descriptive":
        data = _get_per_patient_values(records, variable, patients)
        values = [d["value"] for d in data]
        if len(values) < 2:
            return JSONResponse({"error": "Insufficient data (need at least 2 patients with recorded values)"})
        stats = _descriptive_stats(values)
        return JSONResponse({
            "test_type": "descriptive",
            "variable": var_label,
            "unit": var_unit,
            "stats": stats,
            "patient_values": [
                {"name": d["name"], "value": round(d["value"], 2)}
                for d in sorted(data, key=lambda x: x["value"])
            ],
        })

    # ── Group Comparison ──────────────────────────────────────────────────────
    elif test_type == "group_comparison":
        if not group_by or group_by not in STAT_GROUPS:
            raise HTTPException(status_code=400, detail="Invalid group_by field")
        group_label, group_source = STAT_GROUPS[group_by]
        data = _get_per_patient_values(records, variable, patients, group_source, group_by)

        groups: dict[str, list] = defaultdict(list)
        for d in data:
            if d["group"]:
                groups[d["group"]].append(d["value"])
        groups = {k: v for k, v in groups.items() if len(v) >= 2}

        if len(groups) < 2:
            return JSONResponse({"error": "Need at least 2 groups with ≥2 observations each"})

        group_stats = {g: _descriptive_stats(vs) for g, vs in groups.items()}
        all_normal = all(gs.get("is_normal", False) for gs in group_stats.values())
        group_names = sorted(groups.keys())
        group_arrays = [np.array(groups[g]) for g in group_names]

        if len(groups) == 2:
            if all_normal:
                stat, p = scipy_stats.ttest_ind(*group_arrays, equal_var=False)
                test_name = "Welch's t-test"
                pooled_sd = np.sqrt((group_arrays[0].std(ddof=1)**2 + group_arrays[1].std(ddof=1)**2) / 2)
                effect = abs(group_arrays[0].mean() - group_arrays[1].mean()) / pooled_sd if pooled_sd else 0.0
                effect_label = "Cohen's d"
            else:
                stat, p = scipy_stats.mannwhitneyu(*group_arrays, alternative="two-sided")
                test_name = "Mann-Whitney U"
                n1, n2 = len(group_arrays[0]), len(group_arrays[1])
                effect = float(stat) / (n1 * n2)
                effect_label = "r (rank-biserial)"
        else:
            if all_normal:
                stat, p = scipy_stats.f_oneway(*group_arrays)
                test_name = "One-way ANOVA"
                all_vals = np.concatenate(group_arrays)
                grand_mean = all_vals.mean()
                ss_between = sum(len(g) * (g.mean() - grand_mean)**2 for g in group_arrays)
                ss_total = float(np.sum((all_vals - grand_mean)**2))
                effect = ss_between / ss_total if ss_total > 0 else 0.0
                effect_label = "η²"
            else:
                stat, p = scipy_stats.kruskal(*group_arrays)
                test_name = "Kruskal-Wallis H"
                n_total = sum(len(g) for g in group_arrays)
                effect = (float(stat) - len(groups) + 1) / (n_total - len(groups)) if n_total > len(groups) else 0.0
                effect_label = "ε²"

        return JSONResponse({
            "test_type": "group_comparison",
            "variable": var_label,
            "unit": var_unit,
            "group_by": group_label,
            "test_name": test_name,
            "statistic": round(float(stat), 4),
            "p_value": float(p),
            "significance": "p < 0.001" if p < 0.001 else f"p = {p:.3f}",
            "is_significant": bool(p < 0.05),
            "effect_size": round(float(effect), 3),
            "effect_label": effect_label,
            "all_normal": all_normal,
            "groups": {
                g: {
                    "n": group_stats[g]["n"],
                    "mean": group_stats[g]["mean"],
                    "sd": group_stats[g]["sd"],
                    "median": group_stats[g]["median"],
                    "q1": group_stats[g]["q1"],
                    "q3": group_stats[g]["q3"],
                    "values": [round(v, 2) for v in groups[g]],
                }
                for g in group_names
            },
        })

    # ── Correlation ───────────────────────────────────────────────────────────
    elif test_type == "correlation":
        if not variable2 or variable2 not in STAT_VARS:
            raise HTTPException(status_code=400, detail="Invalid variable2")
        var2_label, var2_unit = STAT_VARS[variable2]

        data1 = {d["patient_id"]: d["value"] for d in _get_per_patient_values(records, variable, patients)}
        data2 = {d["patient_id"]: d["value"] for d in _get_per_patient_values(records, variable2, patients)}
        common_pids = list(set(data1.keys()) & set(data2.keys()))

        if len(common_pids) < 5:
            return JSONResponse({"error": "Insufficient paired data (need at least 5 patients with both values)"})

        x = [data1[pid] for pid in common_pids]
        y = [data2[pid] for pid in common_pids]
        names = [patients[pid].name if pid in patients else f"P{pid}" for pid in common_pids]

        pearson_r, pearson_p = scipy_stats.pearsonr(x, y)
        spearman_r, spearman_p = scipy_stats.spearmanr(x, y)
        slope, intercept, r_lin, _, _ = scipy_stats.linregress(x, y)

        x_line = [min(x), max(x)]
        y_line = [intercept + slope * v for v in x_line]

        return JSONResponse({
            "test_type": "correlation",
            "variable": var_label,
            "unit": var_unit,
            "variable2": var2_label,
            "unit2": var2_unit,
            "n": len(common_pids),
            "pearson_r": round(float(pearson_r), 3),
            "pearson_p": float(pearson_p),
            "spearman_r": round(float(spearman_r), 3),
            "spearman_p": float(spearman_p),
            "r_squared": round(float(r_lin**2), 3),
            "slope": round(float(slope), 4),
            "intercept": round(float(intercept), 4),
            "scatter_x": [round(v, 2) for v in x],
            "scatter_y": [round(v, 2) for v in y],
            "scatter_names": names,
            "reg_x": [round(v, 2) for v in x_line],
            "reg_y": [round(v, 2) for v in y_line],
        })

    # ── Trend ─────────────────────────────────────────────────────────────────
    elif test_type == "trend":
        monthly_vals: dict[str, list] = defaultdict(list)
        for r in records:
            v = getattr(r, variable, None)
            if v is not None:
                try:
                    monthly_vals[r.record_month].append(float(v))
                except (TypeError, ValueError):
                    pass

        if len(monthly_vals) < 3:
            return JSONResponse({"error": "Need at least 3 months of data for trend analysis"})

        sorted_months = sorted(monthly_vals.keys())
        medians = [float(np.median(monthly_vals[m])) for m in sorted_months]
        q1s = [float(np.percentile(monthly_vals[m], 25)) for m in sorted_months]
        q3s = [float(np.percentile(monthly_vals[m], 75)) for m in sorted_months]
        ns = [len(monthly_vals[m]) for m in sorted_months]

        x_idx = list(range(len(sorted_months)))
        slope, intercept, r_lin, p, _ = scipy_stats.linregress(x_idx, medians)
        reg_line = [round(intercept + slope * i, 3) for i in x_idx]

        return JSONResponse({
            "test_type": "trend",
            "variable": var_label,
            "unit": var_unit,
            "months": sorted_months,
            "medians": [round(v, 3) for v in medians],
            "q1s": [round(v, 3) for v in q1s],
            "q3s": [round(v, 3) for v in q3s],
            "ns": ns,
            "slope": round(float(slope), 4),
            "r_squared": round(float(r_lin**2), 3),
            "p_value": float(p),
            "is_significant": bool(p < 0.05),
            "trend_direction": "increasing" if slope > 0 else "decreasing",
            "regression_line": reg_line,
        })

    else:
        raise HTTPException(status_code=400, detail=f"Unknown test_type: {test_type}")

@router.get("", response_class=HTMLResponse)
async def research_hub(request: Request, db: Session = Depends(get_db)):
    _require_researcher_role(request)
    projects = db.query(ResearchProject).order_by(ResearchProject.created_at.desc()).all()
    return templates.TemplateResponse("research_hub.html", {
        "request": request,
        "projects": projects,
        "user": get_user(request)
    })

@router.post("/projects")
async def create_project(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    _require_admin_role(request)
    project = ResearchProject(title=title, description=description)
    db.add(project)
    db.commit()
    return RedirectResponse(url="/research", status_code=303)

@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def view_project(project_id: int, request: Request, db: Session = Depends(get_db)):
    _require_researcher_role(request)
    project = db.query(ResearchProject).filter(ResearchProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404)
        
    records = db.query(ResearchRecord).filter(ResearchRecord.project_id == project_id).order_by(ResearchRecord.test_date.desc()).all()
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    
    # Parse JSON data for display
    parsed_records = []
    for r in records:
        try:
            parsed_data = json.loads(r.data) if r.data else {}
        except:
            parsed_data = {}
        parsed_records.append({"record": r, "parsed_data": parsed_data, "patient": r.patient})
        
    return templates.TemplateResponse("research_project.html", {
        "request": request,
        "project": project,
        "records": parsed_records,
        "patients": patients,
        "user": get_user(request)
    })

@router.get("/projects/{project_id}/record", response_class=HTMLResponse)
async def new_record_form(project_id: int, patient_id: int, test_type: str, request: Request, db: Session = Depends(get_db)):
    project = db.query(ResearchProject).filter(ResearchProject.id == project_id).first()
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not project or not patient:
        raise HTTPException(status_code=404)
        
    from dynamic_vars import get_all_variables
    all_variables = get_all_variables(db)

    # Fetch latest clinical data for auto-filling
    latest_monthly = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).first()
    latest_session = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).first()

    dialysis_years = None
    if patient.hd_wef_date:
        from datetime import date as date_obj
        delta = date_obj.today() - patient.hd_wef_date
        dialysis_years = round(delta.days / 365.25, 1)
        
    return templates.TemplateResponse("research_record_form.html", {
        "request": request,
        "project": project,
        "patient": patient,
        "test_type": test_type,
        "all_variables": all_variables,
        "latest_monthly": latest_monthly,
        "latest_session": latest_session,
        "dialysis_years": dialysis_years,
        "user": get_user(request)
    })

@router.post("/projects/{project_id}/record")
async def save_record(
    project_id: int,
    request: Request,
    patient_id: int = Form(...),
    test_type: str = Form(...),
    test_date: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db)
):
    _require_researcher_role(request)
    user = get_user(request)

    form_data = await request.form()
    
    # Extract all test-specific fields (exclude standard fields)
    standard_fields = ["patient_id", "test_type", "test_date", "notes"]
    test_data = {}
    for key, value in form_data.items():
        if key not in standard_fields and value != "":
            test_data[key] = value
            
    try:
        parsed_date = datetime.strptime(test_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        parsed_date = date_type.today()

    record = ResearchRecord(
        project_id=project_id,
        patient_id=patient_id,
        test_type=test_type,
        test_date=parsed_date,
        data=json.dumps(test_data),
        notes=notes,
        entered_by=(user.get("username") if isinstance(user, dict) else user.username) if user else "Admin"
    )
    
    db.add(record)
    db.commit()
    return RedirectResponse(url=f"/research/projects/{project_id}", status_code=303)

@router.post("/projects/{project_id}/delete")
async def delete_project(project_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin_role(request)
    project = db.query(ResearchProject).filter(ResearchProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404)
    db.delete(project)
    db.commit()
    return RedirectResponse(url="/research", status_code=303)

@router.post("/projects/{project_id}/records/{record_id}/delete")
async def delete_record(project_id: int, record_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin_role(request)
    record = db.query(ResearchRecord).filter(ResearchRecord.id == record_id, ResearchRecord.project_id == project_id).first()
    if not record:
        raise HTTPException(status_code=404)
    db.delete(record)
    db.commit()
    return RedirectResponse(url=f"/research/projects/{project_id}", status_code=303)
