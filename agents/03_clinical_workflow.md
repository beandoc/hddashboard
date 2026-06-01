# 03 — Clinical Workflow & Information Architecture

> Agent memory file · HD Dashboard · Last updated 2026-06-01

---

## Patient Lifecycle States

```
Registration → Active HD Patient → Deactivated
                     ↓
              (Transfer | Transplant | Death | Withdrawal)
```

- `Patient.is_active = True` — active cohort, appears in dashboard
- Deactivation flow in `routers/patients.py` — writes `patient_outcomes` row
- Transplant/transfer patients remain in DB for audit; excluded from ML training cohorts by `is_active` filter

---

## Core Clinical Data Types

### 1. Monthly Records (`monthly_records`)
- **Frequency**: Once per calendar month, entered by staff
- **Entry point**: `GET/POST /entry/{patient_id}` → `entry_form.html`
- **Contains**: All lab values, ESA/iron doses, weight, KDOQI adequacy (Kt/V, URR), hospitalisations
- **Role in ML**: Primary training dataset for ACM, deterioration risk, and mortality risk models

### 2. Session Records (`session_records`)
- **Frequency**: Every dialysis session (2–3×/week)
- **Entry point**: `routers/sessions.py`
- **Contains**: Machine prescription, vitals, intradialytic events, UF data, BP monitoring
- **Role in ML**: Primary training dataset for IDH model; feeds Digital Twin baseline

### 3. Clinical Events (`clinical_events`)
- **Entry point**: `GET/POST /events/{patient_id}` → `events.html`
- **Structured taxonomy**: 5 groups × ~40 event types (see `constants.py`)
- **Hospitalisations**: Automatically creates `hospitalisation_events` row when event_type is in `PROCEDURE_EVENT_TYPES` exclusion set
- **Role in ML**: `num_recent_hospitalizations_90d`, `recent_infection_events` features for deterioration model

### 4. Medication Reconciliation (`med_recon.html`)
- **Entry point**: `GET/POST /med-recon/{patient_id}`
- **Contains**: Current medications, dose, route, frequency

### 5. Fluid Status (`fluid_status.html`)
- **Entry point**: `GET/POST /fluid/{patient_id}`
- **Contains**: Fluid overload assessment, oedema grade, lung auscultation
- **Feeds**: Digital Twin UF module inputs

### 6. Access Surveillance (`access_surveillance_form.html`)
- **Entry point**: Button on `patient_profile.html` → Vascular Access section
- **Contains**: Formal Doppler ultrasound reports (`AccessSurveillanceRecord`)
- **Key clinical values**: `qa_ml_min` (access flow), recirculation %, stenosis markers
- **Digital Twin connection**: `qa_ml_min` → shunt ratio (Qa/CO), used in vascular access domain

---

## KDIGO Clinical Targets (Hard-coded in `constants.py` + ML models)

| Parameter | Target | Alert Threshold |
|-----------|--------|-----------------|
| Haemoglobin | 10.0–11.5 g/dL | < 10.0 g/dL (alert), > 13.0 g/dL (hold ESA) |
| Albumin | ≥ 3.5 g/dL | < 3.5 g/dL alert |
| Phosphorus | 3.5–5.5 mg/dL | > 5.5 mg/dL alert |
| TSAT | 20–30% | < 20% → consider IV iron |
| Ferritin | 200–800 µg/L | > 800 µg/L → hold IV iron |
| spKt/V | ≥ 1.2 | < 1.2 alert |
| URR | ≥ 65% | < 65% alert |
| IDWG | ≤ 2.5 kg | > 2.5 kg alert |
| UF rate | < 10 mL/kg/h | ≥ 10 mL/kg/h → IDH risk |
| iCa | 1.15–1.4 mmol/L | Out of range alert |

---

## ESA Formulation Normalisation

All ESA doses are converted to **EPO-equivalent IU/week SC** before entering any ML model.
Conversion logic: `ml_esa.py::_resolve_weekly_iu_sc(record)`.

| Formulation | Conversion factor |
|-------------|------------------|
| Epoetin-alpha / beta | 1 IU = 1 IU EPO-equiv |
| Darbepoetin | 1 µg = 200 IU EPO-equiv |
| Mircera / Pegepoetin | 1 µg = 75 IU EPO-equiv; monthly dose ÷ 4.33 for weekly |

**ERI** (Erythropoiesis Resistance Index) = EPO IU/week / weight(kg) / Hb(g/dL).
ERI > 15 IU/kg/wk/g/dL = hypo-response flag.

---

## Alert Logic (`alerts.py`)

Alerts are generated from the monthly record for each patient.  All alert checks are deterministic KDIGO rules — no ML involved.

Active alert types:
- `hb_low` — Hb < 10.0 g/dL
- `albumin_low` — Albumin < 3.5 g/dL
- `phos_high` — Phosphorus > 5.5 mg/dL
- `ca_low` — Calcium < 8.4 mg/dL
- `idwg_high` — IDWG > 2.5 kg
- `non_avf` — Patient on catheter (not AVF/AVG)
- `epo_hypo` — High ERI despite ESA therapy
- `iv_iron_rec` — TSAT < 20% or Ferritin < 200

Delivery channels:
- WhatsApp (Twilio) — `task_send_bulk_whatsapp` Celery task
- Ward email — `task_send_ward_email` Celery task (HTML report)
- Daily data-integrity email — 06:00 UTC nightly

---

## Variable Manager (`/variables/manager`)

Allows mapping of non-standard lab names to canonical monthly_record fields.
`constants.py::VAR_TO_MONTHLY` is the canonical name map.
`dynamic_vars.py` handles custom variable definitions per unit.

---

## Patient Portal (`routers/patient_portal.py`)

Separate interface for patients (not clinical staff).
- Auth: `user_type = "patient"` in session cookie
- Entry: `POST /login` with `hid_no` as username
- Features: Symptom reporting, meal diary (food recall), appointment view, reminder preferences
- **Dietary phosphate pipeline**: Patient enters 24h / 3-day food recall → `services/nutrition_service.py` computes `dietary_phosphorus_mg` per day → averaged and stored in `monthly_records` (or pulled directly into Digital Twin phosphate model)

---

## Research Module (`routers/research.py`)

Separate data layer for IRB-approved research projects.
- `research_records` table — deidentified, linkable to patients by `patient_id`
- `research_projects` table — project metadata, IRB reference
- Access: Staff with `role = "admin"` or explicit research permission

---

## Admin Workflows (`routers/admin.py`)

Key admin capabilities:
- `POST /admin/train-deterioration-model` — triggers `task_train_deterioration_model` Celery task
- `POST /admin/train-idh-model` — triggers `task_train_idh_model` Celery task
- `GET /admin/model-status` — returns model artifact metadata
- Database export (JSON backup)
- User management (create/edit/deactivate staff users)
- Alembic migration trigger (if `MIGRATE_SECRET` is set)

---

## ICD-10 Integration

- `GET /icd` → `icd_lookup.html` — search-driven ICD-10 code lookup
- Hospitalisation events can store `hospitalization_icd_code` from the entry form
- Used in deterioration model label: hospitalization = `hospitalization_this_month OR hospitalization_icd_code IS NOT NULL`

---

## Schedule / Appointment System (`routers/schedule.py`)

- HD schedule stored on Patient: `hd_day_1/2/3`, `hd_slot_1/2/3`, `hd_frequency`
- Schedule reminder WhatsApp: `task_send_schedule_reminder` Celery task
- Visual calendar in `schedule.html`

---

## OCR Integration (`routers/ocr.py` / `services/ocr_service.py`)

- Uses `pytesseract` + `google-genai` for lab report parsing
- Extracts values from uploaded report images into `monthly_records`
- Triggered from the entry form "Upload Report" button
