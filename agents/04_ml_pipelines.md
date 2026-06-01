# 04 — ML Pipelines Reference

> Agent memory file · HD Dashboard · Last updated 2026-06-01

---

## Overview of ML Models

| Model | File | Algorithm | Purpose | Status |
|-------|------|-----------|---------|--------|
| Anemia Control Model (ACM) | `ml_acm.py` + `ml_acm_ode.py` | Hybrid ODE + Ridge/MLP | ESA/iron dosing recommendation | Active |
| Digital Twin Hb module | `ml_twin.py` | Bayesian conjugate Gaussian | Prescription scenario Hb forecast | Active |
| IDH Prediction | `ml_idh.py` | XGBoost → LR fallback → heuristic | Pre-session IDH risk | Active (needs training data) |
| Deterioration Risk | `ml_risk.py` | Calibrated Logistic Regression | Next-month hospitalisation probability | Active (needs training data) |
| Mortality Risk | `ml_risk.py` | XGBoost (Xu et al. 2023) + Indian recalibration | 1-year mortality | Active (literature model) |
| Cohort Analytics | `ml_analytics.py` | Logistic + trend regression | Cohort-level KPI tracking | Active |
| Phosphate Model | `phosphate_model.py` | 2-pool RK4 ODE | Pre-dialysis phosphate forecast | Active (inside Digital Twin) |
| KRCRw Model | `krcrw_model.py` | Creatinine clearance equation | Residual kidney function | Active |
| Urea Kinetics | `urea_model.py` | Daugirdas / Leypoldt equations | Kt/V, eKt/V, std Kt/V | Active |
| Data Quality Gate | `ml_quality_gate.py` | Rule-based | Input validation (HEMO Study thresholds) | Always runs first |

---

## 1. Anemia Control Model (ACM)

**Files**: `ml_acm.py`, `ml_acm_ode.py`, `ml_esa.py`  
**Router**: `routers/acm.py`  
**Template**: `templates/acm_dashboard.html`, `templates/acm_audit.html`

### Architecture (Fresenius ACM-aligned)
```
Patient Data → ESA normalisation (ml_esa.py) → Quality Gate → 
ODE Parameter Fitting (scipy L-BFGS-B) → Hybrid Predict:
  Hb_predicted(t+1) = ODE_prediction(t+1) + Residual_MLP_correction(t+1)
→ KDIGO rules → ESA/iron recommendation
```

### ODE Parameters (per-patient, stored in `models/ode_params/patient_{id}.json`)
- `k_epo` — ESA sensitivity [0, 0.15]. When ≈ 0: prediction interval widens (MAE floor = 1.2 g/dL)
- `k_prod` — basal monthly Hb production [0, 1.5]
- `k_loss` — RBC fractional monthly decay ≈ 1/120 [0.1, 0.5]

Fitting: scipy `L-BFGS-B`, 5–15 random restarts, minimum 3 months Hb history.

### 32-Feature Input Vector (`ml_acm.py::ACM_FEATURE_NAMES`)
- Hb 120-day window: current, Δ1mo, Δ3mo, min/max/mean/SD/slope
- Iron: ferritin, TSAT
- Biochemistry: albumin, calcium, CRP, WBC, MCH, MCV, K, phosphorus, Na, overhydration proxy (IDWG/dry_weight)
- HD treatment 140-day: Kt/V, pre-weight, dry weight, ESA norm, ESA 140d mean/count, IV iron 140d total/count
- Demographics: age, sex_f, height_m
- Transfusions 120d

### KDIGO Recommendation Rules (deterministic)
- Hb < 10.0 → increase ESA +25%
- Hb > 13.0 → hold ESA (safety ceiling)
- Hb 10.0–11.5 → maintain
- TSAT < 20% → IV iron supplement
- TSAT 20–30% → maintain iron
- Ferritin > 800 → hold IV iron
- Ferritin high + TSAT low + CRP high → iron sequestration flag (NOT overload)

### Feedback Loop (Celery)
- Every Monday 03:00: `task_backfill_acm_outcomes` — fills `observed_hb_1mo` when follow-up record exists
- Every Monday 03:30: `task_compute_acm_calibration` — slope/MAE/R² + ESA dose-response regression
- Every Monday 04:00: `task_train_acm_model` — refit ODE params + retrain residual MLP

### Prediction Interval (80% PI)
```python
σ(t) = ODE_MAE × confidence_multiplier × √t
Hb ± 1.28 × σ(t)
# confidence_multiplier: 1.0 (high) | 1.3 (moderate) | 1.8 (low)
```

---

## 2. IDH Prediction Model

**File**: `ml_idh.py`  
**Router**: `routers/analytics.py` (exposed via analytics hub)

### Algorithm
XGBoost primary → Calibrated LogisticRegression fallback → Rule-based heuristic

### 26 Features
**Patient/comorbidity (9):** age, dm, chf, cad, pvd, af, liver_disease, lvef, diastolic_dysfunction_grade  
**Labs (2):** albumin, antihypertensive_count  
**Session plan (6):** pre_hd_sbp, idwg_kg, uf_volume_ml, uf_rate_ml_kg_h, dialysate_temp, dialysate_sodium  
**Session context (3):** uf_achievement_ratio, antihypertensive_prehd, intradialytic_meals  
**Temporal/prior (6):** prior_idh_count_7sess, prior_idh_rate_7sess, prior_nadir_sbp_mean, pre_hd_sbp_slope_7sess, albumin_slope_3mo, uf_rate_albumin_ratio

### IDH Definition (Hybrid Label)
- BP data available: SBP drop ≥ 20 mmHg (bp_pre_sys → bp_nadir_sys) OR nadir SBP < 90 mmHg
- Fallback: `idh_episode` Boolean when nadir BP not recorded

### Model Artifacts
- `models/idh_model.joblib` — trained XGBoost
- Registry row in `model_artifacts` (model_name = `"idh_v1"`)
- Training: `task_train_idh_model` Celery task → `POST /analytics/admin/train-idh-model`

### Outcome Back-fill
- `task_backfill_idh_outcomes` — nightly, fills `ml_predictions.observed_outcome` from completed session records
- `task_compute_idh_model_metrics` — delegates to generic `task_compute_model_metrics("idh_v1")`

---

## 3. Deterioration / Hospitalisation Risk

**File**: `ml_risk.py`  
**Router**: `routers/analytics.py`

### Algorithm
Calibrated Logistic Regression (sklearn `CalibratedClassifierCV`)  
Pipeline: `SimpleImputer(median)` → `StandardScaler` → `LogisticRegression(class_weight="balanced")`

### 12 Features (`DETERIORATION_FEATURE_NAMES`)
```python
["hb_alert", "hb_value", "alb_alert", "alb_value", "target_score",
 "epo_hypo_proxy", "age", "cad", "chf", "dm",
 "num_recent_hospitalizations_90d", "recent_infection_events"]
```

### KDOQI Target Score (0–10, used as feature)
6 parameters scored: Hb ≥ 10, Albumin ≥ 3.5, Phosphorus ≤ 5.5, IDWG ≤ 2.5, URR ≥ 65, Kt/V ≥ 1.2

### Risk Thresholds
- Prob ≥ 0.40 → High
- Prob 0.15–0.40 → Moderate
- Prob < 0.15 → Low

### EPF Guard (Statistical Safety)
- Needs ≥ 50 hospitalisation events (5 EPF × 12 features; relaxed from 10 EPF × 10 for small registries)
- Below 50 events → heuristic fallback only
- Below 10 EPF (120 events) → overfitting warning flagged in metadata

### ModelArtifact Gate
**Inference is refused when `model_artifacts` has no row for `"deterioration_v1"`.**  
This prevents stale .pkl files from silently running after a container restart.

### SHAP Explanations
`_compute_deterioration_shap()` — LinearExplainer on CalibratedClassifierCV inner pipeline.  
Returns top-10 feature contributions sorted by |SHAP value|.

### Feature Store
`patient_feature_snapshot` — JSONB, one row per (patient_id, as_of_month).  
Populated nightly by `task_refresh_feature_snapshots`.  
Inference uses snapshot if `stale = False`, else recomputes live.

---

## 4. Mortality Risk (Xu et al. 2023)

**File**: `ml_risk.py` (bottom section)

### Algorithm
XGBoost loaded from literature pre-trained weights + **Indian population recalibration** (Platt scaling).

### Recalibration
```python
_INDIAN_CAL_SLOPE     = 0.72   # risk compression
_INDIAN_CAL_INTERCEPT = -0.40  # logit-space shift
# Derived from: DOPPS India Phase 5, Indian HD Registry ISN 2020
# Must be replaced with locally fitted values once ≥50 mortality events collected
```

### Clinical Note
Indian HD cohort 1-year mortality ≈ 14.2% (vs Chinese cohort 22–28%).
Raw Xu model over-predicts for this population without recalibration.

---

## 5. Data Quality Gate

**File**: `ml_quality_gate.py`

Runs before ALL model inputs.  Based on HEMO Study exclusion criteria + KDOQI HD Adequacy Guidelines + KDIGO CKD-MBD 2017.

### Severity Levels
- **error** (hard limit): value nulled out, never enters model
- **warn** (soft limit): value kept but flagged in UI

### Key Cross-field Checks
- Post-dialysis BUN > pre-dialysis BUN → impossible, reject
- URR inconsistent with pre/post BUN → warn transcription error
- High ferritin + low TSAT + high CRP → iron sequestration flag
- Hb > 13.5 with TSAT < 10% → verify

---

## 6. Model Artifacts on Disk

```
models/
  deterioration_model.joblib      — Calibrated LR (may be absent if not yet trained)
  deterioration_model_meta.json   — Training metadata (cv_auc, n_samples, EPF, etc.)
  idh_model.joblib                — XGBoost IDH model
  acm_residual_mlp.pkl            — ACM residual MLP (population correction)
  ode_params/
    patient_{id}.json             — Per-patient ODE parameters {k_epo, k_prod, k_loss}
```

**Container persistence**: `model_binary` (LargeBinary) in `model_artifacts` table stores the joblib bytes. On Render (ephemeral filesystem), models must be loaded from DB on cold start.

---

## 7. MLOps Metrics Schema

All models write to `ml_model_metrics` with `model_name` discriminator.

| Metric | Meaning | Drift threshold |
|--------|---------|-----------------|
| `calibration_slope` | OLS slope of observed ~ predicted | \|slope - 1.0\| > 0.15 |
| `brier_score` | Mean probability error (or MAE for ACM) | — |
| `roc_auc` | AUROC (or R² for ACM) | — |
| `pr_auc` | Precision-recall AUC | — |
| `drift_flagged` | Boolean alert | triggers `task_alert_model_drift` |

When drift is flagged: `task_alert_model_drift` sends HTML email to `ADMIN_EMAIL`.
