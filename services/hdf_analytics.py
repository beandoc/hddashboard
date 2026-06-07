"""HDF utilization and dialysis adequacy analytics.

eKt/V calculation hierarchy (RA Clinical Practice Guideline HD 2019):
  1. Use directly entered equilibrated_ktv if present.
  2. Apply Tattersall eKt/V formula from spKt/V + session duration + access type:
       eKt/V = (spKt/V × t) / (t + 35)   [AVF/AVG — fistula/graft]
       eKt/V = (spKt/V × t) / (t + 22)   [Catheter]
  3. Estimate spKt/V from Daugirdas formula if raw urea + UF data are available.
  4. Fall back to Log-Ratio from URR as last resort.

Residual Renal Clearance (Kru) integration (RA HD Guideline 2019, §Appendix B):
  Three methods implemented when Kru (or Krcr proxy) is available in MonthlyRecord.krcr:

  A. Combined eKt/V
       eKt/VKidney = Kru × F / Vu
         F   = 5500 (thrice-weekly); Vu = 580 × TW (ml)
       Combined eKt/V = eKt/VDialysis + eKt/VKidney
       Target: Combined eKt/V ≥ 1.2

  B. EKRc — Equivalent Renal urea Clearance (Casino & Lopez)
       EKRc (ml/min) = 1 + (10 × eKt/V)       [thrice-weekly]
       Total EKRc = EKRc_dialysis + Kru
       Target: Total EKRc ≥ 13 ml/min

  C. stdKt/V (Gotch) — not computed here; referenced for schedule comparison.
       Thrice-weekly eKt/V 1.2 ≈ stdKt/V 2.1

HDF Convective Clearance (Appendix C):
  Post-dilution HDF: K = Kc + Kd
    Kc = Quf × SC × ((Qp − Kd) / Qp)
  Convection is negligible for small solutes (urea) but significant for β2-microglobulin.
  Filtration volume (actual_uf_volume from SessionRecord) is the standard metric.

Audit Measure 1 population (RA HD 2019):
  Thrice-weekly patients on dialysis for ≥ 1 year.
  Reports median eKt/V and proportion achieving ≥ 1.2.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from database import MonthlyRecord, Patient, SessionRecord


# ── Clinical thresholds ────────────────────────────────────────────────────────
_EKT_V_MIN: float = 1.2          # KDIGO / RA eKt/V adequacy floor
_COMBINED_EKT_V_MIN: float = 1.2  # same target for combined eKt/V
_EKRC_TARGET_ML_MIN: float = 13.0 # EKRc target for thrice-weekly (Casino & Lopez)
_HD_MIN_HOURS_WEEK: float = 12.0
_THRICE_WEEKLY_MIN_SESSIONS_MONTH: int = 10
_AUDIT_ON_DIALYSIS_YEARS: float = 1.0

# Tattersall constants (minutes)
_TATTERSALL_FISTULA = 35
_TATTERSALL_CATHETER = 22

# Combined eKt/V — Kru inflation factor F by schedule (RA HD 2019)
_KRU_F_THRICE_WEEKLY: float = 5500.0   # ml/min → per-session eKt/V
_VU_FACTOR: float = 580.0              # Vu (ml) = 580 × TW (kg)


# ── Calculation helpers ───────────────────────────────────────────────────────

def _session_hours(s: SessionRecord) -> float:
    h = s.duration_hours or 0
    m = s.duration_minutes or 0
    return h + m / 60.0


def _session_minutes(s: SessionRecord) -> float:
    return _session_hours(s) * 60.0


def _is_hdf(s: SessionRecord) -> bool:
    return bool(s.dialysis_type and "hdf" in s.dialysis_type.lower())


def _is_catheter(access_type: Optional[str]) -> bool:
    if not access_type:
        return False
    a = access_type.lower()
    return any(kw in a for kw in ("catheter", "tcc", "cvc", "line", "ntcc"))


def _tattersall_correction(access_type: Optional[str]) -> int:
    return _TATTERSALL_CATHETER if _is_catheter(access_type) else _TATTERSALL_FISTULA


def compute_ektv_from_spktv(
    spktv: float,
    session_mins: float,
    access_type: Optional[str] = None,
) -> float:
    """
    Tattersall eKt/V formula (RA HD Guideline 2019):
      eKt/V = (spKt/V × t) / (t + c)
      where t = session duration (minutes), c = 35 (fistula) or 22 (catheter).
    """
    c = _tattersall_correction(access_type)
    if session_mins <= 0:
        return spktv  # degenerate case
    return round((spktv * session_mins) / (session_mins + c), 3)


def compute_spktv_daugirdas(
    upre: float,
    upost: float,
    uf_litres: float,
    target_weight_kg: float,
    session_mins: float,
) -> Optional[float]:
    """
    Daugirdas spKt/V formula (RA HD Guideline 2019):
      spKt/V = -ln(Upost/Upre - t/7500) + (UF/TW) × (4 - 3.5 × (Upost/Upre))
    where t is in minutes, UF in litres, TW = target weight in kg.
    Returns None if inputs are invalid.
    """
    if upre <= 0 or upost <= 0 or target_weight_kg <= 0:
        return None
    ratio = upost / upre
    inner = ratio - session_mins / 7500.0
    if inner <= 0:
        return None
    try:
        spktv = -math.log(inner) + (uf_litres / target_weight_kg) * (4.0 - 3.5 * ratio)
        return round(spktv, 3)
    except (ValueError, ZeroDivisionError):
        return None


def compute_ektv_log_ratio_from_urr(urr_pct: float) -> float:
    """
    Log-Ratio Kt/V from URR (RA HD Guideline 2019):
      Kt/V = ln(100 / (100 - URR))
    This equals eKt/V to a close approximation for a 4-hour fistula session at UF/TW=0.02.
    """
    if urr_pct <= 0 or urr_pct >= 100:
        return 0.0
    return round(math.log(100.0 / (100.0 - urr_pct)), 3)


def _ektv_from_urr_full(urr_pct: float, session_mins: float, uf_tw_ratio: float, is_catheter: bool) -> Optional[float]:
    """
    Full-chain eKt/V from URR via Daugirdas spKt/V then Tattersall correction.
    Internal helper for the URR threshold solver.
    """
    ratio = (100.0 - urr_pct) / 100.0
    inner = ratio - session_mins / 7500.0
    if inner <= 0:
        return None
    try:
        spktv = -math.log(inner) + uf_tw_ratio * (4.0 - 3.5 * ratio)
    except ValueError:
        return None
    c = _TATTERSALL_CATHETER if is_catheter else _TATTERSALL_FISTULA
    return (spktv * session_mins) / (session_mins + c)


def compute_urr_target_for_ektv(
    target_ektv: float,
    session_mins: float,
    uf_tw_ratio: float,
    access_type: Optional[str] = None,
) -> Optional[float]:
    """
    Compute the patient-specific URR threshold required to achieve a given eKt/V
    target, for a given session duration and UF/TW ratio (RA HD Guideline 2019
    Appendix B, table).

    Uses binary search over URR [1, 99] with the full Daugirdas + Tattersall chain.
    Returns URR% rounded to 1 decimal place, or None if the target is unachievable.

    This is the computation underlying the guideline reference table (e.g. for a
    4-hour fistula session at UF/TW=0.02 → URR 70.0% required for eKt/V 1.2).
    """
    if session_mins <= 0 or uf_tw_ratio <= 0:
        return None
    is_catheter = _is_catheter(access_type)
    lo, hi = 1.0, 99.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        val = _ektv_from_urr_full(mid, session_mins, uf_tw_ratio, is_catheter)
        if val is None or val < target_ektv:
            lo = mid
        else:
            hi = mid
    result = (lo + hi) / 2.0
    if result >= 99.0:
        return None
    return round(result, 1)


def compute_urr_equivalence_table(
    target_ektv: float = 1.2,
    uf_tw_ratios: tuple = (0.02, 0.03, 0.04),
) -> Dict[str, Any]:
    """
    Generate the URR equivalence reference table (RA HD Guideline 2019 Appendix B).

    For each combination of access type, session duration, and UF/TW ratio, returns
    the URR% threshold required to achieve target_ektv. Matches the published table:
      Fistula 4.0h, UF/TW=0.02 → 70.0%, equivalent to eKt/V 1.2.

    The key clinical message: URR thresholds are NOT fixed — they vary meaningfully
    with session duration and UF/TW. A fixed URR=70% criterion is only valid for
    4-hour fistula patients at UF/TW=0.02.
    """
    fistula_hours = [3.5, 4.0, 4.5, 5.0]
    catheter_hours = [3.5, 4.0, 4.5, 5.0]

    def _row(hours, is_catheter):
        mins = hours * 60.0
        return {
            "hours": hours,
            "access": "catheter" if is_catheter else "fistula",
            "urr_by_uf_tw": {
                str(r): compute_urr_target_for_ektv(target_ektv, mins, r, "catheter" if is_catheter else "avf")
                for r in uf_tw_ratios
            },
        }

    return {
        "target_ektv": target_ektv,
        "uf_tw_ratios": list(uf_tw_ratios),
        "fistula_rows": [_row(h, False) for h in fistula_hours],
        "catheter_rows": [_row(h, True) for h in catheter_hours],
    }


# ── Residual renal clearance (Kru) combination methods ───────────────────────

def compute_ektv_kidney(
    kru_ml_min: float,
    target_weight_kg: float,
    f: float = _KRU_F_THRICE_WEEKLY,
) -> float:
    """
    Convert Kru to an equivalent per-session eKt/V contribution (RA HD 2019 §B).
      eKt/VKidney = Kru × F / Vu
      Vu (ml) = 580 × TW(kg)
      F = 5500 for thrice-weekly schedules
    """
    vu = _VU_FACTOR * target_weight_kg
    if vu <= 0:
        return 0.0
    return round(kru_ml_min * f / vu, 4)


def compute_combined_ektv(
    ektv_dialysis: float,
    kru_ml_min: float,
    target_weight_kg: float,
) -> Dict[str, Any]:
    """
    Combined eKt/V = eKt/VDialysis + eKt/VKidney (RA HD 2019 §B, method A).

    Returns dict with both components and the adequacy verdict.
    kru_ml_min: Kru or Krcr proxy (ml/min).
    """
    ektv_kidney = compute_ektv_kidney(kru_ml_min, target_weight_kg)
    combined = round(ektv_dialysis + ektv_kidney, 3)
    return {
        "ektv_dialysis": round(ektv_dialysis, 3),
        "ektv_kidney": round(ektv_kidney, 4),
        "combined_ektv": combined,
        "adequate": combined >= _COMBINED_EKT_V_MIN,
        "dialysis_alone_adequate": ektv_dialysis >= _EKT_V_MIN,
        "kru_contribution_pct": round(ektv_kidney / combined * 100, 1) if combined > 0 else 0.0,
    }


def compute_ekrc(
    ektv_dialysis: float,
    kru_ml_min: float = 0.0,
) -> Dict[str, Any]:
    """
    EKRc — Equivalent continuous Renal urea Clearance (Casino & Lopez, RA HD 2019 §B, method B).
      EKRc_dialysis (ml/min) = 1 + (10 × eKt/V)   [thrice-weekly]
      Total EKRc = EKRc_dialysis + Kru
      Target: ≥ 13 ml/min
    """
    ekrc_dialysis = round(1.0 + 10.0 * ektv_dialysis, 2)
    total_ekrc = round(ekrc_dialysis + kru_ml_min, 2)
    return {
        "ekrc_dialysis": ekrc_dialysis,
        "kru_ml_min": round(kru_ml_min, 2),
        "total_ekrc": total_ekrc,
        "adequate": total_ekrc >= _EKRC_TARGET_ML_MIN,
        "target": _EKRC_TARGET_ML_MIN,
        "kru_contribution_ml_min": round(kru_ml_min, 2),
    }


# ── HDF convective clearance helpers ─────────────────────────────────────────

def compute_hdf_convective_metrics(sessions: List[SessionRecord]) -> Dict[str, Any]:
    """
    Aggregate HDF filtration (convective) volume metrics for a set of sessions.

    Filtration volume = actual_uf_volume (or uf_volume fallback) per HDF session.
    This is the standard metric for quantifying convective component in post-dilution HDF
    (RA HD 2019 Appendix C). Convective clearance is negligible for small solutes
    (urea) but significant for middle molecules (e.g. β2-microglobulin).
    """
    hdf_sessions = [s for s in sessions if _is_hdf(s)]
    if not hdf_sessions:
        return {
            "hdf_session_count": 0,
            "avg_filtration_volume_l": None,
            "total_filtration_volume_l": None,
            "sessions_with_data": 0,
        }

    volumes = []
    for s in hdf_sessions:
        vol = s.actual_uf_volume if s.actual_uf_volume is not None else s.uf_volume
        if vol is not None and vol > 0:
            volumes.append(vol)

    return {
        "hdf_session_count": len(hdf_sessions),
        "avg_filtration_volume_l": round(statistics.mean(volumes), 2) if volumes else None,
        "total_filtration_volume_l": round(sum(volumes), 1) if volumes else None,
        "sessions_with_data": len(volumes),
    }


def _resolve_ektv(
    record: MonthlyRecord,
    access_type: Optional[str],
    avg_session_mins: float,
) -> Tuple[Optional[float], str]:
    """
    Resolve the best available eKt/V for a monthly record.

    Returns (value, method_label).
    """
    # Priority 1: directly entered eKt/V
    if record.equilibrated_ktv is not None:
        return record.equilibrated_ktv, "measured"

    # Priority 2: Tattersall from spKt/V
    if record.single_pool_ktv is not None and avg_session_mins > 0:
        ektv = compute_ektv_from_spktv(record.single_pool_ktv, avg_session_mins, access_type)
        return ektv, "tattersall"

    # Priority 3: Daugirdas spKt/V from urea values + UF
    if (
        record.pre_dialysis_urea is not None
        and record.post_dialysis_urea is not None
        and record.ufr is not None
        and record.target_dry_weight is not None
        and avg_session_mins > 0
    ):
        spktv = compute_spktv_daugirdas(
            upre=record.pre_dialysis_urea,
            upost=record.post_dialysis_urea,
            uf_litres=record.ufr,
            target_weight_kg=record.target_dry_weight,
            session_mins=avg_session_mins,
        )
        if spktv is not None:
            ektv = compute_ektv_from_spktv(spktv, avg_session_mins, access_type)
            return ektv, "daugirdas+tattersall"

    # Priority 4: Log-Ratio from URR (last resort)
    if record.urr is not None:
        return compute_ektv_log_ratio_from_urr(record.urr), "log_ratio_urr"

    return None, "unavailable"


def _prev_months(anchor: str, n: int) -> List[str]:
    """Return n ascending YYYY-MM strings ending at anchor."""
    dt = datetime.strptime(anchor + "-01", "%Y-%m-%d")
    months = []
    for i in range(n - 1, -1, -1):
        m = dt.replace(day=1)
        for _ in range(i):
            m = (m - timedelta(days=1)).replace(day=1)
        months.append(m.strftime("%Y-%m"))
    return months


# ── Public API ────────────────────────────────────────────────────────────────

def compute_unit_hdf_utilization(db: Session, month_str: str) -> Dict[str, Any]:
    """Unit-level HDF utilization for a given month (YYYY-MM)."""
    sessions: List[SessionRecord] = (
        db.query(SessionRecord)
        .filter(SessionRecord.record_month == month_str)
        .all()
    )

    total = len(sessions)
    hdf_count = sum(1 for s in sessions if _is_hdf(s))

    pat_sessions: Dict[int, List[SessionRecord]] = defaultdict(list)
    for s in sessions:
        pat_sessions[s.patient_id].append(s)

    patient_rows: List[Dict[str, Any]] = []
    for pid, sess in pat_sessions.items():
        phdf = [s for s in sess if _is_hdf(s)]
        total_hrs = sum(_session_hours(s) for s in sess)
        avg_hrs_week = round(total_hrs / 4.33, 1)
        conv = compute_hdf_convective_metrics(sess)
        patient_rows.append({
            "patient_id": pid,
            "total_sessions": len(sess),
            "hdf_sessions": len(phdf),
            "hdf_pct": round(len(phdf) / len(sess) * 100, 1) if sess else 0.0,
            "avg_hrs_week": avg_hrs_week,
            "below_12h_target": avg_hrs_week < _HD_MIN_HOURS_WEEK,
            # HDF convective volume
            "avg_filtration_volume_l": conv["avg_filtration_volume_l"],
            "total_filtration_volume_l": conv["total_filtration_volume_l"],
        })

    patient_rows.sort(key=lambda x: x["hdf_pct"], reverse=True)

    return {
        "month_str": month_str,
        "total_sessions": total,
        "hdf_sessions": hdf_count,
        "unit_hdf_pct": round(hdf_count / total * 100, 1) if total else 0.0,
        "conventional_sessions": total - hdf_count,
        "patient_rows": patient_rows,
    }


def compute_ektv_monitoring(
    db: Session,
    month_str: str,
    lookback_months: int = 6,
    audit_population_only: bool = True,
) -> Dict[str, Any]:
    """
    Monthly eKt/V monitoring (RA HD Audit Measure 1).

    When audit_population_only=True, restricts to thrice-weekly patients
    on dialysis for ≥ 1 year (RA HD 2019 Audit Measure 1 definition).

    eKt/V is resolved via the hierarchy: measured → Tattersall → Daugirdas+Tattersall
    → Log-Ratio from URR.  Session duration and access type are required for
    the Tattersall and Daugirdas steps and are fetched from session records.
    """
    months = _prev_months(month_str, lookback_months)

    # ── Load monthly records ───────────────────────────────────────────────────
    records: List[MonthlyRecord] = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.record_month.in_(months))
        .all()
    )
    by_patient: Dict[int, Dict[str, MonthlyRecord]] = defaultdict(dict)
    for r in records:
        by_patient[r.patient_id][r.record_month] = r

    if not by_patient:
        return {
            "month_str": month_str,
            "months": months,
            "patient_rows": [],
            "unit_adequacy_pct": 0.0,
            "ektv_threshold": _EKT_V_MIN,
            "audit_median_ektv": None,
            "audit_pct_adequate": 0.0,
            "audit_n": 0,
        }

    # ── Load patients (for access type + HD start date) ───────────────────────
    all_pids = list(by_patient.keys())
    patients: Dict[int, Patient] = {
        p.id: p
        for p in db.query(Patient).filter(Patient.id.in_(all_pids)).all()
    }

    # ── Load sessions for the lookback window (avg duration per patient/month) ─
    sessions: List[SessionRecord] = (
        db.query(SessionRecord)
        .filter(
            SessionRecord.patient_id.in_(all_pids),
            SessionRecord.record_month.in_(months),
        )
        .all()
    )
    # avg session duration (minutes) per (patient_id, record_month)
    sess_by_pm: Dict[Tuple[int, str], List[float]] = defaultdict(list)
    monthly_counts: Dict[Tuple[int, str], int] = defaultdict(int)
    for s in sessions:
        mins = _session_minutes(s)
        if mins > 0:
            sess_by_pm[(s.patient_id, s.record_month)].append(mins)
        monthly_counts[(s.patient_id, s.record_month)] += 1

    # ── Build per-patient rows ────────────────────────────────────────────────
    patient_rows: List[Dict[str, Any]] = []

    for pid, month_map in by_patient.items():
        patient = patients.get(pid)
        access_type = patient.access_type if patient else None

        # Audit population filter
        is_audit_patient = False
        if patient and patient.hd_wef_date:
            on_dialysis_since = patient.hd_wef_date
            if hasattr(on_dialysis_since, 'date'):
                on_dialysis_since = on_dialysis_since.date()
            years_on_hd = (date.today() - on_dialysis_since).days / 365.25
            # Session count in anchor month to determine frequency
            anchor_sessions = monthly_counts.get((pid, month_str), 0)
            is_thrice_weekly = anchor_sessions >= _THRICE_WEEKLY_MIN_SESSIONS_MONTH
            is_audit_patient = years_on_hd >= _AUDIT_ON_DIALYSIS_YEARS and is_thrice_weekly

        # Resolve eKt/V for each month
        ektv_values: List[Optional[float]] = []
        method_labels: List[str] = []
        for m in months:
            rec = month_map.get(m)
            if rec is None:
                ektv_values.append(None)
                method_labels.append("no_record")
                continue
            sess_mins_list = sess_by_pm.get((pid, m), [])
            avg_mins = statistics.mean(sess_mins_list) if sess_mins_list else 0.0
            val, method = _resolve_ektv(rec, access_type, avg_mins)
            ektv_values.append(val)
            method_labels.append(method)

        valid = [v for v in ektv_values if v is not None]
        inadequate_months = sum(1 for v in valid if v < _EKT_V_MIN)
        current = ektv_values[-1]
        current_method = method_labels[-1]

        trend = "no_data"
        if len(valid) >= 3:
            if valid[-1] > valid[-3]:
                trend = "improving"
            elif valid[-1] < valid[-3]:
                trend = "declining"
            else:
                trend = "stable"

        # URR, patient-specific URR threshold, and Kru from anchor month record
        anchor_rec = month_map.get(month_str)
        urr_actual = None
        urr_threshold = None     # patient-specific URR needed for eKt/V 1.2
        urr_adequate_by_threshold = None
        combined: Optional[Dict[str, Any]] = None
        ekrc: Optional[Dict[str, Any]] = None

        if anchor_rec:
            if anchor_rec.urr is not None:
                urr_actual = round(anchor_rec.urr, 1)

            # Compute patient-specific URR threshold from their session duration and UF/TW
            anchor_sess_mins_list = sess_by_pm.get((pid, month_str), [])
            avg_mins_anchor = statistics.mean(anchor_sess_mins_list) if anchor_sess_mins_list else 0.0

            if avg_mins_anchor > 0 and anchor_rec.target_dry_weight:
                # Average UF volume per session this month
                anchor_sess_list = [s for s in sessions if s.patient_id == pid and s.record_month == month_str]
                uf_vols = [s.actual_uf_volume or s.uf_volume for s in anchor_sess_list
                           if (s.actual_uf_volume or s.uf_volume)]
                if uf_vols:
                    avg_uf = statistics.mean(uf_vols)
                    uf_tw = avg_uf / anchor_rec.target_dry_weight
                    urr_threshold = compute_urr_target_for_ektv(
                        _EKT_V_MIN, avg_mins_anchor, uf_tw, access_type
                    )
                    if urr_actual is not None and urr_threshold is not None:
                        urr_adequate_by_threshold = urr_actual >= urr_threshold

            # Combined clearance: use krcr as Kru proxy (ml/min)
            kru = anchor_rec.krcr
            tw = anchor_rec.target_dry_weight

            if current is not None and kru is not None and tw:
                combined = compute_combined_ektv(current, kru, tw)
                ekrc = compute_ekrc(current, kru)
            elif current is not None:
                ekrc = compute_ekrc(current, 0.0)

        patient_rows.append({
            "patient_id": pid,
            "months": months,
            "values": ektv_values,
            "method_labels": method_labels,
            "current_ektv": current,
            "current_method": current_method,
            "adequate": current is not None and current >= _EKT_V_MIN,
            "inadequate_months": inadequate_months,
            "trend": trend,
            "is_audit_patient": is_audit_patient,
            "urr_actual": urr_actual,
            "urr_threshold": urr_threshold,
            "urr_adequate_by_threshold": urr_adequate_by_threshold,
            "access_type": access_type,
            # Combined clearance
            "combined": combined,  # None if Kru unavailable
            "ekrc": ekrc,
        })

    # ── Audit Measure 1 summary ───────────────────────────────────────────────
    audit_rows = [r for r in patient_rows if r["is_audit_patient"]] if audit_population_only else patient_rows
    audit_valid = [r["current_ektv"] for r in audit_rows if r["current_ektv"] is not None]
    audit_median = round(statistics.median(audit_valid), 3) if len(audit_valid) >= 2 else (audit_valid[0] if audit_valid else None)
    audit_pct_adequate = (
        sum(1 for v in audit_valid if v >= _EKT_V_MIN) / len(audit_valid) * 100
        if audit_valid else 0.0
    )

    # ── All-patient unit summary ──────────────────────────────────────────────
    all_valid = [r for r in patient_rows if r["current_ektv"] is not None]
    unit_pct_adequate = (
        sum(1 for r in all_valid if r["adequate"]) / len(all_valid) * 100
        if all_valid else 0.0
    )

    return {
        "month_str": month_str,
        "months": months,
        "patient_rows": patient_rows,
        "unit_adequacy_pct": round(unit_pct_adequate, 1),
        "ektv_threshold": _EKT_V_MIN,
        # Audit Measure 1
        "audit_median_ektv": audit_median,
        "audit_pct_adequate": round(audit_pct_adequate, 1),
        "audit_n": len(audit_valid),
        "audit_population_filter": audit_population_only,
    }
