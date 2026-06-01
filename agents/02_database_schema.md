# 02 — Database Schema Reference

> Agent memory file · HD Dashboard · Last updated 2026-06-01
> Current Alembic head: `e44246158d0d`

---

## How the ORM is Organised

All models live in `db/models/`.  `database.py` at root is a **legacy re-export** of every model class plus `SessionLocal` and `Base` — import from there for backward compatibility, but for new code prefer importing directly from `db/models/<file>.py`.

---

## Core Patient Graph

### `patients` — identity + scheduling

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK Integer | |
| `hid_no` | String UNIQUE | Hospital ID (e.g. `20131542744016`) |
| `name` | String | Full name |
| `sex` | String | |
| `age` | Integer | |
| `height` | Float | cm |
| `dry_weight` | Float | kg (prescription baseline) |
| `hd_frequency` | Integer | Sessions/week (default 2) |
| `hd_day_1/2/3` | String | Scheduled days |
| `hd_slot_1/2/3` | String | Scheduled time slots |
| `is_active` | Boolean | Soft-delete |
| `whatsapp_notify` | Boolean | Opt-in for WhatsApp alerts |

**Relationships (1:1 satellites):**
- `credentials` → `patient_credentials` (login_username, hashed_password, reset_token)
- `comorbidity_profile` → `patient_comorbidities`
- `renal_profile` → `patient_renal_profile`
- `viral_markers_` → `patient_viral_markers`
- `vaccination` → `patient_vaccination`
- `vascular_access` → `patient_vascular_access`
- `cardiac` → `patient_cardiac` (EF, LVOT diameter, LVOT VTI, HR, SV, CO)
- `outcomes` → `patient_outcomes`

**Relationships (1:many):**
`records`, `sessions`, `interim_labs`, `meal_records`, `symptom_reports`, `reminders`, `dry_weight_assessments`, `events`, `research_records`, `hospitalisations`, `access_episodes`, `access_events`, `surveillance_records`, `access_alert_overrides`

---

### `patient_comorbidities`

Key columns used by ML models:
- `dm_status` — string ("Type 1", "Type 2", "No", etc.)
- `cad_status` — Boolean
- `chf_status` — Boolean
- `af_status` — Boolean (IDH predictor)
- `charlson_comorbidity_index` — Integer

---

### `patient_cardiac`

Expanded for Cardiac Output computation:
- `ejection_fraction` — Float (default 60.0 %)
- `lvot_diameter` — Float (cm) — needed for SV computation
- `lvot_vti` — Float (cm) — Doppler VTI
- `heart_rate` — Integer (bpm)
- `stroke_volume` — Float (mL) — auto-computed from LVOT diameter × VTI × π/4
- `cardiac_output` — Float (L/min) — SV × HR / 1000

---

## Monthly Clinical Records

### `monthly_records`

One row per patient per calendar month (e.g. `2026-05`).
Entered via `POST /entry/{patient_id}`.

Key lab columns used by ML:
- `hb` — Haemoglobin (g/dL)
- `albumin`, `phosphorus`, `calcium`, `crp`, `wbc_count`
- `serum_ferritin`, `tsat`, `serum_iron`, `tibc`
- `serum_potassium`, `serum_sodium`, `serum_bicarbonate`
- `urr`, `single_pool_ktv` — dialysis adequacy
- `idwg` — interdialytic weight gain (kg)
- `target_dry_weight`

ESA tracking columns:
- `epo_weekly_units` — EPO-equivalent IU/week (normalised from any ESA formulation)
- `epo_mircera_dose` — raw Mircera (C.E.R.A.) dose if applicable
- `darbepoetin_dose` — raw darbepoetin dose
- `epo_alpha_dose` — raw epoetin-alpha dose
- `iv_iron_dose`, `oral_iron_dose`

**IMPORTANT for ESA normalisation:** `ml_esa.py::_resolve_weekly_iu_sc()` converts all formulations to EPO-equivalent IU/week:
- Epoetin-alpha/beta: 1:1 with IU
- Darbepoetin: 1 µg = 200 IU EPO equivalent
- Mircera (Pegepoetin): 1 µg = 75 IU EPO equivalent (monthly → weekly ÷ 4.33)

---

## Session Records

### `session_records`

One row per dialysis session (typically 2–3×/week).

Key columns:
- `session_date`, `record_month`, `patient_id`
- `duration_hours`, `duration_minutes`
- `weight_pre`, `weight_post`
- `uf_volume`, `uf_rate` — mL/kg/h (critical for IDH model)
- `blood_flow_rate` — Qb (mL/min)
- `dialysate_flow` — Qd (mL/min)
- `dialysate_temperature` — °C
- `dialysate_sodium` — mEq/L
- `bp_pre_sys`, `bp_nadir_sys`, `bp_post_sys` — BP monitoring
- `idh_episode` — Boolean (IDH outcome label)
- `access_recirculation_percent`, `access_flow_qa` — Doppler/recirculation
- Bedside access screen: `thrill_grade`, `bruit_grade`, `aneurysm_flag`, `steal_signs_flag`
- Cannulation: `cannulation_attempts`, `cannulation_difficulty`, `needle_infiltration`
- Symptoms: `muscle_cramps`, `nausea_vomiting`, `chest_pain`, `arrhythmia`
- `antihypertensive_taken_prehd` — IDH feature
- `saline_bolus_count` — IDH intervention marker
- `intradialytic_meals_eaten` — IDH feature

---

## ML & Analytics Tables

### `ml_predictions`
One row per inference call. `observed_outcome` back-filled by weekly Celery task.
`input_feature_hash` = SHA-256 of sorted feature JSON (dedup/audit).
`patient_id_hash` = HMAC-SHA256(patient_id) — for cross-model analytics without raw FK join.

### `ml_model_metrics`
Nightly aggregate stats per model (`deterioration_v1`, `idh_v1`, `acm_v1`).
Key: `calibration_slope` (ideal 1.0), `drift_flagged` (threshold ±0.15).

### `model_artifacts`
Registry of trained model .joblib files.  **Inference is refused when no row exists for a given `model_name`.**
`model_binary` (LargeBinary) stores the joblib bytes — survives container redeploys on ephemeral filesystems.

### `acm_recommendations`
One row per patient per month.
- `predicted_hb_1/2/3mo` — ML Hb forecast
- `esa_action`, `esa_change_pct`, `recommended_iu_sc`
- `iron_action`
- `clinician_decision` — `accept | modify | reject`
- `observed_hb_1mo`, `observed_hb_3mo`, `hb_prediction_mae_1mo` — back-filled by Celery

### `twin_simulations`
One row per Digital Twin scenario run.
- `scenario_json` — input parameter set
- `hb_sim_json`, `ktv_sim_json`, `idh_sim_json`, `uf_curve_json` — outputs
- `adopted` — did the clinician apply this scenario?

### `patient_feature_snapshot`
Materialised feature store. One row per (patient_id, as_of_month).
- `feature_vector` — JSONB (12 features for deterioration model)
- `feature_hash` — SHA-256 (training/serving parity check)
- `stale` — Boolean (set true when underlying data changes)

### `audit_logs`
Immutable PHI write audit trail. **Never update or delete rows here.**
`patient_id_hash` = HMAC-SHA256(patient_id) for privacy.

### `clinical_override_logs`
Records when a clinician overrides a model prediction.
`override_direction`: `higher_risk | lower_risk | agree_but_act_differently`
This is the most valuable retraining signal in the system.

---

## Vascular Access Tables

### `access_surveillance_records`
Formal Doppler ultrasound records (from `access_surveillance_form.html`).
- `qa_ml_min` — Doppler access flow rate (mL/min) — fed to Digital Twin
- `recirculation_percent`
- `psv_cm_s`, `edv_cm_s`, `ri` — stenosis markers

### `access_episodes`
Access intervention history (thrombosis, angioplasty, revision).

### `access_events`
Granular per-session access events.

---

## Nutrition Tables

### `patient_meal_records`
Daily food diary entries from the patient portal.
- `total_calories_kcal`, `protein_g`, `potassium_mg`, `phosphorus_mg`
- `dietary_phosphorus_mg` — to be aggregated as 24h/3-day average

**Digital Twin integration:** `dietary_phosphorus_mg` from meal records feeds the phosphate kinetics model. Aggregation logic in `services/nutrition_service.py`.

### `patient_symptom_reports`
Post-dialysis patient-reported outcomes (linked to `session_records`).

---

## Alembic Migrations

Migrations live in `alembic/versions/`.  Key milestones:

| Migration ID | What it adds |
|---|---|
| `0018_acm_twin_tables` | `acm_recommendations`, `twin_simulations` |
| `e44246158d0d` | Current HEAD (check `alembic_version` table) |

**Never run `alembic` commands that inspect the live schema during restricted execution** — use `psql` or `sqlalchemy.inspect` carefully.  
Pre-deploy: `python scripts/pre_deploy.py` runs `alembic upgrade head`.

---

## Key Indexes for Performance

```sql
-- Session analytics (critical for dashboard speed)
ix_session_records_patient_month  (patient_id, record_month)
ix_session_record_month_only       (record_month)

-- Interim labs
ix_interim_patient_month           (patient_id, record_month)
ix_interim_record_month_only       (record_month)

-- ML predictions
(patient_id), (model_name), (input_feature_hash), (created_at)
```
