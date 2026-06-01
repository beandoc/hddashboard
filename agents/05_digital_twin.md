# 05 — Digital Dialysis Twin (DDT)

> Agent memory file · HD Dashboard · Last updated 2026-06-01

---

## What the Digital Twin Is

A **5-domain mechanistic simulation engine** where a single prescription change
propagates across ALL physiological subsystems simultaneously.
No black-box ML — every module uses published clinical equations.

**Primary file**: `ml_twin.py`  
**Router**: `routers/twin.py`  
**Template**: `templates/digital_twin.html`  
**DB table**: `twin_simulations`

**Clinical purpose**: "Before changing the prescription, show what Hb, Kt/V,
phosphate, and IDH risk will be next month."

---

## 5-Domain Architecture

| Domain | Equation/Model | File | Status |
|--------|---------------|------|--------|
| 1. Hb Kinetics | Bayesian conjugate Gaussian + prior from Locatelli et al. | `ml_twin.py::_calibrate_hb_kinetics()` | ✅ Active |
| 2. Dialysis Adequacy | Daugirdas 2nd-gen single pool spKt/V | `ml_twin.py::calculate_ktv_daugirdas()` | ✅ Active |
| 3. eKt/V + std Kt/V | Tattersall / Leypoldt equations | `urea_model.py::calculate_std_ktv()` | ✅ Active |
| 4. Dialyzer clearance Kd | Daugirdas Appendix C | `urea_model.py::calculate_dialyzer_clearance()` | ✅ Active |
| 5. Phosphate Kinetics | 2-pool RK4 ODE (Daugirdas / Laursen) | `phosphate_model.py::estimate_phosphate_kinetics()` | ✅ Active (with fallback) |
| 6. IDH Risk | XGBoost (26 features) | `ml_idh.py::compute_idh_risk()` | ✅ Active (heuristic if untrained) |
| 7. UF Rate Sweep | IDH swept 6–16 mL/kg/h | `ml_twin.py::simulate_uf_rate_idh_curve()` | ✅ Active |

---

## Cross-Domain Cascade Rules (Interdependencies)

```
session_h ↑  →  spKt/V ↑  (more time = more clearance)
              →  phosphate removal ↑
              →  effective UF rate ↓ (same volume over longer time → IDH risk ↓)

Qb ↑         →  dialyzer Kd ↑  →  spKt/V ↑, phosphate clearance ↑

Qd ↑         →  dialyzer Kd ↑ (modest)  →  Kt/V ↑, phosphate ↑

UF rate ↑    →  IDH risk ↑ (critical threshold: 10 mL/kg/h)

PBE dose ↑   →  pre-P ↓ (binder removes ~45 mg P per PBE unit per day)

dialysate_temp ↓  →  IDH risk ↓

ESA dose ↑   →  Hb ↑ (months 1–3 horizon)

Iron (TSAT ↑) →  Hb ↑ (months 1–3 horizon)
```

**Key constant**: `_UF_IDH_THRESHOLD_ML_KG_H = 10.0` — above this, IDH risk rises steeply.

---

## Module 1: Hb Kinetics (Bayesian Conjugate Gaussian)

### Population Priors (Bayesian starting point)
```python
# ESA gain per 1 IU/kg/wk per month
_PRIOR_K_GAIN_MU    = 0.018   # population mean
_PRIOR_K_GAIN_VAR   = 0.007²  # SD ≈ 0.007

# Iron gain per 1% TSAT increase per month
_PRIOR_K_IRON_MU    = 0.015
_PRIOR_K_IRON_VAR   = 0.006²

# Observation noise (month-to-month Hb variability)
_OBS_NOISE_VAR      = 0.25²   # SD ≈ 0.25 g/dL
```

Sources: Locatelli et al. NDT; Fishbane & Spinowitz AJKD 2018; Macdougall et al. NDT 2010.

### Calibration Function
`_calibrate_hb_kinetics(records: List[Dict])` — fits patient-specific k_gain and k_iron from monthly history using Bayesian update (closed-form Gaussian posterior, O(n)):
- When n < 3 observations: prior dominates → wider (honest) uncertainty
- When n ≥ 3: posterior narrows toward patient-specific estimate

### Prediction
`_simulate_hb_trajectory(baseline_hb, esa_iu_norm, delta_tsat, params, months=3)` — projects Hb for months 1, 2, 3 given a scenario change.

---

## Module 2 & 3: Dialysis Adequacy

### spKt/V (Daugirdas 2nd-gen single pool)
```python
def calculate_ktv_daugirdas(pre_bun, post_bun, weight_post, weight_gain, session_h):
    R = post_bun / pre_bun
    ktv = -math.log(R - 0.008 * session_h) + (4 - 3.5*R) * weight_gain / weight_post
```

### eKt/V + std Kt/V (Tattersall / Leypoldt)
`urea_model.py::calculate_std_ktv(spktv, session_h, freq_per_week)`

### Dialyzer Clearance Kd (Daugirdas Appendix C)
`urea_model.py::calculate_dialyzer_clearance(qb, qd, dialyzer_ko_a)`  
Uses blood/dialysate flow rates and membrane mass transfer coefficient.

---

## Module 4: Phosphate Kinetics

**File**: `phosphate_model.py`

### 2-Pool RK4 Model (Daugirdas / Laursen)
Two compartments:
- Extracellular pool: rapidly cleared during dialysis
- Intracellular pool: slow equilibration (rebounds 1–2 h post-session)

Parameters per patient:
- `p_preD` — pre-dialysis phosphate (mg/dL)
- `v_ec` — extracellular distribution volume
- `k_transfer` — inter-compartment rate constant
- `k_binder` — phosphate binder efficacy (PBE units)

### Fallback (Linear Estimate)
When RK4 solver diverges with extreme inputs:
```python
# _phosphate_simple_estimate()
P_post ≈ P_pre - 0.30 × Δsession_h - 0.10 × ΔPBE
```
Coefficients from published Daugirdas estimates.

---

## Module 5: IDH Risk in the Twin

`ml_idh.py::compute_idh_risk(scenario_params)` is called within `run_scenario()`.
If the XGBoost model is not trained, falls back to heuristic (UF rate threshold).

The UF rate sweep `simulate_uf_rate_idh_curve()` scans 6–16 mL/kg/h in 1.0 increments and returns the IDH probability curve — displayed as a line chart in `digital_twin.html`.

---

## `run_scenario()` — The Core Entry Point

```python
# ml_twin.py
def run_scenario(patient_id, scenario: dict, db) -> dict:
    """
    1. Load patient baseline from DB (last session + last monthly record)
    2. Apply scenario overrides (any parameter the clinician changed)
    3. Run all 5 modules
    4. Apply cross-domain cascade rules
    5. Return structured result dict
    6. Save TwinSimulation row to DB
    """
```

### Scenario Parameter Keys
```
session_h, qb_ml_min, qd_ml_min, uf_rate_ml_kg_h,
dialysate_temp_c, dialysate_sodium_meql,
esa_iu_wk, tsat_pct, binder_pbe_day,
dietary_phosphate_mg_day
```

### Output Structure
```json
{
  "hb_trajectory": [{"month": 1, "hb": 10.8, "pi_low": 10.2, "pi_high": 11.4}, ...],
  "ktv": {"sp_ktv": 1.35, "e_ktv": 1.28, "std_ktv": 2.1},
  "phosphate": {"pre_dialysis_p": 4.8, "session_removal_mg": 1200},
  "idh_risk": {"probability": 0.18, "risk_level": "Low"},
  "uf_rate_curve": [{"uf_rate": 6, "idh_prob": 0.05}, ...],
  "cascade_summary": {...}
}
```

---

## `build_twin_plotly_data()` — Chart Rendering

Converts `run_scenario()` output to JSON-serialisable Plotly traces for:
- Hb trajectory (line + shaded 80% PI band)
- Kt/V comparison (baseline vs simulated, bar chart)
- IDH risk (gauge / probability display)
- UF rate sweep (IDH risk curve, line chart)
- Phosphate card (pre-dialysis P, session removal)
- Cascade card (all 5 effects of one change, simultaneously)

---

## Digital Twin UI Parameter Mapping

From `digital_twin.html` UI to data sources:

| UI Parameter | Source in DB | Entry point |
|---|---|---|
| Duration (h) | `session_records.duration_hours` | Session entry form |
| Blood flow Qb | `session_records.blood_flow_rate` | Session entry form |
| Dialysate flow Qd | `session_records.dialysate_flow` | Session entry form |
| UF rate | `session_records.uf_rate` | Session entry form |
| Dialysate temp | `session_records.dialysate_temperature` | Session entry form |
| Dialysate Na | `session_records.dialysate_sodium` | Session entry form |
| Binder dose (PBE) | `monthly_records.phosphate_binder_dose` | Monthly entry form |
| Dietary P | `patient_meal_records.phosphorus_mg` (aggregated) | Patient portal food diary |
| ESA weekly IU | `monthly_records.epo_weekly_units` (normalised) | Monthly entry form |
| TSAT % | `monthly_records.tsat` | Monthly entry form |
| Hb | `monthly_records.hb` | Monthly entry form |
| Cardiac Output | `patient_cardiac.cardiac_output` (calculated) | Patient form |
| Access flow Qa | `access_surveillance_records.qa_ml_min` | Access surveillance form |

---

## Phase 2 Roadmap (Not Yet Built)

| Feature | Reference | Value |
|---------|-----------|-------|
| Two-compartment fluid/volume model | Abohtyra et al. IEEE TBE 2018 | 34% IDH reduction in closed-loop UF control |
| Conformal prediction intervals | MAPIE library | Distribution-free 80% PI coverage guarantee |
| Bayesian MCMC for phosphate ODE params | Bangsgaard et al. MBE 2023 | Narrower credibility intervals |
| Real-time machine data streaming | MQTT → IDH predictions every 15 min | Intra-session risk monitoring |
| Vascular access aging model | Hsieh et al. 2023, IoMT XGBoost | 90.7% precision for access failure prediction |
| Acid-base (HCO₃⁻) kinetics module | — | Dialysate bicarbonate optimisation |

---

## Known Clinical Validation Targets

| Metric | Fresenius ACM | This Implementation |
|--------|--------------|---------------------|
| Predicted Hb MAE | ~0.60–0.75 g/dL | Unknown (need backfill data) |
| IDH AUROC | (Zhang & Kotanko NDT 2023: 0.887) | Unknown (need training data) |
| Phosphate R² | (Laursen et al. 2023: 0.985) | Not yet validated |

---

## Explaining to Clinicians

**One sentence**: "Patient-specific simulator — before changing the prescription,
it shows what Hb, Kt/V, phosphate, and IDH risk will be next month."

**Key clinical analogies**:
- ODE parameters = this patient's personal dose-response curve (like a PK model fitted per patient)
- Prediction interval = "Hb will be 10.4–12.0 g/dL" — communicates uncertainty
- Cascade card = all 5 physiological effects of one prescription change, simultaneously

**Limitations to communicate**:
- ACM KDIGO rules: valid immediately (deterministic)
- ODE/Bayesian predictions: need ≥ 3 months Hb history per patient
- Not a medical device — all recommendations require clinician accept/modify/reject
