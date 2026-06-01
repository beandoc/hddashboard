# 08 — Analytics, Alerts & Cohort Intelligence

> Agent memory file · HD Dashboard · Last updated 2026-06-01

---

## Analytics Architecture

```
dashboard_logic.py     — synchronous computation for the Jinja2 dashboard
ml_analytics.py        — cohort-level ML: mortality risk, trends, composite scoring
bayesian_analytics.py  — Bayesian trend analysis (posterior Hb trends)
ml_trends.py           — time-series trend extraction utilities
routers/analytics.py   — 85 KB router (largest file) — all /analytics/* routes
```

---

## Dashboard KPIs (`dashboard_logic.py::compute_dashboard()`)

Called at startup (warm-up thread) and per request (cached 5 min).

Returns `data` dict with two top-level keys:

### `data["alerts"]` — Clinical Alert Counts
| Key | Definition |
|-----|-----------|
| `hb_low` | Hb < 10.0 g/dL |
| `albumin_low` | Albumin < 3.5 g/dL |
| `phos_high` | Phosphorus > 5.5 mg/dL |
| `ca_low` | Calcium < 8.4 mg/dL |
| `idwg_high` | IDWG > 2.5 kg |
| `non_avf` | Access type ≠ AVF/AVG |
| `epo_hypo` | ESA hypo-response (high ERI) |
| `iv_iron_rec` | TSAT < 20% or Ferritin < 200 |

### `data["metrics"]` — Unit-wide Metrics
```
total_patients, male_patients, female_patients
hb_high (>13 g/dL), hb_variability_high
adherence_risk, ipth_very_high, infectious_hd
avf_low_flow, transplant_prospects, cadaveric_listed
missing_records (patients with no record for current month)
trend_hb, trend_albumin, trend_phosphorus (3-month arrays)
avg_hb (unit-wide mean)
epo_hypo, epo_hypo_r2, epo_hypo_r3 (escalating ERI thresholds)
```

---

## Mortality Risk (`ml_analytics.py`)

### `get_all_patients_mortality_risk(db)` → `List[dict]`
Runs Xu et al. XGBoost + Indian recalibration for every active patient.
Results cached in `_ML_ANALYTICS_CACHE["high_risk_count"]` (5 min TTL).

### `get_high_risk_mortality_count(db)` → `int`
Used in dashboard badge for doctor-role users only.

### `run_cohort_analytics(db)` → `dict`
Aggregates:
- Hb distribution (bins 7–13+ g/dL)
- ESA/iron protocol adherence rate
- KDOQI target achievement rate per parameter
- KDOQI composite score distribution
- IDH event rate (% sessions with IDH)
- Mortality risk distribution (Low/Moderate/High patient counts)

---

## Bayesian Analytics (`bayesian_analytics.py`)

Posterior Hb trend analysis for the cohort:
- Uses conjugate Gaussian posterior on month-to-month Hb changes
- Provides credibility intervals on trend direction (improving / worsening / stable)
- Feeds the `analytics_hub.html` trend cards

---

## KDOQI Target Score (used across analytics + ML)

Computed for each patient-month from available lab values:

```python
parameters = [
    (hb,         hb >= 10.0,          weight=1),
    (albumin,    albumin >= 3.5,       weight=1),
    (phosphorus, phosphorus <= 5.5,    weight=1),
    (idwg,       idwg <= 2.5,          weight=1),
    (urr,        urr >= 65.0,          weight=1),
    (kt_v,       kt_v >= 1.2,          weight=1),
]
# Score = (met / available) × 10
```

Missing parameters are excluded from denominator (not penalised if not measured).
Score < 6 → "Low KDOQI target score" risk factor in deterioration model.

---

## Alert Rule Engine (`alerts.py`)

All alert checks are deterministic KDIGO rules — no ML.
`get_patients_needing_alerts(db, month)` → list of patients with any alert condition.

### ESA Hypo-response Alert Logic
ERI = `epo_weekly_units / weight_kg / hb_g_dL`
- ERI > 10 → EPO hypo-response R1
- ERI > 15 → EPO hypo-response R2
- ERI > 20 → EPO hypo-response R3 (severe, Cohort Management action required)

### Iron Protocol Alert Logic
- TSAT < 20% → IV iron recommended
- TSAT 20–30% → maintain
- TSAT > 30% + Ferritin > 800 → hold IV iron
- High Ferritin + Low TSAT + High CRP → iron sequestration (not overload) — different management

---

## Alert Delivery System

### WhatsApp (Twilio)
```python
# alerts.py
send_whatsapp(contact_no, message)   # single patient
send_bulk_whatsapp_alerts(patients)  # all flagged patients
```
Config: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`

### Ward Email
```python
send_ward_email(alert_patients, month_label, year)
```
Sends HTML table with all alerts to `DOCTOR_EMAIL`.

### Alert Log
All alerts are logged to `alert_logs` table:
- `alert_type`: `"whatsapp"` | `"email"` | `"whatsapp_schedule"`
- `status`: `"sent"` | `"failed"`
- Retry logic: `task_send_bulk_whatsapp` retries up to 3× on delivery failure

---

## Analytics Hub Structure (`routers/analytics.py` — 85 KB)

The analytics router is the largest file. Key sections:

| URL pattern | What it serves |
|-------------|---------------|
| `/analytics/` | Analytics hub landing page |
| `/analytics/patients` | Per-patient analytics table |
| `/analytics/mortality` | Mortality risk dashboard |
| `/analytics/cohort` | Cohort trends (Hb, albumin, phosphorus) |
| `/analytics/idh` | IDH event analysis + model performance |
| `/analytics/esa` | ESA protocol audit: ERI distribution, dose-response |
| `/analytics/access` | Vascular access analytics |
| `/analytics/api/*` | Legacy JSON API (Jinja2 internal only) |
| `/analytics/admin/*` | Admin-only: model training, metrics |

---

## Research Analytics (`routers/research.py`)

- De-identified cohort export for IRB projects
- Kaplan-Meier survival analysis (if `lifelines` installed)
- Subgroup comparisons (AVF vs catheter, DM vs non-DM, etc.)

---

## ml_trends.py Utilities

Key functions used across analytics and ML feature extraction:

```python
_month_to_ordinal(month_str: str) -> int
# Converts "2026-05" → ordinal integer for regression

compute_trend_slope(values: list, months: list) -> float
# OLS slope via numpy polyfit

compute_rolling_stats(values: list, window: int) -> dict
# min, max, mean, SD over window
```

These are the same functions used to compute `hb_trend_slope` and `hb_sd_120d` in the ACM feature vector.

---

## Cohort Dashboard Cards (Context for Frontend)

When reading dashboard code, these are the card IDs and their data sources:

| Card | Data key | Source |
|------|----------|--------|
| Hb Distribution | `cohort_data.hb_distribution` | `run_cohort_analytics()` |
| KDOQI Score | `cohort_data.kdoqi_score_dist` | `run_cohort_analytics()` |
| High Risk Count | `high_risk_count` | `get_high_risk_mortality_count()` |
| Missing Records | `metrics.missing_records` | `compute_dashboard()` |
| ESA Hypo Badge | `metrics.epo_hypo` | `compute_dashboard()` |
| Trend Cards | `data.metrics.trend_hb/albumin/phos` | `compute_dashboard()` |
