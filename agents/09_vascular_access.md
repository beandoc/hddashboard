# 09 — Vascular Access & KRCRw

> Agent memory file · HD Dashboard · Last updated 2026-06-01

---

## Vascular Access Data Model

Three levels of access data:

| Level | Table | Frequency | Purpose |
|-------|-------|-----------|---------|
| Patient-level (static) | `patient_vascular_access` | On registration / change | Access type, creation date, first cannulation, thrombosis history |
| Session-level (bedside screen) | `session_records` (access columns) | Every session | Physical exam (thrill/bruit), cannulation quality, complications |
| Formal surveillance (Doppler) | `access_surveillance_records` | Monthly / triggered | Quantitative flow, stenosis markers, recirculation |

---

## 1. Patient-Level Vascular Access (`patient_vascular_access`)

| Column | Notes |
|--------|-------|
| `access_type` | AVF / AVG / Tunnelled Catheter / Temporary Catheter |
| `access_date` | Creation date |
| `date_first_cannulation` | |
| `history_of_access_thrombosis` | Boolean — IDH model feature |
| `access_intervention_history` | Text — intervention log |
| `catheter_type` | If catheter-based access |
| `catheter_insertion_site` | Right IJV / Left IJV / Femoral / etc. |

---

## 2. Session-Level Bedside Access Screen

Captured in `session_records` per KDOQI 2019 (mandatory every session):

| Column | Values | Clinical Meaning |
|--------|--------|-----------------|
| `thrill_grade` | normal / reduced / absent | AVF flow assessment |
| `bruit_grade` | normal / reduced / absent | AVF turbulence assessment |
| `aneurysm_flag` | Boolean | Aneurysm detected on exam |
| `steal_signs_flag` | Boolean | Hand ischemia signs |
| `cannulation_attempts` | Integer 1–10 | Difficulty quantification |
| `cannulation_difficulty` | routine / difficult / failed | |
| `needle_infiltration` | Boolean | Infiltration event |

**Access recirculation (two-needle urea method):**
- `urea_peripheral_s` — systemic BUN (mmol/L)
- `urea_arterial_a` — arterial-needle BUN
- `urea_venous_v` — venous-needle BUN
- `access_recirculation_percent` — formula: (S-A)/(S-V) × 100
- `access_flow_qa` — derived access flow (mL/min)

---

## 3. Access Surveillance Form (`access_surveillance_form.html`)

**Entry point**: Button on `patient_profile.html` → Vascular Access section.  
**Router**: `routers/patients.py` (or dedicated access route)  
**Table**: `access_surveillance_records`

### Key Fields

| Field | Unit | Clinical Use |
|-------|------|-------------|
| `qa_ml_min` | mL/min | Doppler access flow — **critical for Digital Twin** |
| `recirculation_percent` | % | Access recirculation (formal measurement) |
| `psv_cm_s` | cm/s | Peak systolic velocity — stenosis marker |
| `edv_cm_s` | cm/s | End-diastolic velocity |
| `ri` | 0–1 | Resistive index (RI) — RI > 0.7 → possible stenosis |
| `stenosis_percent` | % | Diameter reduction on Doppler |
| `surveillance_date` | Date | |
| `report_notes` | Text | |

### Digital Twin Connection
`qa_ml_min` → Shunt Ratio computation: `Qa / CO`  
Where CO = `patient_cardiac.cardiac_output` (from echo LVOT method).

---

## Access Alert Logic

### KDOQI 2019 Flow Thresholds
- Qa < 600 mL/min → AVF at risk (monitor closely)
- Qa < 500 mL/min → access failure risk — referral for intervention

`avf_low_flow` alert in dashboard: `qa_ml_min < 600`

### Override Mechanism
`access_alert_overrides` table — clinician can suppress a specific alert for a specific patient for a defined period with documented rationale.

---

## KRCRw Model (`krcrw_model.py`)

**Purpose**: Estimate residual kidney creatinine clearance (KRCRw) — a component of total solute clearance in patients with some residual renal function.

### Formula (Watson/Gotch-Sargent based)
Derived from 24h urine creatinine collection or estimated from interdialytic weight gain and serum creatinine.

Input columns from `patient_renal_profile`:
- `baseline_gcr` — baseline glomerular creatinine clearance
- `baseline_vdcr` — volume of distribution for creatinine

### Clinical Significance
- KRCRw ≥ 2 mL/min contributes meaningfully to total dialysis dose
- Included in std Kt/V calculation (`urea_model.py`)
- Patients with significant RRF may tolerate lower spKt/V from machine (total adequacy maintained)

---

## Access Surveillance Service (`services/access_surveillance_service.py`)

Largest service file (59 KB). Contains:
- Access score computation (composite of flow + exam + cannulation)
- Trend analysis (Qa over time, RI over time)
- Alert generation logic (access-specific alerts beyond dashboard)
- Doppler report parsing and standardisation

---

## Vascular Access Clinical Events (`constants.py`)

Access-specific clinical events tracked in `clinical_events`:
- `"Access Thrombosis"` — creates `HospitalisationEvent` if admission required
- `"AV Fistula Revision"` / `"AV Fistula Failure"` — procedural
- `"Catheter Change"` / `"Catheter / Exit-Site Infection"` — infection marker
- `"AVF / Graft Declot"`, `"AVF / Graft Angioplasty"` — intervention (not hospitalisation)

These feed the `recent_infection_events` feature in the deterioration model (Catheter / Exit-Site Infection).

---

## Cardiac Output Calculation (Echo-derived)

Entered in `patient_form.html` → stored in `patient_cardiac`:

```
CO (L/min) = SV × HR / 1000
SV (mL)    = CSA × VTI
CSA (cm²)  = π × (LVOT_diameter/2)²  = 0.785 × LVOT_diameter²
```

Where:
- `LVOT_diameter` — cm, measured by echo in PLAX view
- `LVOT_VTI` — cm, Doppler envelope area in LVOT (5-chamber view)
- `HR` — heart rate (bpm)

All three inputs captured in `patient_cardiac` table.
`stroke_volume` and `cardiac_output` auto-calculated and stored.

### Use in Digital Twin
`cardiac_output` → denominator for shunt ratio (Qa / CO).  
Shunt ratio > 30% → high-output cardiac failure risk from AVF.
