"""
services/interim_hb_service.py
===============================
Merge InterimLabRecord Hb entries into the monthly record sequence so the
two-compartment ODE can fit on all available Hb observations, not just end-of-month ones.

Design:
  • Monthly records carry the full clinical feature set (ESA, iron, labs, weight).
  • Interim entries carry only Hb (and exact date); all other fields are forward-filled
    from the most-recent preceding monthly record so the ODE and ML feature extractor
    receive consistent dicts regardless of entry type.
  • step_days is computed from the actual calendar gap between consecutive observations.
    The variable-step ODE in ml_acm_ode.py scales all monthly rates by step_days/30.

Public API:
    get_interim_hbs(db, patient_id)               → list of interim Hb dicts (newest-first)
    merge_hb_sequence(monthly_dicts, interim_hbs)  → merged list (newest-first)
"""
from __future__ import annotations

import logging
from datetime import date as _date
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def get_interim_hbs(db, patient_id: int, limit: int = 54) -> List[Dict]:
    """
    Query InterimLabRecord where parameter='hb' for this patient and return
    a list of minimal dicts sorted newest-first.

    Returns dicts with: hb, lab_date (date), record_date (str YYYY-MM-DD),
    is_interim (True), step_days (placeholder 30.0 — overwritten by merge).
    """
    from database import InterimLabRecord

    rows = (
        db.query(InterimLabRecord)
        .filter(
            InterimLabRecord.patient_id == patient_id,
            InterimLabRecord.parameter == "hb",
        )
        .order_by(InterimLabRecord.lab_date.desc())
        .limit(limit)
        .all()
    )
    result = []
    for row in rows:
        if row.value is None:
            continue
        result.append({
            "hb":          float(row.value),
            "lab_date":    row.lab_date,
            "record_date": str(row.lab_date),
            "record_month": str(row.lab_date)[:7],
            "is_interim":  True,
            "step_days":   30.0,   # overwritten by merge_hb_sequence
            "notes":       row.notes or "",
        })
    return result   # newest-first


def _record_date(rec: Dict) -> Optional[_date]:
    """Extract a calendar date from either a monthly or interim record dict."""
    if rec.get("lab_date") and isinstance(rec["lab_date"], _date):
        return rec["lab_date"]
    rd = rec.get("record_date")
    if rd:
        try:
            return _date.fromisoformat(str(rd)[:10])
        except ValueError:
            pass
    ym = rec.get("record_month") or rec.get("record_month")
    if ym and len(ym) >= 7:
        try:
            year, month = int(ym[:4]), int(ym[5:7])
            # Use day 28 — safe for all months, approximates end-of-month labs
            return _date(year, month, 28)
        except (ValueError, OverflowError):
            pass
    return None


def merge_hb_sequence(
    monthly_dicts: List[Dict],
    interim_hbs:   List[Dict],
) -> List[Dict]:
    """
    Merge monthly records and interim Hb entries into one chronological sequence.

    Args:
        monthly_dicts: newest-first list of full clinical record dicts
                       (output of _row_to_dict — must include record_month).
        interim_hbs:   newest-first list of interim Hb dicts
                       (output of get_interim_hbs).

    Returns:
        Merged list newest-first.  Each dict has:
          • All fields from the nearest preceding monthly record (forward-filled).
          • hb: overridden by the interim value when is_interim=True.
          • record_date: ISO date string for the observation.
          • step_days: days from the previous (older) observation — used by the
            variable-step ODE to scale monthly rates correctly.
          • is_interim: bool distinguishing interim vs. monthly entries.

    If interim_hbs is empty the result is identical to monthly_dicts (with
    step_days=30.0 added, computed from adjacent record_month strings).
    """
    if not monthly_dicts and not interim_hbs:
        return []

    # ── Build (date, dict) pairs for all entries ──────────────────────────────
    pairs: List[tuple] = []   # (date, dict, is_interim)

    for rec in monthly_dicts:
        d = _record_date(rec)
        if d is None:
            continue
        entry = dict(rec)
        entry["record_date"] = str(d)
        entry.setdefault("is_interim", False)
        pairs.append((d, entry, False))

    for rec in interim_hbs:
        d = _record_date(rec)
        if d is None:
            continue
        entry = dict(rec)
        entry["record_date"] = str(d)
        entry["is_interim"] = True
        pairs.append((d, entry, True))

    if not pairs:
        return monthly_dicts   # fallback: return originals unchanged

    # ── Sort oldest-first for step_days computation ───────────────────────────
    pairs.sort(key=lambda x: x[0])

    # ── Forward-fill clinical features onto interim entries ───────────────────
    last_monthly: Dict = {}
    merged_oldest_first: List[Dict] = []

    for d, entry, is_interim in pairs:
        if not is_interim:
            last_monthly = entry          # update anchor
            merged_oldest_first.append(entry)
        else:
            # Inherit all clinical fields from the most-recent preceding monthly
            # record.  The interim dict's own fields (hb, record_date, is_interim,
            # step_days, notes) override the monthly anchor where present.
            filled = {**last_monthly, **entry}
            # Never let interim hb be overwritten by the monthly anchor's hb —
            # the interim value is the reason this entry exists.
            filled["hb"] = entry["hb"]
            filled["is_interim"] = True
            merged_oldest_first.append(filled)

    # ── Compute step_days ─────────────────────────────────────────────────────
    for i, entry in enumerate(merged_oldest_first):
        if i == 0:
            entry["step_days"] = 30.0   # first observation: assume one month of run-in
        else:
            prev_d = _record_date(merged_oldest_first[i - 1])
            curr_d = _record_date(entry)
            if prev_d is not None and curr_d is not None:
                delta = (curr_d - prev_d).days
                entry["step_days"] = float(max(1, delta))
            else:
                entry["step_days"] = 30.0

    # Return newest-first (standard for ACM serving and _build_training_set)
    return list(reversed(merged_oldest_first))
