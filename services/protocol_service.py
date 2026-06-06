"""
Bulk protocol helpers — surgical updates to MonthlyRecord that touch ONLY
the relevant columns, leaving all other monthly data intact.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from database import MonthlyRecord, Patient


def _current_month_str() -> str:
    today = datetime.utcnow()
    return f"{today.year}-{today.month:02d}"


def _to_date(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        return None


def get_active_patients_with_iron_status(db: Session) -> List[Dict[str, Any]]:
    """
    Return all active patients enriched with their latest monthly-record
    iron/Hb data and last IV iron entry (product, dose, date).
    Used to pre-populate the bulk protocol form.
    """
    patients = (
        db.query(Patient)
        .filter(Patient.is_active == True)
        .order_by(Patient.name)
        .all()
    )

    current_month = _current_month_str()

    rows = []
    for p in patients:
        # Most recent monthly record (any month)
        latest = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.patient_id == p.id)
            .order_by(MonthlyRecord.record_month.desc())
            .first()
        )

        # Current-month record (may not exist yet)
        current_rec = (
            db.query(MonthlyRecord)
            .filter(
                MonthlyRecord.patient_id == p.id,
                MonthlyRecord.record_month == current_month,
            )
            .first()
        )

        rows.append(
            {
                "id":             p.id,
                "name":           p.name,
                "hid_no":         p.hid_no,
                # Lab status for clinical decision at a glance
                "hb":             latest.hb             if latest else None,
                "serum_ferritin": latest.serum_ferritin  if latest else None,
                "tsat":           latest.tsat            if latest else None,
                "lab_month":      latest.record_month    if latest else None,
                # Pre-fill from CURRENT month if already entered, else last month
                "iv_iron_product": (
                    current_rec.iv_iron_product if current_rec and current_rec.iv_iron_product
                    else (latest.iv_iron_product if latest else "")
                ),
                "iv_iron_dose": (
                    current_rec.iv_iron_dose if current_rec and current_rec.iv_iron_dose
                    else (latest.iv_iron_dose if latest else None)
                ),
                "iv_iron_date": (
                    current_rec.iv_iron_date.isoformat() if current_rec and current_rec.iv_iron_date
                    else None
                ),
                "already_entered_this_month": bool(
                    current_rec and current_rec.iv_iron_product
                ),
            }
        )

    return rows


def bulk_save_iv_iron(
    db: Session,
    entries: List[Dict[str, Any]],
    record_month: Optional[str] = None,
) -> Dict[str, int]:
    """
    Surgically update (or create minimal) MonthlyRecord rows for the given
    patients, writing ONLY iv_iron_product, iv_iron_dose, iv_iron_date.

    entries: list of dicts with keys:
        patient_id   int
        product      str   e.g. "Ferric Carboxymaltose"
        dose         float e.g. 200.0
        date         str   ISO date  e.g. "2026-06-06"

    Returns {"saved": N, "skipped": M}
    """
    month_str = record_month or _current_month_str()
    saved = skipped = 0

    for entry in entries:
        pid = entry.get("patient_id")
        product = (entry.get("product") or "").strip()
        dose_raw = entry.get("dose")
        date_raw = entry.get("date")

        if not pid or not product:
            skipped += 1
            continue

        dose = float(dose_raw) if dose_raw not in (None, "", "None") else None
        iron_date = _to_date(date_raw)

        rec = (
            db.query(MonthlyRecord)
            .filter(
                MonthlyRecord.patient_id == pid,
                MonthlyRecord.record_month == month_str,
            )
            .first()
        )

        if rec:
            rec.iv_iron_product = product
            rec.iv_iron_dose    = dose
            rec.iv_iron_date    = iron_date
            rec.timestamp       = datetime.utcnow()
        else:
            # No monthly record yet — create a minimal one so the iron data
            # is captured without accidentally wiping real lab values.
            rec = MonthlyRecord(
                patient_id=pid,
                record_month=month_str,
                iv_iron_product=product,
                iv_iron_dose=dose,
                iv_iron_date=iron_date,
            )
            db.add(rec)

        saved += 1

    db.commit()
    return {"saved": saved, "skipped": skipped}
