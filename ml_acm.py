"""
ml_acm.py
=========
Anemia Control Model (ACM) for hemodialysis patients.

Implements ML-driven closed-loop anemia management per the architecture in
Cheungpasitporn et al. CKJ 2026 (Fig. 4):

  Patient Data Ingestion → ML Decision Engine → Clinical Oversight →
  Protocol Execution → Feedback & Learning → Audit Dashboard

Full clinical feature set (aligned with published ACM implementations):

  Hb history (120-day window):
    hb_current, delta_hb_1mo, delta_hb_3mo, hb_min_120d, hb_max_120d,
    hb_mean_120d, hb_sd_120d, hb_trend_slope

  Iron panel:
    serum_ferritin, tsat

  Biochemistry:
    albumin, calcium, crp, wbc_count (leukocytes),
    mch, mcv, serum_potassium, phosphorus, serum_sodium,
    overhydration_proxy (IDWG as fraction of dry weight)

  HD treatment data (140-day window):
    single_pool_ktv, pre_dialysis_weight, target_dry_weight,
    epo_weekly_iu_sc (normalized), esa_dose_140d_mean, n_esa_doses_140d,
    iv_iron_dose_140d_total, n_iron_doses_140d

  Demographics:
    age, sex_f (binary), height_m (for BSA/dose normalisation)

  Transfusion history (120-day window):
    transfusion_units_120d

Model: Ridge regression (cross-patient population model) retrained weekly.
Recommendation: KDIGO 2012 §3.4 / KDOQI 2019 anemia guideline-aligned rules.
Override logging: every clinician decision feeds back via ClinicalOverrideLog.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Optional imports ──────────────────────────────────────────────────────────

try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False

try:
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.model_selection import cross_val_predict, KFold
    from sklearn.metrics import mean_absolute_error, r2_score
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

try:
    from sqlalchemy.orm import Session
    _SQLALCHEMY_AVAILABLE = True
except ImportError:
    _SQLALCHEMY_AVAILABLE = False

from ml_esa import _resolve_weekly_iu_sc, normalize_epo_dose, pk_correction_factor

# ── Clinical constants (KDIGO 2012 / KDOQI 2019) ─────────────────────────────

HB_TARGET_LOW  = 10.0   # g/dL — lower bound of KDIGO target range
HB_TARGET_HIGH = 11.5   # g/dL — upper bound (avoid > 12.0)
HB_CEILING     = 13.0   # g/dL — hold ESA unconditionally above this
HB_FLOOR       = 8.0    # g/dL — transfusion consideration threshold

FERRITIN_REPLETE   = 200   # µg/L  — adequate storage
FERRITIN_MAX       = 800   # µg/L  — do not add iron above this
TSAT_TARGET_LOW    = 20    # %     — iron-deficient below
TSAT_TARGET_HIGH   = 30    # %     — target range upper
TSAT_CEILING       = 50    # %     — hold iron above this

ESA_ADJUST_STEP    = 0.25  # ±25% per adjustment cycle (KDIGO recommendation)
ESA_MAX_INCREASE   = 0.50  # never more than +50% in one step
ESA_MIN_DOSE_IU    = 1000  # SC IU/week minimum meaningful dose

MODEL_PATH = os.path.join("models", "acm_residual_mlp.pkl")  # now stores residual MLP

# ── ACM feature names — MUST stay in sync between train/inference ─────────────
# Full feature set aligned with published ACM implementations (Fresenius / Barbieri 2016).
# All values are median-imputed during training; never drop a record for missing features.

ACM_FEATURE_NAMES = [
    # ── Hb history (120-day window) ──────────────────────────────────────────
    "hb_current",        #  0  latest Hb g/dL
    "delta_hb_1mo",      #  1  Hb Δ vs 1 month ago
    "delta_hb_3mo",      #  2  Hb Δ vs 3 months ago (momentum)
    "hb_min_120d",       #  3  minimum Hb in 120-day window
    "hb_max_120d",       #  4  maximum Hb in 120-day window
    "hb_mean_120d",      #  5  mean Hb in 120-day window
    "hb_sd_120d",        #  6  Hb SD (variability — high SD → harder to control)
    "hb_trend_slope",    #  7  OLS slope of Hb over past 4 months (g/dL per month)
    # ── Iron panel ───────────────────────────────────────────────────────────
    "ferritin",          #  8  serum ferritin µg/L
    "tsat",              #  9  transferrin saturation %
    # ── Extended biochemistry ─────────────────────────────────────────────────
    "albumin",           # 10  g/dL
    "calcium",           # 11  mg/dL (mineral metabolism)
    "crp",               # 12  C-reactive protein mg/L (inflammation marker)
    "wbc",               # 13  WBC ×10³/µL (leukocytes — infection/inflammation proxy)
    # mch/mcv removed: no DB columns exist; getattr always returned None → always NaN.
    "potassium",         # 14  serum K mEq/L
    "phosphorus",        # 15  serum phosphate mg/dL
    "sodium",            # 16  serum Na mEq/L
    "overhydration",     # 17  IDWG / dry weight (fraction — volume overload proxy)
    # ── HD treatment history ─────────────────────────────────────────────────
    "ktv",               # 18  single-pool Kt/V (adequacy)
    "pre_weight",        # 19  pre-dialysis weight kg
    "dry_weight",        # 20  target dry weight kg
    "epo_iu_norm",       # 21  weekly SC IU / dry_weight (IU/kg/week)
    "esa_dose_140d_mean",# 22  mean weekly SC IU over 140-day window
    "n_esa_doses_140d",  # 23  number of ESA administrations in 140-day window
    "iv_iron_140d_total",# 24  total IV iron dose mg in 140-day window
    "n_iron_doses_140d", # 25  number of IV iron administrations in 140-day window
    # ── Demographics ─────────────────────────────────────────────────────────
    "age",               # 26  years
    "sex_f",             # 27  1 = female, 0 = male
    "height_m",          # 28  metres (for BSA-adjusted dose normalisation)
    # ── Transfusion history (120-day window) ─────────────────────────────────
    "transfusion_120d",  # 29  PRBC units transfused in past 120 days
    # ── Erythropoiesis marker ─────────────────────────────────────────────────
    "reticulocyte_pct",  # 30  reticulocyte % — partial observation of ODE R state
    # ── Hepcidin proxy ───────────────────────────────────────────────────────
    "hepcidin_proxy",    # 31  1 = high ferritin (>500) + CRP (>10) + low TSAT (<20)
    #                          strongest single ESA-resistance predictor; free from existing labs
    # ── ESA pharmacokinetics ─────────────────────────────────────────────────
    "epo_pk_factor",     # 32  PK AUC correction vs weekly-epoetin ref (1.0=epo, ~5.45=Mircera)
    # ── SOTA extensions (appended; all optional / median-imputed) ─────────────
    # Indices ≥33 are appended so existing feature positions 0–32 stay stable and
    # older saved models keep predicting on the unchanged prefix.
    "eri",               # 33  ESA Resistance Index (weekly IU/kg per g/dL Hb)
    "il6",               # 34  interleukin-6 pg/mL (rarely collected → usually imputed)
    "tnf_alpha",         # 35  TNF-α pg/mL (rarely collected → usually imputed)
    "mis_score",         # 36  Malnutrition-Inflammation Score
    "hospitalization_120d", # 37  count of hospitalized months in 120-day window
]

# ── Singleton model store ─────────────────────────────────────────────────────

_acm_pipeline: Optional[object] = None
_acm_trained_at: Optional[str] = None
_acm_metrics: Dict = {}

# ── Feature extraction ────────────────────────────────────────────────────────


def _to_float(v, default: float = float("nan")) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _hb_stats(records: List[Dict]) -> Dict:
    """Compute Hb summary statistics across the most-recent 4 records (≈120 days).
    A missing month silently shrinks the effective window; callers should ensure
    records are complete before interpreting the stats as a true 120-day window."""
    hb_vals = [_to_float(r.get("hb")) for r in records[:4] if not math.isnan(_to_float(r.get("hb")))]
    if not hb_vals:
        nan = float("nan")
        return {"min": nan, "max": nan, "mean": nan, "sd": nan, "slope": nan}
    slope = float("nan")
    if len(hb_vals) >= 2:
        x = np.arange(len(hb_vals), dtype=float)
        try:
            slope = float(np.polyfit(x, hb_vals, 1)[0])
        except Exception:
            pass
    return {
        "min":   float(np.min(hb_vals)),
        "max":   float(np.max(hb_vals)),
        "mean":  float(np.mean(hb_vals)),
        "sd":    float(np.std(hb_vals)) if len(hb_vals) > 1 else 0.0,
        "slope": slope,
    }


def _esa_history(records: List[Dict]) -> Dict:
    """Aggregate ESA and IV iron data across the most-recent 5 records (≈140 days).
    A missing month shrinks the effective window; callers should note this is a
    record-count window, not a guaranteed calendar-day window."""
    esa_doses, iron_doses = [], []
    for r in records[:5]:
        iu = _resolve_weekly_iu_sc(r)
        if iu is not None:
            esa_doses.append(iu)
        iv = _to_float(r.get("iv_iron_dose"), default=float("nan"))
        if not math.isnan(iv):
            iron_doses.append(iv)
    return {
        "esa_mean":        float(np.mean(esa_doses)) if esa_doses else float("nan"),
        "n_esa":           len(esa_doses),
        "iron_total":      float(sum(iron_doses)) if iron_doses else 0.0,
        "n_iron":          len(iron_doses),
    }


def _parse_record_date(rec: Dict) -> Optional[datetime.date]:
    from datetime import date
    if rec.get("lab_date"):
        ld = rec["lab_date"]
        if isinstance(ld, date):
            return ld
        if isinstance(ld, str):
            try:
                return date.fromisoformat(ld[:10])
            except ValueError:
                pass
    rd = rec.get("record_date")
    if rd:
        try:
            return date.fromisoformat(str(rd)[:10])
        except ValueError:
            pass
    ym = rec.get("record_month")
    if ym and len(ym) >= 7:
        try:
            year, month = int(ym[:4]), int(ym[5:7])
            # Use day 28 — safe for all months
            return date(year, month, 28)
        except (ValueError, OverflowError):
            pass
    return None


def _extract_acm_features(records: List[Dict], patient_meta: Optional[Dict] = None) -> Optional[np.ndarray]:
    """
    Extract the full ACM feature vector (len == len(ACM_FEATURE_NAMES)) from
    newest-first monthly record dicts. Returns None only if the latest record has
    no Hb at all. All other missing values are encoded as NaN and median-imputed
    in the pipeline. Feature positions 0–32 are stable; SOTA extensions are
    appended at indices ≥33 so previously-trained residual models keep predicting
    on the unchanged prefix until retrained.
    """
    if not records:
        return None

    rec = records[0]
    hb = _to_float(rec.get("hb"))
    if math.isnan(hb):
        return None

    date0 = _parse_record_date(rec)

    # ── Time-aware sliding window selection ──────────────────────────────────
    if date0 is not None:
        records_120d = []
        records_140d = []
        for r_other in records:
            d_other = _parse_record_date(r_other)
            if d_other is None:
                continue
            delta_days = (date0 - d_other).days
            if 0 <= delta_days <= 120:
                records_120d.append(r_other)
            if 0 <= delta_days <= 140:
                records_140d.append(r_other)

        # 1-month and 3-month lookbacks (find records closest to 30 and 90 days ago)
        hb_1mo = float("nan")
        hb_3mo = float("nan")
        best_diff_1mo = float("inf")
        best_diff_3mo = float("inf")
        for r_other in records[1:]:
            d_other = _parse_record_date(r_other)
            if d_other is None:
                continue
            delta_days = (date0 - d_other).days
            if 15 <= delta_days <= 45:
                diff = abs(delta_days - 30)
                if diff < best_diff_1mo:
                    val = _to_float(r_other.get("hb"))
                    if not math.isnan(val):
                        hb_1mo = val
                        best_diff_1mo = diff
            elif 60 <= delta_days <= 120:
                diff = abs(delta_days - 90)
                if diff < best_diff_3mo:
                    val = _to_float(r_other.get("hb"))
                    if not math.isnan(val):
                        hb_3mo = val
                        best_diff_3mo = diff
    else:
        records_120d = records[:4]
        records_140d = records[:5]
        hb_1mo = _to_float(records[1].get("hb")) if len(records) > 1 else float("nan")
        hb_3mo = _to_float(records[3].get("hb")) if len(records) > 3 else float("nan")

    delta_1 = (hb - hb_1mo) if not math.isnan(hb_1mo) else float("nan")
    delta_3 = (hb - hb_3mo) if not math.isnan(hb_3mo) else float("nan")
    hb_stat = _hb_stats(records_120d)

    # Iron
    ferritin = _to_float(rec.get("serum_ferritin"))
    tsat     = _to_float(rec.get("tsat"))

    # Extended biochemistry
    albumin   = _to_float(rec.get("albumin"))
    calcium   = _to_float(rec.get("calcium"))
    crp       = _to_float(rec.get("crp"), default=0.0)
    wbc       = _to_float(rec.get("wbc_count"))
    potassium = _to_float(rec.get("serum_potassium"))
    phosphorus= _to_float(rec.get("phosphorus"))
    sodium    = _to_float(rec.get("serum_sodium"))

    dry_wt    = _to_float(rec.get("target_dry_weight"))
    pre_wt    = _to_float(rec.get("last_prehd_weight") or rec.get("weight"))
    idwg      = _to_float(rec.get("idwg"))
    overhydration = (idwg / dry_wt) if (not math.isnan(idwg) and not math.isnan(dry_wt) and dry_wt > 0) else float("nan")

    # HD treatment
    ktv = _to_float(rec.get("single_pool_ktv"))
    iu_sc    = _resolve_weekly_iu_sc(rec)
    epo_norm = (iu_sc / dry_wt) if (iu_sc is not None and not math.isnan(dry_wt) and dry_wt > 0) else float("nan")
    esa_hist = _esa_history(records_140d)

    # Demographics — from patient_meta dict if provided
    pm       = patient_meta or {}
    age      = _to_float(pm.get("age"))
    sex_f    = float(1 if str(pm.get("sex", "")).lower() in ("f", "female") else 0)
    height_m = _to_float(pm.get("height")) / 100.0 if pm.get("height") else float("nan")

    # Transfusion history (120-day window, ≈4 months)
    transfusion_120d = sum(
        (_to_float(r.get("transfusion_units"), default=0.0) or 0.0)
        for r in records_120d
    )

    # Reticulocyte % — most-recent value; NaN when lab not ordered
    reticulocyte_pct = _to_float(records[0].get("reticulocyte_count"))

    # Hepcidin proxy — functional iron deficiency in inflammatory state.
    # All three criteria must be non-missing; any missing lab → 0 (under-flag
    # rather than NaN, since the ESA-resistance flag is additive, not required).
    _ferritin_ok  = not math.isnan(ferritin)  and ferritin > 500.0
    _crp_ok       = not math.isnan(crp)       and crp      > 10.0
    _tsat_ok      = not math.isnan(tsat)      and tsat     < 20.0
    hepcidin_proxy = float(_ferritin_ok and _crp_ok and _tsat_ok)

    # ESA PK correction factor — drug/schedule-specific AUC vs weekly-epoetin ref.
    # Parsed from the dose string in the most-recent record; defaults to 1.0 when
    # unparseable (equivalent to assuming weekly epoetin, no correction applied).
    _dose_str = records[0].get("epo_mircera_dose") or ""
    _parsed   = normalize_epo_dose(_dose_str) if _dose_str else {}
    epo_pk_factor = float(_parsed.get("pk_correction_factor") or 1.0)

    # ── SOTA extensions (all optional; NaN → median-imputed downstream) ─────────
    # ERI = ESA Resistance Index = (weekly SC IU / kg) / Hb. Undefined without an
    # ESA dose or weight → NaN (imputed), never blocks.
    _eri_wt = dry_wt if (not math.isnan(dry_wt) and dry_wt > 0) else pre_wt
    eri = ((iu_sc / _eri_wt) / hb) if (iu_sc is not None and iu_sc > 0 and
                                       not math.isnan(_eri_wt) and _eri_wt > 0 and hb > 0) else float("nan")
    il6       = _to_float(rec.get("il6"))
    tnf_alpha = _to_float(rec.get("tnf_alpha"))
    mis_score = _to_float(rec.get("mis_score"))
    hospitalization_120d = float(sum(
        1 for r in records_120d if bool(r.get("hospitalization_this_month"))
    ))

    return np.array([
        # Hb history
        hb, delta_1, delta_3,
        hb_stat["min"], hb_stat["max"], hb_stat["mean"], hb_stat["sd"], hb_stat["slope"],
        # Iron
        ferritin, tsat,
        # Biochemistry
        albumin, calcium, crp, wbc, potassium, phosphorus, sodium, overhydration,
        # HD treatment
        ktv, pre_wt, dry_wt, epo_norm,
        esa_hist["esa_mean"], esa_hist["n_esa"], esa_hist["iron_total"], esa_hist["n_iron"],
        # Demographics
        age, sex_f, height_m,
        # Transfusions
        transfusion_120d,
        # Erythropoiesis marker
        reticulocyte_pct,
        # Hepcidin proxy + ESA PK
        hepcidin_proxy, epo_pk_factor,
        # SOTA extensions (indices 33–37)
        eri, il6, tnf_alpha, mis_score, hospitalization_120d,
    ])


def _build_training_set(db: "Session") -> Tuple[np.ndarray, np.ndarray]:
    """
    Build (X, y) training set from all patients with ≥ 4 monthly records.
    Target y = Hb in the subsequent month.
    """
    from database import MonthlyRecord, Patient
    from services.interim_hb_service import get_interim_hbs, merge_hb_sequence

    patients = db.query(Patient).all()
    X_rows, y_vals = [], []

    for patient in patients:
        recs = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.patient_id == patient.id)
            .order_by(MonthlyRecord.record_month.desc())
            .all()
        )
        if len(recs) < 4:
            continue

        patient_meta = {
            "age":    getattr(patient, "age", None),
            "sex":    getattr(patient, "sex", None) or getattr(patient, "gender", None),
            "height": getattr(patient, "height", None),
        }
        monthly_dicts = [_row_to_dict(r) for r in recs]
        interim_hbs   = get_interim_hbs(db, patient.id)
        dicts         = merge_hb_sequence(monthly_dicts, interim_hbs)
        # Slide a window: features at position t → target Hb at t-1 (next observation).
        # Only use monthly records as training targets to avoid predicting interim Hb
        # values that do not represent end-of-period steady state.
        for t in range(1, len(dicts)):
            target = dicts[t - 1]
            if target.get("hb") is None:
                continue
            if target.get("is_interim"):
                continue
            feats = _extract_acm_features(dicts[t:], patient_meta=patient_meta)
            if feats is None:
                continue
            X_rows.append(feats)
            y_vals.append(float(target["hb"]))

    if not X_rows:
        return np.array([]), np.array([])

    return np.array(X_rows), np.array(y_vals)


def _row_to_dict(rec) -> Dict:
    """
    Canonical MonthlyRecord ORM → feature dict used by BOTH training and inference.
    All callers (training loop, ODE residual builder, serving router) must go through
    here so train/serving feature sets stay identical.

    B2 fix: transfusion_units reads blood_transfusion_units (the real column name).
    """
    return {
        "hb":                  rec.hb,
        "serum_ferritin":      rec.serum_ferritin,
        "tsat":                rec.tsat,
        "albumin":             rec.albumin,
        "calcium":             rec.calcium,
        "single_pool_ktv":     rec.single_pool_ktv,
        "crp":                 getattr(rec, "crp", None),
        "wbc_count":           getattr(rec, "wbc_count", None),
        "serum_potassium":     getattr(rec, "serum_potassium", None),
        "phosphorus":          rec.phosphorus,
        "serum_sodium":        getattr(rec, "serum_sodium", None),
        "idwg":                rec.idwg,
        "last_prehd_weight":   rec.last_prehd_weight,
        "weight":              rec.last_prehd_weight,
        "target_dry_weight":   rec.target_dry_weight,
        "epo_mircera_dose":    rec.epo_mircera_dose,
        "epo_weekly_units":    rec.epo_weekly_units,
        "esa_modified_at":     getattr(rec, "esa_modified_at", None),
        "desidustat_dose":     getattr(rec, "desidustat_dose", None),
        "iv_iron_dose":        rec.iv_iron_dose,
        "transfusion_units":    getattr(rec, "blood_transfusion_units", None),
        "reticulocyte_count":   getattr(rec, "reticulocyte_count", None),
        # SOTA extensions — optional inflammation/resistance + outcome signals.
        "il6":                  getattr(rec, "il6", None),
        "tnf_alpha":            getattr(rec, "tnf_alpha", None),
        "mis_score":            getattr(rec, "mis_score", None),
        "hospitalization_this_month": getattr(rec, "hospitalization_this_month", None),
        "record_month":         rec.record_month,
    }

# ── Model training ─────────────────────────────────────────────────────────────


def train_acm_model(db: "Session") -> Dict:
    """
    Train the full hybrid ACM:
      1. Fit patient-specific ODE parameters for every patient (scipy L-BFGS-B).
      2. Train the population-level residual MLP on ODE errors across all patients.

    The legacy pipeline (_acm_pipeline) is kept as a fallback but the primary
    prediction path is now hybrid_predict_trajectory() in ml_acm_ode.py.
    """
    global _acm_pipeline, _acm_trained_at, _acm_metrics

    try:
        from ml_acm_ode import train_residual_mlp, get_or_fit_patient_params
    except ImportError as e:
        return {"success": False, "error": f"ml_acm_ode unavailable: {e}"}

    # ── Step 1: fit per-patient ODE parameters ────────────────────────────────
    from database import MonthlyRecord, Patient
    patients = db.query(Patient).all()
    n_ode_fitted = 0
    for patient in patients:
        recs_orm = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.patient_id == patient.id)
            .order_by(MonthlyRecord.record_month.desc())
            .all()
        )
        dicts = [_row_to_dict(r) for r in recs_orm]
        if len(dicts) >= 3:
            get_or_fit_patient_params(patient.id, dicts)
            n_ode_fitted += 1

    # ── Step 2: train residual MLP ────────────────────────────────────────────
    result = train_residual_mlp(db)
    if not result.get("success"):
        logger.warning(f"Residual MLP training failed: {result.get('error')}")

    # ── Step 3: keep legacy pipeline as fallback ──────────────────────────────
    if _SKLEARN_AVAILABLE:
        X, y = _build_training_set(db)
        if len(X) >= 20:
            pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler",  StandardScaler()),
                ("mlp",     MLPRegressor(
                    hidden_layer_sizes=(64, 32), activation="relu", solver="adam",
                    alpha=1e-3, max_iter=500, early_stopping=True,
                    validation_fraction=0.1, random_state=42,
                )),
            ])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cv = KFold(n_splits=min(5, len(X)), shuffle=True, random_state=42)
                y_cv = cross_val_predict(pipeline, X, y, cv=cv)
            mae = float(mean_absolute_error(y, y_cv))
            r2  = float(r2_score(y, y_cv))
            pipeline.fit(X, y)
            _acm_pipeline   = pipeline
            _acm_trained_at = datetime.utcnow().isoformat()
            _acm_metrics    = {"mae_cv": round(mae, 3), "r2_cv": round(r2, 3),
                               "n_samples": len(X)}
            if _JOBLIB_AVAILABLE:
                os.makedirs("models", exist_ok=True)
                joblib.dump(pipeline, MODEL_PATH)
                
                try:
                    from database import ModelArtifact, SessionLocal
                    _art_db = SessionLocal()
                    try:
                        with open(MODEL_PATH, "rb") as f_bin:
                            model_bin_data = f_bin.read()
                        
                        training_data_hash = hashlib.sha256(X.tobytes()).hexdigest()
                        
                        art = ModelArtifact(
                            model_name          = "acm_v1",
                            version             = _acm_trained_at,
                            trained_at          = datetime.utcnow(),
                            training_data_hash  = training_data_hash,
                            metrics_json        = json.dumps(_acm_metrics),
                            feature_schema_json = json.dumps(ACM_FEATURE_NAMES),
                            artifact_path       = MODEL_PATH,
                            model_binary        = model_bin_data,
                        )
                        _art_db.add(art)
                        _art_db.commit()
                    finally:
                        _art_db.close()
                except Exception as _art_exc:
                    logger.warning("Failed to register fallback acm_v1 ModelArtifact: %s", _art_exc)

    logger.info(f"ACM hybrid training: {n_ode_fitted} ODE fits, residual={result}")
    return {
        "success":          True,
        "n_ode_fitted":     n_ode_fitted,
        "residual_result":  result,
        "fallback_metrics": _acm_metrics,
    }


def _restore_model_from_db() -> bool:
    """
    Restore acm_v1 model from ModelArtifact database binary if it exists.
    Writes the binary to MODEL_PATH.
    Returns True if successfully restored, False otherwise.
    """
    try:
        from database import SessionLocal, ModelArtifact
        db = SessionLocal()
        try:
            art = (
                db.query(ModelArtifact)
                .filter(ModelArtifact.model_name == "acm_v1")
                .filter(ModelArtifact.model_binary != None)
                .order_by(ModelArtifact.trained_at.desc())
                .first()
            )
            if art:
                # Ensure target directory exists
                os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
                
                # Write model binary
                with open(MODEL_PATH, "wb") as f:
                    f.write(art.model_binary)
                
                logger.info("Successfully restored acm_v1 model from DB.")
                return True
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to restore acm_v1 model from DB: %s", exc)
    return False


def _load_acm_model() -> bool:
    global _acm_pipeline, _acm_trained_at
    if _acm_pipeline is not None:
        return True
    if not _JOBLIB_AVAILABLE:
        return False
    if not os.path.exists(MODEL_PATH):
        _restore_model_from_db()
    if not os.path.exists(MODEL_PATH):
        return False
    try:
        _acm_pipeline   = joblib.load(MODEL_PATH)
        _acm_trained_at = datetime.utcfromtimestamp(os.path.getmtime(MODEL_PATH)).isoformat()
        return True
    except Exception as e:
        logger.warning(f"Could not load ACM model: {e}")
        return False

# ── Hb trajectory prediction ──────────────────────────────────────────────────


def _heuristic_hb_prediction(feats: np.ndarray) -> float:
    """
    Clinical heuristic when model unavailable: Hb next month ≈ current Hb
    with slight regression toward population mean (10.8), weighted by momentum.
    """
    hb = feats[0] if not math.isnan(feats[0]) else 10.0
    delta = feats[1] if not math.isnan(feats[1]) else 0.0
    population_mean = 10.8
    # Partial mean-reversion + momentum
    return round(hb + 0.3 * delta + 0.15 * (population_mean - hb), 2)


def predict_hb_trajectory(
    records:        List[Dict],
    horizon_months: int = 3,
    patient_meta:   Optional[Dict] = None,
    patient_id:     Optional[int] = None,
) -> Dict:
    """
    Predict Hb trajectory using the hybrid ODE + residual MLP model.

    Primary path: hybrid_predict_trajectory() from ml_acm_ode.py
        — patient-specific ODE (scipy L-BFGS-B fitted) + population residual MLP.
    Fallback: pure MLP pipeline (pre-Phase-1 behaviour).
    Fallback²: clinical heuristic.

    Returns shape compatible with all existing callers.
    """
    # ── Primary: hybrid ODE + residual MLP ────────────────────────────────────
    if patient_id is not None:
        try:
            from ml_acm_ode import hybrid_predict_trajectory
            from ml_esa import _resolve_weekly_iu_sc
            result = hybrid_predict_trajectory(
                patient_id    = patient_id,
                records       = records,
                patient_meta  = patient_meta,
                esa_scenario  = _resolve_weekly_iu_sc(records[0]) if records else None,
                horizon       = horizon_months,
            )
            if result.get("available"):
                result["model_metrics"] = _acm_metrics
                result["model_trained_at"] = _acm_trained_at
                return result
        except Exception as e:
            logger.debug(f"Hybrid ODE prediction failed (patient {patient_id}): {e}")

    # ── Fallback: pure residual MLP ────────────────────────────────────────────
    feats = _extract_acm_features(records, patient_meta=patient_meta)
    if feats is None:
        return {"available": False, "error": "Insufficient data (Hb required)"}

    model_loaded = _load_acm_model()
    confidence   = "mlp" if (model_loaded and _acm_pipeline) else "heuristic"
    predictions  = []
    current_feats = feats.copy()

    # Reconstruct a 4-step Hb buffer (oldest → newest) from the starting features so
    # delta_1mo / delta_3mo / Hb-stats roll forward correctly across the horizon.
    # hb_t-2 is not stored directly; linearly interpolate between t-1 and t-3.
    _hb0   = current_feats[0]
    _d1    = current_feats[1] if not math.isnan(current_feats[1]) else 0.0
    _d3    = current_feats[2] if not math.isnan(current_feats[2]) else 0.0
    _hb_neg1 = _hb0 - _d1
    _hb_neg3 = _hb0 - _d3
    _hb_neg2 = (_hb_neg1 + _hb_neg3) / 2
    _hb_buf  = [_hb_neg3, _hb_neg2, _hb_neg1, _hb0]  # 4-element rolling window

    for month_offset in range(1, horizon_months + 1):
        if model_loaded and _acm_pipeline:
            try:
                pred_hb = float(_acm_pipeline.predict(current_feats.reshape(1, -1))[0])
                pred_hb = round(max(5.0, min(18.0, pred_hb)), 2)
            except Exception:
                pred_hb = _heuristic_hb_prediction(current_feats)
                confidence = "heuristic"
        else:
            pred_hb = _heuristic_hb_prediction(current_feats)

        predictions.append({"month_offset": month_offset, "predicted_hb": pred_hb})

        # Roll the buffer forward and update all 8 Hb-history features (indices 0-7).
        _hb_buf.append(pred_hb)
        _hb_buf = _hb_buf[-4:]                              # keep last 4 (≈120-day window)
        current_feats[0] = pred_hb                          # hb_current
        current_feats[1] = pred_hb - _hb_buf[-2]           # delta_hb_1mo
        current_feats[2] = pred_hb - _hb_buf[0]            # delta_hb_3mo (oldest in buffer)
        current_feats[3] = float(np.min(_hb_buf))           # hb_min_120d
        current_feats[4] = float(np.max(_hb_buf))           # hb_max_120d
        current_feats[5] = float(np.mean(_hb_buf))          # hb_mean_120d
        current_feats[6] = float(np.std(_hb_buf)) if len(_hb_buf) > 1 else 0.0  # hb_sd_120d
        try:
            _x = np.arange(len(_hb_buf), dtype=float)
            current_feats[7] = float(np.polyfit(_x, _hb_buf, 1)[0])  # hb_trend_slope
        except Exception:
            pass  # keep previous slope on degenerate input

    return {
        "available":       True,
        "predictions":     predictions,
        "confidence":      confidence,
        "model_metrics":   _acm_metrics,
        "model_trained_at":_acm_trained_at,
    }

# ── ESA dose recommendation ───────────────────────────────────────────────────


def _classify_hb_trajectory(
    current_hb: float,
    pred_3mo: float,
) -> str:
    """Classify Hb trajectory as 'rising', 'stable', 'falling', or 'falling_fast'."""
    delta = pred_3mo - current_hb
    if delta > 0.8:    return "rising"
    if delta < -1.5:   return "falling_fast"
    if delta < -0.5:   return "falling"
    return "stable"


def _esa_recommendation(
    current_hb: float,
    pred_1mo: float,
    pred_3mo: float,
    current_iu_sc: Optional[float],
    ferritin: Optional[float],
    tsat: Optional[float],
    crp: Optional[float],
    forecast_confidence: str = "heuristic",
    k_epo_near_zero: bool = False,
) -> Dict:
    """
    Generate ESA dosing recommendation using KDIGO 2012 / KDOQI 2019 rules.

    forecast_confidence: value from traj["confidence"] — one of
        "hybrid-calibrated", "ode-calibrated", "population-prior",
        "mlp", "heuristic".
    k_epo_near_zero: True when the per-patient ODE fit could not resolve ESA
        sensitivity from the available history (sparse / uniform dosing).

    When confidence is low (population-prior, heuristic, or k_epo≈0) the
    function ignores forecast-driven decisions and falls back to current-Hb
    rules only, capping adjustments at ±25% to avoid overshoot.

    Returns:
        {
            action: "increase" | "decrease" | "hold" | "maintain",
            esa_change_pct: float,           # e.g. +25 or -25
            recommended_iu_sc: float | None, # new weekly dose
            rationale: str,
            safety_flags: [str],
        }
    """
    action          = "maintain"
    change_pct      = 0.0
    safety_flags    = []
    rationale_parts = []

    # Forecast is trustworthy only when the ODE was calibrated on this patient's
    # history and k_epo is meaningfully identified.
    _LOW_CONFIDENCE = forecast_confidence in ("population-prior", "heuristic") or k_epo_near_zero
    if _LOW_CONFIDENCE:
        safety_flags.append(
            f"Forecast confidence '{forecast_confidence}' — dose adjustments capped at ±25% "
            "and +50% escalation suppressed (KDIGO §3.4: avoid rapid dose changes with uncertain trajectory)."
        )

    # Safety: Hb above ceiling — unconditional hold
    if current_hb >= HB_CEILING:
        safety_flags.append(f"Hb {current_hb:.1f} ≥ {HB_CEILING} g/dL — hold ESA until Hb drops below 12.0")
        return {
            "action": "hold",
            "esa_change_pct": -100.0,
            "recommended_iu_sc": 0.0,
            "rationale": f"ESA held: Hb {current_hb:.1f} g/dL exceeds safety ceiling ({HB_CEILING} g/dL). Resume when Hb < 12.0.",
            "safety_flags": safety_flags,
        }

    # A3 fix: Hb ≥ 12.0 → unconditional ESA reduction, regardless of forecast.
    # Forecast should never suppress a guideline-indicated de-escalation (KDIGO/TREAT).
    if current_hb >= 12.0:
        action, change_pct = "decrease", -ESA_ADJUST_STEP * 100
        rationale_parts.append(
            f"Hb {current_hb:.1f} g/dL ≥ 12.0 g/dL — reduce ESA by 25% unconditionally "
            "(CV/thrombotic risk; KDIGO §3.6.1, TREAT trial)."
        )
        # Skip the forecast-driven branches below; compute dose and return.
        recommended_iu = None
        if current_iu_sc is not None and current_iu_sc > 0:
            recommended_iu = round(max(ESA_MIN_DOSE_IU, current_iu_sc * (1.0 + change_pct / 100.0)), -2)
        return {
            "action":            action,
            "esa_change_pct":    change_pct,
            "recommended_iu_sc": recommended_iu,
            "rationale":         " ".join(rationale_parts),
            "safety_flags":      safety_flags,
        }

    # Iron stores inadequate — do not increase ESA, fix iron first
    iron_deficient = (
        (tsat is not None and tsat < TSAT_TARGET_LOW) or
        (ferritin is not None and ferritin < 100)
    )
    if iron_deficient:
        safety_flags.append("Iron-deficient: correct iron stores before escalating ESA (KDIGO §3.4.1)")
        rationale_parts.append("Iron replete first — ESA response limited without adequate iron.")

    # High CRP — may blunt ESA response
    if crp is not None and crp > 20:
        safety_flags.append(f"CRP {crp:.0f} mg/L — acute inflammation may cause ESA hyporesponse")
        rationale_parts.append("Active inflammation detected; verify ESA response once CRP resolves.")

    trajectory = _classify_hb_trajectory(current_hb, pred_3mo)

    # 11.5–12.0 buffer band: only reduce if forecast confirms persistence
    if current_hb > HB_TARGET_HIGH and pred_1mo > HB_TARGET_HIGH:
        action, change_pct = "decrease", -ESA_ADJUST_STEP * 100
        rationale_parts.append(
            f"Hb {current_hb:.1f} g/dL above target {HB_TARGET_HIGH} g/dL and predicted to remain elevated — reduce ESA by 25%."
        )

    elif current_hb < HB_TARGET_LOW and not iron_deficient:
        # Hb below target and iron replete: increase.
        # A2 fix: +50% escalation requires calibrated forecast; cap at +25% when confidence is low.
        if trajectory == "falling_fast" and not _LOW_CONFIDENCE:
            change_pct = ESA_MAX_INCREASE * 100
        else:
            change_pct = ESA_ADJUST_STEP * 100
        action = "increase"
        if trajectory == "falling_fast" and _LOW_CONFIDENCE:
            rationale_parts.append(
                f"Hb {current_hb:.1f} g/dL below target (trajectory: {trajectory}) — "
                f"capped at +25% (not +50%) because forecast confidence is '{forecast_confidence}'. "
                "Recheck in 4 weeks before further escalation."
            )
        else:
            rationale_parts.append(
                f"Hb {current_hb:.1f} g/dL below target {HB_TARGET_LOW} g/dL (trajectory: {trajectory}) — increase ESA by {change_pct:.0f}%."
            )

    elif trajectory == "falling" and current_hb < 11.0 and not _LOW_CONFIDENCE:
        # Pre-emptive increase: only act on forecast-driven "falling" when forecast is trusted
        action, change_pct = "increase", ESA_ADJUST_STEP * 100
        rationale_parts.append(
            f"Hb {current_hb:.1f} g/dL falling and projected to drop below target — pre-emptive +25% increase."
        )

    elif trajectory == "rising" and pred_3mo > HB_TARGET_HIGH and not _LOW_CONFIDENCE:
        # Pre-emptive decrease: suppress when forecast is unreliable
        action, change_pct = "decrease", -ESA_ADJUST_STEP * 100
        rationale_parts.append(
            f"Hb predicted to rise to {pred_3mo:.1f} g/dL — reduce ESA by 25% to avoid overshoot."
        )

    else:
        rationale_parts.append(
            f"Hb {current_hb:.1f} g/dL within or near target range; maintain current ESA dose."
        )

    # Compute actual recommended dose
    recommended_iu = None
    if current_iu_sc is not None and current_iu_sc > 0:
        factor = 1.0 + change_pct / 100.0
        recommended_iu = round(max(ESA_MIN_DOSE_IU, current_iu_sc * factor), -2)  # round to nearest 100 IU
    elif action == "increase":
        recommended_iu = 4000.0  # starter dose when no prior ESA

    return {
        "action":             action,
        "esa_change_pct":     change_pct,
        "recommended_iu_sc":  recommended_iu,
        "rationale":          " ".join(rationale_parts),
        "safety_flags":       safety_flags,
    }


def _iron_recommendation(
    ferritin: Optional[float],
    tsat: Optional[float],
    crp: Optional[float],
) -> Dict:
    """
    Generate IV iron supplementation recommendation per KDIGO 2012 §3.4.
    """
    safety_flags = []
    action       = "maintain"
    rationale    = ""

    if ferritin is None or tsat is None:
        return {
            "action":    "check",
            "rationale": "Iron panel incomplete — check ferritin and TSAT before recommending iron.",
            "safety_flags": ["Missing ferritin or TSAT"],
        }

    # Safety: iron overload
    if ferritin > FERRITIN_MAX:
        safety_flags.append(f"Ferritin {ferritin:.0f} µg/L — hold IV iron (risk of iron overload)")
        return {
            "action":    "hold",
            "rationale": f"Ferritin {ferritin:.0f} µg/L exceeds {FERRITIN_MAX} µg/L threshold. Hold all IV iron until ferritin < 800.",
            "safety_flags": safety_flags,
        }

    if tsat > TSAT_CEILING:
        safety_flags.append(f"TSAT {tsat:.0f}% — hold iron (functional overload)")
        return {
            "action":    "hold",
            "rationale": f"TSAT {tsat:.0f}% above {TSAT_CEILING}%. Hold IV iron — excess transferrin saturation risks tissue deposition.",
            "safety_flags": safety_flags,
        }

    # Inflammation: high ferritin with low TSAT = iron trapped in RES, not deficiency
    inflam_sequestration = ferritin > 500 and tsat < 20
    if inflam_sequestration and crp and crp > 10:
        safety_flags.append("High ferritin + low TSAT with elevated CRP — iron sequestration, not deficiency")
        return {
            "action":    "investigate",
            "rationale": (
                f"High ferritin ({ferritin:.0f} µg/L) with low TSAT ({tsat:.0f}%) and CRP {crp:.0f} mg/L "
                "indicates inflammation-driven iron trapping (RES sequestration). "
                "Address inflammation — do NOT interpret as iron deficiency. (KDIGO §3.4.3)"
            ),
            "safety_flags": safety_flags,
        }

    # Iron-deficient: supplement
    if tsat < TSAT_TARGET_LOW or ferritin < 100:
        action = "supplement"
        rationale = (
            f"Iron deficient: TSAT {tsat:.0f}% (target ≥{TSAT_TARGET_LOW}%) or "
            f"Ferritin {ferritin:.0f} µg/L (target ≥100 µg/L). "
            "Initiate IV iron repletion course (e.g. 1000 mg iron sucrose over 2 weeks). "
            "Recheck ferritin + TSAT in 4 weeks."
        )

    elif tsat < TSAT_TARGET_HIGH and ferritin < FERRITIN_REPLETE:
        action = "supplement"
        rationale = (
            f"Functional iron deficiency: TSAT {tsat:.0f}% < 30% with ferritin {ferritin:.0f} µg/L < 200 µg/L. "
            "Continue maintenance IV iron (e.g. 100–200 mg monthly). (KDIGO §3.4.2)"
        )

    else:
        action = "maintain"
        rationale = (
            f"Iron replete: TSAT {tsat:.0f}%, ferritin {ferritin:.0f} µg/L — continue maintenance iron protocol. "
            "No loading dose required."
        )

    return {"action": action, "rationale": rationale, "safety_flags": safety_flags}

# ── Main recommendation entry point ──────────────────────────────────────────


def generate_acm_recommendation(
    patient_id: int,
    records: List[Dict],
    horizon_months: int = 3,
    patient_meta: Optional[Dict] = None,
) -> Dict:
    """
    Full ACM recommendation for a patient.

    Args:
        patient_id: Patient primary key.
        records:    Monthly records (newest-first dicts from MonthlyRecord).
        horizon_months: Hb prediction horizon.

    Returns:
        Complete recommendation dict for storage and display.
    """
    if not records:
        return {"available": False, "error": "No monthly records available"}

    latest = records[0]
    current_hb  = _to_float(latest.get("hb"))
    ferritin    = _to_float(latest.get("serum_ferritin"), default=None)
    tsat_val    = _to_float(latest.get("tsat"), default=None)
    albumin     = _to_float(latest.get("albumin"), default=None)
    crp_val     = _to_float(latest.get("crp"), default=None)
    current_iu  = _resolve_weekly_iu_sc(latest)

    if math.isnan(current_hb):
        return {"available": False, "error": "Latest Hb not recorded"}

    ferritin_f = None if (ferritin is None or math.isnan(ferritin)) else ferritin
    tsat_f     = None if (tsat_val is None or math.isnan(tsat_val)) else tsat_val
    crp_f      = None if (crp_val is None or math.isnan(crp_val)) else crp_val

    # Hb trajectory prediction — hybrid ODE preferred, fallback to MLP/heuristic
    traj = predict_hb_trajectory(
        records,
        horizon_months = horizon_months,
        patient_meta   = patient_meta,
        patient_id     = patient_id,
    )
    pred_1mo = pred_3mo = None
    if traj.get("available"):
        preds = traj["predictions"]
        pred_1mo = preds[0]["predicted_hb"] if len(preds) >= 1 else current_hb
        pred_3mo = preds[2]["predicted_hb"] if len(preds) >= 3 else current_hb
    else:
        pred_1mo = pred_3mo = current_hb

    # Extract forecast confidence and k_epo signal from trajectory result
    _forecast_confidence = traj.get("confidence", "heuristic")
    _k_epo_near_zero = bool(
        traj.get("ode_params", {}).get("k_epo_near_zero") or
        traj.get("params",     {}).get("k_epo_near_zero")
    )

    # ── Resistance / ERI (needs no inflammation labs) ──────────────────────────
    from services.acm_optimizer import compute_eri, optimize_esa, optimize_iron, hifphi_switch
    weight_kg = _to_float(latest.get("last_prehd_weight") or latest.get("weight") or
                          latest.get("target_dry_weight"))
    weight_kg = weight_kg if not math.isnan(weight_kg) else None
    eri = compute_eri(current_iu, weight_kg, current_hb)

    resistance_flag = False
    try:
        from ml_esa import detect_epo_hyporesponse
        _hypo = detect_epo_hyporesponse(records)
        resistance_flag = bool(_hypo.get("data", {}).get("hypo_response"))
    except Exception:
        _hypo = {}

    # ── ESA recommendation — model-based optimizer (heuristic fallback inside) ──
    esa_rec = optimize_esa(
        patient_id          = patient_id,
        records             = records,
        current_iu_sc       = current_iu,
        ferritin            = ferritin_f,
        tsat                = tsat_f,
        crp                 = crp_f,
        forecast_confidence = _forecast_confidence,
        k_epo_near_zero     = _k_epo_near_zero,
        hb_target           = (HB_TARGET_LOW, HB_TARGET_HIGH),
        horizon             = horizon_months,
        patient_meta        = patient_meta,
    )

    # ── Iron recommendation — quantified repletion dose ────────────────────────
    iron_rec = optimize_iron(
        ferritin = ferritin_f,
        tsat     = tsat_val if (tsat_val is not None and not math.isnan(tsat_val)) else None,
        crp      = crp_f,
    )

    # ── HIF-PHI (Desidustat) ESA-sparing suggestion ────────────────────────────
    hifphi_suggestion = hifphi_switch(
        records         = records,
        eri             = eri,
        resistance_flag = resistance_flag,
        current_esa_iu  = current_iu,
        ferritin        = ferritin_f,
        tsat            = tsat_f,
    )

    # Safety classification
    hb_status = (
        "critical_low"  if current_hb < HB_FLOOR else
        "low"           if current_hb < HB_TARGET_LOW else
        "on_target"     if current_hb <= HB_TARGET_HIGH else
        "high"          if current_hb < HB_CEILING else
        "critical_high"
    )

    all_safety = esa_rec["safety_flags"] + iron_rec["safety_flags"]
    if current_hb < HB_FLOOR:
        all_safety.insert(0, f"CRITICAL: Hb {current_hb:.1f} g/dL — consider transfusion evaluation")

    return {
        "available":       True,
        "patient_id":      patient_id,
        "recommendation_month": latest.get("record_month"),
        "generated_at":    datetime.utcnow().isoformat(),
        "current_hb":      round(current_hb, 1),
        "hb_status":       hb_status,
        "hb_trajectory":   traj,
        "predicted_hb_1mo": round(pred_1mo, 2),
        "predicted_hb_2mo": round(traj["predictions"][1]["predicted_hb"], 2) if traj.get("available") and len(traj["predictions"]) >= 2 else round(pred_1mo, 2),
        "predicted_hb_3mo": round(pred_3mo, 2),
        "esa_recommendation": esa_rec,
        "iron_recommendation": iron_rec,
        "ferritin":        ferritin_f,
        "tsat":            tsat_f,
        "albumin":         albumin if (albumin is not None and not math.isnan(albumin)) else None,
        "crp":             crp_f,
        "current_iu_sc":   current_iu,
        "safety_flags":    all_safety,
        "confidence":      traj.get("confidence", "heuristic"),
        # ── SOTA additions ────────────────────────────────────────────────────
        "method":            esa_rec.get("method", "heuristic"),
        "eri":               eri,
        "resistance_flag":   resistance_flag,
        "target_attainment": esa_rec.get("target_attainment"),
        "dose_response_curve": esa_rec.get("dose_response_curve", []),
        "hifphi_suggestion": hifphi_suggestion,
        "recommended_iron_mg": iron_rec.get("recommended_mg"),
    }


def get_acm_model_status() -> Dict:
    """Return ACM model metadata for admin display."""
    loaded = _load_acm_model()
    return {
        "available":    loaded,
        "trained_at":   _acm_trained_at,
        "metrics":      _acm_metrics,
        "model_path":   MODEL_PATH,
        "feature_names": ACM_FEATURE_NAMES,
        "n_features":   len(ACM_FEATURE_NAMES),
    }


def get_fleet_acm_summary(db: "Session") -> Dict:
    """
    Compute fleet-wide ACM performance summary for the audit dashboard.
    Returns Hb distribution stats, protocol adherence, override rate.
    """
    from database import ACMRecommendation, MonthlyRecord
    from sqlalchemy import func

    try:
        total = db.query(ACMRecommendation).count()
        accepted = db.query(ACMRecommendation).filter(
            ACMRecommendation.clinician_decision == "accept"
        ).count()
        modified = db.query(ACMRecommendation).filter(
            ACMRecommendation.clinician_decision == "modify"
        ).count()
        rejected = db.query(ACMRecommendation).filter(
            ACMRecommendation.clinician_decision == "reject"
        ).count()

        # Recent Hb statistics from monthly records (last 3 months)
        from dashboard_logic import get_current_month_str
        current_month = get_current_month_str()
        y, m = int(current_month[:4]), int(current_month[5:7])
        recent_months = []
        for i in range(3):
            target_m = m - i
            target_y = y
            while target_m <= 0:
                target_m += 12
                target_y -= 1
            recent_months.append(f"{target_y}-{target_m:02d}")

        recent_hb = db.query(MonthlyRecord.hb).filter(
            MonthlyRecord.hb.isnot(None),
            MonthlyRecord.record_month.in_(recent_months)
        ).all()
        hb_vals = [r[0] for r in recent_hb if r[0] is not None]
        on_target = sum(1 for v in hb_vals if HB_TARGET_LOW <= v <= HB_TARGET_HIGH)

        return {
            "total_recommendations":  total,
            "accepted":               accepted,
            "modified":               modified,
            "rejected":               rejected,
            "pending":                total - accepted - modified - rejected,
            "acceptance_rate":        round(accepted / total * 100, 1) if total else 0,
            "n_patients_with_hb":     len(hb_vals),
            "hb_on_target_pct":       round(on_target / len(hb_vals) * 100, 1) if hb_vals else 0,
            "hb_mean":                round(float(np.mean(hb_vals)), 2) if hb_vals else None,
            "hb_sd":                  round(float(np.std(hb_vals)), 2) if hb_vals else None,
        }
    except Exception as e:
        logger.warning(f"Fleet ACM summary failed: {e}")
        return {}
