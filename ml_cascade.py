"""
ml_cascade.py
=============
Clinical Cascade Analysis for hemodialysis patients:
  - MIA Syndrome (Malnutrition-Inflammation-Atherosclerosis)
  - Cardiorenal Cascade
  - AVF Maturation Monitoring
  - Post-Dialysis Syndrome (PDS)
  - Blood Flow Rate (BFR) Trend Analysis
  - Occult Volume Overload Detection
"""
import logging
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── Shared GNRI helper ────────────────────────────────────────────────────────

def _compute_gnri(alb_val: float, weight_val: float, height: float, sex: str) -> Optional[float]:
    """
    Compute Geriatric Nutritional Risk Index (GNRI).
    Returns None if any required value is missing/invalid.
    Formula: 14.89 * Albumin (g/dL) + 41.7 * (Weight / IDW)
    IDW: height - 100 - ((height - 150) / 4) for Male
         height - 100 - ((height - 150) / 2.5) for Female
    """
    if alb_val is None or weight_val is None or height is None:
        return None
    h_diff = height - 150
    if sex == "Male":
        idw = height - 100 - (h_diff / 4)
    else:
        idw = height - 100 - (h_diff / 2.5)
    if idw <= 0:
        return None
    w_ratio = min(1.0, weight_val / idw)
    return (14.89 * alb_val) + (41.7 * w_ratio)


def compute_mia_score(db: Session, patient_id: int, prefetched_records = None, recent_sessions = None, prefetched_interims = None) -> Dict:
    """
    Calculate Malnutrition, Inflammation, Atherosclerosis (MIA) Syndrome components.
    Based on Geriatric Nutritional Risk Index (GNRI) and clinical history.
    """
    from database import MonthlyRecord, Patient, SessionRecord

    patient = db.get(Patient, patient_id)
    if not patient:
        return {}

    # 1. Atherosclerosis Component
    athero = False
    if patient.cad_status or patient.history_of_stroke or patient.history_of_pvd:
        athero = True

    # 2. Inflammation Component (CRP > 0.3 mg/dL)
    if prefetched_records is not None:
        recent_rec = next((r for r in reversed(prefetched_records) if r.crp is not None), None)
    else:
        recent_rec = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.crp.isnot(None)
        ).order_by(MonthlyRecord.record_month.desc()).first()

    crp_val = recent_rec.crp if recent_rec else None

    if crp_val is None:
        if prefetched_interims is not None:
            recent_crp_interim = next((il for il in prefetched_interims if il.parameter == 'crp'), None)
        else:
            from database import InterimLabRecord
            recent_crp_interim = db.query(InterimLabRecord).filter(
                InterimLabRecord.patient_id == patient_id,
                InterimLabRecord.parameter == 'crp'
            ).order_by(InterimLabRecord.lab_date.desc()).first()
        crp_val = recent_crp_interim.value if recent_crp_interim else None

    inflam = False
    if crp_val is not None and crp_val > 3.0:
        inflam = True

    # 3. Malnutrition Component (GNRI < 92)
    if prefetched_records is not None:
        recent_rec_alb = next((r for r in reversed(prefetched_records) if r.albumin is not None), None)
    else:
        recent_rec_alb = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.albumin.isnot(None)
        ).order_by(MonthlyRecord.record_month.desc()).first()

    alb_val = recent_rec_alb.albumin if recent_rec_alb else None

    if recent_sessions is not None:
        recent_session = recent_sessions[0] if recent_sessions else None
    else:
        recent_session = db.query(SessionRecord).filter(
            SessionRecord.patient_id == patient_id
        ).order_by(SessionRecord.session_date.desc()).first()

    weight_val = recent_session.weight_pre if recent_session else None
    height = patient.height
    sex = patient.sex

    malnut = False
    gnri = None
    risk_grade = "N/A"

    if alb_val and weight_val and height:
        gnri = _compute_gnri(alb_val, weight_val, height, sex)
        if gnri is not None:
            if gnri < 82: risk_grade = "Major Risk"
            elif gnri < 92: risk_grade = "Moderate Risk"
            elif gnri < 98: risk_grade = "Low Risk"
            else: risk_grade = "No Risk"

            if gnri < 92:
                malnut = True

    # Sensitivity analysis: Albumin < 3.5
    malnut_sensitivity = False
    if alb_val is not None and alb_val < 3.5:
        malnut_sensitivity = True

    # BUG 3 FIX: all three are bools, not None; compute directly without None check
    score = int(athero) + int(inflam) + int(malnut)

    available = gnri is not None
    missing_inputs = []
    if alb_val is None: missing_inputs.append("Albumin")
    if weight_val is None: missing_inputs.append("Weight")
    if height is None: missing_inputs.append("Height")
    if crp_val is None: missing_inputs.append("CRP")

    return {
        "available": available,
        "error": None if available else "Insufficient data for full MIA scoring.",
        "data": {
            "score": score,
            "components": {
                "malnutrition": malnut,
                "inflammation": inflam,
                "atherosclerosis": athero
            },
            "metrics": {
                "gnri": round(gnri, 2) if gnri is not None else None,
                "risk_grade": risk_grade,
                "crp": crp_val,
                "albumin": alb_val,
                "weight": weight_val,
                "malnut_sensitivity": malnut_sensitivity
            },
            "inputs_missing": missing_inputs
        }
    }


_UNSPECIFIED = object()


def analyze_mia_cascade(db, patient_id: int, prefetched_records = None, recent_sessions = _UNSPECIFIED) -> dict:
    """
    Malnutrition–Inflammation–Atherosclerosis (MIA) Early Warning Dashboard.
    Updated to align with GNRI-based definitions and CRP > 0.3 thresholds.
    """
    from database import MonthlyRecord, Patient, SessionRecord

    p = db.get(Patient, patient_id)
    if not p: return {"available": False}

    if prefetched_records is not None:
        records = prefetched_records
    else:
        records = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id
        ).order_by(MonthlyRecord.record_month.asc()).all()

    if not records:
        return {"available": False}

    records = records[-9:]

    # Calculate IDW once using shared helper
    height = p.height
    sex = p.sex

    timeline = []

    # Static Atherosclerosis (History based)
    has_athero_history = bool(p.cad_status or p.history_of_stroke or p.history_of_pvd)

    for rec in records:
        m = rec.record_month
        scores       = {}
        data_available = {}
        missing_fields = {}
        values       = {}
        events       = []

        # ── 1. NUTRITION (GNRI based) ─────────────────────────────────────────
        nut_score   = 0
        alb = rec.albumin

        # Get weight from Monthly if available, else fallback
        weight = rec.target_dry_weight
        if weight is None:
            if recent_sessions is not _UNSPECIFIED and recent_sessions is not None:
                sess = next((s for s in recent_sessions if s.record_month == m), None)
            elif recent_sessions is not _UNSPECIFIED:
                sess = None
            else:
                sess = db.query(SessionRecord).filter(
                    SessionRecord.patient_id == patient_id,
                    SessionRecord.record_month == m
                ).first()
            if sess: weight = sess.weight_pre

        if alb is not None and weight is not None and height:
            gnri = _compute_gnri(alb, weight, height, sex)
            if gnri is not None:
                values["nutrition"] = {"GNRI": round(gnri, 1), "albumin": alb, "weight": weight}

                if gnri < 82:
                    nut_score = 2
                    events.append({"icon": "🥩", "color": "#ef4444", "text": f"Major Malnutrition Risk (GNRI {gnri:.1f})"})
                elif gnri < 92:
                    nut_score = 1
                    events.append({"icon": "🥩", "color": "#f59e0b", "text": f"Moderate Malnutrition Risk (GNRI {gnri:.1f})"})
                elif gnri < 98:
                    nut_score = 1

                # Sensitivity check: Albumin < 3.5
                if alb < 3.5:
                    events.append({"icon": "🧪", "color": "#f59e0b", "text": f"Low Albumin (<3.5 g/dL): {alb:.1f}"})

        scores["nutrition"] = nut_score
        data_available["nutrition"] = (alb is not None)
        missing_fields["nutrition"] = ["albumin"] if alb is None else []

        # ── 2. INFLAMMATION (CRP > 0.3) ───────────────────────────────────────
        inflam_score = 0
        crp = getattr(rec, "crp", None)

        # Fallback: look back up to 6 months if current month missing CRP
        if crp is None:
            prev_crps = [getattr(r, "crp", None) for r in records if r.record_month < rec.record_month]
            valid_prev = [v for v in prev_crps if v is not None]
            if valid_prev:
                crp = valid_prev[-1]  # use latest available

        if crp is not None:
            values["inflammation"] = {"CRP": crp}
            if crp > 3.0:
                inflam_score = 2
                events.append({"icon": "🔥", "color": "#ef4444", "text": f"High Inflammation (CRP {crp:.2f} > 3.0)"})
            elif crp > 1.0:
                inflam_score = 1

        scores["inflammation"] = inflam_score
        data_available["inflammation"] = (crp is not None)
        missing_fields["inflammation"] = ["CRP"] if crp is None else []

        # ── 3. ATHEROSCLEROSIS — Dynamic Multi-tier Assessment ────────────────
        # Tier 1 (score 2): Confirmed history of CAD / stroke / PVD — static
        # Tier 2 (score 1): Wide pulse pressure >60 mmHg — validated arterial
        #   stiffness surrogate in HD (Guerin et al. JASN 2001; London et al. KI 2001)
        # Tier 3 (score 1): Isolated systolic hypertension (SBP >160) without
        #   wide PP — early vascular marker
        # Bonus: PWV from research records if available
        athero_score = 0
        bp_sys = getattr(rec, "bp_sys", None)
        bp_dia = getattr(rec, "bp_dia", None)
        pulse_pressure = (bp_sys - bp_dia) if (bp_sys and bp_dia) else None
        bp_data_available = bp_sys is not None

        if has_athero_history:
            # Tier 1 — confirmed macrovascular disease
            athero_score = 2
            values["atherosclerosis"] = {
                "status": "History+",
                "basis":  "Confirmed CAD / stroke / PVD"
            }
            events.append({
                "icon": "🫀", "color": "#ef4444",
                "text": "Confirmed atherosclerotic history (CAD / Stroke / PVD)"
            })

        elif pulse_pressure is not None and pulse_pressure > 60:
            # Tier 2 — wide pulse pressure → arterial stiffness (subclinical atherosclerosis)
            athero_score = 1
            values["atherosclerosis"] = {
                "status":        "Arterial Stiffness Detected",
                "pulse_pressure": round(pulse_pressure, 1),
                "bp_sys":        bp_sys,
                "bp_dia":        bp_dia,
                "basis":         "Wide Pulse Pressure >60 mmHg"
            }
            events.append({
                "icon": "🩸", "color": "#f59e0b",
                "text": (
                    f"Wide pulse pressure {pulse_pressure:.0f} mmHg (SBP {bp_sys}/DBP {bp_dia}) — "
                    "arterial stiffness marker, surrogate for subclinical atherosclerosis "
                    "(Guerin et al. JASN 2001)"
                )
            })

        elif bp_sys and bp_sys > 160:
            # Tier 3 — isolated systolic hypertension (early vascular marker)
            athero_score = 1
            values["atherosclerosis"] = {
                "status": "Isolated Systolic Hypertension",
                "bp_sys": bp_sys,
                "basis":  "SBP >160 mmHg"
            }
            events.append({
                "icon": "📈", "color": "#fb923c",
                "text": f"Isolated systolic hypertension SBP {bp_sys} mmHg — early vascular risk marker"
            })

        elif pulse_pressure is not None and pulse_pressure > 40:
            # Borderline — elevated but not yet >60
            athero_score = 0
            values["atherosclerosis"] = {
                "status":        "Borderline Pulse Pressure",
                "pulse_pressure": round(pulse_pressure, 1),
                "basis":         "PP 40-60 mmHg — monitor trend"
            }

        scores["atherosclerosis"] = athero_score
        # data_available True if ANY assessment basis exists (history or BP)
        data_available["atherosclerosis"] = has_athero_history or bp_data_available
        missing_fields["atherosclerosis"] = (
            [] if (has_athero_history or bp_data_available)
            else ["BP systolic/diastolic (for pulse pressure calculation)"]
        )

        # ── 4. DIALYSIS & EVENTS ──────────────────────────────────────────────
        dial_score = 0
        ktv = rec.single_pool_ktv
        if ktv is not None:
            if ktv < 1.2:
                dial_score = 2
                events.append({"icon": "📉", "color": "#ef4444", "text": f"Critically inadequate dialysis (spKt/V {ktv:.2f} < 1.2)"})
            elif ktv < 1.4:
                dial_score = 1
                events.append({"icon": "📉", "color": "#f59e0b", "text": f"Sub-optimal dialysis (spKt/V {ktv:.2f} < 1.4)"})
        scores["dialysis"] = dial_score
        data_available["dialysis"] = (ktv is not None)
        missing_fields["dialysis"] = ["Kt/V"] if ktv is None else []

        hosp_score = 0
        if rec.hospitalization_this_month:
            hosp_score = 2
            events.append({"icon": "🏥", "color": "#6366f1", "text": "Hospitalization recorded"})
        scores["events"] = hosp_score
        data_available["events"] = True
        missing_fields["events"] = []

        # Completeness per month — lab domains only (events is always present, so excluded)
        LAB_DOMAINS = ("nutrition", "inflammation", "atherosclerosis", "dialysis")
        m_total = sum(1 for k in LAB_DOMAINS if data_available.get(k))
        scored_domains = [k for k in LAB_DOMAINS if data_available.get(k)]
        entry_total = sum(scores.get(k, 0) for k in scored_domains)
        timeline.append({
            "label": m,
            "scores": scores,
            "data_available": data_available,
            "missing_fields": missing_fields,
            "values": values,
            "events": events,
            "completeness_pct": round((m_total / 4) * 100),
            "total": entry_total,
            "domains_with_data": len(scored_domains),
        })

    # Summary Stats
    _LAB_DOMAINS = ("nutrition", "inflammation", "atherosclerosis", "dialysis")
    total_data_points = sum(1 for t in timeline for k in _LAB_DOMAINS if t["data_available"].get(k))
    completeness = (total_data_points / (len(timeline) * 4)) * 100 if timeline else 0

    alert = any(t["total"] >= 4 for t in timeline[-2:]) if timeline else False
    if alert:
        worst = max(timeline[-2:], key=lambda t: t["total"])
        high_domains = [k for k in ("nutrition", "inflammation", "atherosclerosis", "dialysis") if worst["scores"].get(k, 0) >= 2]
        cascade_reason = f"Persistent multi-domain risk: {', '.join(high_domains)} scoring high in recent months."
    else:
        cascade_reason = ""

    last_month = timeline[-1] if timeline else None
    inputs_missing = []
    if last_month:
        for dom_missing in last_month["missing_fields"].values():
            inputs_missing.extend(dom_missing)

    return {
        "available": True,
        "timeline": timeline,
        "data_completeness": round(completeness, 1),
        "months_of_data": len(timeline),
        "alert_triggered": alert,
        "cascade_reason": cascade_reason,
        "inputs_missing": list(set(inputs_missing)),
    }


def analyze_cardiorenal_cascade(db, patient_id: int, prefetched_records = None, prefetched_bia = _UNSPECIFIED) -> dict:
    """
    Cardiorenal / Fluid Overload Cascade.
    """
    from database import Patient, MonthlyRecord, DryWeightAssessment

    p = db.get(Patient, patient_id)
    if not p:
        return {"available": False}

    if prefetched_records is not None:
        records = prefetched_records
    else:
        records = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id
        ).order_by(MonthlyRecord.record_month.asc()).all()

    if not records:
        return {"available": False}

    records = records[-6:]

    events       = []
    risk_score   = 0
    inputs_found = []
    inputs_missing = []

    # ── 1. CARDIAC STATUS (from patient profile) ──────────────────────────────
    ef = p.ejection_fraction
    dd = p.diastolic_dysfunction

    if ef is not None:
        inputs_found.append(f"EF {ef:.0f}%")
        if ef < 40:
            risk_score += 3
            events.append({"type": "cardiac",
                "text": f"Severe LV systolic dysfunction — EF {ef:.0f}% (high filling pressures, fluid retention risk)"})
        elif ef < 50:
            risk_score += 2
            events.append({"type": "cardiac",
                "text": f"Mild–moderate LV systolic dysfunction — EF {ef:.0f}%"})
    else:
        inputs_missing.append("Ejection fraction (echo)")

    if dd and dd.lower() not in ("none", ""):
        inputs_found.append(f"DD {dd}")
        if "grade iii" in dd.lower() or "grade 3" in dd.lower():
            risk_score += 3
            events.append({"type": "cardiac",
                "text": f"Severe diastolic dysfunction ({dd}) — markedly raised filling pressures"})
        elif "grade ii" in dd.lower() or "grade 2" in dd.lower():
            risk_score += 2
            events.append({"type": "cardiac",
                "text": f"Moderate diastolic dysfunction ({dd})"})
        elif "grade i" in dd.lower() or "grade 1" in dd.lower():
            risk_score += 1
            events.append({"type": "cardiac",
                "text": f"Mild diastolic dysfunction ({dd})"})
    else:
        inputs_missing.append("Diastolic dysfunction grade (echo)")

    # ── 2. NT-proBNP ──────────────────────────────────────────────────────────
    nt_vals = [(r.record_month, r.nt_probnp) for r in records if r.nt_probnp is not None]
    if nt_vals:
        latest_nt = nt_vals[-1][1]
        inputs_found.append(f"NT-proBNP {latest_nt:.0f} pg/mL")
        age = p.age or 60
        t_elevated, t_marked, t_severe = (2000, 4000, 10000) if age >= 75 else (1000, 2000, 5000)
        if latest_nt > t_severe:
            risk_score += 3
            events.append({"type": "biomarker",
                "text": f"NT-proBNP severely elevated: {latest_nt:.0f} pg/mL (>{t_severe} — strong fluid overload signal in HD)"})
        elif latest_nt > t_marked:
            risk_score += 2
            events.append({"type": "biomarker",
                "text": f"NT-proBNP markedly elevated: {latest_nt:.0f} pg/mL (>{t_marked} — significant volume excess)"})
        elif latest_nt > t_elevated:
            risk_score += 1
            events.append({"type": "biomarker",
                "text": f"NT-proBNP elevated: {latest_nt:.0f} pg/mL (>{t_elevated} — monitor closely)"})
        if len(nt_vals) >= 3:
            vals = [v for _, v in nt_vals[-3:]]
            if vals[-1] > vals[-2] > vals[-3]:
                risk_score += 1
                events.append({"type": "biomarker",
                    "text": f"NT-proBNP rising trend: {vals[-3]:.0f} → {vals[-2]:.0f} → {vals[-1]:.0f} pg/mL over 3 months"})
    else:
        inputs_missing.append("NT-proBNP (monthly record)")

    # ── 3. BIA FLUID STATUS ───────────────────────────────────────────────────
    if prefetched_bia is not _UNSPECIFIED:
        latest_bia = prefetched_bia
    else:
        latest_bia = (
            db.query(DryWeightAssessment)
            .filter(DryWeightAssessment.patient_id == patient_id,
                    DryWeightAssessment.bia_fluid_overload_litres != None)
            .order_by(DryWeightAssessment.assessment_date.desc())
            .first()
        )
    if latest_bia:
        fo = latest_bia.bia_fluid_overload_litres
        oh = latest_bia.bia_overhydration_percent
        inputs_found.append(f"BIA fluid overload {fo:+.1f} L")
        if fo > 2.5:
            risk_score += 2
            events.append({"type": "fluid",
                "text": f"BIA: severe fluid overload {fo:.1f} L above target (>{2.5} L threshold)"})
        elif fo > 1.0:
            risk_score += 1
            events.append({"type": "fluid",
                "text": f"BIA: fluid overload {fo:.1f} L above target — moderate volume excess"})
        if oh is not None and oh > 15:
            risk_score += 1
            events.append({"type": "fluid",
                "text": f"BIA: overhydration {oh:.1f}% body water — exceeds 15% threshold"})
    else:
        inputs_missing.append("BIA fluid overload (dry-weight assessment)")

    # ── 4. INTERDIALYTIC WEIGHT GAIN ──────────────────────────────────────────
    idwgs = [(r.record_month, r.idwg) for r in records if r.idwg is not None]
    if idwgs:
        latest_idwg = idwgs[-1][1]
        avg_idwg    = sum(v for _, v in idwgs) / len(idwgs)
        inputs_found.append(f"IDWG {latest_idwg:.1f} kg")
        if latest_idwg > 3.5 or avg_idwg > 3.0:
            risk_score += 2
            events.append({"type": "fluid",
                "text": f"High interdialytic weight gain: latest {latest_idwg:.1f} kg, avg {avg_idwg:.1f} kg — volume loading risk"})
        elif latest_idwg > 2.5:
            risk_score += 1
            events.append({"type": "fluid",
                "text": f"Elevated IDWG: {latest_idwg:.1f} kg (target <2.5 kg)"})
    else:
        inputs_missing.append("IDWG (monthly record)")

    # ── 5. RESIDUAL URINE OUTPUT ──────────────────────────────────────────────
    urine_vals = [(r.record_month, r.residual_urine_output) for r in records if r.residual_urine_output is not None]
    if urine_vals:
        latest_uo = urine_vals[-1][1]
        inputs_found.append(f"Urine output {latest_uo:.0f} mL/day")
        if latest_uo < 200:
            risk_score += 2
            events.append({"type": "renal",
                "text": f"Oliguria/anuria: urine output {latest_uo:.0f} mL/day — minimal fluid buffering capacity"})
        elif latest_uo < 500:
            risk_score += 1
            events.append({"type": "renal",
                "text": f"Low residual urine output: {latest_uo:.0f} mL/day — limited salt and water excretion"})
        if len(urine_vals) >= 2:
            first_uo = urine_vals[0][1]
            if first_uo - latest_uo > 200:
                risk_score += 1
                events.append({"type": "renal",
                    "text": f"Declining urine output: {first_uo:.0f} → {latest_uo:.0f} mL/day over {len(urine_vals)} months"})
    else:
        inputs_missing.append("Residual urine output (monthly record)")

    # ── 6. FLUID-RELATED HOSPITALISATIONS ─────────────────────────────────────
    fluid_keywords = {"fluid", "j81", "i50", "oedema", "edema", "pulmonary", "overload"}
    recent_hosps = [r for r in records if r.hospitalization_this_month]
    fluid_hosps  = [r for r in recent_hosps if r.hospitalization_icd_code and
                    any(kw in r.hospitalization_icd_code.lower() for kw in fluid_keywords)]

    if fluid_hosps:
        risk_score += 4
        events.append({"type": "outcome",
            "text": f"{len(fluid_hosps)} hospitalization(s) linked to fluid overload / pulmonary oedema in last {len(records)} months"})
    elif recent_hosps:
        events.append({"type": "outcome",
            "text": f"{len(recent_hosps)} hospitalization(s) in last {len(records)} months (ICD codes not fluid-specific)"})

    # ── Data sufficiency ──────────────────────────────────────────────────────
    total_inputs   = len(inputs_found) + len(inputs_missing)
    completeness   = round(len(inputs_found) / total_inputs * 100) if total_inputs else 0
    reliable       = len(inputs_found) >= 3
    cascade_detected = risk_score >= 5 and reliable

    if not reliable:
        status_label = "UNKNOWN"
        message = (f"Insufficient data to assess risk reliably — "
                   f"only {len(inputs_found)} of {total_inputs} expected inputs recorded.")
    elif cascade_detected:
        status_label = "HIGH RISK"
        message = "Cardiorenal / fluid overload cascade detected — multiple concurrent risk factors."
    elif risk_score >= 3:
        status_label = "MODERATE RISK"
        message = "Moderate cardiorenal risk — monitor fluid balance closely."
    else:
        status_label = "LOW RISK"
        message = "No active cardiorenal fluid cascade — current data within acceptable range."

    return {
        "available":        True,
        "cascade_detected": cascade_detected,
        "risk_score":       risk_score,
        "status_label":     status_label,
        "reliable":         reliable,
        "data_completeness": completeness,
        "inputs_found":     inputs_found,
        "inputs_missing":   inputs_missing,
        "events":           events,
        "months_assessed":  len(records),
        "message":          message,
    }


def analyze_avf_maturation(db, patient_id: int, patient_obj = None, recent_sessions = None) -> dict:
    """
    Vascular Access Surveillance: AVF Maturation Monitoring (KDOQI rule-based).
    """
    from database import Patient, SessionRecord
    from datetime import date, datetime

    if patient_obj is None:
        p = db.get(Patient, patient_id)
    else:
        p = patient_obj

    if not p:
        return {"available": False}

    access_type_clean = (p.access_type or "").strip().lower()
    is_catheter = any(k in access_type_clean for k in ("cath", "tcc", "permacath", "p/cath"))
    is_avf_or_graft = any(k in access_type_clean for k in ("avf", "graft")) or (not is_catheter and access_type_clean)

    events = []
    alerts = []
    risk_score = 0
    today = date.today()
    delay_days = None
    has_access_data = bool(p.access_date or p.date_first_cannulation)

    # ── 1. Maturation Monitoring (AVF/Graft only) ─────────────────────────────
    if is_avf_or_graft:
        def _to_date(val):
            if val is None: return None
            if isinstance(val, (date, datetime)): return val
            try:
                return datetime.strptime(val.split(" ")[0], "%Y-%m-%d").date()
            except:
                return None

        access_date = _to_date(p.access_date)
        hd_wef_date = _to_date(p.hd_wef_date)

        if access_date and not p.date_first_cannulation:
            days_since_surgery = (today - access_date).days

            if not hd_wef_date:
                # Scenario B (Pre-emptive, HD not yet started)
                delay_days = days_since_surgery
                events.append({
                    "text": (
                        f"Pre-emptive AVF created {days_since_surgery} days ago. "
                        "Patient is not yet on dialysis — cannulation pending HD initiation. "
                        "No maturation failure concern at this stage."
                    )
                })

            elif hd_wef_date > access_date:
                # Scenario B variant (HD started after AVF creation)
                pre_hd_wait_days = (hd_wef_date - access_date).days
                days_since_hd_start = (today - hd_wef_date).days
                delay_days = days_since_hd_start
                events.append({
                    "text": (
                        f"AVF created {pre_hd_wait_days} days before HD initiation "
                        f"({hd_wef_date.strftime('%d %b %Y') if hd_wef_date else 'N/A'}). "
                        f"Maturation clock starts from HD start date: "
                        f"{days_since_hd_start} days elapsed without cannulation."
                    )
                })
                if days_since_hd_start > 42:
                    alerts.append(
                        f"AVF Cannulation Overdue: {days_since_hd_start} days since HD initiation "
                        f"without first cannulation — KDOQI recommends cannulation within 6 weeks "
                        f"of HD start when fistula is clinically mature."
                    )
                    risk_score += 3
                elif days_since_hd_start > 28:
                    events.append({
                        "text": (
                            f"Approaching 6-week cannulation threshold since HD start "
                            f"({days_since_hd_start} days). Assess fistula thrill/bruit; "
                            "consider Doppler if maturation is in doubt."
                        )
                    })

            else:
                # Scenario A (Bridge phase)
                delay_days = days_since_surgery
                events.append({
                    "text": (
                        f"AVF created {days_since_surgery} days ago "
                        f"(HD via catheter since {hd_wef_date.strftime('%d %b %Y') if hd_wef_date else 'N/A'}). "
                        "First cannulation date not yet recorded."
                    )
                })
                if days_since_surgery > 42:
                    is_high_risk = bool(p.age and p.age >= 65) or bool(p.dm_status and p.dm_status.strip().lower() not in ("none", ""))
                    if is_high_risk:
                        alerts.append(
                            f"AVF Maturation Surveillance: {days_since_surgery} days since surgery without cannulation. "
                            "Note: Patient is elderly or diabetic — maturation may naturally take up to 12 weeks. "
                            "Assess clinically for thrill/bruit and consider Doppler ultrasound before initiating cannulation."
                        )
                    else:
                        alerts.append(
                            f"AVF Maturation Surveillance: {days_since_surgery} days since surgery without cannulation. "
                            "Fistula should be assessed for maturity. Consider Doppler ultrasound before starting cannulation."
                        )
                    risk_score += 3
                elif days_since_surgery > 28:
                    events.append({
                        "text": (
                            "Approaching 4-week mark since AVF surgery. "
                            "Assess thrill and bruit; schedule Doppler if maturation is uncertain."
                        )
                    })

        elif p.access_date and p.date_first_cannulation:
            # Scenario C (Historic — cannulation already done)
            if p.hd_wef_date and p.hd_wef_date > p.access_date:
                cannulation_vs_hd_start = (p.date_first_cannulation - p.hd_wef_date).days
                cannulation_vs_surgery  = (p.date_first_cannulation - p.access_date).days
                delay_days = cannulation_vs_hd_start
                events.append({
                    "text": (
                        f"AVF created {cannulation_vs_surgery} days before first cannulation "
                        f"({(p.hd_wef_date - p.access_date).days} days of which preceded HD initiation). "
                        f"First cannulation occurred {cannulation_vs_hd_start} days after HD start."
                    )
                })
                if cannulation_vs_hd_start > 45:
                    risk_score += 1
                    events.append({"text": "Delayed cannulation after HD initiation (> 6 weeks) — prolonged catheter dependency recorded."})
            else:
                delay_days = (p.date_first_cannulation - p.access_date).days
                if delay_days >= 0:
                    events.append({"text": f"AVF matured and first cannulated in {delay_days} days from surgery."})
                    if delay_days > 45:
                        risk_score += 2
                        events.append({"text": "Delayed AVF maturation (> 6 weeks) recorded in history."})

        elif not p.access_date and p.date_first_cannulation:
            events.append({"text": f"First cannulation recorded on {p.date_first_cannulation}; surgery date not entered."})

    elif is_catheter:
        events.append({"text": f"Patient on catheter access ({p.access_type.strip()}). AVF maturation monitoring not applicable."})

    # ── 2. Functional Monitoring (Recent Sessions) ────────────────────────────
    if recent_sessions is None:
        recent_sessions = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).limit(5).all()

    low_bfr_count = 0
    high_recirc_count = 0
    qa_alerts = []

    for s in recent_sessions:
        bfr = s.actual_blood_flow_rate or s.blood_flow_rate
        if bfr and bfr < 250:
            low_bfr_count += 1

        qa = s.access_flow_qa
        if qa:
            if qa < 300:
                qa_alerts.append(f"Impending Failure (Qa {qa} < 300): Not usable for effective HD.")
            elif qa < 400:
                qa_alerts.append(f"High Non-Maturation Risk (Qa {qa} < 400).")
            elif qa < 500:
                qa_alerts.append(f"Poor Maturation/Failure (Qa {qa} < 500).")
            elif qa < 600:
                qa_alerts.append(f"Sub-optimal performance (Qa {qa} < 600): High risk for stenosis/thrombosis (KDOQI).")

        if s.access_recirculation_percent and s.access_recirculation_percent > 10:
            high_recirc_count += 1
        elif s.urea_peripheral_s and s.urea_arterial_a and s.urea_venous_v:
            try:
                s_val, a_val, v_val = s.urea_peripheral_s, s.urea_arterial_a, s.urea_venous_v
                if abs(s_val - v_val) > 0.1:
                    recirc = ((s_val - a_val) / (s_val - v_val)) * 100
                    if recirc > 10: high_recirc_count += 1
            except: pass

    if low_bfr_count >= 2:
        alerts.append(f"Suboptimal Pump Flow: BFR < 250 ml/min in {low_bfr_count}/5 recent sessions.")
        risk_score += 2

    if qa_alerts:
        unique_qa = list(dict.fromkeys(qa_alerts))
        alerts.extend(unique_qa[:2])
        risk_score += 3

    if high_recirc_count >= 1:
        alerts.append("Significant Access Recirculation (>10%) detected.")
        risk_score += 3

    # Capture access-specific risk before adding demographic context scores.
    # cascade_detected must only fire on actual access problems — demographics
    # alone (elderly + DM = +3) would otherwise trip the threshold on every
    # such patient regardless of fistula status.
    access_risk_score = risk_score
    maturation_failure = any("Maturation Failure" in a for a in alerts)
    cascade_detected = access_risk_score >= 3 or maturation_failure

    # ── 3. Correlation with Demographics ──────────────────────────────────────
    if p.age and p.age >= 65:
        risk_score += 1
        events.append({"text": f"Age {p.age} yrs correlates with impaired vascular remodeling."})

    if p.dm_status and p.dm_status.strip().lower() not in ("none", ""):
        risk_score += 2
        events.append({"text": f"DM ({p.dm_status}) increases risk of intimal hyperplasia."})

    if p.handgrip_strength and p.handgrip_strength < 20:
        risk_score += 2
        events.append({"text": f"Sarcopenia (Handgrip {p.handgrip_strength} kg) linked to fistula failure."})

    default_message = "Vascular access functioning within parameters." if has_access_data else "Access dates not recorded — enter surgery and first cannulation dates in the patient profile."

    return {
        "available": True,
        "error":     None,
        "data": {
            "cascade_detected": cascade_detected,
            "maturation_failure": maturation_failure,
            "suboptimal_flow": low_bfr_count >= 2,
            "high_recirculation": high_recirc_count >= 1,
            "alerts": alerts,
            "risk_score": risk_score,
            "delay_days": delay_days,
            "has_access_data": has_access_data,
            "is_catheter": is_catheter,
            "events": events,
            "message": alerts[0] if alerts else default_message,
        }
    }


_FATIGUE_FIELDS = [
    'fatigue_physical_exhaustion', 'fatigue_lack_of_energy', 'fatigue_sleepiness',
    'fatigue_reduced_stamina', 'fatigue_prolonged_rest', 'fatigue_washed_out',
    'fatigue_motivation_loss',
]
_COG_FIELDS = [
    'cog_brain_fog', 'cog_poor_concentration', 'cog_slowed_thinking',
    'cog_memory_difficulty', 'cog_reduced_alertness', 'cog_decision_difficulty',
]
_PSYCH_FIELDS = [
    'psych_low_mood', 'psych_anxiety', 'psych_irritability',
    'psych_emotional_exhaustion', 'psych_overwhelmed', 'psych_reduced_purpose',
]
_PHYS_FIELDS = [
    'phys_muscle_weakness', 'phys_dizziness', 'phys_headache', 'phys_body_pain',
    'phys_sob', 'phys_palpitations', 'phys_gait_instability', 'phys_cramps',
]
_SLEEP_FIELDS = [
    'sleep_daytime_sleepiness', 'sleep_poor_sleep_post_hd',
    'sleep_unrefreshing', 'sleep_disturbance',
]
_FUNC_FIELDS = [
    'func_mobility', 'func_household', 'func_work', 'func_social',
    'func_exercise', 'func_family', 'func_independence', 'func_life_participation',
]
_DRT_MINS_MAP = {
    '<1h': 30, '<1 hour': 30, '< 1 hour': 30,
    '1-2h': 90, '1-2 hours': 90,
    '2-6h': 240, '2-6 hours': 240,
    '6-12h': 540, '6-12 hours': 540,
    '>12h': 720, '>12 hours': 720, '> 12 hours': 720,
    'Whole day': 960, 'whole day': 960,
    'Never fully recover': 1440, 'never fully recover': 1440,
}


def _domain_avg(rep, fields):
    vals = [getattr(rep, f, None) for f in fields]
    valid = [v for v in vals if v is not None]
    return round(sum(valid) / len(valid), 1) if valid else None


def _drt_mins_from_rep(rep):
    """Return DRT in minutes from either legacy integer field or new string field."""
    legacy = getattr(rep, 'dialysis_recovery_time_mins', None)
    if legacy is not None:
        return legacy
    new_str = getattr(rep, 'dialysis_recovery_time', None)
    if new_str:
        return _DRT_MINS_MAP.get(new_str.strip())
    return None


def analyze_pds(db: Session, patient_id: int, prefetched_reports = None, recent_sessions = None) -> Dict:
    """
    Correlates PatientSymptomReports with recent SessionRecords to identify
    clinical drivers of Post-Dialysis Syndrome (PDS).

    Matching strategy (in priority order):
      1. Explicit session_id FK on the report.
      2. report.session_date (the date the patient says the session was on)
         matched against session records within a ±2-day window.
      3. report.reported_at.date() as fallback, also ±2-day window.

    Reports without a matched session are still surfaced — they appear in the
    "all_reports" list on the returned dict so the template can show them even
    when no clinical correlation is possible.
    """
    from database import PatientSymptomReport, SessionRecord, MonthlyRecord
    from datetime import timedelta

    if prefetched_reports is not None:
        reports = prefetched_reports
    else:
        reports = (
            db.query(PatientSymptomReport)
            .filter(PatientSymptomReport.patient_id == patient_id)
            .order_by(PatientSymptomReport.reported_at.desc())
            .limit(20)
            .all()
        )

    if not reports:
        return {"available": False, "message": "No post-dialysis symptom logs recorded yet."}

    if recent_sessions is not None:
        recent_sessions = recent_sessions[:30]
    else:
        recent_sessions = (
            db.query(SessionRecord)
            .filter(SessionRecord.patient_id == patient_id)
            .order_by(SessionRecord.session_date.desc())
            .limit(30)
            .all()
        )

    def _find_session(rep):
        """Return the closest SessionRecord for a given report, or None."""
        if rep.session_id:
            return next((s for s in recent_sessions if s.id == rep.session_id), None)

        # Prefer the explicitly stored session_date; fall back to reported_at date
        anchor = rep.session_date or rep.reported_at.date()

        # Search within a 2-day window before the anchor (patient logs after HD)
        for delta in range(3):  # 0, 1, 2 days prior
            target = anchor - timedelta(days=delta)
            match = next((s for s in recent_sessions if s.session_date == target), None)
            if match:
                return match
        return None

    def _parse_drt(val):
        if not val:
            return None
        # Convert the categorical string to an approximate minutes value for charting
        mapping = {
            "<1 hour": 30,
            "1-2 hours": 90,
            "2-6 hours": 240,
            "6-12 hours": 540,
            ">12 hours": 720,
            "Whole day": 1440,
            "Never fully recover before next dialysis": 2880,
        }
        return mapping.get(val, None)

    # Build per-report dicts; include unmatched reports with sess=None
    all_reports = []
    correlated_events = []

    for rep in reports:
        sess = _find_session(rep)

        ufr = None
        if sess:
            # Prefer the pre-computed uf_rate (mL/kg/hr stored at session creation).
            # Fall back to deriving from weights + duration if not stored, using the same
            # KDOQI formula: (fluid_removed_mL) / (weight_pre_kg × duration_hr).
            ufr = sess.uf_rate
            if ufr is None:
                duration = (sess.duration_hours or 0) + (sess.duration_minutes or 0) / 60
                if sess.weight_pre and sess.weight_post and duration > 0 and sess.weight_pre > 0:
                    ufr = round(
                        ((sess.weight_pre - sess.weight_post) * 1000) / (duration * sess.weight_pre), 1
                    )

        report_dict = {
            "date": str(rep.session_date or rep.reported_at.date()),
            "reported_at": str(rep.reported_at.date()),
            "drt_mins": _parse_drt(rep.dialysis_recovery_time),
            "drt_str": rep.dialysis_recovery_time,
            "tiredness": rep.fatigue_physical_exhaustion,
            "energy": rep.fatigue_lack_of_energy,
            "activity_impact": rep.func_life_participation,
            "mood": rep.psych_low_mood,
            "alertness": rep.cog_brain_fog,
            "sleepiness": rep.fatigue_sleepiness,
            "missed_event": True if rep.func_social == 10 else False,
            "symptoms": rep.symptoms,
            "notes": rep.notes,
            "session_matched": sess is not None,
            "ufr": ufr,
            "idh": sess.idh_episode if sess else None,
            "temp": sess.dialysate_temperature if sess else None,
            "exercise": sess.intradialytic_exercise_mins if sess else None,
            # Multidimensional domain scores (0-10 averages)
            "fatigue":       _domain_avg(rep, _FATIGUE_FIELDS),
            "cognitive":     _domain_avg(rep, _COG_FIELDS),
            "psychological": _domain_avg(rep, _PSYCH_FIELDS),
            "physical":      _domain_avg(rep, _PHYS_FIELDS),
            "sleep":         _domain_avg(rep, _SLEEP_FIELDS),
            "functional":    _domain_avg(rep, _FUNC_FIELDS),
            "cgi_severity":  getattr(rep, 'cgi_severity', None),
            "cgi_phenotype": getattr(rep, 'cgi_dominant_phenotype', None),
            "func_items": {
                "Mobility":          getattr(rep, 'func_mobility', None),
                "Household":         getattr(rep, 'func_household', None),
                "Work":              getattr(rep, 'func_work', None),
                "Social":            getattr(rep, 'func_social', None),
                "Exercise":          getattr(rep, 'func_exercise', None),
                "Family":            getattr(rep, 'func_family', None),
                "Independence":      getattr(rep, 'func_independence', None),
                "Life Participation": getattr(rep, 'func_life_participation', None),
            },
        }
        all_reports.append(report_dict)

        # correlated_events: matched + DRT (used for clinical flag checks against session data)
        if rep.dialysis_recovery_time is not None and sess:
            correlated_events.append(report_dict)

    # DRT-based analytics — avg uses ALL reports with a DRT value (matched or not)
    reports_with_drt = [r for r in all_reports if r["drt_mins"] is not None]
    avg_drt = None
    flags = []
    interventions = []
    risk_level = "low"

    if reports_with_drt:
        avg_drt = sum(e["drt_mins"] for e in reports_with_drt) / len(reports_with_drt)

        if avg_drt > 120:  # > 2 hours
            risk_level = "high" if avg_drt > 240 else "medium"
            flags.append(f"Prolonged average recovery time: {round(avg_drt/60, 1)} hours.")

            limit = 240 if avg_drt > 240 else 120
            if any(e["ufr"] and e["ufr"] > 10.0 and e["drt_mins"] > limit for e in correlated_events):
                flags.append("Prolonged DRT correlates with high Ultrafiltration Rate.")
                interventions.append("Review fluid allowance and target dry weight.")

            if any(e["idh"] and e["drt_mins"] > limit for e in correlated_events):
                flags.append("Prolonged DRT correlates with Intradialytic Hypotension.")
                interventions.append("Consider cool dialysate or adjusting dialysate sodium.")

            latest_monthly = (
                db.query(MonthlyRecord)
                .filter(MonthlyRecord.patient_id == patient_id)
                .order_by(MonthlyRecord.record_month.desc())
                .first()
            )
            if latest_monthly and latest_monthly.albumin and latest_monthly.albumin < 3.5:
                flags.append("Prolonged DRT in setting of hypoalbuminemia.")
                interventions.append("Evaluate for protein-energy wasting; encourage intradialytic meals if appropriate.")

    unmatched_count = sum(1 for r in all_reports if not r["session_matched"])

    # Domain analytics: reports that have at least one domain score filled
    _domain_keys = ('fatigue', 'cognitive', 'psychological', 'physical', 'sleep')
    domain_reports = [
        r for r in all_reports
        if any(r.get(d) is not None for d in _domain_keys)
    ]
    # Oldest-first for trend charts; latest first for radar
    domain_history = list(reversed(domain_reports[-8:]))  # up to 8 assessments, oldest→newest
    latest_domains = domain_reports[0] if domain_reports else None  # all_reports is desc

    return {
        "available": True,
        "avg_drt_mins": round(avg_drt) if avg_drt is not None else None,
        "avg_drt_hours": round(avg_drt / 60, 1) if avg_drt is not None else None,
        "risk_level": risk_level,
        "css_class": "danger" if risk_level == "high" else ("warning" if risk_level == "medium" else "success"),
        "flags": flags,
        "interventions": interventions,
        "events": correlated_events,        # DRT-correlated events for the DRT/UFR chart
        "all_reports": all_reports,         # all reports including unmatched (for the table)
        "unmatched_count": unmatched_count,
        "has_domain_data": bool(domain_reports),
        "domain_history": domain_history,   # oldest→newest, for trend line chart
        "latest_domains": latest_domains,   # most recent with domain scores (for radar)
    }


def analyze_bfr_trend(sessions: List[Dict]) -> Dict:
    """
    Analyse blood flow rate trend across per-session records for vascular
    access monitoring.
    """
    _null = {
        "available": False,
        "alert_level": "unknown",
        "message": "No session records found. Log sessions to enable BFR monitoring.",
        "n_sessions": 0,
    }
    if not sessions:
        return _null

    # Filter to sessions that have at least one BFR value
    bfr_sessions = [
        s for s in sessions
        if s.get("actual_blood_flow_rate") is not None
        or s.get("blood_flow_rate") is not None
    ]
    if not bfr_sessions:
        return {**_null, "available": False,
                "message": "Sessions exist but no BFR values entered yet."}

    # Sort oldest → newest for trend calculation
    bfr_sessions = sorted(bfr_sessions, key=lambda s: s.get("session_date") or "")

    latest      = bfr_sessions[-1]
    latest_abfr = latest.get("actual_blood_flow_rate")
    latest_pbfr = latest.get("blood_flow_rate")

    bfr_deficit = None
    if latest_abfr is not None and latest_pbfr is not None:
        bfr_deficit = round(latest_pbfr - latest_abfr, 1)

    # ── Trend slope ───────────────────────────────────────────────────────────
    actual_series = [
        (i, s["actual_blood_flow_rate"])
        for i, s in enumerate(bfr_sessions)
        if s.get("actual_blood_flow_rate") is not None
    ]
    slope = None
    if len(actual_series) >= 3:
        xs = [p[0] for p in actual_series]
        ys = [p[1] for p in actual_series]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        sxx = sum((x - x_mean) ** 2 for x in xs)
        sxy = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(len(xs)))
        slope = round(sxy / sxx, 2) if sxx else 0.0

    rolling_slope = None
    if len(actual_series) >= 3:
        recent_series = actual_series[-6:]
        r_xs = [p[0] for p in recent_series]
        r_ys = [p[1] for p in recent_series]
        r_x_mean = sum(r_xs) / len(r_xs)
        r_y_mean = sum(r_ys) / len(r_ys)
        r_sxx = sum((x - r_x_mean) ** 2 for x in r_xs)
        r_sxy = sum((r_xs[idx] - r_x_mean) * (r_ys[idx] - r_y_mean) for idx in range(len(r_xs)))
        rolling_slope = round(r_sxy / r_sxx, 2) if r_sxx else 0.0

    # ── Consecutive decline counter ───────────────────────────────────────────
    consecutive_decline = 0
    abfr_vals = [s["actual_blood_flow_rate"] for s in bfr_sessions
                 if s.get("actual_blood_flow_rate") is not None]
    for i in range(len(abfr_vals) - 1, 0, -1):
        if abfr_vals[i] < abfr_vals[i - 1]:
            consecutive_decline += 1
        else:
            break

    # ── Access condition summary (last 5 sessions) ────────────────────────────
    recent_conditions = [
        s.get("access_condition") for s in bfr_sessions[-5:]
        if s.get("access_condition")
    ]
    poor_or_infected = any(
        c in ("Poor", "Infected") for c in recent_conditions
    )

    # ── Alert classification ──────────────────────────────────────────────────
    alert_level = "ok"
    alert_reasons = []

    if latest_abfr is not None:
        if latest_abfr < 200:
            alert_level = "critical"
            alert_reasons.append(f"BFR {latest_abfr:.0f} mL/min — critically low (target ≥ 250)")
        elif latest_abfr < 250:
            alert_level = "warning" if alert_level != "critical" else alert_level
            alert_reasons.append(f"BFR {latest_abfr:.0f} mL/min — below target (250–400)")

    if bfr_deficit is not None and bfr_deficit > 50:
        alert_level = "warning" if alert_level == "ok" else alert_level
        alert_reasons.append(f"BFR deficit {bfr_deficit:.0f} mL/min (prescribed {latest_pbfr:.0f}, achieved {latest_abfr:.0f})")

    if consecutive_decline >= 3:
        alert_level = "warning" if alert_level == "ok" else alert_level
        alert_reasons.append(f"{consecutive_decline} consecutive sessions with declining BFR — early dysfunction signal")

    if rolling_slope is not None and rolling_slope <= -5.0:
        alert_level = "critical"
        alert_reasons.append(f"Progressive decline: BFR rolling slope is {rolling_slope:+.1f} mL/min/session (stenosis risk)")

    if poor_or_infected:
        alert_level = "critical"
        alert_reasons.append("Access condition flagged as Poor / Infected in recent sessions")

    # ── Build message ─────────────────────────────────────────────────────────
    if alert_level == "critical":
        message = "⚠ Access at risk: " + "; ".join(alert_reasons) + ". Urgent review / fistulogram."
    elif alert_level == "warning":
        message = "BFR concern: " + "; ".join(alert_reasons) + ". Monitor closely."
    else:
        bfr_txt = f"{latest_abfr:.0f} mL/min" if latest_abfr else "not recorded"
        message = f"Access functioning well. Latest BFR {bfr_txt}."
        if slope is not None and slope < -5:
            message += f" Mild downward trend ({slope:+.1f} mL/min per session) — watch."

    return {
        "available":            True,
        "alert_level":          alert_level,
        "css_class":            "danger" if alert_level == "critical" else
                                "warning" if alert_level == "warning" else "success",
        "latest_actual_bfr":   latest_abfr,
        "latest_prescribed_bfr": latest_pbfr,
        "bfr_deficit":         bfr_deficit,
        "slope":               slope,
        "rolling_slope":       rolling_slope,
        "consecutive_decline": consecutive_decline,
        "access_conditions":   recent_conditions,
        "poor_or_infected":    poor_or_infected,
        "n_sessions":          len(bfr_sessions),
        "alert_reasons":       alert_reasons,
        "message":             message,
    }


def detect_occult_overload(
    db: Session,
    patient_id: int,
    prefetched_records: list = None,
    recent_sessions: list = None,
):
    """
    Identifies 'Sarcopenia-Masked Occult Volume Overload'.
    Logic: Stable/Rising weight + Falling Albumin + High IDWG + Respiratory symptoms.
    """
    from database import Patient, MonthlyRecord, SessionRecord

    patient = db.get(Patient, patient_id)
    if not patient: return None

    if prefetched_records is not None:
        first_record = prefetched_records[0] if prefetched_records else None
        recent_records = [r for r in prefetched_records if r.albumin is not None][-3:]
        recent_records = list(reversed(recent_records))
    else:
        first_record = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.asc()).first()
        recent_records = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.albumin.isnot(None)
        ).order_by(MonthlyRecord.record_month.desc()).limit(3).all()

    if recent_sessions is not None:
        sessions = recent_sessions[:10]
    else:
        sessions = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).limit(10).all()

    dw_change = 0
    if first_record and first_record.target_dry_weight and patient.dry_weight:
        dw_change = patient.dry_weight - first_record.target_dry_weight

    alb_decline = False
    if len(recent_records) >= 2:
        alb_decline = recent_records[0].albumin < recent_records[-1].albumin

    breathless = any([(s.pre_hd_dyspnea_likert and s.pre_hd_dyspnea_likert >= 3) or
                      (s.post_hd_dyspnea_likert and s.post_hd_dyspnea_likert >= 3) for s in sessions])

    emergency_sessions = [s for s in sessions if s.is_emergency and s.reason_emergency in ["Fluid Overload", "Pulmonary Oedema", "Severe Dyspnea"]]
    freq_emergency = len(emergency_sessions) >= 1

    if (dw_change >= 0 and alb_decline) or (breathless and alb_decline) or (freq_emergency):
        reason = f"Stable/rising dry weight ({round(dw_change,1)}kg change) with declining Albumin and persistent dyspnea."
        if freq_emergency:
            reason = f"Emergency session required due to {emergency_sessions[0].reason_emergency}. " + reason

        return {
            "available": True,
            "error":     None,
            "data": {
                "type": "Occult Overload Suspected",
                "reason": reason,
                "recommendation": "Perform BIA, IVC Diameter check, and Lung USG. Review dry weight and consider upgrading to 3x/week schedule.",
                "severity": "High"
            }
        }

    return {
        "available": False,
        "error":     "No occult overload detected.",
        "data":      {}
    }


def analyze_idwg_velocity(sessions: List[Dict], dry_weight: Optional[float] = None) -> Dict:
    """
    Analyze the interdialytic weight gain (IDWG) velocity (fluid accumulation rate)
    between consecutive dialysis sessions.

    Formula:
      IDWG = weight_pre[t] - weight_post[t-1]
      Days = session_date[t] - session_date[t-1] (in days)
      Daily Velocity (kg/day) = IDWG / Days
    """
    _null = {
        "available": False,
        "alert_level": "unknown",
        "message": "No sufficient session records to compute IDWG velocity.",
        "points": [],
        "avg_velocity": None,
        "rolling_slope": None,
    }
    if len(sessions) < 2:
        return _null

    # Sort oldest to newest
    cron_sessions = sorted(sessions, key=lambda s: s.get("session_date") or "")

    points = []
    from datetime import datetime
    for i in range(1, len(cron_sessions)):
        curr = cron_sessions[i]
        prev = cron_sessions[i - 1]

        w_pre = curr.get("weight_pre")
        w_post_prev = prev.get("weight_post")
        d_curr_str = curr.get("session_date")
        d_prev_str = prev.get("session_date")

        if w_pre is not None and w_post_prev is not None and d_curr_str and d_prev_str:
            try:
                d_curr = datetime.strptime(d_curr_str, "%Y-%m-%d").date()
                d_prev = datetime.strptime(d_prev_str, "%Y-%m-%d").date()
                delta_days = (d_curr - d_prev).days
                if delta_days > 0:
                    idwg = round(w_pre - w_post_prev, 2)
                    velocity = round(idwg / delta_days, 2) # kg/day
                    pct_velocity = None
                    if dry_weight and dry_weight > 0:
                        pct_velocity = round((velocity / dry_weight) * 100, 2) # % dry weight/day
                    points.append({
                        "date": d_curr_str,
                        "idwg": idwg,
                        "days": delta_days,
                        "velocity": velocity,
                        "pct_velocity": pct_velocity
                    })
            except Exception:
                continue

    if not points:
        return _null

    # Calculate average velocity over last 6 points
    recent_points = points[-6:]
    avg_vel = round(sum(p["velocity"] for p in recent_points) / len(recent_points), 2)

    # Compute slope of velocity (acceleration)
    # y = velocity, x = index
    slope = None
    if len(recent_points) >= 3:
        xs = list(range(len(recent_points)))
        ys = [p["velocity"] for p in recent_points]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        sxx = sum((x - x_mean) ** 2 for x in xs)
        sxy = sum((xs[idx] - x_mean) * (ys[idx] - y_mean) for idx in range(len(xs)))
        slope = round(sxy / sxx, 3) if sxx else 0.0

    # Determine alert level
    alert_level = "ok"
    alert_reasons = []

    latest_vel = recent_points[-1]["velocity"]
    if latest_vel > 2.0:
        alert_level = "critical"
        alert_reasons.append(f"Latest fluid gain rate {latest_vel:.2f} kg/day is critically high (>2.0 kg/day)")
    elif latest_vel > 1.5:
        alert_level = "warning"
        alert_reasons.append(f"Latest fluid gain rate {latest_vel:.2f} kg/day is elevated (>1.5 kg/day)")

    if avg_vel > 1.5:
        alert_level = "critical"
        alert_reasons.append(f"Average fluid gain rate {avg_vel:.2f} kg/day is critically high")
    elif avg_vel > 1.2:
        alert_level = "warning" if alert_level != "critical" else alert_level
        alert_reasons.append(f"Average fluid gain rate {avg_vel:.2f} kg/day is elevated")

    if slope is not None and slope > 0.15:
        alert_level = "warning" if alert_level == "ok" else alert_level
        alert_reasons.append(f"Fluid accumulation is accelerating (velocity slope +{slope:.2f} kg/day per session)")

    # Build message
    if alert_level == "critical":
        message = "🚨 CRITICAL: Rapid fluid accumulation rate. " + "; ".join(alert_reasons) + ". Counsel patient on strict fluid limit (<1L/day) and low-salt diet. Check compliance."
    elif alert_level == "warning":
        message = "⚠ Warning: Elevated fluid accumulation rate. " + "; ".join(alert_reasons) + ". Monitor dry weight and BP."
    else:
        message = f"Fluid accumulation velocity is stable. Average rate {avg_vel:.2f} kg/day."

    return {
        "available": True,
        "alert_level": alert_level,
        "css_class": "danger" if alert_level == "critical" else "warning" if alert_level == "warning" else "success",
        "points": points,
        "avg_velocity": avg_vel,
        "latest_velocity": latest_vel,
        "rolling_slope": slope,
        "message": message,
    }
