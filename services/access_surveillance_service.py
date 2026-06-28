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
    "avg_maturation_failure_days": 42,    # 6 weeks — upper bound of AVG cannulation readiness (KDOQI 2019 Guideline 9.4)
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
    "qa_baseline_window_sessions": 6,   # ≥6 sessions needed to distinguish true decline from ±15–20% measurement noise
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

_UNSPECIFIED = object()

def compute_access_action_items(
    db: Session,
    patient_id: int,
    config: dict | None = None,
    current_episode: AccessEpisode | None = _UNSPECIFIED,
    recent_sessions: list[SessionRecord] | None = None,
    all_events: list[AccessEvent] | None = None,
    all_episodes: list[AccessEpisode] | None = None,
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

    if current_episode is _UNSPECIFIED:
        episode = (
            db.query(AccessEpisode)
            .filter(
                AccessEpisode.patient_id == patient_id,
                AccessEpisode.is_current == True,
            )
            .order_by(AccessEpisode.creation_date.desc())
            .first()
        )
    else:
        episode = current_episode

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
        crbsi_rate = _compute_crbsi_rate_3m(db, patient_id, today, all_episodes_list=all_episodes, all_events_list=all_events)
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
            # AVF: KDOQI Glossary — 6 months (180 days) without first cannulation = failure
            # AVG: KDOQI 2019 Guideline 9.4 — conventional AVG ready in 2–6 weeks;
            #      42 days (6 weeks) used as failure threshold to catch non-maturing grafts early.
            add(
                "urgent",
                "maturation",
                f"{ac} maturation failure: {days_since_creation} days since creation, "
                f"never successfully cannulated "
                f"(KDOQI threshold {failure_days} days — "
                f"{'6 months per KDOQI Glossary' if ac == 'AVF' else '6 weeks per KDOQI 2019 Guideline 9.4'})",
            )

    # AV intervention rate — 1-2-3 rule (KDOQI Goals Box 3)
    _check_intervention_rate(db, episode, config, today, add, all_events_list=all_events)

    # Bedside exam deterioration — 2 consecutive sessions with abnormal thrill/bruit
    _check_bedside_exam_trend(db, patient_id, add, sessions_list=recent_sessions)

    # Qa absolute threshold
    qa_threshold_key = "qa_absolute_threshold_avf" if ac == "AVF" else "qa_absolute_threshold_avg"
    qa_threshold = _cfg(config, qa_threshold_key)
    recent_qa = _get_recent_qa(db, patient_id, n=2, sessions_list=recent_sessions)
    if len(recent_qa) == 2 and all(q < qa_threshold for q in recent_qa):
        add(
            "this_week",
            "qa_flow",
            f"Qa below absolute threshold ({recent_qa[0]:.0f} mL/min, threshold {qa_threshold:.0f}) on last 2 measurements — clinical review + consider imaging",
        )

    baseline_window = _cfg(config, "qa_baseline_window_sessions")
    qa_decline_pct = _cfg(config, "qa_relative_decline_pct")
    relative_decline, qa_baseline = _compute_qa_relative_decline(
        db, patient_id, int(baseline_window), sessions_list=recent_sessions
    )
    if relative_decline is not None and relative_decline >= qa_decline_pct:
        add(
            "this_week",
            "qa_flow",
            f"Qa persistent decline {relative_decline:.0f}% below {window}-session baseline "
            f"({qa_baseline:.0f} mL/min) — all 3 most recent readings confirm trend "
            f"(threshold {qa_decline_pct:.0f}%) — clinical review + consider imaging".replace(
                f"{window}-session", f"{int(baseline_window)}-session"
            ),
        )

    # Recirculation
    recirc_threshold = _cfg(config, "recirculation_threshold_pct")
    recent_recirc = _get_recent_recirculation(db, patient_id, n=2, sessions_list=recent_sessions)
    if len(recent_recirc) == 2 and all(r >= recirc_threshold for r in recent_recirc):
        add(
            "this_week",
            "recirculation",
            f"High recirculation ({recent_recirc[0]:.0f}%) on last 2 sessions (threshold {recirc_threshold:.0f}%) — clinical review + consider imaging",
        )

    # Cannulation failure rate (last 20 sessions)
    failure_rate_threshold = _cfg(config, "cannulation_failure_rate_alert")
    cannulation_failure_rate = _compute_cannulation_failure_rate(db, patient_id, n=20, sessions_list=recent_sessions)
    if cannulation_failure_rate is not None and cannulation_failure_rate >= failure_rate_threshold:
        add(
            "this_week",
            "cannulation",
            f"Cannulation failure rate {cannulation_failure_rate:.1f}% over last 20 sessions (threshold {failure_rate_threshold:.0f}%) — clinical review",
        )

    # Steal Grade 3 — auto-urgent (check recent confirmed events)
    _check_steal_grade3(db, patient_id, ep_id, add, all_events_list=all_events)

    items.sort(key=lambda x: {"urgent": 0, "this_week": 1, "routine": 2}[x["priority"]])
    return items


def _check_intervention_rate(
    db: Session, episode: Any, config: dict, today: date, add, all_events_list: list = None
):
    """Check KDOQI 1-2-3 rule: ≤2 to establish, ≤3/year to maintain."""
    from db.models.clinical import AccessEvent

    ac = (episode.access_class or "").upper()
    establish_max = _cfg(config, "av_interventions_establish_max")
    maintain_max = _cfg(config, "av_interventions_maintain_per_year_max")

    if all_events_list is None:
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
    else:
        all_events = sorted(
            [
                e for e in all_events_list
                if e.episode_id == episode.id
                and e.status == "confirmed"
                and e.action_taken in _INTERVENTION_ACTIONS
            ],
            key=lambda e: e.event_date
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


def _check_bedside_exam_trend(db: Session, patient_id: int, add, sessions_list: list = None):
    """Flag if thrill or bruit was abnormal in last 2 consecutive sessions."""
    from db.models.sessions import SessionRecord

    if sessions_list is None:
        recent = (
            db.query(SessionRecord)
            .filter(SessionRecord.patient_id == patient_id)
            .order_by(SessionRecord.session_date.desc())
            .limit(2)
            .all()
        )
    else:
        recent = sessions_list[:2]

    if len(recent) < 2:
        return
    thrill_bad = all(s.thrill_grade and s.thrill_grade != "normal" for s in recent)
    bruit_bad = all(s.bruit_grade and s.bruit_grade != "normal" for s in recent)
    if thrill_bad:
        add("this_week", "bedside_exam", "Thrill abnormal in last 2 consecutive sessions — consider imaging (KDOQI 13.4)")
    if bruit_bad:
        add("this_week", "bedside_exam", "Bruit abnormal in last 2 consecutive sessions — consider imaging (KDOQI 13.4)")


def _check_steal_grade3(db: Session, patient_id: int, episode_id: int, add, all_events_list: list = None):
    from db.models.clinical import AccessEvent

    if all_events_list is None:
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
    else:
        grade3_events = [
            e for e in all_events_list
            if e.patient_id == patient_id
            and e.episode_id == episode_id
            and e.event_type == "steal_syndrome"
            and e.steal_grade == "grade_3"
            and e.status == "confirmed"
        ]
        grade3 = sorted(grade3_events, key=lambda e: e.event_date, reverse=True)[0] if grade3_events else None
    if grade3:
        add(
            "urgent",
            "steal",
            f"Steal syndrome Grade 3 confirmed ({grade3.event_date}) — urgent surgical referral required (KDOQI Table 18.3)",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helper data extractors
# ─────────────────────────────────────────────────────────────────────────────

def _get_recent_qa(db: Session, patient_id: int, n: int, sessions_list: list = None) -> list[float]:
    from db.models.sessions import SessionRecord

    if sessions_list is None:
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
    else:
        return [s.access_flow_qa for s in sessions_list if s.access_flow_qa is not None][:n]


def _compute_qa_relative_decline(
    db: Session, patient_id: int, window: int, sessions_list: list = None
) -> tuple[float | None, float | None]:
    """Return (decline_pct, baseline_qa) from rolling baseline to the most recent Qa, or (None, None).

    KDOQI 2019 Guideline 13.3 requires decline to be *persistent* across multiple
    readings before it is considered clinically significant. A single outlier low
    session (e.g. from malpositioning, patient movement) must not trigger an alert.

    Logic:
      - Fetch the last (window + 3) Qa values (oldest-to-newest after sort).
      - Compute a rolling baseline from the oldest `window` readings.
      - Require that the 3 most recent readings are ALL below the baseline before
        returning a non-zero decline. If fewer than 3 recent readings exist below
        baseline, the decline is suppressed (returns (None, None)).
      - The reported decline % is from baseline to the single latest reading.
    """
    from db.models.sessions import SessionRecord

    n_needed = window + 3   # baseline window + 3 persistence readings

    if sessions_list is None:
        rows = (
            db.query(SessionRecord.access_flow_qa)
            .filter(
                SessionRecord.patient_id == patient_id,
                SessionRecord.access_flow_qa.isnot(None),
            )
            .order_by(SessionRecord.session_date.desc())
            .limit(n_needed)
            .all()
        )
        values = [r[0] for r in rows]   # newest first
    else:
        values = [s.access_flow_qa for s in sessions_list if s.access_flow_qa is not None][:n_needed]

    if len(values) < window + 1:
        return None, None

    # newest first → values[0] is latest, values[-window:] are the oldest (baseline)
    recent_readings = values[:3]          # up to 3 most recent
    baseline_readings = values[3:3 + window] if len(values) >= 3 + window else values[len(recent_readings):]

    if not baseline_readings:
        return None, None

    baseline = sum(baseline_readings) / len(baseline_readings)
    if baseline <= 0:
        return None, None

    # Persistence gate: require ALL available recent readings to be below baseline
    # (minimum 1, ideally 3 — enforces KDOQI "persistent" criterion)
    if not recent_readings or not all(q < baseline for q in recent_readings):
        return None, None

    latest = recent_readings[0]
    decline = max((baseline - latest) / baseline * 100, 0.0)
    return decline, round(baseline, 0)


def _get_recent_recirculation(db: Session, patient_id: int, n: int, sessions_list: list = None) -> list[float]:
    from db.models.sessions import SessionRecord

    if sessions_list is None:
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
    else:
        return [s.access_recirculation_percent for s in sessions_list if s.access_recirculation_percent is not None][:n]


def _compute_cannulation_failure_rate(db: Session, patient_id: int, n: int, sessions_list: list = None) -> float | None:
    """Return cannulation failure rate (%) over the last *n* sessions in the window.

    ⚠ Denominator contract:
        The denominator is always the total number of sessions in the requested
        window (n), NOT only sessions where cannulation_difficulty was documented.
        Using documented-only as the denominator inflates the rate whenever nurses
        chart only difficult events and omit routine ones — a common documentation
        pattern that would produce false-positive alerts at the 5% threshold.

    Returns None when fewer than 1 session exists in the window (no data at all).
    Sessions in the window where cannulation_difficulty is NULL are counted as
    non-failure (i.e. presumed routine) so the denominator remains stable.
    """
    from db.models.sessions import SessionRecord

    if sessions_list is None:
        # Fetch the n most-recent sessions, regardless of documentation status.
        # We need the full row to count total sessions; filter for documented
        # failures separately.
        rows = (
            db.query(SessionRecord.cannulation_difficulty)
            .filter(SessionRecord.patient_id == patient_id)
            .order_by(SessionRecord.session_date.desc())
            .limit(n)
            .all()
        )
        total = len(rows)                                     # true denominator
        failed = sum(1 for r in rows if r[0] == "failed")
    else:
        window = sessions_list[:n]                            # honour the n-session limit
        total = len(window)                                   # true denominator
        failed = sum(1 for s in window if s.cannulation_difficulty == "failed")

    if total == 0:
        return None
    return failed / total * 100


def _compute_crbsi_rate_3m(db: Session, patient_id: int, today: date, all_episodes_list: list = None, all_events_list: list = None) -> float | None:
    """CRBSI rate per 1000 catheter-days over rolling 3 months."""
    from db.models.clinical import AccessEpisode, AccessEvent

    cutoff = today - timedelta(days=90)

    if all_episodes_list is None:
        episodes = (
            db.query(AccessEpisode)
            .filter(
                AccessEpisode.patient_id == patient_id,
                AccessEpisode.access_class == "TCC",
            )
            .all()
        )
    else:
        episodes = [
            ep for ep in all_episodes_list
            if ep.patient_id == patient_id
            and ep.access_class == "TCC"
        ]

    catheter_days = 0
    for ep in episodes:
        start = max(ep.creation_date, cutoff)
        end = ep.loss_date if ep.loss_date else today
        if end >= start:
            catheter_days += (end - start).days

    if catheter_days == 0:
        return None

    if all_events_list is None:
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
    else:
        confirmed_crbsi = sum(
            1 for e in all_events_list
            if e.patient_id == patient_id
            and e.event_type == "crbsi_confirmed"
            and e.status == "confirmed"
            and e.event_date >= cutoff
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

    from sqlalchemy.orm import joinedload, selectinload
    active_patients = (
        db.query(Patient)
        .options(
            joinedload(Patient.vascular_access),
            selectinload(Patient.access_episodes),
        )
        .filter(Patient.is_active == True)
        .all()
    )
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
    # NOTE: KDOQI 2019 Guideline 1.2 abandoned prescriptive AVF% targets in favour of
    # individualised ESKD Life-Plans. The 65% floor reflects the ERA-EDTA registry
    # median (66–72%) and is a defensible aspirational threshold, not a hard mandate.
    avf_patients = [p for p in active_patients if _is_access_class(p, "AVF")]
    results.append(bench(
        "Prevalent AVF Rate", "AVF",
        len(avf_patients), total, 65.0, True,
        "Active patients at month-end",
        "Aspirational goal (ERA-EDTA median 66–72%). KDOQI 2019 mandates no fixed % target.",
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
    # NOTE: KDOQI 2019 expresses 65% as a minimum aspirational threshold for centres with
    # adequate pre-dialysis infrastructure, not a universal pass/fail. Units with high
    # urgent-start HD populations, elderly/frail patients, or those with diabetes-related
    # poor vessel anatomy may legitimately score below 65% without representing poor care.
    new_starts = [p for p in active_patients if p.hd_wef_date and p.hd_wef_date >= month_start and p.hd_wef_date <= month_end]
    new_avf_starts = [p for p in new_starts if _is_access_class(p, "AVF")]
    if new_starts:
        results.append(bench(
            "Incident AVF Rate", "AVF",
            len(new_avf_starts), len(new_starts), 65.0, True,
            "New HD starts in month",
            "Minimum aspirational goal (KDOQI 2019). May be lower in urgent-start, elderly, "
            "diabetic or frail populations — case-mix adjustment required before benchmarking.",
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
    # KDOQI 2019 Goals Box targets (episodes/patient-year → /100 patient-months):
    #   AVF: <0.25/pt-year  = 0.25/12 × 100 = 2.08 per 100 pt-months
    #   AVG: <0.50/pt-year  = 0.50/12 × 100 = 4.17 per 100 pt-months
    # The former code used 0.5 for both, which equals 6/pt-year — 12× too permissive for AVF.
    _THROMBOSIS_TARGETS = {"AVF": 2.08, "AVG": 4.17}
    for ac_label in ("AVF", "AVG"):
        ac_patients = [p for p in active_patients if _is_access_class(p, ac_label)]

        # ── 4.3 FIX: robust thrombosis numerator ────────────────────────────────
        # The AccessEvent.access_class field is denormalised from the episode at
        # event-creation time (analytics router lines 623-628). However events
        # created via legacy routes, direct DB inserts, or migration scripts may
        # have access_class = NULL, causing a silent zero rate that appears green.
        #
        # Query strategy: count events that match EITHER
        #   (a) AccessEvent.access_class == ac_label  (populated correctly), OR
        #   (b) AccessEvent.access_class IS NULL but the linked episode has
        #       access_class == ac_label  (fallback for legacy/migration rows).
        #
        # This is implemented as two separate counts unioned in Python to avoid a
        # complex ORM outer-join that differs between SQLite and PostgreSQL.
        thrombosis_events_direct = (
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
        # Fallback: null access_class — join through episode
        thrombosis_events_via_episode = (
            db.query(AccessEvent)
            .join(AccessEpisode, AccessEvent.episode_id == AccessEpisode.id)
            .filter(
                AccessEvent.access_class.is_(None),
                AccessEpisode.access_class == ac_label,
                AccessEvent.event_type == "thrombosis",
                AccessEvent.status == "confirmed",
                AccessEvent.event_date >= month_start,
                AccessEvent.event_date <= month_end,
            )
            .count()
        )
        thrombosis_events = thrombosis_events_direct + thrombosis_events_via_episode
        # ── end 4.3 FIX ─────────────────────────────────────────────────────────

        patient_months = len(ac_patients)  # 1 month
        thr_target = _THROMBOSIS_TARGETS[ac_label]
        if patient_months:
            thr_rate = round(thrombosis_events / patient_months * 100, 2)

            # Data-quality guard: a zero thrombosis rate in an active unit with
            # multiple patients on AVF/AVG is clinically implausible and more
            # likely reflects missing event documentation than a true zero.
            # Log a warning so the discrepancy is surfaced in server logs.
            if thrombosis_events == 0 and len(ac_patients) >= 5:
                logger.warning(
                    "compute_unit_benchmarks: %s thrombosis rate is 0 for %d patients "
                    "in %s–%s. Verify that thrombosis events are being logged and that "
                    "AccessEvent.access_class is populated correctly.",
                    ac_label, len(ac_patients), month_start, month_end,
                )

            results.append({
                "name": f"{ac_label} Thrombosis Rate",
                "access_class": ac_label,
                "numerator": thrombosis_events,
                "denominator": patient_months,
                "rate": thr_rate,
                "target": thr_target,
                "rag": rag(thr_rate, thr_target, False),
                "denominator_label": (
                    f"100 {ac_label} patient-months "
                    f"(KDOQI target <{thr_target}/100 pt-months = "
                    f"<{round(thr_target / 100 * 12, 2)}/pt-year)"
                ),
                "notes": (
                    f"Confirmed thrombosis events only. "
                    f"KDOQI target: <{thr_target} per 100 {ac_label} patient-months "
                    f"({'0.25' if ac_label == 'AVF' else '0.50'} episodes/patient-year). "
                    f"{'⚠ Rate is 0 — verify event documentation completeness.' if thrombosis_events == 0 else ''}"
                ).strip(),
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


# ─────────────────────────────────────────────────────────────────────────────
# Legacy access-type normalisation
# ─────────────────────────────────────────────────────────────────────────────
# Canonical access classes (exactly as stored in AccessEpisode.access_class):
#   AVF | AVG | TCC | NON_TUNNELLED
#
# The legacy PatientVascularAccess.access_type field is a free-text string
# imported from spreadsheets and entered by different operators over time.
# Substring matching against free text is fragile:
#   - "Left IJV Permcath" should be TCC, but "TEMP" does not appear in it.
#   - "AV Graft" contains neither "AVG" nor "GRAFT" (exact) in all variants.
#   - A string like "AVF + TCC bridge" would match both AVF and TCC.
#
# Fix: an explicit canonical lookup table. All known legacy strings are mapped
# to exactly one class. Unknown strings → None (logged, never double-counted).
# The table must be extended if new legacy values are discovered — see the
# warning log that fires for unrecognised strings.
# ─────────────────────────────────────────────────────────────────────────────
_LEGACY_ACCESS_TYPE_TO_CLASS: dict[str, str] = {
    # AVF variants
    "AVF":                          "AVF",
    "AV FISTULA":                   "AVF",
    "ARTERIOVENOUS FISTULA":        "AVF",
    "RC AVF":                       "AVF",
    "RADIOCEPHALIC AVF":            "AVF",
    "BC AVF":                       "AVF",
    "BRACHIOCEPHALIC AVF":          "AVF",
    "BB AVF":                       "AVF",
    "BRACHIOBASILIC AVF":           "AVF",
    "LEFT AVF":                     "AVF",
    "RIGHT AVF":                    "AVF",
    "LT AVF":                       "AVF",
    "RT AVF":                       "AVF",
    "AVF LT":                       "AVF",
    "AVF RT":                       "AVF",
    "FISTULA":                      "AVF",
    # AVG variants
    "AVG":                          "AVG",
    "AV GRAFT":                     "AVG",
    "ARTERIOVENOUS GRAFT":          "AVG",
    "GORE-TEX GRAFT":               "AVG",
    "PTFE GRAFT":                   "AVG",
    "SYNTHETIC GRAFT":              "AVG",
    "LOOP GRAFT":                   "AVG",
    "GRAFT":                        "AVG",
    # TCC — tunnelled/permanent CVC variants
    "TCC":                          "TCC",
    "PERMCATH":                     "TCC",
    "PERM CATH":                    "TCC",
    "PERMANENT CATHETER":           "TCC",
    "TUNNELLED CVC":                "TCC",
    "TUNNELED CVC":                 "TCC",
    "TUNNELLED CATHETER":           "TCC",
    "TUNNELED CATHETER":            "TCC",
    "LONG-TERM CVC":                "TCC",
    "LONG TERM CVC":                "TCC",
    "PERM CVC":                     "TCC",
    "PERMANENT CVC":                "TCC",
    "IJV PERMCATH":                 "TCC",
    "LEFT IJV PERMCATH":            "TCC",
    "RIGHT IJV PERMCATH":           "TCC",
    "LT IJV PERMCATH":              "TCC",
    "RT IJV PERMCATH":              "TCC",
    "HICKMAN":                      "TCC",
    "TESIO":                        "TCC",
    "SPLIT CATH":                   "TCC",
    "MAHURKAR (PERM)":              "TCC",
    "MAHURKAR PERM":                "TCC",
    # NON_TUNNELLED variants
    "NON_TUNNELLED":                "NON_TUNNELLED",
    "NON TUNNELLED":                "NON_TUNNELLED",
    "NON-TUNNELLED":                "NON_TUNNELLED",
    "TEMP CVC":                     "NON_TUNNELLED",
    "TEMPORARY CVC":                "NON_TUNNELLED",
    "DLJC":                         "NON_TUNNELLED",
    "DOUBLE LUMEN JUGULAR CATHETER":"NON_TUNNELLED",
    "MAHURKAR":                     "NON_TUNNELLED",
    "MAHURKAR (TEMP)":              "NON_TUNNELLED",
    "MAHURKAR TEMP":                "NON_TUNNELLED",
    "VASCATH":                      "NON_TUNNELLED",
    "TEMPORARY CATHETER":           "NON_TUNNELLED",
    "TEMP CATHETER":                "NON_TUNNELLED",
    "SHALDON":                      "NON_TUNNELLED",
}


def _normalise_legacy_access_type(raw: str) -> str | None:
    """Map a free-text legacy access_type string to one canonical class.

    Returns one of: 'AVF' | 'AVG' | 'TCC' | 'NON_TUNNELLED' | None.
    Returns None (never raises) when the string is unrecognised.
    A warning is logged so unrecognised values can be added to the table.

    ⚠ This function intentionally returns a SINGLE class.  There is no
    multi-match path — a patient is classified into exactly one category
    or reported as unknown.  This prevents the double-counting bug that
    the previous substring-matching fallback was susceptible to.
    """
    key = raw.strip().upper()
    if key in _LEGACY_ACCESS_TYPE_TO_CLASS:
        return _LEGACY_ACCESS_TYPE_TO_CLASS[key]

    # Second pass: try stripping common site prefixes ("LEFT ", "RIGHT ",
    # "LT ", "RT ", "BIL ") and re-looking up the remainder.
    for prefix in ("LEFT ", "RIGHT ", "LT ", "RT ", "BIL ", "L ", "R "):
        if key.startswith(prefix):
            trimmed = key[len(prefix):]
            if trimmed in _LEGACY_ACCESS_TYPE_TO_CLASS:
                return _LEGACY_ACCESS_TYPE_TO_CLASS[trimmed]

    logger.warning(
        "access_surveillance: unrecognised legacy access_type %r — "
        "patient excluded from access-class denominator. "
        "Add this value to _LEGACY_ACCESS_TYPE_TO_CLASS to resolve.",
        raw,
    )
    return None


def _is_access_class(patient: Any, ac: str) -> bool:
    """Return True iff the patient's current access is classified as *ac*.

    Classification priority (highest wins):
      1. AccessEpisode.access_class for the row where is_current=True.
         This is the authoritative source — always preferred.
      2. _normalise_legacy_access_type() on PatientVascularAccess.access_type
         when no current AccessEpisode exists.
         Returns False (not an error) if the legacy string is unrecognised —
         an unrecognised patient is simply excluded from the denominator
         rather than silently misclassified into a wrong bucket.

    A patient is NEVER matched to more than one access class (no double-counting).
    """
    ac_upper = ac.upper()

    # ── Primary path: current AccessEpisode ──────────────────────────────────
    if hasattr(patient, "access_episodes") and patient.access_episodes:
        current = [e for e in patient.access_episodes if e.is_current]
        if current:
            # Take the most recently created current episode if multiple exist.
            ep = max(current, key=lambda e: e.creation_date or date.min)
            stored = (ep.access_class or "").upper()
            # Normalise the stored value: 'NON_TUNNELLED' stored as-is in DB.
            if stored == "NON_TUNNELLED" and ac_upper in ("NON_TUNNELLED", "NON-TUNNELLED"):
                return True
            return stored == ac_upper

    # ── Fallback: legacy PatientVascularAccess.access_type ───────────────────
    if (
        hasattr(patient, "vascular_access")
        and patient.vascular_access
        and patient.vascular_access.access_type
    ):
        canonical = _normalise_legacy_access_type(patient.vascular_access.access_type)
        if canonical is None:
            return False   # unrecognised — exclude rather than misclassify
        return canonical == ac_upper

    return False


def _unit_catheter_days(db: Session, month_start: date, month_end: date) -> int:
    """Sum TCC catheter-days for all patients in the given date range.

    Convention: EXCLUSIVE end-date (end - start).days, matching the
    CDC/NHSN device-days methodology used for CRBSI rate calculation.
    The catheter is counted from its insertion date up to (but not
    including) its removal/loss date, because a device removed on day N
    was not present for the entirety of day N.

    ⚠ The previous implementation used (end - start).days + 1 (inclusive
    end), which inflated the denominator by one day per episode — slightly
    understating the CRBSI rate. Corrected to exclusive-end.
    """
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
        if end > start:          # strictly greater: zero-day episodes contribute 0
            total += (end - start).days
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
    """Per-patient variant of _unit_catheter_days.

    Uses exclusive end-date convention (CDC/NHSN device-days) — see
    _unit_catheter_days for the full rationale.
    """
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
        if end > start:          # exclusive end — see _unit_catheter_days
            total += (end - start).days
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
# Access-Loss Clinical Attention Score (per-patient)
#
# ⚠ IMPORTANT — VALIDATION STATUS:
# This is an unvalidated, internally-designed clinical attention tool.
# The weights below were assigned by clinical consensus at development time
# and have NOT been validated against outcome data or published in any
# peer-reviewed study. KDOQI 2019 does NOT define these numeric weights.
#
# The score MUST NOT be interpreted as a probability of access loss.
# It is a structured prioritisation aid to surface patients warranting
# closer clinical attention — equivalent to a weighted checklist.
#
# The relative ordering of factors reflects clinical judgement at the time
# of development. Thrombosis history (3.0) and Steal Gr3 (4.0) weights may
# require recalibration once outcome data are available.
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

# Thresholds: raw score → attention level label
# NOTE: These raw score cut-offs (6.0 / 3.0) are arbitrary calibration points,
# not derived from clinical outcome data.
_RISK_LEVELS = [(6.0, "High"), (3.0, "Moderate"), (0.0, "Low")]


def compute_access_loss_risk(
    db: Session,
    patient_id: int,
    config: dict | None = None,
) -> dict:
    """Compute a weighted clinical attention score for a single patient's current access.

    Returns a structured dict indicating which risk factors are present and
    a normalised score index (0–100). This is NOT a calibrated probability
    of access loss — it is an unvalidated prioritisation aid.

    Returns: {attention_level, score, max_score, risk_score_index, factors, episode_id, access_class}
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
    decline, _baseline = _compute_qa_relative_decline(db, patient_id, baseline_window)
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
    attention_level = next(label for threshold, label in _RISK_LEVELS if score >= threshold)
    # risk_score_index: weighted score as a fraction of max possible, scaled to 0–100.
    # This is NOT a calibrated probability — do not display with a % sign.
    risk_score_index = round(score / max_score * 100, 1)

    return {
        "available": True,
        "patient_id": patient_id,
        "episode_id": episode.id,
        "access_class": ac,
        "score": round(score, 1),
        "max_score": round(max_score, 1),
        "risk_score_index": risk_score_index,
        # Backward-compat alias so existing template references still resolve:
        "risk_pct": risk_score_index,
        "risk_level": attention_level,
        "factors": factors,
    }


def compute_unit_access_risk(
    db: Session,
    config: dict | None = None,
) -> list[dict]:
    """Run access-loss risk scoring for all active patients with a current episode.

    Uses 5 batch queries instead of N×10 per-patient queries.
    Returns list sorted by score descending.
    """
    from db.models.patient import Patient
    from db.models.clinical import AccessEpisode, AccessEvent
    from db.models.sessions import SessionRecord
    from sqlalchemy import func

    if config is None:
        config = _load_config(db)

    today = date.today()

    # ── 1. Active patients ────────────────────────────────────────────────────
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    if not patients:
        return []
    pid_list = [p.id for p in patients]
    patient_map = {p.id: p for p in patients}

    # ── 2. Current access episodes (one per patient) ──────────────────────────
    ep_subq = (
        db.query(
            AccessEpisode.patient_id,
            AccessEpisode.id.label("ep_id"),
            AccessEpisode.access_class,
            AccessEpisode.creation_date,
            AccessEpisode.first_cannulation_date,
            AccessEpisode.succession_plan,
            AccessEpisode.loss_date,
            func.row_number().over(
                partition_by=AccessEpisode.patient_id,
                order_by=AccessEpisode.creation_date.desc(),
            ).label("rn"),
        )
        .filter(
            AccessEpisode.patient_id.in_(pid_list),
            AccessEpisode.is_current == True,
        )
        .subquery()
    )
    episode_rows = (
        db.query(ep_subq).filter(ep_subq.c.rn == 1).all()
    )
    episodes: dict[int, Any] = {}  # patient_id → episode row
    ep_id_to_pid: dict[int, int] = {}
    for row in episode_rows:
        episodes[row.patient_id] = row
        ep_id_to_pid[row.ep_id] = row.patient_id

    if not episodes:
        return []

    ep_ids = list(ep_id_to_pid.keys())

    # ── 3. AccessEvents for all episodes (thrombosis, steal, interventions) ───
    year_ago = today - timedelta(days=365)
    all_events = (
        db.query(
            AccessEvent.episode_id,
            AccessEvent.event_type,
            AccessEvent.steal_grade,
            AccessEvent.action_taken,
            AccessEvent.event_date,
            AccessEvent.status,
        )
        .filter(
            AccessEvent.episode_id.in_(ep_ids),
            AccessEvent.status == "confirmed",
        )
        .all()
    )
    # Index events by episode_id
    events_by_ep: dict[int, list] = {eid: [] for eid in ep_ids}
    for ev in all_events:
        events_by_ep[ev.episode_id].append(ev)

    # ── 4. Recent session data: Qa, recirculation, cannulation, thrill/bruit ──
    # Fetch last 5 sessions per patient (enough for Qa baseline window + recent checks)
    sess_subq = (
        db.query(
            SessionRecord.patient_id,
            SessionRecord.access_flow_qa,
            SessionRecord.access_recirculation_percent,
            SessionRecord.cannulation_difficulty,
            SessionRecord.thrill_grade,
            SessionRecord.bruit_grade,
            SessionRecord.session_date,
            func.row_number().over(
                partition_by=SessionRecord.patient_id,
                order_by=SessionRecord.session_date.desc(),
            ).label("rn"),
        )
        .filter(SessionRecord.patient_id.in_(pid_list))
        .subquery()
    )
    recent_sessions = (
        db.query(sess_subq).filter(sess_subq.c.rn <= 21).all()
    )
    sessions_by_pid: dict[int, list] = {pid: [] for pid in pid_list}
    for s in recent_sessions:
        sessions_by_pid[s.patient_id].append(s)
    # Sessions are already ordered desc by session_date within each patient

    # ── Score each patient in Python ──────────────────────────────────────────
    maintain_max = _cfg(config, "av_interventions_maintain_per_year_max")
    results = []

    for pid, ep in episodes.items():
        p = patient_map.get(pid)
        if not p:
            continue

        ac = (ep.access_class or "").upper()
        score = 0.0
        factors: list[str] = []
        evs = events_by_ep.get(ep.ep_id, [])
        sess = sessions_by_pid.get(pid, [])

        # Thrombosis history
        thrombus = sum(1 for e in evs if e.event_type == "thrombosis")
        if thrombus:
            score += _RISK_WEIGHTS["thrombosis_history"]
            factors.append(f"Thrombosis history ({thrombus} confirmed)")

        # Steal Grade 3
        steal3 = sum(1 for e in evs if e.event_type == "steal_syndrome" and e.steal_grade == "grade_3")
        if steal3:
            score += _RISK_WEIGHTS["steal_grade3"]
            factors.append("Steal syndrome Grade 3 confirmed")

        # Qa below threshold
        qa_key = "qa_absolute_threshold_avf" if ac == "AVF" else "qa_absolute_threshold_avg"
        qa_threshold = _cfg(config, qa_key)
        qa_vals = [s.access_flow_qa for s in sess if s.access_flow_qa is not None]
        if qa_vals and qa_vals[0] < qa_threshold:
            score += _RISK_WEIGHTS["qa_below_threshold"]
            factors.append(f"Qa {qa_vals[0]:.0f} mL/min < threshold {qa_threshold:.0f}")

        # Qa relative decline
        baseline_window = int(_cfg(config, "qa_baseline_window_sessions"))
        qa_decline_pct = _cfg(config, "qa_relative_decline_pct")
        if len(qa_vals) >= baseline_window + 1:
            latest_qa = qa_vals[0]
            baseline = sum(qa_vals[3:3 + baseline_window]) / baseline_window if len(qa_vals) >= 3 + baseline_window else sum(qa_vals[1:]) / (len(qa_vals) - 1)
            # Persistence gate: all 3 most recent readings must be below baseline
            recent_3 = qa_vals[:3]
            if baseline > 0 and all(q < baseline for q in recent_3):
                decline = max((baseline - latest_qa) / baseline * 100, 0.0)
                if decline >= qa_decline_pct:
                    score += _RISK_WEIGHTS["qa_declining"]
                    factors.append(f"Qa declining {decline:.0f}% from baseline (persistent over {len(recent_3)} sessions)")

        # High recirculation (last 2 sessions with a reading)
        recirc_threshold = _cfg(config, "recirculation_threshold_pct")
        recirc_vals = [s.access_recirculation_percent for s in sess if s.access_recirculation_percent is not None]
        if len(recirc_vals) >= 2 and all(r >= recirc_threshold for r in recirc_vals[:2]):
            score += _RISK_WEIGHTS["high_recirculation"]
            factors.append(f"Recirculation ≥{recirc_threshold:.0f}% last 2 sessions")

        # Cannulation failure rate (last 20 sessions with a reading)
        failure_threshold = _cfg(config, "cannulation_failure_rate_alert")
        cann_vals = [s.cannulation_difficulty for s in sess if s.cannulation_difficulty is not None]
        if cann_vals:
            fail_rate = sum(1 for v in cann_vals[:20] if v == "failed") / min(len(cann_vals), 20) * 100
            if fail_rate >= failure_threshold:
                score += _RISK_WEIGHTS["cannulation_failure_high"]
                factors.append(f"Cannulation failure rate {fail_rate:.1f}%")

        # Bedside exam deterioration (last 2 sessions)
        if len(sess) >= 2:
            recent2 = sess[:2]
            if all(s.thrill_grade and s.thrill_grade != "normal" for s in recent2):
                score += _RISK_WEIGHTS["thrill_bruit_abnormal"]
                factors.append("Thrill abnormal last 2 sessions")
            if all(s.bruit_grade and s.bruit_grade != "normal" for s in recent2):
                score += _RISK_WEIGHTS["thrill_bruit_abnormal"]
                factors.append("Bruit abnormal last 2 sessions")

        # Excess maintenance interventions (AV only, past 12 months after first use)
        if ac in ("AVF", "AVG") and ep.first_cannulation_date:
            start_date = max(ep.first_cannulation_date, year_ago)
            maintain_count = sum(
                1 for e in evs
                if e.action_taken in _INTERVENTION_ACTIONS
                and e.event_date >= start_date
                and e.event_date >= ep.first_cannulation_date
            )
            if maintain_count > maintain_max:
                score += _RISK_WEIGHTS["excess_interventions"]
                factors.append(f"{maintain_count} maintenance interventions past 12 months (KDOQI ≤{maintain_max})")

        # Maturation delay
        if ac in ("AVF", "AVG") and not ep.first_cannulation_date:
            delay_key = "avf_maturation_delay_days" if ac == "AVF" else "avg_maturation_delay_days"
            delay_days = _cfg(config, delay_key)
            days_since = (today - ep.creation_date).days
            if days_since > delay_days:
                score += _RISK_WEIGHTS["maturation_delay"]
                factors.append(f"Maturation delay: {days_since} days, not yet cannulated")

        # TCC long duration
        if ac == "TCC":
            tcc_alert = _cfg(config, "tcc_duration_alert_days")
            days_in = (today - ep.creation_date).days
            if days_in > tcc_alert:
                score += _RISK_WEIGHTS["tcc_long_duration"]
                factors.append(f"TCC in situ {days_in} days (alert >{tcc_alert})")

        # Life-plan missing
        if not ep.succession_plan:
            score += _RISK_WEIGHTS["life_plan_missing"]
            factors.append("Succession plan not documented")

        max_score = sum(_RISK_WEIGHTS.values())
        attention_level = next(label for threshold, label in _RISK_LEVELS if score >= threshold)
        # risk_score_index: fraction of max weighted score × 100 — NOT a probability.
        risk_score_index = round(score / max_score * 100, 1)

        results.append({
            "available": True,
            "patient_id": pid,
            "patient_name": p.name,
            "hid_no": p.hid_no,
            "episode_id": ep.ep_id,
            "access_class": ac,
            "score": round(score, 1),
            "max_score": round(max_score, 1),
            "risk_score_index": risk_score_index,
            "risk_pct": risk_score_index,   # backward-compat alias for templates
            "risk_level": attention_level,
            "factors": factors,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def compute_unit_qa_distribution(db: Session) -> list[dict]:
    """Return last Qa reading per active patient for unit-level distribution chart.

    Single batch query using DISTINCT ON / subquery — no per-patient round-trips.
    """
    from db.models.patient import Patient
    from db.models.sessions import SessionRecord
    from sqlalchemy import func

    # One query: for each patient get their most recent session with a Qa value
    subq = (
        db.query(
            SessionRecord.patient_id,
            SessionRecord.access_flow_qa,
            SessionRecord.session_date,
            func.row_number().over(
                partition_by=SessionRecord.patient_id,
                order_by=SessionRecord.session_date.desc(),
            ).label("rn"),
        )
        .filter(SessionRecord.access_flow_qa.isnot(None))
        .subquery()
    )
    latest_qa = (
        db.query(subq.c.patient_id, subq.c.access_flow_qa, subq.c.session_date)
        .filter(subq.c.rn == 1)
        .all()
    )

    # Build patient map in a second query (one query, not N)
    pid_list = [r[0] for r in latest_qa]
    if not pid_list:
        return []
    from sqlalchemy.orm import joinedload
    patients = (
        db.query(Patient)
        .options(joinedload(Patient.vascular_access))
        .filter(
            Patient.id.in_(pid_list),
            Patient.is_active == True,
        )
        .all()
    )
    p_map = {p.id: p for p in patients}

    rows = []
    for pid, qa, sess_date in latest_qa:
        p = p_map.get(pid)
        if p:
            rows.append({
                "patient_name": p.name,
                "hid_no": p.hid_no,
                "qa": qa,
                "date": str(sess_date),
                "access_type": p.access_type or "Unknown",
            })
    return rows


def compute_avf_rate_trend(db: Session, n_months: int = 6) -> list[dict]:
    """Compute prevalent AVF rate for each of the last n_months months.

    Loads all active patients once, then computes per-month counts in Python.
    """
    from db.models.patient import Patient
    from sqlalchemy.orm import joinedload
    import calendar

    today = date.today()

    # Single query — load all active patients with an HD start date once
    all_pts = (
        db.query(Patient)
        .options(joinedload(Patient.vascular_access))
        .filter(
            Patient.is_active == True,
            Patient.hd_wef_date.isnot(None),
        )
        .all()
    )

    results = []
    for i in range(n_months - 1, -1, -1):
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        month_label = month_end.strftime("%b %Y")

        # Filter in Python — no extra DB round-trip
        cohort = [p for p in all_pts if p.hd_wef_date <= month_end]
        total = len(cohort)
        avf = sum(1 for p in cohort if p.access_type and "AVF" in p.access_type.upper())
        tcc = sum(1 for p in cohort if p.access_type and any(k in p.access_type.upper() for k in ("TCC", "PERMACATH", "CVC")))
        results.append({
            "month": month_label,
            "total": total,
            "avf": avf,
            "tcc": tcc,
            "avf_rate": round(avf / total * 100, 1) if total else 0,
            "tcc_rate": round(tcc / total * 100, 1) if total else 0,
        })
    return results
