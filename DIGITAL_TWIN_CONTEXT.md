# Anemia Control Model & Digital Dialysis Twin — Project Context

> **Agent memory file** — saved in application root for AI assistant continuity.
> Last updated: 2026-06-01. Update this file whenever architecture, clinical decisions,
> or outstanding work changes significantly.

---

## Project Overview

A **FastAPI + Jinja2** hemodialysis clinical dashboard with two integrated AI subsystems:
1. **Anemia Control Model (ACM)** — predicts Hb trajectory and generates personalized ESA + IV iron dosing recommendations
2. **Digital Dialysis Twin** — 5-domain physiological simulator for prescription "what-if" analysis

Both are designed around published clinical AI architecture:
- **ACM**: Aligned with Fresenius Medical Care ACM (Fuertinger et al., CJASN 2024) — ANN + patient-specific ODE
- **Digital Twin**: Aligned with Cheungpasitporn et al. CKJ 2026 and Kotanko/RRI twin framework

---

## Architecture Decisions

### ACM — Hybrid ODE + Residual MLP (the Fresenius approach)

**File:** `ml_acm_ode.py`

The prediction pipeline is:
```
Hb_predicted(t+1) = ODE_predicted(t+1)  +  Residual_MLP_correction(t+1)
                     ↑ patient-specific       ↑ population correction
                     3 parameters fitted       32-feature ANN (64→32 ReLU)
                     per patient via scipy
```

**ODE parameters per patient** (stored in `models/ode_params/patient_{id}.json`):
- `k_epo`  — ESA sensitivity [0, 0.15]. When k_epo ≈ 0, ESA history is too sparse. **Prediction intervals widen automatically.**
- `k_prod` — basal monthly Hb production (endogenous EPO contribution) [0, 1.5]
- `k_loss` — RBC fractional monthly decay ≈ 1/120 day lifespan [0.1, 0.5]

Fitting: scipy L-BFGS-B with 5–15 random restarts. Minimum 3 months of Hb history required.

**32-feature input vector** (`ml_acm.py::ACM_FEATURE_NAMES`):
- Hb 120-day window: current, Δ1mo, Δ3mo, min/max/mean/SD/slope
- Iron: ferritin, TSAT
- Biochemistry: albumin, calcium, CRP, WBC, MCH, MCV, K, phosphorus, Na, overhydration proxy
- HD treatment (140-day): Kt/V, pre-weight, dry weight, ESA normalized, ESA 140d mean/count, IV iron 140d total/count
- Demographics: age, sex_f, height_m
- Transfusions 120d

**Why this design:** Pure empirical MLP needs thousands of patient-months. The ODE only needs 3 months because it's fitting 3 physiologically-bounded parameters, not learning from scratch. Residual MLP handles what ODE misses (inflammation, transfusions, iron transitions).

---

### Digital Twin — 5-Domain Integrated Simulator

**File:** `ml_twin.py`

| Module | Equation/Model | File |
|---|---|---|
| 1. Hb kinetics | Patient ODE + residual MLP | `ml_acm_ode.py` |
| 2. spKt/V | Daugirdas 2nd-gen single pool | `ml_twin.py::calculate_ktv_daugirdas` |
| 3. eKt/V + std Kt/V | Tattersall / Leypoldt | `urea_model.py::calculate_std_ktv` |
| 4. Dialyzer clearance Kd | Daugirdas Appendix C | `urea_model.py::calculate_dialyzer_clearance` |
| 5. Phosphate kinetics | 2-pool RK4 (Daugirdas/Laursen) | `phosphate_model.py::estimate_phosphate_kinetics` |
| 6. IDH risk | XGBoost + 39 features | `ml_idh.py::compute_idh_risk` |
| 7. UF rate sweep | IDH swept 6–16 mL/kg/h | `ml_twin.py::simulate_uf_rate_idh_curve` |

**Cross-domain cascade rules** (key clinical insight):
```
session_h ↑  →  spKt/V ↑, phosphate removal ↑, effective UF rate ↓ → IDH risk ↓
Qb ↑         →  dialyzer Kd ↑ → spKt/V ↑, phosphate clearance ↑
UF rate ↑    →  IDH risk ↑
PBE dose ↑   →  pre-dialysis phosphate ↓
temp ↓       →  IDH risk ↓
```

**Phosphate model fallback:** The RK4 solver diverges with extreme inputs. Linear fallback (`_phosphate_simple_estimate`) uses published coefficient estimates: −0.30 mg/dL per +1h session, −0.10 mg/dL per +1 PBE.

---

### Data Quality Gate

**File:** `ml_quality_gate.py`

Validates ALL inputs before they enter any model. Based on:
- HEMO Study exclusion criteria (Daugirdas & Depner, NDT 2017)
- KDOQI HD Adequacy Guidelines
- KDIGO CKD-MBD 2017

Severity levels:
- **error** (hard limit): value nulled out, never enters model
- **warn** (soft limit): value kept but flagged in UI

Key cross-field checks:
- Post-dialysis BUN > pre-dialysis BUN → impossible, reject
- URR inconsistent with pre/post BUN → warn transcription error
- High ferritin + low TSAT + high CRP → iron sequestration flag (NOT iron overload)
- Hb > 13.5 with TSAT < 10% → verify

---

### Prediction Intervals (Uncertainty Quantification)

**File:** `ml_acm_ode.py::ode_predict_trajectory`

80% prediction interval: `Hb ± 1.28 × σ(t)` where:
- `σ(t) = ODE_MAE × confidence_multiplier × √t`
- `confidence_multiplier`: 1.0 (high), 1.3 (moderate), 1.8 (low)
- `t` = months ahead (uncertainty widens with horizon)
- When k_epo ≈ 0: MAE floor set to 1.2 g/dL

Displayed as shaded band on digital_twin.html Hb chart.

---

## Database Tables (ACM-specific)

| Table | Purpose | Key columns |
|---|---|---|
| `acm_recommendations` | One row per patient per month | `predicted_hb_1/2/3mo`, `esa_action`, `iron_action`, `clinician_decision`, `observed_hb_1mo` (backfilled), `hb_prediction_mae_1mo` |
| `twin_simulations` | Log of every scenario run | `scenario_json`, `hb_sim_json`, `ktv_sim_json`, `idh_sim_json`, `uf_curve_json` (now includes phosphate + cascade) |
| `ml_model_metrics` (model_name='acm_v1') | Weekly calibration stats | `calibration_slope` (ideal 1.0), `brier_score` (=MAE for continuous), `roc_auc` (=R²), `drift_detail` JSON |

Migration: `alembic/versions/0018_acm_twin_tables.py`

---

## Celery Beat Schedule (ACM pipeline — every Monday UTC)

```
03:00  task_backfill_acm_outcomes     — fills observed_hb_1mo when follow-up record exists
03:30  task_compute_acm_calibration   — slope/MAE/R²/ESA dose-response regression
04:00  task_train_acm_model           — refit ODE params + retrain residual MLP
```

---

## Clinical Constants (KDIGO 2012 / KDOQI 2019)

| Parameter | Value | Source |
|---|---|---|
| Hb target range | 10.0–11.5 g/dL | KDIGO 2012 §3.4 |
| Hb ceiling (hold ESA) | 13.0 g/dL | KDIGO 2012 |
| ESA adjustment step | ±25% per cycle | KDIGO recommendation |
| Iron: TSAT target | 20–30% | KDIGO 2012 §3.4 |
| Iron: Ferritin max | 800 µg/L (hold IV iron) | KDIGO 2012 |
| spKt/V target | ≥ 1.2 | KDIGO 2015 HD Adequacy |
| Phosphate target | 3.5–5.5 mg/dL | KDIGO CKD-MBD 2017 |
| UF rate safety | < 10 mL/kg/h | KDIGO recommendation |

---

## Known Gaps & Next Steps

### What works reliably today
- KDIGO recommendation rules (ESA ±25%, iron protocol) — deterministic, no training data needed
- Daugirdas Kt/V, eKt/V, std Kt/V — validated equations
- IDH XGBoost with 39 features (when model is trained)
- Phosphate 2-pool kinetics with linear fallback
- Input quality gate (HEMO Study thresholds)
- ODE parameter fitting with prediction intervals

### What needs more patient data
- Residual MLP (needs ≥200 patient-months to generalize)
- ESA dose-response calibration (needs ≥5 accepted recs with follow-up)
- Reliability diagram (needs backfill data)

### Phase 2 (not yet built)
- Two-compartment fluid/volume model (Abohtyra et al. IEEE 2018) — real-time RBV tracking, proven 34% IDH reduction when used for closed-loop UF control
- Conformal prediction intervals (MAPIE library) on IDH XGBoost — distribution-free coverage guarantees
- Bayesian MCMC for phosphate ODE parameters (Bangsgaard et al. MBE 2023) — narrower credibility intervals with consecutive session data
- Real-time machine data streaming (MQTT → IDH predictions every 15 min intra-session)
- Vascular access aging model (IoMT XGBoost, Hsieh et al. 2023, 90.7% precision)
- Acid-base (HCO₃⁻) kinetics module

### Statistical closeness to Fresenius ACM
| Feature | Fresenius ACM | This implementation |
|---|---|---|
| Model class | ANN + physiologic ODE | ✅ Same (hybrid ODE + residual MLP) |
| Feature set | 32 clinical variables | ✅ Identical |
| ODE structure | Erythropoiesis ODE, scipy fitted | ✅ Same architecture |
| Training scale | 79,426 patient-months | ⚠ Local population only |
| Predicted Hb MAE | ~0.60–0.75 g/dL | Unknown (need backfill data) |
| Regulatory | EU MDR 2017/745 certified | Not a medical device |

---

## File Map (ACM + Twin)

```
ml_acm.py              — Feature extraction, KDIGO rules, generate_acm_recommendation()
ml_acm_ode.py          — Erythropoiesis ODE, scipy fitting, hybrid_predict_trajectory()
ml_twin.py             — 5-domain run_scenario(), build_twin_plotly_data()
ml_quality_gate.py     — Input validation (HEMO thresholds, clinical ranges)
ml_esa.py              — ESA dose normalization, ERI calculation
ml_idh.py              — IDH XGBoost prediction (39 features)
urea_model.py          — Kt/V, eKt/V, std Kt/V, dialyzer clearance
phosphate_model.py     — 2-pool phosphate RK4 kinetics
krcrw_model.py         — Residual kidney creatinine clearance (KRCRw)

routers/acm.py         — /acm/{patient_id}, /acm/audit, /acm/{id}/decide
routers/twin.py        — /twin/{patient_id}, /twin/{id}/simulate, /twin/{id}/history

templates/acm_dashboard.html  — Per-patient ACM recommendation + clinician decision
templates/acm_audit.html      — Fleet calibration: reliability diagram, ESA dose-response
templates/digital_twin.html   — 5-domain scenario sandbox with Plotly

tasks.py               — task_backfill_acm_outcomes, task_compute_acm_calibration, task_train_acm_model
celery_app.py          — Beat: Mon 03:00/03:30/04:00 UTC for ACM pipeline

models/ode_params/     — Per-patient ODE JSON files (patient_{id}.json)
models/acm_residual_mlp.pkl    — Residual MLP (population correction)

alembic/versions/0018_acm_twin_tables.py — ACMRecommendation + TwinSimulation tables
```

---

## Key Literature

| Paper | What it proves | Relevance |
|---|---|---|
| Fuertinger et al. CJASN 2024 | 25% ESA reduction, 47% Hb target attainment in RCT | ACM clinical validation target |
| Garbelli et al. Biomedicines 2024 | 74.3 vs 86.7 hospitalizations/100 person-years | ACM outcomes benchmark |
| Fuertinger et al. CPT PSP 2018 | Virtual Anemia Trial — 6,659 patient avatars | ODE architecture reference |
| Zhang & Kotanko NDT 2023 | AUROC 0.887 for IDH at 15–75 min horizon | IDH model validation target |
| Laursen et al. Physiol Rep 2023 | Phosphate 2-pool model R²=0.985 | Phosphate module validation |
| Bangsgaard et al. MBE 2023 | Bayesian MCMC for phosphate ODE | Phase 2 upgrade path |
| Abohtyra et al. IEEE TBE 2018 | 2-compartment fluid model, 30-min calibration | Phase 2 fluid module |
| Daugirdas Semin Dialysis 2025 | Multi-solute kinetic programs (urea/P/Cr/B2M) | Adequacy module foundation |
| Cheungpasitporn et al. CKJ 2026 | AI roadmap for nephrology (paper driving this work) | Overall architecture |

---

## Explaining to Senior Nephrologist

**One sentence:** "Patient-specific physiological simulator — before changing the prescription, it shows what Hb, Kt/V, phosphate, and IDH risk will be next month."

**Key clinical analogies:**
- ODE parameters = this patient's personal dose-response curve (like fitting a PK model per patient)
- Prediction interval = "Hb will be 10.4–12.0 g/dL" — communicates uncertainty, earns trust
- Cascade card = all five physiological effects of one prescription change, simultaneously

**What to say about statistical validity:**
- KDIGO rules: valid immediately (deterministic)
- ODE predictions: valid with ≥3 months history per patient
- Calibration MAE target: < 0.75 g/dL to match Fresenius benchmark
- Not a medical device — all recommendations require clinician accept/modify/reject
