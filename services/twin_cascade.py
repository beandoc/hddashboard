"""
services/twin_cascade.py
========================
Cross-domain cascade summary: propagates prescription changes across all five
Digital Twin domains and surfaces clinically meaningful interdependency messages.
"""
from __future__ import annotations

from typing import Dict, List

# ── Cross-domain cascade summary ──────────────────────────────────────────────


def _cascade_summary(scenario: dict, baseline: dict, results: dict) -> List[dict]:
    """
    Generate a human-readable list of cascade effects for the UI.
    Each item: {domain, direction, message, delta}.
    """
    items = []
    s = scenario or {}

    def _changed(key, default_val, base_keys=None):
        if key not in s:
            return False
        if base_keys is None:
            base_keys = [key]
        base_val = None
        for bk in base_keys:
            if bk in baseline and baseline[bk] is not None:
                base_val = baseline[bk]
                break
        if base_val is None:
            base_val = default_val
        try:
            return abs(float(s[key]) - float(base_val)) > 1e-7
        except (ValueError, TypeError):
            return s[key] != base_val

    session_changed = _changed("session_h", 4.0, ["session_duration_h", "session_h"])
    qb_changed      = _changed("qb_ml_min", 300.0, ["qb_ml_min", "qb"])
    uf_changed      = _changed("uf_rate_ml_kg_h", 10.0, ["uf_rate_ml_kg_h", "uf_rate"]) or _changed("uf_volume_L", 2.5, ["uf_volume_L", "uf_volume"])
    pbe_changed     = _changed("p_binder_pbe", 3.0, ["p_binder_pbe", "pbe"])
    temp_changed    = _changed("dialysate_temp", 36.5, ["dialysate_temp", "temp"])
    na_changed      = _changed("dialysate_sodium", 138.0, ["dialysate_sodium", "sodium"])

    ktv  = results.get("ktv_extended", {})
    phos = results.get("phosphate", {})
    idh  = results.get("idh_sim", {})

    if session_changed:
        new_h = _safe_float(s.get("session_h"), 4.0)
        old_h = _safe_float(baseline.get("session_h") or baseline.get("session_duration_h"), 4.0)
        dh = new_h - old_h
        d_ktv = ktv.get("delta_sp_ktv") or 0
        items.append({
            "domain": "Session duration",
            "direction": "up" if dh > 0 else "down",
            "message": (
                f"Session {new_h:.2g}h (+{dh:.2g}h) → "
                f"spKt/V {'+' if d_ktv >= 0 else ''}{d_ktv:.2f} · "
                f"phosphate removal {'↑' if dh > 0 else '↓'} · "
                f"effective UF rate {'↓' if dh > 0 else '↑'} (same fluid, more time)"
            ),
        })

    if qb_changed:
        new_qb = _safe_float(s.get("qb_ml_min"), 300.0)
        old_qb = _safe_float(baseline.get("qb_ml_min"), 300.0)
        d_kd = ktv.get("delta_kd") or 0
        items.append({
            "domain": "Blood flow (Qb)",
            "direction": "up" if new_qb > old_qb else "down",
            "message": (
                f"Qb {new_qb:.0f} mL/min → dialyzer Kd {'+' if d_kd >= 0 else ''}{d_kd:.0f} mL/min · "
                f"urea clearance {'↑' if new_qb > old_qb else '↓'} · "
                f"phosphate removal {'↑' if new_qb > old_qb else '↓'}"
            ),
        })

    if uf_changed:
        rate = _safe_float(s.get("uf_rate_ml_kg_h"), 10.0)
        d_idh = idh.get("delta_risk_pct") or 0
        items.append({
            "domain": "UF rate",
            "direction": "up" if d_idh > 0 else "down",
            "message": (
                f"UF {rate:.1f} mL/kg/h → IDH risk {'+' if d_idh >= 0 else ''}{d_idh:.1f}% · "
                f"convective phosphate removal {'↑' if rate > 10 else '↓'}"
            ),
        })

    if pbe_changed:
        d_p = phos.get("delta_p") or 0
        items.append({
            "domain": "Phosphate binder",
            "direction": "down",
            "message": (
                f"PBE {s.get('p_binder_pbe', '?')} units/day → "
                f"pre-P {'↑' if d_p > 0 else '↓'} {abs(d_p):.2f} mg/dL "
                f"({'above' if (phos.get('scenario_p') or 0) > 5.5 else 'below' if (phos.get('scenario_p') or 0) < 3.5 else 'within'} target)"
            ),
        })

    if temp_changed:
        t = _safe_float(s.get("dialysate_temp"), 36.5)
        d_idh = idh.get("delta_risk_pct") or 0
        items.append({
            "domain": "Dialysate temperature",
            "direction": "down" if t < 36.5 else "up",
            "message": (
                f"Dialysate {t}°C → IDH risk {'+' if d_idh >= 0 else ''}{d_idh:.1f}% "
                f"({'cooler dialysate reduces IDH risk' if t < 36.5 else 'warmer dialysate increases IDH risk'})"
            ),
        })

    if na_changed:
        na = _safe_float(s.get("dialysate_sodium"), 138.0)
        items.append({
            "domain": "Dialysate sodium",
            "direction": "up" if na > 138 else "down",
            "message": (
                f"Dialysate Na {na:.0f} mEq/L — "
                f"{'higher Na reduces osmotic gradient → less IDH but may worsen thirst/IDWG' if na > 138 else 'lower Na increases fluid shift → watch for cramps/IDH'}"
            ),
        })

    if not items:
        items.append({
            "domain": "No changes",
            "direction": "neutral",
            "message": "No prescription parameters changed from baseline.",
        })

    return items


