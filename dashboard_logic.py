"""
dashboard_logic.py
==================
Core clinical calculation logic for the Hemodialysis Dashboard.
"""
from sqlalchemy.orm import Session
from database import Patient, MonthlyRecord
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def get_current_month_str() -> str:
    return datetime.now().strftime("%Y-%m")


def get_month_label(month_str: str) -> str:
    try:
        return datetime.strptime(month_str, "%Y-%m").strftime("%B")
    except (ValueError, TypeError):
        return month_str or ""


def _prev_month_str(month_str: str) -> str:
    try:
        dt = datetime.strptime(month_str, "%Y-%m")
        if dt.month == 1:
            return f"{dt.year - 1}-12"
        return f"{dt.year}-{dt.month - 1:02d}"
    except (ValueError, TypeError):
        return ""


def _make_metric() -> dict:
    return {"count": 0, "names": []}


def _corrected_calcium(calcium, albumin) -> float:
    if calcium is None:
        return None
    alb = albumin if albumin is not None else 4.0
    return round(calcium + 0.8 * (4.0 - alb), 2)


def _build_alerts(r: MonthlyRecord, corrected_ca) -> list:
    alerts = []
    if r.hb and r.hb < 10:
        alerts.append("Low Hb < 10")
    if r.albumin and r.albumin < 3.5:
        alerts.append("Low Albumin < 3.5")
    if corrected_ca and corrected_ca < 8.5:
        alerts.append("Low Ca < 8.5")
    if r.phosphorus and r.phosphorus > 5.5:
        alerts.append("High Phos > 5.5")
    if r.idwg and r.idwg > 2.5:
        alerts.append("High IDWG > 2.5 kg")
    if r.ipth and r.ipth > 300:
        alerts.append("iPTH > 300")
    if r.vit_d and r.vit_d < 20:
        alerts.append("Low Vit D < 20")
    if r.av_daily_protein and r.av_daily_protein < 1.0:
        alerts.append("Low Protein Intake")
    if (r.ast and r.ast > 40) or (r.alt and r.alt > 40):
        alerts.append("Elevated LFTs")
    if r.urr and r.urr < 65:
        alerts.append("Low URR (Intensify Dialysis)")
    return alerts


def get_patients_needing_alerts(db: Session, month_str: str) -> list:
    """Return list of {patient, record, alerts} for all patients with active alerts."""
    records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()
    patient_ids = [r.patient_id for r in records]
    patients = db.query(Patient).filter(
        Patient.id.in_(patient_ids),
        Patient.is_active == True
    ).all()
    patient_map = {p.id: p for p in patients}
    record_map = {r.patient_id: r for r in records}

    result = []
    for pid, r in record_map.items():
        p = patient_map.get(pid)
        if not p:
            continue
        corrected_ca = _corrected_calcium(r.calcium, r.albumin)
        alerts = _build_alerts(r, corrected_ca)
        if alerts:
            result.append({
                "patient": p,
                "record": {
                    "hb": r.hb,
                    "albumin": r.albumin,
                    "phosphorus": r.phosphorus,
                    "corrected_ca": corrected_ca,
                    "ipth": r.ipth,
                    "idwg": r.idwg,
                },
                "alerts": alerts,
            })
    return result


def compute_dashboard(db: Session, month_str: str = None) -> dict:
    if not month_str:
        month_str = get_current_month_str()

    prev_month = _prev_month_str(month_str)

    active_patients = db.query(Patient).filter(Patient.is_active == True).all()
    patient_map = {p.id: p for p in active_patients}

    curr_records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()
    prev_records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == prev_month).all()
    curr_map = {r.patient_id: r for r in curr_records}
    prev_map = {r.patient_id: r for r in prev_records}

    # Demographics
    total = len(active_patients)
    male = sum(1 for p in active_patients if (p.sex or "").strip() == "Male")
    female = sum(1 for p in active_patients if (p.sex or "").strip() == "Female")
    unknown_sex = total - male - female
    unknown_sex_names = [p.name for p in active_patients if (p.sex or "").strip() not in ("Male", "Female")]

    # Today's HD patients
    today_day = datetime.now().strftime("%a")  # Mon, Tue, Wed …
    todays_hd = _make_metric()
    for p in active_patients:
        slots = " ".join(filter(None, [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3]))
        if today_day.lower() in slots.lower():
            todays_hd["count"] += 1
            todays_hd["names"].append(p.name)

    # Clinical buckets
    non_avf = {"count": 0, "names": [], "types": {}}
    high_idwg = _make_metric()
    low_albumin = _make_metric()
    low_calcium = _make_metric()
    high_phosphorus = _make_metric()
    iv_iron = _make_metric()
    hb_drop_alert = _make_metric()
    dialysis_intensification = _make_metric()
    high_ipth = _make_metric()
    low_vit_d = _make_metric()
    low_protein = _make_metric()
    elevated_liver = _make_metric()

    trend_hb, trend_albumin, trend_phosphorus = [], [], []
    patient_rows = []

    for pid, p in patient_map.items():
        r = curr_map.get(pid)
        has_record = r is not None
        corrected_ca = _corrected_calcium(r.calcium if r else None, r.albumin if r else None)
        alerts = _build_alerts(r, corrected_ca) if r else []

        patient_rows.append({
            "id": p.id,
            "name": p.name,
            "hid": p.hid_no,
            "access": (r.access_type if r else None) or p.access_type,
            "idwg": r.idwg if r else None,
            "hb": r.hb if r else None,
            "ferritin": r.serum_ferritin if r else None,
            "tsat": r.tsat if r else None,
            "corrected_ca": corrected_ca,
            "phosphorus": r.phosphorus if r else None,
            "albumin": r.albumin if r else None,
            "ipth": r.ipth if r else None,
            "vit_d": r.vit_d if r else None,
            "protein": r.av_daily_protein if r else None,
            "alerts": alerts,
            "has_record": has_record,
        })

        if not r:
            continue

        name = p.name
        prev_r = prev_map.get(pid)

        # Non-AVF access
        raw_access = (r.access_type or p.access_type or "").strip()
        access = "Permacath" if raw_access in ("P/Cath", "P-Cath", "Permacath", "PCATH") else raw_access
        if access and access.upper() != "AVF":
            non_avf["count"] += 1
            non_avf["names"].append(name)
            if access not in non_avf["types"]:
                non_avf["types"][access] = {"count": 0, "names": []}
            non_avf["types"][access]["count"] += 1
            non_avf["types"][access]["names"].append(name)

        if r.idwg and r.idwg > 2.5:
            high_idwg["count"] += 1; high_idwg["names"].append(name)

        if r.albumin and r.albumin < 2.0:
            low_albumin["count"] += 1; low_albumin["names"].append(name)

        if corrected_ca and corrected_ca < 8.5:
            low_calcium["count"] += 1; low_calcium["names"].append(name)

        if r.phosphorus and r.phosphorus > 5.5:
            high_phosphorus["count"] += 1; high_phosphorus["names"].append(name)

        if (r.tsat and r.tsat < 20) or (r.serum_ferritin and r.serum_ferritin < 200):
            iv_iron["count"] += 1; iv_iron["names"].append(name)

        if r.hb and prev_r and prev_r.hb and (prev_r.hb - r.hb) > 1.5:
            hb_drop_alert["count"] += 1; hb_drop_alert["names"].append(name)

        if r.urr and r.urr < 65:
            dialysis_intensification["count"] += 1; dialysis_intensification["names"].append(name)

        if r.ipth and r.ipth > 300:
            high_ipth["count"] += 1; high_ipth["names"].append(name)

        if r.vit_d and r.vit_d < 20:
            low_vit_d["count"] += 1; low_vit_d["names"].append(name)

        if r.av_daily_protein and r.av_daily_protein < 1.0:
            low_protein["count"] += 1; low_protein["names"].append(name)

        if (r.ast and r.ast > 40) or (r.alt and r.alt > 40):
            elevated_liver["count"] += 1; elevated_liver["names"].append(name)

        # Trend data (for charts)
        if r.hb is not None:
            trend_hb.append({"patient": name, "current": r.hb,
                              "previous": prev_r.hb if prev_r else None})
        if r.albumin is not None:
            trend_albumin.append({"patient": name, "current": r.albumin,
                                   "previous": prev_r.albumin if prev_r else None})
        if r.phosphorus is not None:
            trend_phosphorus.append({"patient": name, "current": r.phosphorus,
                                      "previous": prev_r.phosphorus if prev_r else None})

    # Sort worst-first for chart carousels
    trend_hb.sort(key=lambda x: x["current"] or 99)
    trend_albumin.sort(key=lambda x: x["current"] or 99)
    trend_phosphorus.sort(key=lambda x: -(x["current"] or 0))
    patient_rows.sort(key=lambda x: x["name"])

    return {
        "metrics": {
            "total": total,
            "male": male,
            "female": female,
            "unknown_sex": unknown_sex,
            "unknown_sex_names": unknown_sex_names,
            "non_avf": non_avf,
            "high_idwg": high_idwg,
            "low_albumin": low_albumin,
            "low_calcium": low_calcium,
            "high_phosphorus": high_phosphorus,
            "iv_iron": iv_iron,
            "hb_drop_alert": hb_drop_alert,
            "dialysis_intensification": dialysis_intensification,
            "high_ipth": high_ipth,
            "low_vit_d": low_vit_d,
            "low_protein": low_protein,
            "elevated_liver": elevated_liver,
            "todays_hd": todays_hd,
            "trend_hb": trend_hb,
            "trend_albumin": trend_albumin,
            "trend_phosphorus": trend_phosphorus,
        },
        "patient_rows": patient_rows,
        "month_label": get_month_label(month_str),
        "prev_month_label": get_month_label(prev_month),
    }
