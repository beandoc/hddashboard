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

    # Drug-change groups: (modification_date_field, dose_fields_to_rewind_on_early_base)
    _MOD_GROUPS = [
        ("esa_modified_at",              ["epo_mircera_dose", "epo_weekly_units", "esa_type", "desidustat_dose"]),
        ("desidustat_modified_at",       ["desidustat_dose"]),
        ("phosphate_binder_modified_at", ["phosphate_binder_dose_mg", "phosphate_binder_type",
                                          "phosphate_binder_freq", "phosphate_binder_details"]),
    ]

    for idx, rec in enumerate(monthly_dicts):
        d = _record_date(rec)
        if d is None:
            continue
        entry = dict(rec)
        entry["record_date"] = str(d)
        entry.setdefault("is_interim", False)

        prior_rec = monthly_dicts[idx + 1] if idx + 1 < len(monthly_dicts) else None

        for mod_field, dose_fields in _MOD_GROUPS:
            mod_val = rec.get(mod_field)
            if not mod_val:
                continue
            try:
                mod_date = _date.fromisoformat(str(mod_val)[:10])
            except ValueError:
                continue

            # Synthetic entry starts as a copy of the current monthly record (new doses).
            synthetic = dict(rec)
            synthetic["record_date"] = str(mod_date)
            synthetic["is_interim"] = True
            synthetic["hb"] = None   # no Hb measurement at a dose-change event

            # For any OTHER drug group whose change date is AFTER this synthetic
            # entry's date, that drug's dose hadn't changed yet — rewind those
            # fields to the prior month's values in this synthetic entry.
            for other_mod_field, other_dose_fields in _MOD_GROUPS:
                if other_mod_field == mod_field:
                    continue
                other_mod_val = rec.get(other_mod_field)
                if other_mod_val:
                    try:
                        other_mod_date = _date.fromisoformat(str(other_mod_val)[:10])
                        if other_mod_date > mod_date:
                            for field in other_dose_fields:
                                synthetic[field] = prior_rec.get(field) if prior_rec else None
                    except ValueError:
                        pass

            if d < mod_date:
                # Monthly anchor pre-dates the change: patient was on the OLD dose
                # from month start until mod_date.  Rewind those fields in the anchor.
                for field in dose_fields:
                    entry[field] = prior_rec.get(field) if prior_rec else None

            pairs.append((mod_date, synthetic, True))

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
            # Real interim labs carry their own Hb; synthetic dose-change entries
            # carry hb=None — forward-fill from the most-recent monthly anchor.
            if entry.get("hb") is not None:
                filled["hb"] = entry["hb"]
            else:
                filled["hb"] = last_monthly.get("hb")

            # Synthetic dose-change entries explicitly carry their new dose values —
            # enforce them over whatever the monthly anchor had for all three drug groups.
            _DOSE_FIELDS = [
                "epo_mircera_dose", "epo_weekly_units", "esa_type", "desidustat_dose",
                "phosphate_binder_dose_mg", "phosphate_binder_type",
                "phosphate_binder_freq", "phosphate_binder_details",
            ]
            for field in _DOSE_FIELDS:
                if field in entry and entry[field] is not None:
                    filled[field] = entry[field]

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
