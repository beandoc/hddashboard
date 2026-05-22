"""
dashboard_logic.py
==================
Core clinical calculation logic for the Hemodialysis Dashboard.
Locked - Do not modify without clinical validation.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from database import Patient, MonthlyRecord, InterimLabRecord, SessionRecord, ClinicalEvent
from datetime import datetime, timedelta
import logging
from ml_analytics import normalize_epo_dose

logger = logging.getLogger(__name__)

# In-memory cache for dashboard results
_DASHBOARD_CACHE = {}
_CACHE_EXPIRY_SECONDS = 300  # 5 minutes — monthly data changes infrequently during a shift


def _resolve_epo_dose(r):
    """Return weekly SC IU dose from MonthlyRecord, or None if not determinable.

    Returns None for HIF-PHI agents (Desidustat / Roxadustat) — ERI and EPO
    responsiveness metrics are mechanistically inapplicable for oral HIF-PHI
    therapy and must NOT be computed from EPO IU equivalents.
    """
    # ── Guard: HIF-PHI agents are NOT dosed in IU; exclude from ERI pipeline ──
    _esa = (r.esa_type or "").strip().lower()
    if _esa in ("desidustat", "roxadustat", "daprodustat", "vadadustat"):
        return None  # ERI/EPO responsiveness not applicable

    if r.epo_weekly_units:
        return r.epo_weekly_units
    if r.epo_mircera_dose:
        _p = normalize_epo_dose(r.epo_mircera_dose)
        if _p.get("confidence") == "high":
            return _p.get("weekly_iu_iv")
    return None


def _esa_hypo_causes(r) -> list[str]:
    """
    Check known causes of ESA hyporesponsiveness for a MonthlyRecord.
    Returns list of cause strings to display alongside the HypoR flag.
    """
    causes = []

    # 1. Absolute iron deficiency: TSAT < 20%; fall back to serum_iron < 60 when TSAT absent
    #    (Ferritin excluded — unreliable at this facility)
    abs_iron = (
        (r.tsat is not None and r.tsat < 20) or
        (r.tsat is None and r.serum_iron is not None and r.serum_iron < 60)
    )
    # 2. Functional iron deficiency: TSAT 20–25% (iron available but utilisation poor)
    func_iron = (
        not abs_iron and
        r.tsat is not None and 20 <= r.tsat < 25
    )
    if abs_iron:
        causes.append("Absolute Iron Deficiency")
    elif func_iron:
        causes.append("Functional Iron Deficiency")

    # 3. Infection / Inflammation: High TLC (WBC > 10 ×10³/µL) or high CRP
    if r.wbc_count is not None and r.wbc_count > 10:
        causes.append(f"High TLC ({r.wbc_count:.1f})")
    elif hasattr(r, "crp") and r.crp is not None and r.crp > 10:
        causes.append(f"Inflammation (CRP {r.crp:.1f})")

    # 4. Inadequate dialysis: spKt/V < 1.2
    if r.single_pool_ktv is not None and r.single_pool_ktv < 1.2:
        causes.append(f"Inadequate Dialysis (Kt/V {r.single_pool_ktv:.2f})")

    # 5. Severe hyperparathyroidism: iPTH > 800 pg/mL
    if r.ipth is not None and r.ipth > 800:
        causes.append(f"Severe HPT (iPTH {r.ipth:.0f})")

    return causes


def get_current_month_str():
    return datetime.now().strftime("%Y-%m")

def get_month_label(month_str: str) -> str:
    dt = datetime.strptime(month_str, "%Y-%m")
    return dt.strftime("%B %Y")

def get_effective_month(db: Session, requested_month: str = None) -> tuple:
    """
    Returns (month_str, data_note).
    Falls back to the previous month when the current month has no records yet,
    or when fewer than 50% of active patients have records (month is still being
    entered and the incomplete data would mislead clinical metrics).
    """
    if requested_month:
        return requested_month, None

    current = get_current_month_str()
    current_dt = datetime.strptime(current, "%Y-%m")
    # 1st of current month minus 1 day gives last day of prev month
    prev_dt = current_dt.replace(day=1) - timedelta(days=1)
    prev = prev_dt.strftime("%Y-%m")

    record_count = db.query(func.count(MonthlyRecord.patient_id)).filter(
        MonthlyRecord.record_month == current
    ).scalar() or 0

    if record_count == 0:
        return prev, "new_month_no_data"

    active_count = db.query(func.count(Patient.id)).filter(Patient.is_active == True).scalar() or 0
    threshold = active_count * 0.5
    
    if active_count > 0 and record_count < threshold:
        import logging
        logging.info(f"Fallback triggered: month={current}, records={record_count}, active={active_count}, threshold={threshold}. Using {prev}")
        return prev, "new_month_no_data"

    return current, None

def make_sparkline_points(values: list, width: int = 70, height: int = 20) -> str:
    # Filter out None values
    valid_vals = [float(v) for v in values if v is not None]
    if len(valid_vals) < 2:
        return ""
    min_v = min(valid_vals)
    max_v = max(valid_vals)
    range_v = max_v - min_v if max_v != min_v else 1.0
    
    points = []
    n = len(values)
    for i, v in enumerate(values):
        if v is None:
            continue
        # x-coordinate evenly spaced
        x = (i / (n - 1)) * width if n > 1 else width / 2
        # y-coordinate normalized (inverted since SVG y=0 is top)
        y = height - ((float(v) - min_v) / range_v) * (height - 4) - 2
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def compute_dashboard(db: Session, month: str = None):
    """
    Compute aggregate metrics and per-patient rows for the clinical dashboard.
    Uses in-memory caching to avoid redundant heavy calculations.
    """
    if not month:
        month = get_current_month_str()

    # 1. Check Cache
    global _DASHBOARD_CACHE
    
    # Get last modification timestamp for this month to invalidate cache if data changed
    last_mod = db.query(func.max(MonthlyRecord.timestamp)).filter(MonthlyRecord.record_month == month).scalar()
    last_mod_str = last_mod.isoformat() if last_mod else "none"
    
    cache_key = f"{month}_{last_mod_str}_v2"
    now = datetime.utcnow()
    
    if cache_key in _DASHBOARD_CACHE:
        cached_data, expiry = _DASHBOARD_CACHE[cache_key]
        if now < expiry:
            return cached_data

    # 2. If not in cache or expired, compute from scratch
    try:
        y, m = int(month[:4]), int(month[5:7])
        if m == 1:
            prev_month = f"{y-1}-12"
        else:
            prev_month = f"{y}-{m-1:02d}"
    except Exception as e:
        logger.error(f"Month parsing error for '{month}': {e}")
        raise


    metrics = {
        'total_patients': {'count': 0, 'names': []},
        'male_patients': {'count': 0, 'names': []},
        'female_patients': {'count': 0, 'names': []},
        'non_avf': {'count': 0, 'names': [], 'types': {}},
        'idwg_high': {'count': 0, 'names': []},
        'albumin_low': {'count': 0, 'names': []},
        'calcium_low': {'count': 0, 'names': []},
        'phos_high': {'count': 0, 'names': []},
        'epo_hypo':    {'count': 0, 'names': []},   # HypoR1: ERI ≥ 2.0 WITH Hb < 11.0 g/dL (KDIGO)
        'epo_hypo_r2': {'count': 0, 'names': []},   # HypoR2: ERI ≥ 1.5 WITH Hb < 11.0 g/dL
        'epo_hypo_r3': {'count': 0, 'names': [], 'cutoff': None},  # HypoR3: top 10th %ile dose WITH Hb < 11.0
        'esa_de_escalation': {'count': 0, 'names': []},  # Hb at/above target but dose still high — consider weaning
        'iv_iron_rec': {'count': 0, 'names': []},
        'hb_high': {'count': 0, 'names': []},
        'hb_variability_high': {'count': 0, 'names': []}, # Range > 2.5 g/dL (High risk)
        'hb_drop_alert': {'count': 0, 'names': []},
        'dialysis_intensification': {'count': 0, 'names': []},
        'missing_records': {'count': 0, 'names': []},
        'adherence_risk':  {'count': 0, 'names': [], 'flags': {}}, # USRDS criteria
        'ipth_very_high': {'count': 0, 'names': []},               # iPTH > 1000 pg/mL
        'infectious_hd': {'count': 0, 'names': []},                # HBsAg / HCV / HIV positive on HD
        'avf_low_flow': {'count': 0, 'names': []},                 # AVF with actual BFR < 250 ml/min
        'transplant_prospects': {'count': 0, 'names': []},         # Active or Listed transplant candidates
        'cadaveric_listed': {'count': 0, 'names': []},             # Registered on cadaveric waitlist
        'avf_count': 0,                                             # For vascular access bar chart
        'avg_count': 0,
        'trend_hb': [],
        'trend_albumin': [],
        'trend_phosphorus': [],
        'avg_hb': None,
    }

    # 6-month list for Hb Variability
    six_months = []
    try:
        curr_y, curr_m = int(month[:4]), int(month[5:7])
        for i in range(6):
            target_m = curr_m - i
            target_y = curr_y
            while target_m <= 0:
                target_m += 12
                target_y -= 1
            six_months.append(f"{target_y}-{target_m:02d}")
    except:
        six_months = [month]

    # Fetch all active patients in alphabetical order (eager-load sub-tables used for new metrics)
    from sqlalchemy.orm import joinedload
    active_patients = (
        db.query(Patient)
        .filter(Patient.is_active == True)
        .options(
            joinedload(Patient.viral_markers_),
            joinedload(Patient.renal_profile),
            joinedload(Patient.vascular_access),
        )
        .order_by(Patient.name)
        .all()
    )
    patient_map = {p.id: p for p in active_patients}
    
    # Process Demographics
    for p in active_patients:
        metrics['total_patients']['count'] += 1
        metrics['total_patients']['names'].append(p.name)
        
        s = (p.sex or "Unknown").strip().capitalize()
        if s == "Male":
            metrics['male_patients']['count'] += 1
            metrics['male_patients']['names'].append(p.name)
        elif s == "Female":
            metrics['female_patients']['count'] += 1
            metrics['female_patients']['names'].append(p.name)

    # Fetch Clinical Records for selected month
    records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month).yield_per(100).all()
    record_map = {r.patient_id: r for r in records}

    # Fetch previous month records for trendlines
    prev_records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == prev_month).yield_per(100).all()
    prev_record_map = {r.patient_id: r for r in prev_records}

    # Fetch all records for the last 6 months for variability and sparklines
    all_6m_records = db.query(MonthlyRecord).filter(
        MonthlyRecord.record_month.in_(six_months)
    ).all()
    
    # Map patient_id -> chronologically sorted lists of hb, albumin, single_pool_ktv
    chrono_months = list(reversed(six_months))
    history_by_patient = {}
    hb_history = {}
    for rec in all_6m_records:
        pid = rec.patient_id
        if pid not in history_by_patient:
            history_by_patient[pid] = {m: {"hb": None, "albumin": None, "ktv": None} for m in chrono_months}
        if rec.record_month in history_by_patient[pid]:
            history_by_patient[pid][rec.record_month] = {
                "hb": float(rec.hb) if rec.hb is not None else None,
                "albumin": float(rec.albumin) if rec.albumin is not None else None,
                "ktv": float(rec.single_pool_ktv) if rec.single_pool_ktv is not None else None
            }
        
        # Keep hb_history populated for backward compatibility with existing code
        if rec.hb is not None:
            if pid not in hb_history:
                hb_history[pid] = []
            hb_history[pid].append(rec.hb)

    # Fetch interim records for this month
    interim_labs = db.query(InterimLabRecord).filter(InterimLabRecord.record_month == month).order_by(InterimLabRecord.lab_date.asc()).yield_per(100).all()
    # Build a map of patient_id -> {parameter: latest_value}
    interim_map = {}
    for il in interim_labs:
        if il.patient_id not in interim_map:
            interim_map[il.patient_id] = {}
        interim_map[il.patient_id][il.parameter] = {
            "value": il.value,
            "date": il.lab_date,
            "trigger": il.trigger
        }

    # ── Pre-pass: collect all EPO doses for HypoR3 (80th percentile cutoff) ──
    _all_doses = []
    for _r in records:
        _d = _resolve_epo_dose(_r)
        if _d:
            _all_doses.append(_d)
    _all_doses.sort()

    def _percentile(sorted_vals, p):
        if not sorted_vals:
            return None
        idx = (p / 100) * (len(sorted_vals) - 1)
        lo, hi = int(idx), min(int(idx) + 1, len(sorted_vals) - 1)
        return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)

    _hypo_r3_cutoff = _percentile(_all_doses, 90)  # top 10% = > 90th percentile
    metrics['epo_hypo_r3']['cutoff'] = round(_hypo_r3_cutoff, 0) if _hypo_r3_cutoff else None

    # Fetch sessions for the month to check adherence (skipping/shortening)
    all_month_sessions = db.query(SessionRecord).filter(SessionRecord.record_month == month).all()
    session_by_patient = {}
    for s in all_month_sessions:
        if s.patient_id not in session_by_patient:
            session_by_patient[s.patient_id] = []
        session_by_patient[s.patient_id].append(s)

    # Fetch latest session date per patient for current month
    session_map = {}
    session_rows = (
        db.query(SessionRecord.patient_id, func.max(SessionRecord.session_date))
        .filter(SessionRecord.patient_id.in_([p.id for p in active_patients]))
        .group_by(SessionRecord.patient_id)
        .all()
    )
    for pid, sdate in session_rows:
        session_map[pid] = sdate

    # ── Transplant prospects & infectious serology (patient-level, no record needed) ──
    for p in active_patients:
        tp = (p.transplant_prospect or "").strip()
        if tp in ("Active", "Listed", "Inactive"):
            metrics['transplant_prospects']['count'] += 1
            metrics['transplant_prospects']['names'].append(p.name)
        if tp == "Listed":
            metrics['cadaveric_listed']['count'] += 1
            metrics['cadaveric_listed']['names'].append(p.name)
        _hbsag = (p.viral_hbsag or "").strip().lower()
        _hcv   = (p.viral_anti_hcv or "").strip().lower()
        _hiv   = (p.viral_hiv or "").strip().lower()
        if "positive" in _hbsag or "positive" in _hcv or "positive" in _hiv:
            metrics['infectious_hd']['count'] += 1
            metrics['infectious_hd']['names'].append(p.name)

    # ── Latest actual blood flow rate per patient (for AVF low-flow check) ──
    _avf_bfr_rows = (
        db.query(SessionRecord.patient_id, func.max(SessionRecord.actual_blood_flow_rate))
        .filter(
            SessionRecord.patient_id.in_([p.id for p in active_patients]),
            SessionRecord.actual_blood_flow_rate.isnot(None),
        )
        .group_by(SessionRecord.patient_id)
        .all()
    )
    _avf_bfr_map = {pid: bfr for pid, bfr in _avf_bfr_rows}

    # ── Batch-load latest hospitalization/discharge event per patient ────────
    # Replaces 1-query-per-patient lookup inside the loop (N+1 → 1 query).
    # We fetch all Hospitalization/Discharge events for active patients, sorted
    # desc by date then id, and keep only the most-recent one per patient.
    hosp_events_raw = (
        db.query(ClinicalEvent)
        .filter(
            ClinicalEvent.patient_id.in_([p.id for p in active_patients]),
            ClinicalEvent.event_type.in_(["Hospitalization", "Discharge"]),
        )
        .order_by(ClinicalEvent.patient_id, ClinicalEvent.event_date.desc(), ClinicalEvent.id.desc())
        .all()
    )
    # Keep only the most-recent event per patient
    latest_hosp_event: dict = {}
    for ev in hosp_events_raw:
        if ev.patient_id not in latest_hosp_event:
            latest_hosp_event[ev.patient_id] = ev

    patient_rows = []

    for p in active_patients:
        r = record_map.get(p.id)

        # Determine which core fields are missing (for the Missing Data counter)
        # Core fields required for complete clinical review:
        _CORE_FIELDS = {
            "Hb": r.hb if r else None,
            "Albumin": r.albumin if r else None,
            "Phosphorus": r.phosphorus if r else None,
            "Calcium": r.calcium if r else None,
            "TSAT": r.tsat if r else None,
        }
        _missing_fields = [k for k, v in _CORE_FIELDS.items() if v is None]

        # 1. Determine Admission Status (O(1) dict lookup — batch-loaded above)
        last_hosp_event = latest_hosp_event.get(p.id)
        is_admitted = (last_hosp_event.event_type == "Hospitalization") if last_hosp_event else False

        # 2. Initialize Row Basic Data
        _has_missing_data = bool(_missing_fields)
        row = {
            "id": p.id,
            "last_session_date": session_map.get(p.id),
            "name": p.name,
            "hid": p.hid_no,
            "has_record": r is not None,
            "has_missing_data": _has_missing_data,
            "is_admitted": is_admitted,
            "missing_fields": _missing_fields,
            "access": r.access_type if r else p.access_type,
            "idwg": r.idwg if r else None,
            "hb": r.hb if r else None,
            "ferritin": r.serum_ferritin if r else None,
            "tsat": r.tsat if r else None,
            "corrected_ca": round(r.calcium + 0.8 * (4.0 - r.albumin), 2) if (r and r.calcium and r.albumin and r.calcium is not None and r.albumin is not None) else (r.calcium if r else None),
            "phosphorus": r.phosphorus if r else None,
            "albumin": r.albumin if r else None,
            "ipth": r.ipth if r else None,
            "vit_d": r.vit_d if r else None,
            "protein": r.av_daily_protein if r else None,
            "hb_var_range": None,
            "hb_var_pattern": None,
            "adherence_flags": [],
            "is_interim": False,
            "interim_details": {},
            "alerts": []
        }

        # 2.5 Sparkline Trends
        p_hist = history_by_patient.get(p.id, {})
        hb_vals = [p_hist.get(m, {}).get("hb") for m in chrono_months] if p_hist else []
        alb_vals = [p_hist.get(m, {}).get("albumin") for m in chrono_months] if p_hist else []
        ktv_vals = [p_hist.get(m, {}).get("ktv") for m in chrono_months] if p_hist else []
        
        # Helper to check trend direction
        def get_trend_dir(vals):
            valid = [v for v in vals if v is not None]
            if len(valid) < 2:
                return "stable"
            return "up" if valid[-1] >= valid[0] else "down"
            
        row["hb_sparkline"] = {
            "points": make_sparkline_points(hb_vals),
            "values": [v for v in hb_vals if v is not None],
            "last": next((v for v in reversed(hb_vals) if v is not None), None),
            "trend": get_trend_dir(hb_vals)
        }
        row["alb_sparkline"] = {
            "points": make_sparkline_points(alb_vals),
            "values": [v for v in alb_vals if v is not None],
            "last": next((v for v in reversed(alb_vals) if v is not None), None),
            "trend": get_trend_dir(alb_vals)
        }
        row["ktv_sparkline"] = {
            "points": make_sparkline_points(ktv_vals),
            "values": [v for v in ktv_vals if v is not None],
            "last": next((v for v in reversed(ktv_vals) if v is not None), None),
            "trend": get_trend_dir(ktv_vals)
        }

        # 3. Hb Variability Analysis
        hist = hb_history.get(p.id, [])
        if len(hist) >= 1:
            hb_var_range = round(max(hist) - min(hist), 1)
            row["hb_var_range"] = hb_var_range
            if hb_var_range > 2.5:
                metrics['hb_variability_high']['count'] += 1
                metrics['hb_variability_high']['names'].append(p.name)
            
            has_low = any(v < 11.0 for v in hist)
            has_target = any(11.0 <= v < 12.5 for v in hist)
            has_high = any(v >= 12.5 for v in hist)
            
            if has_low and not has_target and not has_high: hb_var_pattern = 1
            elif not has_low and has_target and not has_high: hb_var_pattern = 2
            elif not has_low and not has_target and has_high: hb_var_pattern = 3
            elif has_low and has_target and not has_high: hb_var_pattern = 4
            elif not has_low and has_target and has_high: hb_var_pattern = 5
            elif has_low and has_high: hb_var_pattern = 6
            row["hb_var_pattern"] = hb_var_pattern

        # 4. Adherence Monitor (USRDS)
        adherence_flags = []
        pt_sessions = session_by_patient.get(p.id, [])
        if len(pt_sessions) < 10 and not is_admitted:
             adherence_flags.append("Skipped Sessions")
        
        shortened = False
        for s in pt_sessions:
            actual_min = (s.duration_hours or 0) * 60 + (s.duration_minutes or 0)
            prescribed_min = s.scheduled_treatment_duration or 240
            if prescribed_min - actual_min >= 10:
                shortened = True
                break
        if shortened: adherence_flags.append("Shortened Sessions")
            
        if r and r.idwg and (r.target_dry_weight or p.dry_weight):
            dw = r.target_dry_weight or p.dry_weight
            if (r.idwg / dw * 100) > 5.7: adherence_flags.append("High IDWG (>5.7%)")
        
        if r and r.phosphorus and r.phosphorus > 7.5: adherence_flags.append("Hyperphosphatemia (>7.5)")
            
        if adherence_flags:
            metrics['adherence_risk']['count'] += 1
            metrics['adherence_risk']['names'].append(p.name)
            metrics['adherence_risk']['flags'][p.id] = adherence_flags
            row["adherence_flags"] = adherence_flags
            for f in adherence_flags:
                row["alerts"].append(f)

        # 5. Override with Latest Interim Labs
        p_interim = interim_map.get(p.id, {})
        if p_interim:
            if "hb" in p_interim:
                row["hb"] = p_interim["hb"]["value"]
                row["is_interim"] = True
                row["interim_details"]["hb"] = p_interim["hb"]
            if "albumin" in p_interim:
                row["albumin"] = p_interim["albumin"]["value"]
                row["is_interim"] = True
                row["interim_details"]["albumin"] = p_interim["albumin"]
            if "phosphorus" in p_interim:
                row["phosphorus"] = p_interim["phosphorus"]["value"]
                row["is_interim"] = True
                row["interim_details"]["phosphorus"] = p_interim["phosphorus"]
            if "calcium" in p_interim:
                # Recalculate corrected calcium if either calcium or albumin is interim
                _ca = p_interim["calcium"]["value"]
                _alb = row["albumin"] # might be interim already
                row["corrected_ca"] = round(_ca + 0.8 * (4.0 - _alb), 2) if (_ca and _alb) else _ca
                row["is_interim"] = True
                row["interim_details"]["calcium"] = p_interim["calcium"]
            elif "albumin" in p_interim:
                # Albumin updated but calcium is from MonthlyRecord
                _ca = r.calcium if r else None
                _alb = p_interim["albumin"]["value"]
                row["corrected_ca"] = round(_ca + 0.8 * (4.0 - _alb), 2) if (_ca and _alb) else _ca
            
            if "ipth" in p_interim:
                row["ipth"] = p_interim["ipth"]["value"]
                row["is_interim"] = True
                row["interim_details"]["ipth"] = p_interim["ipth"]
            if "vit_d" in p_interim:
                row["vit_d"] = p_interim["vit_d"]["value"]
                row["is_interim"] = True
                row["interim_details"]["vit_d"] = p_interim["vit_d"]
        
        # 1. Vascular Access classification
        name = p.name
        raw_access = ((r.access_type if r else None) or p.access_type or "").strip()
        _a_upper = raw_access.upper()
        if any(kw in _a_upper for kw in ("PERMACATH", "P/CATH", "P-CATH", "PCATH", "TCC", "DLJC", "FEMORAL")):
            access = "Permacath"
        else:
            access = raw_access
        _access_up = access.upper()

        # Track AVF / AVG counts for the bar chart
        if "AVF" in _access_up or "FISTULA" in _access_up:
            metrics['avf_count'] += 1
        elif "AVG" in _access_up or "GRAFT" in _access_up:
            metrics['avg_count'] += 1

        if access and "AVF" not in _access_up and "FISTULA" not in _access_up:
            metrics['non_avf']['count'] += 1
            metrics['non_avf']['names'].append(name)
            if access not in metrics['non_avf']['types']:
                metrics['non_avf']['types'][access] = {"count": 0, "names": []}
            metrics['non_avf']['types'][access]["count"] += 1
            metrics['non_avf']['types'][access]["names"].append(name)
            row["alerts"].append("Non-AVF")

        # AVF with low blood flow (< 250 ml/min)
        if "AVF" in _access_up or "FISTULA" in _access_up:
            _bfr = _avf_bfr_map.get(p.id)
            if _bfr is not None and _bfr < 250:
                metrics['avf_low_flow']['count'] += 1
                metrics['avf_low_flow']['names'].append(name)
                row["alerts"].append("AVF Low Flow")

        if r:
                
            prev_r = prev_record_map.get(p.id)

            # 2. IDWG >= 2.5kg
            if r.idwg and r.idwg >= 2.5:
                metrics['idwg_high']['count'] += 1
                metrics['idwg_high']['names'].append(name)
                row["alerts"].append("High Interdialytic Weight Gain")

            # Hb < 9 g/dL — tracked for Hemoglobin trendline
            # Use row["hb"] so interim lab overrides are reflected (not raw r.hb)
            effective_hb = row["hb"]
            prev_hb = prev_r.hb if prev_r else None
            hb_drop = round(prev_hb - effective_hb, 2) if effective_hb and prev_hb else None
            if effective_hb and effective_hb < 9:
                metrics['trend_hb'].append({
                    "id": p.id,
                    "name": name,
                    "current": effective_hb,
                    "previous": prev_hb,
                    "drop": hb_drop,
                })

            # Hb Drop Alert: Hb drops by > 1.5 g/dL compared to previous month
            if hb_drop and hb_drop > 1.5:
                metrics['hb_drop_alert']['count'] += 1
                metrics['hb_drop_alert']['names'].append(name)
                row["alerts"].append("Hb Drop")

            # Dialysis Intensification Alert: Phos rising (current > prev) AND IDWG >= 2.5
            prev_phos = prev_r.phosphorus if prev_r else None
            effective_phos = r.phosphorus
            phos_rising = (effective_phos is not None) and (prev_phos is not None) and (effective_phos > prev_phos)
            effective_idwg = r.idwg
            if phos_rising and effective_idwg and effective_idwg >= 2.5:
                metrics['dialysis_intensification']['count'] += 1
                metrics['dialysis_intensification']['names'].append(name)
                row["alerts"].append("Intensify Dialysis")
                
            # 2.5 High Hb > 13.0 g/dL (Risk: Stroke/Thrombosis)
            if effective_hb and effective_hb > 13.0:
                metrics['hb_high']['count'] += 1
                metrics['hb_high']['names'].append(name)
                row["alerts"].append("High Hb (>13)")

            # 3. Albumin < 2.5 g/dL (User remapped from 3.5)
            if r.albumin and r.albumin < 2.5:
                metrics['albumin_low']['count'] += 1
                metrics['albumin_low']['names'].append(name)
                metrics['trend_albumin'].append({
                    "id": p.id,
                    "name": name,
                    "current": r.albumin,
                    "previous": prev_r.albumin if prev_r else None
                })
                row["alerts"].append("Low Albumin")

            # 4. Corrected Calcium < 8.0 mg/dL (User remapped from 8.5)
            corr_ca = row["corrected_ca"]
            if corr_ca and corr_ca < 8.0:
                metrics['calcium_low']['count'] += 1
                metrics['calcium_low']['names'].append(name)
                row["alerts"].append("Low Corrected Calcium")
                
            # 5. Phosphorus > 5.5 mg/dL
            if r.phosphorus and r.phosphorus > 5.5:
                metrics['phos_high']['count'] += 1
                metrics['phos_high']['names'].append(name)
                metrics['trend_phosphorus'].append({
                    "id": p.id,
                    "name": name,
                    "current": r.phosphorus,
                    "previous": prev_r.phosphorus if prev_r else None
                })
                row["alerts"].append("High Phos")

            # ── 6. ESA Response Classification (KDIGO 2012) ─────────────────
            # ERI = (dose_IU/wk ÷ weight_kg) ÷ (Hb_g/dL × 10)
            #
            # CRITICAL GATE: HypoR is only clinically valid when Hb is BELOW
            # target (< 11.0 g/dL). When Hb is at/above target the correct
            # interpretation is NOT hyporesponsiveness but rather a dose that
            # has not been weaned — flag for de-escalation instead.
            #
            # Hb < 11.0  AND high ERI/dose  →  HypoR1 / HypoR2 / HypoR3
            # Hb 11–13    AND dose_kg ≥ 150  →  ESA De-escalation Due
            # Hb > 13.0   AND any dose       →  ESA Over-dosing Risk
            # (threshold 150 IU/kg/wk ≈ Mircera 100 mcg/month on 60 kg)
            _epo_sc = _resolve_epo_dose(r)

            if _epo_sc:
                _weight = r.target_dry_weight or p.dry_weight or 60.0
                _dose_kg = _epo_sc / _weight
                # Use row["hb"] so interim lab overrides are respected
                _hb_eff = row["hb"]
                _eri = (_dose_kg / (_hb_eff * 10)) if _hb_eff and _hb_eff > 0 else None

                # Hb status relative to target
                _hb_below_target  = (_hb_eff is None) or (_hb_eff < 11.0)
                _hb_at_target     = _hb_eff is not None and 11.0 <= _hb_eff <= 13.0
                _hb_above_safe    = _hb_eff is not None and _hb_eff > 13.0

                # True hyporesponsiveness — Hb-gated per ERBP/KDIGO
                # ERI code units = standard_ERI / 10  (standard = dose_kg / Hb_g/dL)
                # Guideline thresholds: ERI > 15.4 IU/kg/wk/g/dL → code > 1.54
                #                       SC EPO > 300 IU/kg/wk  (IV EPO > 450)
                hypo_r1 = bool(_hb_below_target and _eri and (_eri >= 2.0 or _dose_kg >= 300))
                hypo_r2 = bool(_hb_below_target and _eri and _eri >= 1.54)
                hypo_r3 = bool(_hb_below_target and _hypo_r3_cutoff and _epo_sc > _hypo_r3_cutoff)

                # De-escalation: Hb on-target but dose not yet weaned
                _de_escalation = bool(
                    (_hb_at_target and _dose_kg >= 150) or
                    (_hb_above_safe and _dose_kg >= 50)   # any meaningful dose when Hb is supratherapeutic
                )

                _any_hypo = hypo_r1 or hypo_r2 or hypo_r3
                _causes   = _esa_hypo_causes(r) if _any_hypo else []

                if hypo_r1:
                    metrics['epo_hypo']['count'] += 1
                    metrics['epo_hypo']['names'].append(name)
                    row["alerts"].append("HypoR1")
                if hypo_r2:
                    metrics['epo_hypo_r2']['count'] += 1
                    metrics['epo_hypo_r2']['names'].append(name)
                    if not hypo_r1:
                        row["alerts"].append("HypoR2")
                if hypo_r3:
                    metrics['epo_hypo_r3']['count'] += 1
                    metrics['epo_hypo_r3']['names'].append(name)
                    if not hypo_r1 and not hypo_r2:
                        row["alerts"].append("HypoR3")

                if _de_escalation and not _any_hypo:
                    metrics['esa_de_escalation']['count'] += 1
                    metrics['esa_de_escalation']['names'].append(name)
                    if _hb_above_safe:
                        row["alerts"].append("ESA Over-dosing Risk")
                    else:
                        row["alerts"].append("ESA De-escalation Due")

                row["eri"]             = round(_eri, 2) if _eri else None
                row["dose_kg"]         = round(_dose_kg, 1)
                row["epo_hypo_causes"] = _causes
                row["esa_de_escalation"] = _de_escalation

            # iPTH > 1000 pg/mL — severe hyperparathyroidism
            _ipth_eff = row.get("ipth")
            if _ipth_eff and _ipth_eff > 1000:
                metrics['ipth_very_high']['count'] += 1
                metrics['ipth_very_high']['names'].append(name)
                row["alerts"].append("iPTH > 1000")

            # 7. IV Iron Recommended:
            #    Hb < 10 AND iron-deficient by TSAT or serum iron, AND no iron overload.
            #    Ferritin is NOT used as inclusion criterion — not reliably available.
            #    Withhold if TSAT ≥ 40% or ferritin ≥ 700 ng/mL (ERBP iron overload threshold).
            #    Iron deficiency: TSAT < 30% or serum_iron < 60 µg/dL.
            #    If neither marker available → flag anyway (no data ≠ safe; clinician should check).
            _iv_hb         = row["hb"]
            _tsat_low      = r.tsat is not None and r.tsat < 30
            _iron_low      = r.serum_iron is not None and r.serum_iron < 60
            _iron_unknown  = r.tsat is None and r.serum_iron is None
            _iron_overload = (
                (r.tsat is not None and r.tsat >= 40) or
                (r.serum_ferritin is not None and r.serum_ferritin >= 700)
            )
            if _iv_hb and _iv_hb < 10 and not _iron_overload and (_tsat_low or _iron_low or _iron_unknown):
                metrics['iv_iron_rec']['count'] += 1
                metrics['iv_iron_rec']['names'].append(name)
                row["alerts"].append("IV Iron Rec")
        else:
            metrics['missing_records']['count'] += 1
            metrics['missing_records']['names'].append(name)

        try:
            patient_rows.append(row)
        except Exception as e:
            logger.error(f"Error processing row for patient {p.id}: {e}")
            raise

    _hb_vals = [row["hb"] for row in patient_rows if row.get("hb") is not None]
    metrics['avg_hb'] = round(sum(_hb_vals) / len(_hb_vals), 1) if _hb_vals else None

    result = {
        "metrics": metrics,
        "patient_rows": patient_rows,
        "month_label": get_month_label(month),
        "prev_month_label": get_month_label(prev_month),
        "total_active": len(active_patients)
    }
    
    # 3. Store in cache
    _DASHBOARD_CACHE[cache_key] = (result, now + timedelta(seconds=_CACHE_EXPIRY_SECONDS))
    
    return result


def get_patients_needing_alerts(db: Session, month: str = None):
    if not month:
        month = get_current_month_str()

    active_patients = db.query(Patient).filter(Patient.is_active == True).all()
    records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month).all()
    record_map = {r.patient_id: r for r in records}

    result = []
    for p in active_patients:
        r = record_map.get(p.id)
        if not r:
            continue
        alerts = []
        # Fallback to baseline if monthly record is missing it
        raw_access = (r.access_type or p.access_type or "").strip()
        _a_upper = raw_access.upper()
        if any(kw in _a_upper for kw in ("PERMACATH", "P/CATH", "P-CATH", "PCATH", "TCC", "DLJC", "FEMORAL")):
            access = "Permacath"
        else:
            access = raw_access
        if access and "AVF" not in access.upper():
            alerts.append("Non-AVF")
        if r.idwg and r.idwg >= 2.5:
            alerts.append("High Interdialytic Weight Gain")
        if r.albumin and r.albumin < 2.5:
            alerts.append("Low Albumin")
        # Corrected Calcium check
        _corr_ca = (r.calcium + 0.8 * (4.0 - r.albumin)) if (r.calcium and r.albumin) else r.calcium
        if _corr_ca and _corr_ca < 8.0:
            alerts.append("Low Corrected Calcium")
        if r.phosphorus and r.phosphorus > 5.5:
            alerts.append("High Phos")
        _epo_sc = _resolve_epo_dose(r)
        if _epo_sc and r.hb:
            _weight   = r.target_dry_weight or p.dry_weight or 60.0
            _dose_kg  = _epo_sc / _weight
            _eri      = _dose_kg / (r.hb * 10)
            _hb_below = r.hb < 11.0
            _hb_above_safe = r.hb > 13.0
            if _hb_below and (_eri >= 2.0 or _dose_kg >= 450):
                alerts.append("HypoR1")
            elif _hb_below and _eri >= 1.5:
                alerts.append("HypoR2")
            elif _hb_above_safe and _dose_kg >= 50:
                alerts.append("ESA Over-dosing Risk")
            elif not _hb_below and _dose_kg >= 150:
                alerts.append("ESA De-escalation Due")
        if alerts:
            result.append({
                "patient": p,
                "alerts": alerts,
                "record": {
                    "hb": r.hb,
                    "albumin": r.albumin,
                    "phosphorus": r.phosphorus,
                    "corrected_ca": _corr_ca,
                    "idwg": r.idwg,
                    "ipth": r.ipth,
                },
            })
    return result
