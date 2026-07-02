"""
services/data_completeness.py
=============================
Single source of truth for *which* patient clinical fields are expected and at
what severity, plus the scanning logic that flags blank / nil / absent values.

Consumed by:
  • routers/admin.py            → the /admin/missing-data page (cohort + patient)
  • scripts/scan_missing_values → the CLI scanner

The clinical model is extremely granular (hundreds of fields across demographics,
seven 1:1 profile tables and the monthly lab record), so blanks slip through
un-noticed. This module makes them visible.

A value counts as MISSING when it is None or an empty/whitespace string. Booleans
set to ``False`` are NOT flagged — ``False`` is a real clinical answer (e.g. "no
history of stroke"); only a NULL boolean is genuinely un-recorded.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import (
    Patient,
    PatientComorbidities,
    PatientRenalProfile,
    PatientViralMarkers,
    PatientVaccination,
    PatientVascularAccess,
    PatientCardiac,
    MonthlyRecord,
    SessionRecord,
)

REQUIRED = "required"
RECOMMENDED = "recommended"


def is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


# ── Field specification ────────────────────────────────────────────────────────
# Each entry: (attribute_name, human_label, severity)

PATIENT_FIELDS = [
    ("sex", "Sex", REQUIRED),
    ("age", "Age", REQUIRED),
    ("dry_weight", "Dry Weight", REQUIRED),
    ("height", "Height", REQUIRED),
    ("diagnosis", "Diagnosis", REQUIRED),
    ("hd_wef_date", "HD Start Date (WEF)", REQUIRED),
    ("hd_frequency", "HD Frequency", REQUIRED),
    ("blood_group", "Blood Group", RECOMMENDED),
    ("healthcare_facility", "Healthcare Facility", RECOMMENDED),
    ("contact_no", "Contact Number", RECOMMENDED),
]

MONTHLY_FIELDS = [
    ("hb", "Hemoglobin (Hb)", REQUIRED),
    ("albumin", "Albumin", REQUIRED),
    ("calcium", "Calcium", REQUIRED),
    ("phosphorus", "Phosphorus", REQUIRED),
    ("serum_potassium", "Potassium", REQUIRED),
    ("single_pool_ktv", "Kt/V (single-pool)", REQUIRED),
    ("urr", "URR", RECOMMENDED),
    ("serum_sodium", "Sodium", RECOMMENDED),
    ("serum_bicarbonate", "Bicarbonate", RECOMMENDED),
    ("serum_creatinine", "Creatinine", RECOMMENDED),
    ("ipth", "iPTH", RECOMMENDED),
    ("serum_ferritin", "Ferritin", RECOMMENDED),
    ("tsat", "TSAT", RECOMMENDED),
    ("esa_type", "ESA Type", RECOMMENDED),
]

# ESA agents dosed via HIF-PHI (oral, not IU-based) — see dashboard_logic._resolve_epo_dose.
_HIF_PHI_AGENTS = {"desidustat", "roxadustat", "daprodustat", "vadadustat"}


def _check_esa_dosing(rec) -> list:
    """Cross-field check mirroring dashboard_logic._resolve_epo_dose().

    A patient recorded as on ESA therapy but with no dose value the app can
    resolve silently blocks ERI / ESA-hyporesponsiveness alerting for that
    month — the field-by-field check above can't see this because no single
    column is "the" dose field; it's whichever one matches esa_type.
    """
    esa = (rec.esa_type or "").strip().lower()
    if not esa:
        return []  # esa_type itself is flagged separately; patient may not be on ESA at all
    if esa in _HIF_PHI_AGENTS:
        if is_missing(rec.desidustat_dose):
            return [{"field": "desidustat_dose",
                     "label": "HIF-PHI Dose (blocks anemia monitoring)", "severity": REQUIRED}]
        return []
    if is_missing(rec.epo_weekly_units) and is_missing(rec.epo_mircera_dose):
        return [{"field": "epo_dose",
                 "label": "ESA Dose (blocks ERI calculation)", "severity": REQUIRED}]
    return []

# 1:1 clinical-profile tables. row_severity = severity assigned when the whole
# row is absent for a patient.
PROFILE_SECTIONS = [
    {
        "model": PatientComorbidities, "label": "Comorbidities", "icon": "medical_information",
        "row_severity": REQUIRED,
        "fields": [
            ("dm_status", "Diabetes Status", REQUIRED),
            ("htn_status", "Hypertension", REQUIRED),
            ("smoking_status", "Smoking Status", RECOMMENDED),
            ("charlson_comorbidity_index", "Charlson Index", RECOMMENDED),
            ("alcohol_consumption", "Alcohol Use", RECOMMENDED),
        ],
    },
    {
        "model": PatientRenalProfile, "label": "Renal Profile", "icon": "water_drop",
        "row_severity": REQUIRED,
        "fields": [
            ("primary_renal_disease", "Primary Renal Disease", REQUIRED),
            ("dialysis_modality", "Dialysis Modality", REQUIRED),
            ("date_esrd_diagnosis", "ESRD Diagnosis Date", RECOMMENDED),
            ("transplant_prospect", "Transplant Prospect", RECOMMENDED),
        ],
    },
    {
        "model": PatientViralMarkers, "label": "Viral Markers", "icon": "coronavirus",
        "row_severity": REQUIRED,
        "fields": [
            ("viral_hbsag", "HBsAg", REQUIRED),
            ("viral_anti_hcv", "Anti-HCV", REQUIRED),
            ("viral_hiv", "HIV", REQUIRED),
        ],
    },
    {
        "model": PatientVascularAccess, "label": "Vascular Access", "icon": "cable",
        "row_severity": REQUIRED,
        "fields": [
            ("access_type", "Access Type", REQUIRED),
            ("access_date", "Access Date", RECOMMENDED),
        ],
    },
    {
        "model": PatientCardiac, "label": "Cardiac", "icon": "cardiology",
        "row_severity": RECOMMENDED,
        "fields": [
            ("ejection_fraction", "Ejection Fraction", RECOMMENDED),
            ("echo_date", "Echo Date", RECOMMENDED),
        ],
    },
    {
        "model": PatientVaccination, "label": "Vaccination", "icon": "vaccines",
        "row_severity": RECOMMENDED,
        "fields": [
            ("hep_b_status", "Hep B Status", RECOMMENDED),
        ],
    },
]

# Column order for the cohort matrix (Monthly Labs / Session Records appended).
SECTION_ORDER = ["Demographics"] + [s["label"] for s in PROFILE_SECTIONS] + \
    ["Monthly Labs", "Session Records"]


def _check(row, fields):
    """Return [{field,label,severity}] for blank fields on a row."""
    out = []
    for attr, label, sev in fields:
        if is_missing(getattr(row, attr, None)):
            out.append({"field": attr, "label": label, "severity": sev})
    return out


def scan_patient(db: Session, patient: Patient, caches: dict | None = None) -> dict:
    """Detailed completeness breakdown for one patient, section by section.

    ``caches`` (optional) lets the cohort scan avoid per-patient queries by
    passing pre-loaded dicts: {"profiles": {label: {pid: row}},
    "latest_monthly": {pid: rec}, "session_pids": set, "outcomes": {pid: row}}.
    """
    caches = caches or {}
    sections = {}

    # Demographics (always present — it's the Patient row itself).
    sections["Demographics"] = {
        "row_present": True, "icon": "badge",
        "missing": _check(patient, PATIENT_FIELDS),
    }

    # 1:1 profile sections.
    for spec in PROFILE_SECTIONS:
        label = spec["label"]
        if "profiles" in caches:
            row = caches["profiles"].get(label, {}).get(patient.id)
        else:
            row = db.query(spec["model"]).filter(
                spec["model"].patient_id == patient.id).first()
        if row is None:
            sections[label] = {"row_present": False, "icon": spec["icon"],
                               "row_severity": spec["row_severity"], "missing": []}
        else:
            sections[label] = {"row_present": True, "icon": spec["icon"],
                               "missing": _check(row, spec["fields"])}

    # Latest monthly labs.
    if "latest_monthly" in caches:
        rec = caches["latest_monthly"].get(patient.id)
    else:
        rec = (db.query(MonthlyRecord)
               .filter(MonthlyRecord.patient_id == patient.id)
               .order_by(MonthlyRecord.record_month.desc()).first())
    if rec is None:
        sections["Monthly Labs"] = {"row_present": False, "icon": "science",
                                    "row_severity": REQUIRED, "missing": []}
    else:
        sections["Monthly Labs"] = {"row_present": True, "icon": "science",
                                    "latest_month": rec.record_month,
                                    "missing": _check(rec, MONTHLY_FIELDS) + _check_esa_dosing(rec)}

    # Session records presence.
    if "session_pids" in caches:
        has_sessions = patient.id in caches["session_pids"]
    else:
        has_sessions = db.query(SessionRecord.id).filter(
            SessionRecord.patient_id == patient.id).first() is not None
    if not has_sessions:
        sections["Session Records"] = {"row_present": False, "icon": "event_note",
                                       "row_severity": RECOMMENDED, "missing": []}

    req, rec_ct = _tally(sections)
    return {"id": patient.id, "name": patient.name, "hid_no": patient.hid_no,
            "sections": sections, "req_missing": req, "rec_missing": rec_ct}


def _tally(sections) -> tuple[int, int]:
    req = rec = 0
    for sec in sections.values():
        if sec.get("row_present") is False:
            if sec.get("row_severity") == REQUIRED:
                req += 1
            else:
                rec += 1
        for m in sec.get("missing", []):
            if m["severity"] == REQUIRED:
                req += 1
            else:
                rec += 1
    return req, rec


def scan_cohort(db: Session) -> dict:
    """Scan every active patient. Returns summary, per-patient rows, hot-spots
    and systemic gaps — everything the overview page needs."""
    patients = (db.query(Patient).filter(Patient.is_active == True)  # noqa: E712
                .order_by(Patient.name).all())
    total = len(patients)

    # Bulk-load to avoid N+1 queries.
    caches = {"profiles": {}, "latest_monthly": {}, "session_pids": set()}
    for spec in PROFILE_SECTIONS:
        caches["profiles"][spec["label"]] = {
            getattr(r, "patient_id"): r for r in db.query(spec["model"]).all()}
    for rec in (db.query(MonthlyRecord)
                .order_by(MonthlyRecord.record_month.asc()).all()):
        caches["latest_monthly"][rec.patient_id] = rec  # last wins = latest month
    caches["session_pids"] = {
        pid for (pid,) in db.query(SessionRecord.patient_id).distinct().all()}

    rows = [scan_patient(db, p, caches) for p in patients]

    # Cohort hot-spots + systemic (missing for ALL patients) detection.
    counts: dict[str, dict] = {}
    for e in rows:
        for label, sec in e["sections"].items():
            if sec.get("row_present") is False:
                key = f"{label} (whole section)"
                counts.setdefault(key, {"n": 0, "sev": sec.get("row_severity")})
                counts[key]["n"] += 1
            for m in sec.get("missing", []):
                key = f"{label} · {m['label']}"
                counts.setdefault(key, {"n": 0, "sev": m["severity"]})
                counts[key]["n"] += 1

    systemic, hotspots = [], []
    for key, v in counts.items():
        item = {"label": key, "n": v["n"], "severity": v["sev"], "total": total}
        if total and v["n"] == total:
            systemic.append(item)
        else:
            hotspots.append(item)
    hotspots.sort(key=lambda x: (-x["n"], x["label"]))
    systemic.sort(key=lambda x: x["label"])

    fully = sum(1 for e in rows if not e["req_missing"] and not e["rec_missing"])
    latest_month = None
    for e in rows:
        m = e["sections"].get("Monthly Labs", {}).get("latest_month")
        if m and (latest_month is None or m > latest_month):
            latest_month = m

    return {
        "total": total,
        "fully_complete": fully,
        "with_required": sum(1 for e in rows if e["req_missing"]),
        "with_recommended": sum(1 for e in rows if e["rec_missing"]),
        "latest_month": latest_month,
        "patients": sorted(rows, key=lambda e: (-e["req_missing"], -e["rec_missing"], e["name"])),
        "hotspots": hotspots,
        "systemic": systemic,
        "section_order": SECTION_ORDER,
    }
