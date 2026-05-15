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
from ml_analytics import (
    run_cohort_analytics,
    run_group_comparison,
    run_correlation_analysis,
    run_survival_analysis,
    run_logrank_test,
    run_cox_ph,
    run_bayesian_multilevel,
)


def _survival_endpoint(p, study_end):
    """Return (event_date, event_flag) with proper cause-specific censoring.

    Competing events (transplant, transfer, withdrawal) are censored at the date
    they occurred rather than at study_end. This prevents inflation of at-risk
    time for patients who left dialysis follow-up before the study end date.
    """
    if p.date_of_death and p.date_of_death <= study_end:
        return p.date_of_death, 1

    competing = []
    if getattr(p, "date_of_transplant", None) and p.date_of_transplant <= study_end:
        competing.append(p.date_of_transplant)
    if p.date_facility_transfer and p.date_facility_transfer <= study_end:
        competing.append(p.date_facility_transfer)
    if p.withdrawal_date and p.withdrawal_date <= study_end:
        competing.append(p.withdrawal_date)

    censor_date = min(competing) if competing else study_end
    return censor_date, 0

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
    # ── Tier-1 Derived Variables (computed at query time from existing fields) ─
    "nlr":                        ("NLR (Neutrophil : Lymphocyte)",  "ratio"),
    "pulse_pressure":             ("Pulse Pressure",                  "mmHg"),
    "bmi":                        ("BMI",                             "kg/m²"),
    "hd_vintage_months":          ("HD Vintage",                      "months"),
    "idh_count_month":            ("IDH Episodes / Month",            "n"),
    "session_compliance_pct":     ("Session Compliance Rate",         "%"),
    "dialysis_time_shortfall_mins": ("Dialysis Time Shortfall",       "min/session"),
}

DERIVED_VARS = {
    "nlr", "pulse_pressure", "bmi", "hd_vintage_months",
    "idh_count_month", "session_compliance_pct", "dialysis_time_shortfall_mins",
}
_SESSION_DERIVED_VARS = {"idh_count_month", "session_compliance_pct", "dialysis_time_shortfall_mins"}

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
    "primary_cause_of_death": ("Cause of Death", "patient"),
}


# Patient-level binary covariates available for Cox PH and Bayesian MLM.
# (label, encoding_hint) — encoding_hint: "bool" for Boolean fields, "dm" for dm_status, "sex_f" for sex
COX_COVARIATES = {
    "sex":               ("Female Sex",          "sex_f"),
    "dm_status":         ("Diabetes",             "dm"),
    "htn_status":        ("Hypertension",          "bool"),
    "cad_status":        ("Coronary Artery Disease","bool"),
    "chf_status":        ("CHF",                  "bool"),
    "history_of_stroke": ("Stroke History",        "bool"),
    "history_of_pvd":    ("Peripheral Vascular Disease", "bool"),
    "smoking_status":    ("Current Smoker",        "smoke"),
}


def _encode_cox_covariate(patient, field: str, hint: str) -> Optional[float]:
    """Return 0/1 encoding for a patient-level covariate, or None if unknown."""
    val = getattr(patient, field, None)
    if val is None:
        return None
    if hint == "bool":
        if isinstance(val, bool):
            return 1.0 if val else 0.0
        s = str(val).strip().lower()
        if s in ("true", "yes", "1"):
            return 1.0
        if s in ("false", "no", "0", "none", ""):
            return 0.0
        return None
    if hint == "dm":
        s = str(val).strip().lower()
        return 0.0 if s in ("none", "", "no", "false") else 1.0
    if hint == "sex_f":
        s = str(val).strip().lower()
        if s in ("female", "f"):
            return 1.0
        if s in ("male", "m"):
            return 0.0
        return None
    if hint == "smoke":
        s = str(val).strip().lower()
        return 1.0 if "current" in s else 0.0
    return None


def _group_label(val):
    if val is None or val == "" or str(val).lower() in ("none", "nan"):
        return None
    if isinstance(val, bool):
        return "Yes" if val else "No"
    return str(val)


def _compute_derived(records, patients, sessions_by_patient_month):
    """Compute Tier-1 derived variables indexed by (patient_id, record_month)."""
    import calendar as _cal
    derived: dict = {}
    for r in records:
        pid = r.patient_id
        month = r.record_month
        key = (pid, month)
        d: dict = {}
        pat = patients.get(pid)

        # NLR — neutrophil / lymphocyte (both stored as % or abs on same scale)
        n, lc = r.neutrophil_count, r.lymphocyte_count
        if n is not None and lc is not None and lc > 0:
            d["nlr"] = round(n / lc, 2)

        # Pulse pressure
        if r.bp_sys is not None and r.bp_dia is not None:
            d["pulse_pressure"] = round(r.bp_sys - r.bp_dia, 1)

        # BMI — use this month's pre-HD weight + patient height
        if r.last_prehd_weight is not None and pat and pat.height and pat.height > 0:
            h_m = pat.height / 100.0
            d["bmi"] = round(r.last_prehd_weight / (h_m ** 2), 1)

        # HD vintage (months since hd_wef_date at start of this record month)
        if pat and pat.hd_wef_date:
            try:
                y, mo = map(int, month.split("-"))
                rec_date = datetime(y, mo, 1).date()
                vintage_days = (rec_date - pat.hd_wef_date).days
                if vintage_days >= 0:
                    d["hd_vintage_months"] = round(vintage_days / 30.44, 1)
            except Exception:
                pass

        # Session-derived variables
        sess_list = sessions_by_patient_month.get(key, [])
        if sess_list:
            d["idh_count_month"] = int(sum(1 for s in sess_list if s.idh_episode))

            if pat and pat.hd_frequency and pat.hd_frequency > 0:
                try:
                    y, mo = map(int, month.split("-"))
                    days_in_month = _cal.monthrange(y, mo)[1]
                    expected = pat.hd_frequency * days_in_month / 7.0
                    d["session_compliance_pct"] = round(
                        min(len(sess_list) / expected * 100.0, 100.0), 1
                    )
                except Exception:
                    pass

            shortfalls = []
            for s in sess_list:
                if s.scheduled_treatment_duration is not None:
                    actual_mins = (s.duration_hours or 0) * 60 + (s.duration_minutes or 0)
                    if actual_mins > 0:
                        shortfalls.append(s.scheduled_treatment_duration - actual_mins)
            if shortfalls:
                d["dialysis_time_shortfall_mins"] = round(
                    sum(shortfalls) / len(shortfalls), 1
                )

        if d:
            derived[key] = d
    return derived


def _get_per_patient_values(records, variable, patients, group_source=None, group_field=None, derived=None):
    vals = defaultdict(list)
    monthly_groups = defaultdict(list)

    for r in records:
        if derived is not None and variable in DERIVED_VARS:
            v = derived.get((r.patient_id, r.record_month), {}).get(variable)
        else:
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
    now = datetime.now().strftime("%Y-%m")
    return templates.TemplateResponse("research_stats.html", {
        "request": request,
        "user": user,
        "patient_count": patient_count,
        "stat_vars": STAT_VARS,
        "stat_groups": STAT_GROUPS,
        "cox_covariates": COX_COVARIATES,
        "now": now,
    })


@router.post("/stats/run")
async def run_stat_test(request: Request, db: Session = Depends(get_db)):
    user = get_user(request)
    role = user.get("role") if isinstance(user, dict) else getattr(user, "role", "")
    if role not in ("admin", "doctor", "staff"):
        raise HTTPException(status_code=403, detail="Access denied")
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

    active_patients = {p.id: p for p in db.query(Patient).filter(Patient.is_active == True).all()}
    active_ids = set(active_patients.keys())

    records = [
        r for r in db.query(MonthlyRecord).filter(
            MonthlyRecord.record_month >= date_from,
            MonthlyRecord.record_month <= date_to,
        ).all()
        if r.patient_id in active_ids
    ]

    patients = active_patients

    # Load per-session data only when the selected variable needs it
    sessions_by_patient_month: dict = {}
    if variable in _SESSION_DERIVED_VARS or (variable2 and variable2 in _SESSION_DERIVED_VARS):
        all_sessions = [
            s for s in db.query(SessionRecord).filter(
                SessionRecord.record_month >= date_from,
                SessionRecord.record_month <= date_to,
            ).all()
            if s.patient_id in active_ids
        ]
        for s in all_sessions:
            k = (s.patient_id, s.record_month)
            sessions_by_patient_month.setdefault(k, []).append(s)
    derived = _compute_derived(records, patients, sessions_by_patient_month)

    # ── Descriptive ───────────────────────────────────────────────────────────
    if test_type == "descriptive":
        data = _get_per_patient_values(records, variable, patients, derived=derived)
        values = [d["value"] for d in data]
        if len(values) < 2:
            return JSONResponse({"error": "Insufficient data (need at least 2 patients with recorded values)"})
        stats = _descriptive_stats(values)
        
        # Add CV% and outliers for UI
        if stats.get("n", 0) > 1:
            stats["cv_percent"] = round((stats["sd"] / stats["mean"] * 100), 1) if stats["mean"] != 0 else 0.0
            
            # Robust Outliers
            med = stats["median"]
            mad = np.median([abs(x - med) for x in values])
            stats["outliers"] = [v for v in values if abs(v - med) / (1.4826 * mad) > 3.0] if mad > 0 else []

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
        data = _get_per_patient_values(records, variable, patients, group_source, group_by, derived=derived)

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
                # Use the new robust group comparison module
                res = run_group_comparison(groups, test_type="kruskal-wallis")
                stat, p, test_name = res["statistic"], res["p_value"], "Kruskal-Wallis H"
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

        data1 = {d["patient_id"]: d["value"] for d in _get_per_patient_values(records, variable, patients, derived=derived)}
        data2 = {d["patient_id"]: d["value"] for d in _get_per_patient_values(records, variable2, patients, derived=derived)}
        common_pids = list(set(data1.keys()) & set(data2.keys()))

        n1, n2, n_both = len(data1), len(data2), len(common_pids)
        if n_both < 3:
            return JSONResponse({
                "error": (
                    f"Insufficient paired data — only {n_both} patient(s) have both variables recorded "
                    f"in this date range. "
                    f"{var_label}: {n1} patient(s) | {var2_label}: {n2} patient(s). "
                    f"Check that both fields are entered in monthly records, or widen the date range."
                )
            })
        low_n_warning = n_both < 5

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
            "low_n_warning": low_n_warning,
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
            if variable in DERIVED_VARS:
                v = derived.get((r.patient_id, r.record_month), {}).get(variable)
            else:
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

        def _month_ord(m):
            y, mo = map(int, m.split("-"))
            return y * 12 + mo

        x_ord = [_month_ord(m) for m in sorted_months]
        x0 = x_ord[0]
        x_rel = [x - x0 for x in x_ord]
        slope, intercept, r_lin, p, _ = scipy_stats.linregress(x_rel, medians)
        reg_line = [round(intercept + slope * x, 3) for x in x_rel]

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

    # ── Survival Analysis (Kaplan-Meier) ─────────────────────────────────────
    elif test_type == "survival":
        from datetime import date as date_obj
        try:
            date_to_parsed = datetime.strptime(date_to + "-01", "%Y-%m-%d").date()
        except (ValueError, TypeError):
            date_to_parsed = date_obj.today()

        all_patients = db.query(Patient).filter(Patient.hd_wef_date != None).all()

        durations, events = [], []
        for p in all_patients:
            if p.hd_wef_date > date_to_parsed:
                continue
            end_date, event = _survival_endpoint(p, date_to_parsed)
            duration_days = (end_date - p.hd_wef_date).days
            if duration_days <= 0:
                continue
            durations.append(round(duration_days / 30.44, 1))
            events.append(event)

        if len(durations) < 5:
            return JSONResponse({"error": "Insufficient data (need ≥5 patients with HD start dates recorded)"})

        res = run_survival_analysis(durations, events)
        if not res["available"]:
            return JSONResponse({"error": res["message"]})

        return JSONResponse({
            "test_type": "survival",
            "n": len(durations),
            "n_events": sum(events),
            "n_censored": len(events) - sum(events),
            "timeline": res["timeline"],
            "median_survival": res["median_survival"],
        })

    # ── Log-Rank Test (survival by group) ────────────────────────────────────
    elif test_type == "logrank":
        if not group_by or group_by not in STAT_GROUPS:
            raise HTTPException(status_code=400, detail="Invalid group_by field")
        group_label, group_source = STAT_GROUPS[group_by]
        if group_source != "patient":
            return JSONResponse({"error": "Log-Rank grouping is only supported for patient-level attributes (not monthly fields)"})

        from datetime import date as date_obj
        try:
            date_to_parsed = datetime.strptime(date_to + "-01", "%Y-%m-%d").date()
        except (ValueError, TypeError):
            date_to_parsed = date_obj.today()

        all_patients = db.query(Patient).filter(Patient.hd_wef_date != None).all()
        groups_data: dict[str, dict] = defaultdict(lambda: {"durations": [], "events": []})

        for p in all_patients:
            if p.hd_wef_date > date_to_parsed:
                continue
            grp = _group_label(getattr(p, group_by, None))
            if not grp:
                continue
            end_date, event = _survival_endpoint(p, date_to_parsed)
            duration_days = (end_date - p.hd_wef_date).days
            if duration_days <= 0:
                continue
            groups_data[grp]["durations"].append(round(duration_days / 30.44, 1))
            groups_data[grp]["events"].append(event)

        valid_groups = {k: v for k, v in groups_data.items() if len(v["durations"]) >= 3}
        if len(valid_groups) < 2:
            return JSONResponse({"error": "Need ≥2 groups with ≥3 patients with known HD start dates"})

        group_names = sorted(valid_groups.keys())
        curves = {}
        for g in group_names:
            r = run_survival_analysis(valid_groups[g]["durations"], valid_groups[g]["events"])
            curves[g] = {
                "timeline": r["timeline"] if r["available"] else [],
                "median_survival": r["median_survival"] if r["available"] else None,
                "n": len(valid_groups[g]["durations"]),
                "n_events": sum(valid_groups[g]["events"]),
            }

        logrank = None
        if len(group_names) == 2:
            a, b = group_names[0], group_names[1]
            logrank = run_logrank_test(
                valid_groups[a]["durations"], valid_groups[a]["events"],
                valid_groups[b]["durations"], valid_groups[b]["events"],
            )

        return JSONResponse({
            "test_type": "logrank",
            "group_by": group_label,
            "group_names": group_names,
            "curves": curves,
            "logrank": logrank,
            "is_significant": logrank["significant"] if logrank else None,
            "p_value": logrank["p_value"] if logrank else None,
        })

    # ── Cox Proportional Hazards ──────────────────────────────────────────────
    elif test_type == "cox":
        selected_covs = body.get("covariates", list(COX_COVARIATES.keys()))
        selected_covs = [c for c in selected_covs if c in COX_COVARIATES]
        if not selected_covs:
            return JSONResponse({"error": "Select at least one covariate for Cox PH."})

        from datetime import date as date_obj
        try:
            date_to_parsed = datetime.strptime(date_to + "-01", "%Y-%m-%d").date()
        except (ValueError, TypeError):
            date_to_parsed = date_obj.today()

        all_patients = db.query(Patient).filter(Patient.hd_wef_date != None).all()

        durations, events, X_rows, included_covs = [], [], [], selected_covs[:]
        for p in all_patients:
            if p.hd_wef_date > date_to_parsed:
                continue
            end_date, ev = _survival_endpoint(p, date_to_parsed)
            dur_days = (end_date - p.hd_wef_date).days
            if dur_days <= 0:
                continue

            row = []
            skip = False
            for field in included_covs:
                _, hint = COX_COVARIATES[field]
                enc = _encode_cox_covariate(p, field, hint)
                if enc is None:
                    skip = True
                    break
                row.append(enc)
            if skip:
                continue

            durations.append(round(dur_days / 30.44, 1))
            events.append(ev)
            X_rows.append(row)

        if len(durations) < 10:
            return JSONResponse({"error": "Insufficient complete-case data for Cox PH (need ≥10 patients with all covariates recorded)."})

        cov_labels = [COX_COVARIATES[f][0] for f in included_covs]
        res = run_cox_ph(durations, events, X_rows, cov_labels)
        if not res["available"]:
            return JSONResponse({"error": res["message"]})

        return JSONResponse({
            "test_type": "cox",
            "n": res["n"],
            "n_events": res["n_events"],
            "n_censored": res["n"] - res["n_events"],
            "c_index": res["c_index"],
            "converged": res["converged"],
            "covariates": res["covariates"],
            "message": res["message"],
        })

    # ── Bayesian Multilevel Model ─────────────────────────────────────────────
    elif test_type == "bayes_mlm":
        if not variable or variable not in STAT_VARS:
            raise HTTPException(status_code=400, detail="Invalid variable for Bayesian MLM.")

        var_label, var_unit = STAT_VARS[variable]
        selected_covs = body.get("covariates", [])
        selected_covs = [c for c in selected_covs if c in COX_COVARIATES]

        try:
            date_from_parsed = datetime.strptime(date_from + "-01", "%Y-%m-%d").date() if date_from else None
            date_to_parsed2 = datetime.strptime(date_to + "-01", "%Y-%m-%d").date() if date_to else None
        except (ValueError, TypeError):
            date_from_parsed = None
            date_to_parsed2 = None

        query = db.query(MonthlyRecord)
        if date_from_parsed:
            query = query.filter(MonthlyRecord.record_month >= date_from_parsed.strftime("%Y-%m"))
        if date_to_parsed2:
            query = query.filter(MonthlyRecord.record_month <= date_to_parsed2.strftime("%Y-%m"))
        records = query.all()

        all_patients_list = db.query(Patient).all()
        pat_map = {p.id: p for p in all_patients_list}

        # Build derived lookup for this bayes_mlm record set
        bayes_derived = _compute_derived(records, pat_map, {})

        def _get_bayes_val(r):
            if variable in DERIVED_VARS:
                return bayes_derived.get((r.patient_id, r.record_month), {}).get(variable)
            return getattr(r, variable, None)

        # Build month → ordinal index (centred)
        months_seen = sorted({r.record_month for r in records if _get_bayes_val(r) is not None})
        if len(months_seen) < 2:
            return JSONResponse({"error": "Need ≥2 distinct months of data for Bayesian MLM."})
        month_ord = {m: i for i, m in enumerate(months_seen)}
        mid = (len(months_seen) - 1) / 2.0

        y_list, X_list, pid_list = [], [], []
        for r in records:
            val = _get_bayes_val(r)
            if val is None:
                continue
            try:
                y_val = float(val)
            except (TypeError, ValueError):
                continue

            pat = pat_map.get(r.patient_id)
            if pat is None:
                continue

            cov_row = [month_ord[r.record_month] - mid]  # centred time
            skip = False
            for field in selected_covs:
                _, hint = COX_COVARIATES[field]
                enc = _encode_cox_covariate(pat, field, hint)
                if enc is None:
                    skip = True
                    break
                cov_row.append(enc)
            if skip:
                continue

            y_list.append(y_val)
            X_list.append(cov_row)
            pid_list.append(r.patient_id)

        if len(y_list) < 10:
            return JSONResponse({"error": "Insufficient data for Bayesian MLM (need ≥10 observations with all covariates recorded)."})

        predictor_names = ["Time (months, centred)"] + [COX_COVARIATES[f][0] for f in selected_covs]
        res = run_bayesian_multilevel(y_list, X_list, pid_list, predictor_names)
        if not res["available"]:
            return JSONResponse({"error": res["message"]})

        return JSONResponse({
            "test_type": "bayes_mlm",
            "variable": var_label,
            "unit": var_unit,
            "n_obs": res["n_obs"],
            "n_patients": res["n_patients"],
            "fixed_effects": res["fixed_effects"],
            "sigma2_e": res["sigma2_e"],
            "sigma2_a": res["sigma2_a"],
            "icc": res["icc"],
            "random_effects": res["random_effects"],
            "n_samples": res["n_samples"],
            "message": res["message"],
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
