
# Digital Dialysis Twin — Implementation Plan v2
> Based on: Deep-research report "Digital Twins in Hemodialysis: Current State and Future Directions" vs. existing DDT (agents/05_digital_twin.md)  
> Date: 2026-06-02  
> Author: Claude Code gap analysis + clinical review

---

## Executive Summary

The HD Dashboard DDT is **ahead of most academic prototypes** in mechanistic depth (5-domain physics, Bayesian Hb, 2-pool phosphate RK4, XGBoost IDH). The research report confirms our architecture matches the Fresenius grey-box benchmark. However, four **clinical safety gaps** need immediate fixes before new features are added, and five **high-impact extensions** are justified by the research evidence.

---

## Phase 0 — Clinical Safety Fixes (Do These First)
*No new models. Fix existing outputs that could mislead clinicians.*

### 0.1 — UF Rate Mortality Threshold Annotation
**Evidence**: Castro & Wu NDT 2024 (N=805 Spanish HD patients) identifies **< 4 mL/kg/h** as the mortality-reduction UF threshold. Current DDT sweep starts at 6 mL/kg/h and flags steep IDH risk only above 10 mL/kg/h. Clinicians optimising to "6–8 mL/kg/h" may still be above the mortality threshold.

**Files to change**:
- `ml_twin.py::simulate_uf_rate_idh_curve()` — add `mortality_threshold_ml_kg_h = 4.0` to returned dict
- `ml_twin.py::build_twin_plotly_data()` — add vertical reference line at 4 mL/kg/h on UF sweep chart
- `templates/digital_twin.html` — render new annotation as a labelled dashed line with citation

**Acceptance criterion**: UF sweep chart displays a red dashed vertical line at 4 mL/kg/h labelled "Mortality threshold (Castro & Wu NDT 2024)".

---

### 0.2 — IDH Heuristic Fallback Warning
**Evidence**: When `models/idh_model.joblib` is absent, `ml_idh.py` silently returns a UF-rate-only probability — no access to the 9 comorbidity features (CHF, CAD, LV dysfunction) that are the dominant IDH risk predictors. A CHF patient could receive "Low" risk from the heuristic.

**Files to change**:
- `ml_idh.py` — add a `model_is_heuristic: bool` field to every returned probability dict
- `routers/twin.py` — propagate `model_is_heuristic` flag through run_scenario() response
- `templates/digital_twin.html` — show amber warning banner: "IDH risk estimate uses UF-rate heuristic only. Comorbidity-adjusted prediction requires ≥500 session records with BP nadir data."

**Acceptance criterion**: Banner is visible whenever IDH model is untrained. No warning when XGBoost model is loaded.

---

### 0.3 — Mortality Risk "Literature Calibration" UI Warning
**Evidence**: `ml_risk.py` uses `_INDIAN_CAL_SLOPE = 0.72, _INDIAN_CAL_INTERCEPT = -0.40` from DOPPS India Phase 5 aggregate data, not this center's cohort. High-risk populations (high DM/cardiac comorbidity) may be systematically underestimated until local Platt scaling is fitted (≥50 deaths).

**Files to change**:
- `routers/analytics.py` (or equivalent mortality risk endpoint) — add `calibration_source: "literature_dopps_india"` field to response
- Analytics dashboard template — show footnote: "Mortality risk calibration uses published Indian HD population parameters. Local recalibration requires ≥50 confirmed deaths."

**Acceptance criterion**: Mortality risk dashboard shows calibration source footnote.

---

### 0.4 — Wire Dietary Phosphate to run_scenario() Baseline
**Evidence**: Patient meal logs exist in `patient_meal_records.phosphorus_mg` (aggregated by `services/nutrition_service.py`) but are NOT auto-populated into the Digital Twin phosphate model baseline. The phosphate RK4 model uses a manually entered or default `dietary_phosphate_mg_day`, causing systematic underestimation of pre-dialysis phosphate for high-dietary-phosphate patients.

**Files to change**:
- `ml_twin.py::run_scenario()` — before applying scenario overrides, query `services/nutrition_service.py` for the patient's 7-day rolling mean dietary_phosphate_mg_day; use as default baseline if the scenario dict does not override it
- `routers/twin.py` — add `dietary_phosphate_source: "meal_logs" | "manual_entry" | "default_1200mg"` to response

**Acceptance criterion**: When a patient has ≥3 meal diary entries in the last 30 days, the phosphate simulation baseline is sourced from those records. `dietary_phosphate_source` field confirms the source.

---

## Phase 1 — High-Impact Extensions (Next 4–8 Weeks)
*Research-backed features with clear clinical evidence.*

### 1.1 — Conformal Prediction Intervals on IDH XGBoost (MAPIE)
**Evidence**: Research report explicitly recommends MAPIE (distribution-free 80% PI coverage guarantee) for IDH uncertainty quantification. Currently only Hb trajectory has prediction intervals — IDH returns a single point probability.

**Approach**:
- Add `mapie` to `requirements.in`
- In `ml_idh.py::train_idh_model()`: wrap fitted XGBoost with `MapieClassifier(method="score", cv=5)`
- Return `idh_prob_lower`, `idh_prob_upper` alongside `idh_prob` in inference output
- Add to `ml_twin.py::build_twin_plotly_data()`: render IDH gauge with confidence band

**Files**:
- `ml_idh.py` — model training and inference
- `ml_twin.py` — build_twin_plotly_data() IDH gauge update
- `requirements.in` — add mapie>=0.9

**Acceptance criterion**: IDH probability is reported as `0.22 [0.14–0.31]` (point estimate + 80% PI). PI width narrows as more session records are collected.

---

### 1.2 — UF Sweep Range Extension to 4 mL/kg/h
**Evidence**: Castro & Wu NDT 2024 shows mortality risk rises above 4 mL/kg/h UF rate. Current sweep starts at 6 mL/kg/h, leaving the mortality-reduction range entirely off the chart.

**Files to change**:
- `ml_twin.py::simulate_uf_rate_idh_curve()` — change lower bound from 6.0 to 3.5 mL/kg/h
- Ensure IDH heuristic and XGBoost model are calibrated for sub-6 UF rates (the 26-feature XGBoost should handle this; the UF-rate heuristic floor may need review)

**Acceptance criterion**: UF sweep chart spans 3.5–16 mL/kg/h with the mortality threshold (4 mL/kg/h) and IDH risk threshold (10 mL/kg/h) both annotated.

---

### 1.3 — ML Model Auto-Restore from `model_binary` on Boot
**Evidence**: Internal operational gap (not from research report). Render's ephemeral filesystem loses `.pkl` files on container restart. Models must be retrained after every deploy, breaking continuous IDH and deterioration risk predictions.

**Files to change**:
- `main.py::startup_event()` — add model restore loop: for each model name in `["idh_v1", "deterioration_v1", "acm_v1"]`, check if `.pkl` file exists on disk; if not, query `model_artifacts` table for `model_binary` bytes and write to disk
- Add `services/model_registry.py::restore_all_models_from_db()` helper
- Protect against race condition: only restore if `model_binary` IS NOT NULL in DB

**Acceptance criterion**: After container restart with no `.pkl` files, startup log shows "Restored idh_v1 from database (147 KB)" for each previously trained model.

---

### 1.4 — Patient-Facing DT Summary Card
**Evidence**: Research report identifies patient education and engagement as a key DT use case (Vallée 2023). The patient portal has a meal diary and symptom log but no exposure to their own simulation results.

**Approach** (read-only, no simulation controls for patient):
- Add `/patient/my-twin` route in `routers/patient_portal.py`
- Display last simulation result (from `twin_simulations` table) in plain language
- Show: "Your dialysis is removing enough waste (Kt/V: 1.35 ✓)", "Your blood count is predicted to be 10.8 g/dL next month", "Your IDH risk at current settings is Low"
- No parameter controls for patient — clinician-only

**Files**:
- `routers/patient_portal.py` — new `/my-twin` route
- `templates/patient_twin_card.html` — new template, dark glassmorphic theme

**Acceptance criterion**: Patient login can see plain-language summary of their most recent simulation. No simulation controls exposed.

---

## Phase 2 — Medium-Impact Extensions (8–16 Weeks)
*Significant engineering effort; validated clinical benefit in literature.*

### 2.1 — Two-Compartment Fluid/Volume Model (Abohtyra 2018)
**Evidence**: Abohtyra et al. IEEE TBE 2018 showed **34% IDH reduction** with closed-loop UF control using a two-compartment plasma refilling model. This is the most evidence-backed IDH prevention intervention available.

**Architecture**:
- New file: `fluid_volume_model.py`
- Model: plasma refilling rate + interstitial fluid compartment; parameterized by patient weight, hematocrit, and session UF rate
- Integrate into `ml_twin.py::run_scenario()` as Domain 6: `fluid_volume`
- Output: `plasma_refilling_rate`, `predicted_rbv_at_session_end`, `optimal_uf_rate` (rate that keeps RBV above threshold)
- Update `agents/05_digital_twin.md` to reflect 6-domain architecture

**Files**:
- New: `fluid_volume_model.py`
- Modified: `ml_twin.py` — integrate new domain into run_scenario()
- Modified: `templates/digital_twin.html` — add RBV curve to scenario output
- New migration: `alembic/versions/` — add `fluid_volume_params` JSONB column to `twin_simulations`

**Acceptance criterion**: Scenario output includes `fluid_volume.optimal_uf_rate_ml_kg_h` — the UF rate at which predicted RBV remains above 85% of baseline.

---

### 2.2 — Vascular Access Time-to-Failure Model (Hsieh 2023)
**Evidence**: Hsieh et al. 2023 IoMT XGBoost achieves 90.7% precision for access failure prediction using longitudinal Qa trend + recirculation + pressure readings.

**Architecture**:
- New file: `services/access_failure_model.py`
- Features: rolling Qa trend (last 6 surveillance records), delta_Qa (rate of change), recirculation %, PSV/EDV ratio, time-since-creation, access_type
- Model: XGBoost with Platt calibration → probability of failure within 90 days
- Output: displayed on vascular access dashboard as a risk timeline

**Files**:
- New: `services/access_failure_model.py`
- Modified: `routers/access.py` — add `/access/failure-risk/{patient_id}` endpoint
- Modified: `templates/vascular_access.html` — add 90-day failure probability badge
- New Celery task: weekly `task_compute_access_failure_risk` for all patients with ≥3 surveillance records

**Acceptance criterion**: Patients with ≥3 Doppler surveillance records show a "90-day failure risk" probability badge on their access page.

---

### 2.3 — Bayesian MCMC for Phosphate ODE Parameters (Bangsgaard 2023)
**Evidence**: Bangsgaard et al. MBE 2023 shows Bayesian MCMC on the 2-pool phosphate ODE achieves R²=0.985 and much narrower credibility intervals compared to deterministic parameter fitting.

**Architecture**:
- Add `pymc` or `numpyro` to `requirements.in`
- New: `phosphate_mcmc.py` — MCMC sampler for `v_ec`, `k_transfer`, `k_binder` per patient
- Run as background Celery task (weekly, per patient with ≥3 monthly phosphate records)
- Store posterior samples as JSONB in patient record; use posterior mean + HDI for prediction intervals on phosphate forecast

**Files**:
- New: `phosphate_mcmc.py`
- Modified: `phosphate_model.py` — accept pre-fitted MCMC posterior as optional parameter override
- Modified: `celery_app.py` — add weekly `task_mcmc_phosphate_calibration`
- Modified: `agents/05_digital_twin.md` — update phosphate model section

**Acceptance criterion**: Phosphate forecast card in `digital_twin.html` shows credibility interval: "Pre-dialysis phosphate: 4.8 mg/dL [4.1–5.6, 80% HDI]".

---

## Phase 3 — Long-Term / Infrastructure (16+ Weeks)
*Major architectural changes. Only begin after Phase 0–2 are complete.*

### 3.1 — Real-Time MQTT Intra-Session IDH Prediction
**Evidence**: Fresenius ACM AUROC 0.887 benchmark is for **intra-session** IDH predictions updated every 15 minutes from machine telemetry. Current DDT is pre-session only. This is the most important architectural gap for hemodynamic safety.

**Approach**:
- Deploy MQTT broker (Eclipse Mosquitto or HiveMQ) in Render infrastructure
- Define message schema: machine → MQTT → Redis → Celery task → IDH re-inference
- New: `services/mqtt_ingestion.py` — MQTT subscriber, validates and stores intra-session readings
- New: `tasks/intra_session_idh.py` — Celery task triggered per message, runs IDH inference with updated features
- WebSocket or SSE push to bedside screen (`templates/bedside_screen.html`)

**Files**: Major architectural addition — 4+ new files, 2 new Render services (MQTT broker, WebSocket server)

**Acceptance criterion**: During a live dialysis session, IDH risk probability on the bedside screen updates every 15 minutes from machine telemetry without clinician action.

---

### 3.2 — HL7 FHIR Data Pipeline
**Evidence**: Research report identifies HL7/FHIR interoperability as a prerequisite for clinical deployment at scale and for regulatory compliance.

**Approach**:
- Implement FHIR R4 export for `Patient`, `Observation`, `MedicationAdministration`, and `DiagnosticReport` resource types
- Use `fhir.resources` Python library
- New: `routers/fhir.py` — read-only FHIR endpoints under `/fhir/r4/`
- Enables hospital EHR pull (labs auto-populating into monthly_records) and audit trail for regulatory purposes

**Acceptance criterion**: GET `/fhir/r4/Patient/{id}/Observation` returns compliant FHIR R4 JSON for all lab results for that patient.

---

## Implementation Priority Matrix

| # | Feature | Phase | Clinical Impact | Effort | Evidence Strength |
|---|---------|-------|----------------|--------|------------------|
| 0.1 | UF mortality threshold annotation | 0 | HIGH (safety) | XS | Castro & Wu NDT 2024 |
| 0.2 | IDH heuristic fallback warning | 0 | HIGH (safety) | XS | Internal audit |
| 0.3 | Mortality calibration UI warning | 0 | MEDIUM (safety) | XS | DOPPS India |
| 0.4 | Wire dietary phosphate to run_scenario | 0 | MEDIUM (safety) | S | Internal gap |
| 1.1 | MAPIE conformal PI on IDH | 1 | HIGH | S | Research report |
| 1.2 | UF sweep to 4 mL/kg/h lower bound | 1 | HIGH | XS | Castro & Wu NDT 2024 |
| 1.3 | Auto-restore models from DB on boot | 1 | HIGH (ops) | S | Internal gap |
| 1.4 | Patient-facing DT summary card | 1 | MEDIUM | M | Vallée 2023 |
| 2.1 | Two-compartment fluid/volume model | 2 | HIGH | L | Abohtyra IEEE TBE 2018 (34% IDH reduction) |
| 2.2 | Access failure time-to-failure model | 2 | HIGH | M | Hsieh 2023 (90.7% precision) |
| 2.3 | Bayesian MCMC phosphate ODE | 2 | MEDIUM | M | Bangsgaard MBE 2023 (R²=0.985) |
| 3.1 | MQTT intra-session IDH streaming | 3 | HIGH | XL | Fresenius ACM (AUROC 0.887) |
| 3.2 | HL7 FHIR pipeline | 3 | LOW (now) | XL | Regulatory |

**Effort scale**: XS < 1 day | S = 1–3 days | M = 1–2 weeks | L = 2–4 weeks | XL = 1–2 months

---

## Data Collection Priorities (Parallel Track)

These are not coding tasks — they are clinical workflow requirements that unlock model training:

| Model | Data needed | Threshold | Action |
|-------|------------|-----------|--------|
| IDH XGBoost | `bp_nadir_sys` recorded in every session | ≥500 sessions | Make BP nadir a mandatory bedside field |
| Deterioration LR | Hospitalization outcomes in `monthly_records` | ≥50 events | Ensure every admission is recorded |
| Mortality recalibration | Confirmed deaths in `patient_outcomes` | ≥50 deaths | Long-term follow-up; no shortcut |
| ACM residual MLP | Patient-months of Hb + ESA + iron records | ≥200 patient-months | Sustained data entry (12–18 months) |
| Access failure XGBoost | Doppler Qa + recirculation in surveillance form | ≥3 records/patient | Add Doppler to routine surveillance protocol |

---

## Files DO NOT Touch
Per CLAUDE.md protected file list — implement all new features as new modules:
- `dashboard_logic.py` — clinical calculations
- `database.py` — SQLAlchemy models (add migrations, don't modify)
- `alerts.py` — KDIGO alert rules
- `ml_analytics.py` — core ML risk engines
- `dynamic_vars.py` — dynamic patient variables

---

## References

- Abohtyra et al. IEEE Trans Biomed Eng 2018 — Two-compartment UF control, 34% IDH reduction
- Bangsgaard et al. Math Biosci Eng 2023 — Bayesian MCMC phosphate ODE, R²=0.985
- Castro & Wu NDT Abstract 2024 — UF rate < 4 mL/kg/h mortality threshold, N=805
- Fuertinger et al. CJASN 2024 — Fresenius ACM grey-box architecture, MAE < 0.75 g/dL target
- Hsieh et al. 2023 IoMT XGBoost — Access failure prediction, 90.7% precision
- Laursen et al. 2023 — Phosphate R² validation
- Pan et al. 2025 — HDT (Human Digital Twin) integration framework
- Vallée 2023 — DT taxonomy, patient engagement, IoMT integration
- Zhang & Kotanko NDT 2023 — IDH prediction AUROC 0.887 (Fresenius benchmark)
