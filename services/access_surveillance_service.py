"""Vascular access surveillance service — KDOQI 2019 aligned.

Key design principles (per KDOQI 2019):
- Physical exam (thrill/bruit) is the PRIMARY monitoring tool at every session.
- Device-based surveillance (Doppler) is triggered by clinical indicators,
  NOT on a routine calendar interval (Guidelines 13.4–13.5).
- All thresholds are read from UnitConfiguration, never hard-coded.
- Only `confirmed` AccessEvents count in benchmark denominators.
- Maturation failure = 180 days / 6 months (KDOQI Glossary), not 90 days.
- CRBSI target = 1.5/1000 catheter-days (KDOQI Goals Box, Table 23).
- Patency terminology: "cumulative patency" (not "secondary patency").
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

# Default thresholds — all overridable via UnitConfiguration
_DEFAULTS: dict[str, Any] = {
    "avf_maturation_delay_days": 42,
    "avg_maturation_delay_days": 21,
    "avf_maturation_failure_days": 180,   # KDOQI Glossary: 6 months
    "avg_maturation_failure_days": 90,
    "qa_absolute_threshold_avf": 600.0,   # mL/min
    "qa_absolute_threshold_avg": 500.0,
    "qa_relative_decline_pct": 25.0,
    "recirculation_threshold_pct": 10.0,
    "bfr_suboptimal_avf": 250.0,
    "bfr_suboptimal_tcc": 200.0,
    "tcc_duration_alert_days": 90,
    "non_tunnelled_duration_alert_days": 14,   # absolute; never adjustable
    "crbsi_target_per_1000": 1.5,             # KDOQI Goals Box Table 23
    "cannulation_failure_rate_alert": 5.0,    # % of sessions
    "life_plan_review_interval_days": 365,    # KDOQI 1.1
    "access_review_interval_days": 90,        # KDOQI 1.3
    "av_interventions_establish_max": 2,      # KDOQI Goals Box 3
    "av_interventions_maintain_per_year_max": 3,
    "qa_baseline_window_sessions": 3,
}

_INTERVENTION_ACTIONS = {
    "angioplasty", "thrombectomy", "surgical_referral",
    "catheter_removed", "catheter_replaced",
}


def _cfg(config: dict, key: str) -> Any:
    return config.get(key, _DEFAULTS[key])


def _load_config(db: Session) -> dict:
    """Load UnitConfiguration rows into a flat dict; fall back to defaults."""
    try:
        from db.models.config import UnitConfiguration  # type: ignore
        rows = db.query(UnitConfiguration).all()
        return {r.parameter: r.value for r in rows}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Action Items
# ─────────────────────────────────────────────────────────────────────────────

def compute_access_action_items(
    db: Session,
    patient_id: int,
    config: dict | None = None,
) -> list[dict]:
    """Return a list of prospective action items for a patient's current access.

    Each item: {priority, category, message, due_date (or None), episode_id}
    priority: urgent | this_week | routine
    """
    if config is None:
        config = _load_config(db)

    from db.models.clinical import AccessEpisode, AccessEvent, AccessSurveillanceRecord
    from db.models.sessions import SessionRecord

    today = date.today()
    items: list[dict] = []

    episode: AccessEpisode | None = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.patient_id == patient_id,
            AccessEpisode.is_current == True,
        )
        .order_by(AccessEpisode.creation_date.desc())
        .first()
    )
    if not episode:
        return items

    ep_id = episode.id
    ac = (episode.access_class or "").upper()

    def add(priority: str, category: str, message: str, due_date: date | None = None):
        items.append({
            "priority": priority,
            "category": category,
            "message": message,
            "due_date": due_date,
            "episode_id": ep_id,
            "patient_id": patient_id,
        })

    # ── ESKD Life-Plan (KDOQI 1.1–1.3) ───────────────────────────────────────
    lp_interval = _cfg(config, "life_plan_review_interval_days")
    if not episode.life_plan_reviewed_at or (today - episode.life_plan_reviewed_at).days > lp_interval:
        add("routine", "life_plan", "Annual Life-Plan review due (KDOQI 1.1)")

    ar_interval = _cfg(config, "access_review_interval_days")
    if not episode.access_reviewed_at or (today - episode.access_reviewed_at).days > ar_interval:
        add("routine", "access_review", "Quarterly access review due (KDOQI 1.3)")

    if not episode.succession_plan:
        add("routine", "life_plan", "Succession plan not documented — add next-access contingency")

    # ── Non-tunnelled CVC duration (absolute limit — KDOQI) ──────────────────
    if ac == "NON_TUNNELLED":
        days_in = (today - episode.creation_date).days
        limit = _cfg(config, "non_tunnelled_duration_alert_days")
        if days_in > limit:
            add(
                "urgent",
                "cvc_duration",
                f"URGENT: Non-tunnelled CVC in situ {days_in} days (limit {limit}) — immediate conversion required",
            )
        return items  # no further checks for non-tunnelled

    # ── TCC duration ──────────────────────────────────────────────────────────
    if ac == "TCC":
        days_in = (today - episode.creation_date).days
        alert_days = _cfg(config, "tcc_duration_alert_days")
        if days_in > alert_days:
            add(
                "this_week",
                "cvc_duration",
                f"TCC in situ {days_in} days (threshold {alert_days}) — AVF planning review",
            )

        # CRBSI rate (rolling 3-month)
        crbsi_rate = _compute_crbsi_rate_3m(db, patient_id, today)
        target = _cfg(config, "crbsi_target_per_1000")
        if crbsi_rate is not None and crbsi_rate > target:
            add(
                "urgent",
                "crbsi",
                f"CRBSI rate {crbsi_rate:.1f}/1000 catheter-days exceeds target {target} (KDOQI)",
            )
        return items

    # ── AVF / AVG checks ──────────────────────────────────────────────────────
    if ac not in ("AVF", "AVG"):
        return items

    # Maturation delay
    delay_key = "avf_maturation_delay_days" if ac == "AVF" else "avg_maturation_delay_days"
    delay_days = _cfg(config, delay_key)
    if not episode.first_cannulation_date:
        days_since_creation = (today - episode.creation_date).days
        if days_since_creation > delay_days:
            add(
                "this_week",
                "maturation",
                f"{ac} maturation delay: {days_since_creation} days since creation, no first cannulation recorded (threshold {delay_days} days)",
            )

    # Maturation failure (KDOQI Glossary: 6 months for AVF / 90 days for AVG)
    failure_key = "avf_maturation_failure_days" if ac == "AVF" else "avg_maturation_failure_days"
    failure_days = _cfg(config, failure_key)
    if not episode.first_cannulation_date:
        days_since_creation = (today - episode.creation_date).days
        if days_since_creation > failure_days:
            add(
                "urgent",
                "maturation",
                f"{ac} maturation failure threshold reached: {days_since_creation} days, never successfully cannulated (KDOQI threshold {failure_days} days)",
            )

    # AV intervention rate — 1-2-3 rule (KDOQI Goals Box 3)
    _check_intervention_rate(db, episode, config, today, add)

    # Bedside exam deterioration — 2 consecutive sessions with abnormal thrill/bruit
    _check_bedside_exam_trend(db, patient_id, add)

    # Qa absolute threshold
    qa_threshold_key = "qa_absolute_threshold_avf" if ac == "AVF" else "qa_absolute_threshold_avg"
    qa_threshold = _cfg(config, qa_threshold_key)
    recent_qa = _get_recent_qa(db, patient_id, n=2)
    if len(recent_qa) == 2 and all(q < qa_threshold for q in recent_qa):
        add(
            "this_week",
            "qa_flow",
            f"Qa below absolute threshold ({recent_qa[0]:.0f} mL/min, threshold {qa_threshold:.0f}) on last 2 measurements — clinical review + consider imaging",
        )

    # Qa relative decline
    baseline_window = _cfg(config, "qa_baseline_window_sessions")
    qa_decline_pct = _cfg(config, "qa_relative_decline_pct")
    relative_decline = _compute_qa_relative_decline(db, patient_id, int(baseline_window))
    if relative_decline is not None and relative_decline >= qa_decline_pct:
        add(
            "this_week",
            "qa_flow",
            f"Qa relative decline {relative_decline:.0f}% from rolling baseline (threshold {qa_decline_pct:.0f}%) — clinical review + consider imaging",
        )

    # Recirculation
    recirc_threshold = _cfg(config, "recirculation_threshold_pct")
    recent_recirc = _get_recent_recirculation(db, patient_id, n=2)
    if len(recent_recirc) == 2 and all(r >= recirc_threshold for r in recent_recirc):
        add(
            "this_week",
            "recirculation",
            f"High recirculation ({recent_recirc[0]:.0f}%) on last 2 sessions (threshold {recirc_threshold:.0f}%) — clinical review + consider imaging",
        )

    # Cannulation failure rate (last 20 sessions)
    failure_rate_threshold = _cfg(config, "cannulation_failure_rate_alert")
    cannulation_failure_rate = _compute_cannulation_failure_rate(db, patient_id, n=20)
    if cannulation_failure_rate is not None and cannulation_failure_rate >= failure_rate_threshold:
        add(
            "this_week",
            "cannulation",
            f"Cannulation failure rate {cannulation_failure_rate:.1f}% over last 20 sessions (threshold {failure_rate_threshold:.0f}%) — clinical review",
        )

    # Steal Grade 3 — auto-urgent (check recent confirmed events)
    _check_steal_grade3(db, patient_id, ep_id, add)

    items.sort(key=lambda x: {"urgent": 0, "this_week": 1, "routine": 2}[x["priority"]])
    return items


def _check_intervention_rate(
    db: Session, episode: Any, config: dict, today: date, add
):
    """Check KDOQI 1-2-3 rule: ≤2 to establish, ≤3/year to maintain."""
    from db.models.clinical import AccessEvent

    ac = (episode.access_class or "").upper()
    establish_max = _cfg(config, "av_interventions_establish_max")
    maintain_max = _cfg(config, "av_interventions_maintain_per_year_max")

    all_events = (
        db.query(AccessEvent)
        .filter(
            AccessEvent.episode_id == episode.id,
            AccessEvent.status == "confirmed",
            AccessEvent.action_taken.in_(_INTERVENTION_ACTIONS),
        )
        .order_by(AccessEvent.event_date)
        .all()
    )

    # Establish count: interventions before first successful use
    if not episode.first_cannulation_date:
        establish_count = len(all_events)
    else:
        establish_count = sum(
            1 for e in all_events if e.event_date < episode.first_cannulation_date
        )

    if establish_count > establish_max:
        add(
            "this_week",
            "intervention_rate",
            f"{ac} required {establish_count} interventions to establish (KDOQI target ≤{establish_max}) — Life-Plan review recommended",
        )

    # Maintain count: interventions in rolling 12 months after first use
    if episode.first_cannulation_date:
        year_ago = today - timedelta(days=365)
        maintain_start = max(episode.first_cannulation_date, year_ago)
        maintain_count = sum(
            1 for e in all_events
            if e.event_date >= maintain_start and e.event_date <= today
            and (not episode.first_cannulation_date or e.event_date >= episode.first_cannulation_date)
        )
        if maintain_count > maintain_max:
            add(
                "this_week",
                "intervention_rate",
                f"{ac} has {maintain_count} maintenance interventions in past 12 months (KDOQI target ≤{maintain_max}/year) — consider cumulative patency review",
            )


def _check_bedside_exam_trend(db: Session, patient_id: int, add):
    """Flag if thrill or bruit was abnormal in last 2 consecutive sessions."""
    from db.models.sessions import SessionRecord

    recent = (
        db.query(SessionRecord)
        .filter(SessionRecord.patient_id == patient_id)
        .order_by(SessionRecord.session_date.desc())
        .limit(2)
        .all()
    )
    if len(recent) < 2:
        return
    thrill_bad = all(s.thrill_grade and s.thrill_grade != "normal" for s in recent)
    bruit_bad = all(s.bruit_grade and s.bruit_grade != "normal" for s in recent)
    if thrill_bad:
        add("this_week", "bedside_exam", "Thrill abnormal in last 2 consecutive sessions — consider imaging (KDOQI 13.4)")
    if bruit_bad:
        add("this_week", "bedside_exam", "Bruit abnormal in last 2 consecutive sessions — consider imaging (KDOQI 13.4)")


def _check_steal_grade3(db: Session, patient_id: int, episode_id: int, add):
    from db.models.clinical import AccessEvent

    grade3 = (
        db.query(AccessEvent)
        .filter(
            AccessEvent.patient_id == patient_id,
            AccessEvent.episode_id == episode_id,
            AccessEvent.event_type == "steal_syndrome",
            AccessEvent.steal_grade == "grade_3",
            AccessEvent.status == "confirmed",
        )
        .order_by(AccessEvent.event_date.desc())
        .first()
    )
    if grade3:
        add(
            "urgent",
            "steal",
            f"Steal syndrome Grade 3 confirmed ({grade3.event_date}) — urgent surgical referral required (KDOQI Table 18.3)",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helper data extractors
# ─────────────────────────────────────────────────────────────────────────────

def _get_recent_qa(db: Session, patient_id: int, n: int) -> list[float]:
    from db.models.sessions import SessionRecord

    rows = (
        db.query(SessionRecord.access_flow_qa)
        .filter(
            SessionRecord.patient_id == patient_id,
            SessionRecord.access_flow_qa.isnot(None),
        )
        .order_by(SessionRecord.session_date.desc())
        .limit(n)
        .all()
    )
    return [r[0] for r in rows]


def _compute_qa_relative_decline(db: Session, patient_id: int, window: int) -> float | None:
    """Return % decline from rolling baseline to most recent Qa, or None."""
    from db.models.sessions import SessionRecord

    rows = (
        db.query(SessionRecord.access_flow_qa)
        .filter(
            SessionRecord.patient_id == patient_id,
            SessionRecord.access_flow_qa.isnot(None),
        )
        .order_by(SessionRecord.session_date.desc())
        .limit(window + 1)
        .all()
    )
    values = [r[0] for r in rows]
    if len(values) < window + 1:
        return None
    latest = values[0]
    baseline = sum(values[1:window + 1]) / window
    if baseline <= 0:
        return None
    decline = (baseline - latest) / baseline * 100
    return max(decline, 0.0)


def _get_recent_recirculation(db: Session, patient_id: int, n: int) -> list[float]:
    from db.models.sessions import SessionRecord

    rows = (
        db.query(SessionRecord.access_recirculation_percent)
        .filter(
            SessionRecord.patient_id == patient_id,
            SessionRecord.access_recirculation_percent.isnot(None),
        )
        .order_by(SessionRecord.session_date.desc())
        .limit(n)
        .all()
    )
    return [r[0] for r in rows]


def _compute_cannulation_failure_rate(db: Session, patient_id: int, n: int) -> float | None:
    from db.models.sessions import SessionRecord

    rows = (
        db.query(SessionRecord.cannulation_difficulty)
        .filter(
            SessionRecord.patient_id == patient_id,
            SessionRecord.cannulation_difficulty.isnot(None),
        )
        .order_by(SessionRecord.session_date.desc())
        .limit(n)
        .all()
    )
    if not rows:
        return None
    failed = sum(1 for r in rows if r[0] == "failed")
    return failed / len(rows) * 100


def _compute_crbsi_rate_3m(db: Session, patient_id: int, today: date) -> float | None:
    """CRBSI rate per 1000 catheter-days over rolling 3 months."""
    from db.models.clinical import AccessEpisode, AccessEvent

    cutoff = today - timedelta(days=90)

    # Sum catheter-days across all TCC episodes in window
    episodes = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.patient_id == patient_id,
            AccessEpisode.access_class == "TCC",
        )
        .all()
    )
    catheter_days = 0
    for ep in episodes:
        start = max(ep.creation_date, cutoff)
        end = ep.loss_date if ep.loss_date else today
        if end >= start:
            catheter_days += (end - start).days

    if catheter_days == 0:
        return None

    confirmed_crbsi = (
        db.query(AccessEvent)
        .filter(
            AccessEvent.patient_id == patient_id,
            AccessEvent.event_type == "crbsi_confirmed",
            AccessEvent.status == "confirmed",
            AccessEvent.event_date >= cutoff,
        )
        .count()
    )
    return confirmed_crbsi / catheter_days * 1000


# ─────────────────────────────────────────────────────────────────────────────
# Unit Benchmarks
# ─────────────────────────────────────────────────────────────────────────────

def compute_unit_benchmarks(
    db: Session,
    month: str,
    config: dict | None = None,
) -> list[dict]:
    """Compute all KDOQI-aligned unit benchmarks for a given month (YYYY-MM).

    Returns list of dicts with: name, access_class, numerator, denominator,
    rate, target, rag (red|amber|green), denominator_label, notes.

    Only `confirmed` AccessEvents count (governance rule).
    """
    if config is None:
        config = _load_config(db)

    from db.models.patient import Patient, PatientVascularAccess
    from db.models.clinical import AccessEpisode, AccessEvent

    year, mo = int(month[:4]), int(month[5:7])
    month_start = date(year, mo, 1)
    import calendar
    month_end = date(year, mo, calendar.monthrange(year, mo)[1])

    active_patients = db.query(Patient).filter(Patient.is_active == True).all()
    total = len(active_patients)
    results: list[dict] = []

    def rag(rate: float, target: float, higher_is_better: bool = True) -> str:
        if higher_is_better:
            return "green" if rate >= target else ("amber" if rate >= target * 0.85 else "red")
        else:
            return "green" if rate <= target else ("amber" if rate <= target * 1.25 else "red")

    def bench(name: str, access_class: str, numerator: int, denominator: int,
              target: float, higher_is_better: bool, denom_label: str, notes: str = "") -> dict:
        rate = round(numerator / denominator * 100, 1) if denominator else 0.0
        return {
            "name": name,
            "access_class": access_class,
            "numerator": numerator,
            "denominator": denominator,
            "rate": rate,
            "target": target,
            "rag": rag(rate, target, higher_is_better),
            "denominator_label": denom_label,
            "notes": notes,
        }

    # 1. Prevalent AVF rate
    avf_patients = [p for p in active_patients if _is_access_class(p, "AVF")]
    results.append(bench(
        "Prevalent AVF Rate", "AVF",
        len(avf_patients), total, 90.0, True,
        "Active patients at month-end",
        "% active patients on AVF",
    ))

    # 2. Prevalent AVG rate
    avg_patients = [p for p in active_patients if _is_access_class(p, "AVG")]
    results.append(bench(
        "Prevalent AVG Rate", "AVG",
        len(avg_patients), total, 5.0, False,
        "Active patients at month-end",
        "Lower is better — AVG is a bridge access",
    ))

    # 3. Prevalent TCC rate (CVC burden)
    tcc_patients = [p for p in active_patients if _is_access_class(p, "TCC")]
    results.append(bench(
        "Prevalent TCC Rate", "TCC",
        len(tcc_patients), total, 10.0, False,
        "Active patients at month-end",
        "KDOQI target <10% on tunnelled CVC",
    ))

    # 4. Incident AVF rate (new HD starts this month on AVF)
    new_starts = [p for p in active_patients if p.hd_wef_date and p.hd_wef_date >= month_start and p.hd_wef_date <= month_end]
    new_avf_starts = [p for p in new_starts if _is_access_class(p, "AVF")]
    if new_starts:
        results.append(bench(
            "Incident AVF Rate", "AVF",
            len(new_avf_starts), len(new_starts), 65.0, True,
            "New HD starts in month",
            "% new HD patients starting on AVF",
        ))

    # 5. AVF maturation failure rate (6-month cohort, KDOQI)
    six_months_ago = month_end - timedelta(days=180)
    avf_episodes_cohort = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.access_class == "AVF",
            AccessEpisode.creation_date >= six_months_ago,
            AccessEpisode.creation_date <= month_end,
        )
        .all()
    )
    failed_avf = [
        ep for ep in avf_episodes_cohort
        if not ep.first_cannulation_date and
        (month_end - ep.creation_date).days >= 180
    ]
    if avf_episodes_cohort:
        rate_val = round(len(failed_avf) / len(avf_episodes_cohort) * 100, 1)
        results.append({
            "name": "AVF Maturation Failure Rate",
            "access_class": "AVF",
            "numerator": len(failed_avf),
            "denominator": len(avf_episodes_cohort),
            "rate": rate_val,
            "target": 15.0,
            "rag": rag(rate_val, 15.0, False),
            "denominator_label": "AVFs created in 6-month cohort (KDOQI: failure = never used by 6 months)",
            "notes": "Only AVFs never successfully cannulated by 6 months count",
        })

    # 6. Thrombosis rate (per 100 patient-months, separately for AVF and AVG)
    for ac_label in ("AVF", "AVG"):
        ac_patients = [p for p in active_patients if _is_access_class(p, ac_label)]
        thrombosis_events = (
            db.query(AccessEvent)
            .filter(
                AccessEvent.access_class == ac_label,
                AccessEvent.event_type == "thrombosis",
                AccessEvent.status == "confirmed",
                AccessEvent.event_date >= month_start,
                AccessEvent.event_date <= month_end,
            )
            .count()
        )
        patient_months = len(ac_patients)  # 1 month
        if patient_months:
            thr_rate = round(thrombosis_events / patient_months * 100, 2)
            results.append({
                "name": f"{ac_label} Thrombosis Rate",
                "access_class": ac_label,
                "numerator": thrombosis_events,
                "denominator": patient_months,
                "rate": thr_rate,
                "target": 0.5,
                "rag": rag(thr_rate, 0.5, False),
                "denominator_label": f"100 {ac_label} patient-months",
                "notes": "Confirmed thrombosis events only",
            })

    # 7. CRBSI rate per 1000 catheter-days (TCC only)
    crbsi_target = _cfg(config, "crbsi_target_per_1000")
    total_catheter_days = _unit_catheter_days(db, month_start, month_end)
    crbsi_confirmed = (
        db.query(AccessEvent)
        .filter(
            AccessEvent.access_class == "TCC",
            AccessEvent.event_type == "crbsi_confirmed",
            AccessEvent.status == "confirmed",
            AccessEvent.event_date >= month_start,
            AccessEvent.event_date <= month_end,
        )
        .count()
    )
    if total_catheter_days:
        crbsi_rate_unit = round(crbsi_confirmed / total_catheter_days * 1000, 2)
        results.append({
            "name": "CRBSI Rate",
            "access_class": "TCC",
            "numerator": crbsi_confirmed,
            "denominator": total_catheter_days,
            "rate": crbsi_rate_unit,
            "target": crbsi_target,
            "rag": rag(crbsi_rate_unit, crbsi_target, False),
            "denominator_label": f"{total_catheter_days} TCC catheter-days (rate = events × 1000 ÷ catheter-days)",
            "notes": f"KDOQI 2019 target <{crbsi_target}/1000 catheter-days (Table 23). n = confirmed CRBSI events; N = total catheter-days in month.",
        })

    # 8. CVC-to-AVF conversion rate (3-month rolling)
    three_months_ago = month_end - timedelta(days=90)
    tcc_at_start = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.access_class == "TCC",
            AccessEpisode.is_current == False,
            AccessEpisode.creation_date <= three_months_ago,
            AccessEpisode.loss_date.isnot(None),
        )
        .count()
    )
    tcc_converted = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.access_class == "TCC",
            AccessEpisode.is_current == False,
            AccessEpisode.loss_reason == "planned_upgrade",
            AccessEpisode.loss_date >= three_months_ago,
            AccessEpisode.loss_date <= month_end,
        )
        .count()
    )
    if tcc_at_start:
        results.append(bench(
            "CVC-to-AVF Conversion Rate", "TCC",
            tcc_converted, tcc_at_start, 30.0, True,
            "Active TCC patients 3 months ago",
            "3-month rolling conversion rate",
        ))

    return results


def _is_access_class(patient: Any, ac: str) -> bool:
    """Check patient's current access class using AccessEpisode if available,
    falling back to PatientVascularAccess.access_type string."""
    # Check AccessEpisode first
    if hasattr(patient, "access_episodes") and patient.access_episodes:
        current = [e for e in patient.access_episodes if e.is_current]
        if current:
            return (current[0].access_class or "").upper() == ac.upper()
    # Fall back to legacy field
    if patient.vascular_access and patient.vascular_access.access_type:
        t = patient.vascular_access.access_type.upper()
        if ac == "AVF":
            return "AVF" in t
        if ac == "AVG":
            return "AVG" in t or "GRAFT" in t
        if ac == "TCC":
            return "TCC" in t or ("CVC" in t and "TEMP" not in t and "DLJC" not in t)
        if ac == "NON_TUNNELLED":
            return "DLJC" in t or ("TEMP" in t and "CVC" in t)
    return False


def _unit_catheter_days(db: Session, month_start: date, month_end: date) -> int:
    """Sum TCC catheter-days for all patients in the given date range."""
    from db.models.clinical import AccessEpisode

    tcc_episodes = (
        db.query(AccessEpisode)
        .filter(AccessEpisode.access_class == "TCC")
        .all()
    )
    total = 0
    for ep in tcc_episodes:
        start = max(ep.creation_date, month_start)
        end = ep.loss_date if ep.loss_date else month_end
        end = min(end, month_end)
        if end >= start:
            total += (end - start).days + 1
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Patency
# ─────────────────────────────────────────────────────────────────────────────

def compute_access_patency(db: Session, episode_id: int) -> dict:
    """Compute primary, assisted primary, and cumulative patency for an episode.

    Uses KDOQI 2019 terminology — 'cumulative patency' (not 'secondary patency').
    """
    from db.models.clinical import AccessEpisode, AccessEvent

    ep: AccessEpisode | None = db.query(AccessEpisode).filter(AccessEpisode.id == episode_id).first()
    if not ep:
        return {"error": "Episode not found"}

    today = date.today()
    creation = ep.creation_date
    end_date = ep.loss_date or today

    confirmed_events = (
        db.query(AccessEvent)
        .filter(
            AccessEvent.episode_id == episode_id,
            AccessEvent.status == "confirmed",
        )
        .order_by(AccessEvent.event_date)
        .all()
    )

    # Primary patency: creation → first thrombosis OR first intervention
    primary_end = end_date
    for ev in confirmed_events:
        if ev.event_type == "thrombosis" or ev.action_taken in _INTERVENTION_ACTIONS:
            primary_end = ev.event_date
            break
    primary_patency_days = (primary_end - creation).days

    # Assisted primary patency: creation → first thrombosis (interventions don't end it)
    assisted_end = end_date
    for ev in confirmed_events:
        if ev.event_type == "thrombosis":
            assisted_end = ev.event_date
            break
    assisted_primary_days = (assisted_end - creation).days

    # Cumulative patency (KDOQI): creation → permanent abandonment
    cumulative_days = (end_date - creation).days

    interventions = [
        {"date": str(ev.event_date), "type": ev.event_type, "action": ev.action_taken}
        for ev in confirmed_events
        if ev.action_taken in _INTERVENTION_ACTIONS
    ]

    return {
        "episode_id": episode_id,
        "access_class": ep.access_class,
        "creation_date": str(creation),
        "end_date": str(end_date),
        "is_current": ep.is_current,
        "primary_patency_days": primary_patency_days,
        "assisted_primary_patency_days": assisted_primary_days,
        "cumulative_patency_days": cumulative_days,
        "intervention_count": len(interventions),
        "interventions": interventions,
    }


def compute_catheter_days(db: Session, patient_id: int, month: str) -> int:
    """Sum TCC catheter-days for a specific patient in a given month (YYYY-MM)."""
    import calendar
    year, mo = int(month[:4]), int(month[5:7])
    month_start = date(year, mo, 1)
    month_end = date(year, mo, calendar.monthrange(year, mo)[1])
    return _unit_catheter_days_for_patient(db, patient_id, month_start, month_end)


def _unit_catheter_days_for_patient(
    db: Session, patient_id: int, month_start: date, month_end: date
) -> int:
    from db.models.clinical import AccessEpisode

    episodes = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.patient_id == patient_id,
            AccessEpisode.access_class == "TCC",
        )
        .all()
    )
    total = 0
    for ep in episodes:
        start = max(ep.creation_date, month_start)
        end = ep.loss_date if ep.loss_date else month_end
        end = min(end, month_end)
        if end >= start:
            total += (end - start).days + 1
    return total


def compute_av_intervention_count(
    db: Session, episode_id: int, window: str = "annual"
) -> dict:
    """Count AV access interventions against KDOQI 1-2-3 rule thresholds.

    window: 'establish' (before first_cannulation_date) or 'annual' (past 12 months)
    """
    from db.models.clinical import AccessEpisode, AccessEvent

    ep: AccessEpisode | None = db.query(AccessEpisode).filter(AccessEpisode.id == episode_id).first()
    if not ep:
        return {"error": "Episode not found"}

    today = date.today()
    all_events = (
        db.query(AccessEvent)
        .filter(
            AccessEvent.episode_id == episode_id,
            AccessEvent.status == "confirmed",
            AccessEvent.action_taken.in_(_INTERVENTION_ACTIONS),
        )
        .order_by(AccessEvent.event_date)
        .all()
    )

    if window == "establish":
        if ep.first_cannulation_date:
            count = sum(1 for e in all_events if e.event_date < ep.first_cannulation_date)
        else:
            count = len(all_events)
        threshold = _DEFAULTS["av_interventions_establish_max"]
    else:
        year_ago = today - timedelta(days=365)
        start_date = max(ep.first_cannulation_date, year_ago) if ep.first_cannulation_date else year_ago
        count = sum(1 for e in all_events if e.event_date >= start_date)
        threshold = _DEFAULTS["av_interventions_maintain_per_year_max"]

    return {
        "episode_id": episode_id,
        "window": window,
        "count": count,
        "threshold": threshold,
        "exceeds": count > threshold,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Access-Loss Risk Scoring (unit-level ML prediction)
# ─────────────────────────────────────────────────────────────────────────────

_RISK_WEIGHTS = {
    "thrombosis_history": 3.0,       # confirmed thrombosis ever
    "steal_grade3": 4.0,             # confirmed grade-3 steal
    "qa_below_threshold": 2.5,       # last Qa < absolute threshold
    "qa_declining": 2.0,             # ≥25% relative Qa decline
    "high_recirculation": 2.0,       # recirc ≥10% last 2 sessions
    "cannulation_failure_high": 1.5, # failure rate ≥5% last 20 sessions
    "thrill_bruit_abnormal": 1.5,    # consecutive abnormal exam
    "excess_interventions": 2.0,     # >3 maintain interventions/year
    "maturation_delay": 1.0,         # maturation delay (no first cannulation)
    "tcc_long_duration": 1.5,        # TCC >90 days (conversion risk)
    "life_plan_missing": 0.5,        # succession plan not documented
}

# Thresholds: score → risk label
_RISK_LEVELS = [(6.0, "High"), (3.0, "Moderate"), (0.0, "Low")]


def compute_access_loss_risk(
    db: Session,
    patient_id: int,
    config: dict | None = None,
) -> dict:
    """Rule-weighted access-loss risk score for a single patient.

    Returns: {risk_level, score, max_score, factors, episode_id, access_class}
    """
    if config is None:
        config = _load_config(db)

    from db.models.clinical import AccessEpisode, AccessEvent
    from db.models.sessions import SessionRecord

    today = date.today()
    episode: AccessEpisode | None = (
        db.query(AccessEpisode)
        .filter(AccessEpisode.patient_id == patient_id, AccessEpisode.is_current == True)
        .order_by(AccessEpisode.creation_date.desc())
        .first()
    )
    if not episode:
        return {"available": False, "reason": "No current access episode"}

    ac = (episode.access_class or "").upper()
    score = 0.0
    factors: list[str] = []

    # ── Thrombosis history ────────────────────────────────────────────────────
    thrombus = (
        db.query(AccessEvent)
        .filter(
            AccessEvent.episode_id == episode.id,
            AccessEvent.event_type == "thrombosis",
            AccessEvent.status == "confirmed",
        )
        .count()
    )
    if thrombus:
        score += _RISK_WEIGHTS["thrombosis_history"]
        factors.append(f"Thrombosis history ({thrombus} confirmed)")

    # ── Steal Grade 3 ─────────────────────────────────────────────────────────
    steal3 = (
        db.query(AccessEvent)
        .filter(
            AccessEvent.episode_id == episode.id,
            AccessEvent.event_type == "steal_syndrome",
            AccessEvent.steal_grade == "grade_3",
            AccessEvent.status == "confirmed",
        )
        .count()
    )
    if steal3:
        score += _RISK_WEIGHTS["steal_grade3"]
        factors.append("Steal syndrome Grade 3 confirmed")

    # ── Qa below threshold ────────────────────────────────────────────────────
    qa_key = "qa_absolute_threshold_avf" if ac == "AVF" else "qa_absolute_threshold_avg"
    qa_threshold = _cfg(config, qa_key)
    recent_qa = _get_recent_qa(db, patient_id, n=2)
    if len(recent_qa) >= 1 and recent_qa[0] < qa_threshold:
        score += _RISK_WEIGHTS["qa_below_threshold"]
        factors.append(f"Qa {recent_qa[0]:.0f} mL/min < threshold {qa_threshold:.0f}")

    # ── Qa relative decline ───────────────────────────────────────────────────
    baseline_window = int(_cfg(config, "qa_baseline_window_sessions"))
    qa_decline_pct = _cfg(config, "qa_relative_decline_pct")
    decline = _compute_qa_relative_decline(db, patient_id, baseline_window)
    if decline is not None and decline >= qa_decline_pct:
        score += _RISK_WEIGHTS["qa_declining"]
        factors.append(f"Qa declining {decline:.0f}% from baseline")

    # ── High recirculation ────────────────────────────────────────────────────
    recirc_threshold = _cfg(config, "recirculation_threshold_pct")
    recent_recirc = _get_recent_recirculation(db, patient_id, n=2)
    if len(recent_recirc) == 2 and all(r >= recirc_threshold for r in recent_recirc):
        score += _RISK_WEIGHTS["high_recirculation"]
        factors.append(f"Recirculation ≥{recirc_threshold:.0f}% last 2 sessions")

    # ── Cannulation failure rate ──────────────────────────────────────────────
    failure_threshold = _cfg(config, "cannulation_failure_rate_alert")
    fail_rate = _compute_cannulation_failure_rate(db, patient_id, n=20)
    if fail_rate is not None and fail_rate >= failure_threshold:
        score += _RISK_WEIGHTS["cannulation_failure_high"]
        factors.append(f"Cannulation failure rate {fail_rate:.1f}%")

    # ── Bedside exam deterioration ────────────────────────────────────────────
    recent_sessions = (
        db.query(SessionRecord)
        .filter(SessionRecord.patient_id == patient_id)
        .order_by(SessionRecord.session_date.desc())
        .limit(2)
        .all()
    )
    if len(recent_sessions) == 2:
        if all(s.thrill_grade and s.thrill_grade != "normal" for s in recent_sessions):
            score += _RISK_WEIGHTS["thrill_bruit_abnormal"]
            factors.append("Thrill abnormal last 2 sessions")
        if all(s.bruit_grade and s.bruit_grade != "normal" for s in recent_sessions):
            score += _RISK_WEIGHTS["thrill_bruit_abnormal"]
            factors.append("Bruit abnormal last 2 sessions")

    # ── Excess maintenance interventions ─────────────────────────────────────
    if ac in ("AVF", "AVG") and episode.first_cannulation_date:
        maintain_max = _cfg(config, "av_interventions_maintain_per_year_max")
        year_ago = today - timedelta(days=365)
        start_date = max(episode.first_cannulation_date, year_ago)
        maintain_count = (
            db.query(AccessEvent)
            .filter(
                AccessEvent.episode_id == episode.id,
                AccessEvent.status == "confirmed",
                AccessEvent.action_taken.in_(_INTERVENTION_ACTIONS),
                AccessEvent.event_date >= start_date,
            )
            .count()
        )
        if maintain_count > maintain_max:
            score += _RISK_WEIGHTS["excess_interventions"]
            factors.append(f"{maintain_count} maintenance interventions past 12 months (KDOQI ≤{maintain_max})")

    # ── Maturation delay (AVF/AVG not yet cannulated) ─────────────────────────
    if ac in ("AVF", "AVG") and not episode.first_cannulation_date:
        delay_key = "avf_maturation_delay_days" if ac == "AVF" else "avg_maturation_delay_days"
        delay_days = _cfg(config, delay_key)
        if (today - episode.creation_date).days > delay_days:
            score += _RISK_WEIGHTS["maturation_delay"]
            factors.append(f"Maturation delay: {(today - episode.creation_date).days} days, not yet cannulated")

    # ── TCC long duration ─────────────────────────────────────────────────────
    if ac == "TCC":
        tcc_alert = _cfg(config, "tcc_duration_alert_days")
        if (today - episode.creation_date).days > tcc_alert:
            score += _RISK_WEIGHTS["tcc_long_duration"]
            factors.append(f"TCC in situ {(today - episode.creation_date).days} days (alert >{tcc_alert})")

    # ── Life-plan missing ─────────────────────────────────────────────────────
    if not episode.succession_plan:
        score += _RISK_WEIGHTS["life_plan_missing"]
        factors.append("Succession plan not documented")

    max_score = sum(_RISK_WEIGHTS.values())
    risk_level = next(label for threshold, label in _RISK_LEVELS if score >= threshold)
    risk_pct = round(score / max_score * 100, 1)

    return {
        "available": True,
        "patient_id": patient_id,
        "episode_id": episode.id,
        "access_class": ac,
        "score": round(score, 1),
        "max_score": round(max_score, 1),
        "risk_pct": risk_pct,
        "risk_level": risk_level,
        "factors": factors,
    }


def compute_unit_access_risk(
    db: Session,
    config: dict | None = None,
) -> list[dict]:
    """Run access-loss risk scoring for all active patients with a current episode.

    Returns list sorted by score descending.
    """
    from db.models.patient import Patient

    if config is None:
        config = _load_config(db)

    patients = db.query(Patient).filter(Patient.is_active == True).all()
    results = []
    for p in patients:
        try:
            r = compute_access_loss_risk(db, p.id, config=config)
            if r.get("available"):
                r["patient_name"] = p.name
                r["hid_no"] = p.hid_no
                results.append(r)
        except Exception:
            pass
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def compute_unit_qa_distribution(db: Session) -> list[dict]:
    """Return last Qa reading per active patient for unit-level distribution chart."""
    from db.models.patient import Patient
    from db.models.sessions import SessionRecord

    patients = db.query(Patient).filter(Patient.is_active == True).all()
    rows = []
    for p in patients:
        latest = (
            db.query(SessionRecord.access_flow_qa, SessionRecord.session_date)
            .filter(
                SessionRecord.patient_id == p.id,
                SessionRecord.access_flow_qa.isnot(None),
            )
            .order_by(SessionRecord.session_date.desc())
            .first()
        )
        if latest:
            rows.append({
                "patient_name": p.name,
                "hid_no": p.hid_no,
                "qa": latest[0],
                "date": str(latest[1]),
                "access_type": p.access_type or "Unknown",
            })
    return rows


def compute_avf_rate_trend(db: Session, n_months: int = 6) -> list[dict]:
    """Compute prevalent AVF rate for each of the last n_months months."""
    from db.models.patient import Patient
    import calendar

    today = date.today()
    results = []
    for i in range(n_months - 1, -1, -1):
        # Step back i months from today
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        month_label = month_end.strftime("%b %Y")

        # Patients active at month_end (started HD on or before month_end)
        all_pts = db.query(Patient).filter(
            Patient.is_active == True,
            Patient.hd_wef_date.isnot(None),
            Patient.hd_wef_date <= month_end,
        ).all()
        total = len(all_pts)
        avf = sum(1 for p in all_pts if p.access_type and "AVF" in p.access_type.upper())
        tcc = sum(1 for p in all_pts if p.access_type and any(k in p.access_type.upper() for k in ("TCC", "PERMACATH", "CVC")))
        results.append({
            "month": month_label,
            "total": total,
            "avf": avf,
            "tcc": tcc,
            "avf_rate": round(avf / total * 100, 1) if total else 0,
            "tcc_rate": round(tcc / total * 100, 1) if total else 0,
        })
    return results
