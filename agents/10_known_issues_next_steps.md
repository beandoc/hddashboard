# 10 — Known Issues, Gaps & Next Steps

> Agent memory file · HD Dashboard · Last updated 2026-06-01
> Update this file whenever a known issue is resolved or a new one is discovered.

---

## Current Status Summary

| Subsystem | Status | Notes |
|-----------|--------|-------|
| KDIGO alert rules | ✅ Production-ready | Deterministic, no training data needed |
| Daugirdas Kt/V | ✅ Validated | Published equations, unit-tested |
| IDH XGBoost | ⚠ Needs training data | Heuristic fallback active |
| Deterioration model | ⚠ Needs training data | Heuristic fallback active; needs ≥50 hospitalisation events |
| ACM ODE prediction | ✅ Active | Per-patient fitting, needs ≥3 months Hb history |
| ACM residual MLP | ⚠ Needs more data | Generalises after ≥200 patient-months |
| Mortality risk (Xu) | ⚠ Indian recalibration literature-only | Must be replaced with local cohort fit after ≥50 deaths |
| Phosphate 2-pool RK4 | ✅ Active | Linear fallback when RK4 diverges |
| Digital Twin | ✅ Active | All 5 domains running |
| Celery beat | ✅ Configured | Needs Redis in production |
| Feature store | ✅ Active | Nightly materialisation |
| MLOps drift detection | ✅ Active | Drift threshold: |slope - 1.0| > 0.15 |
| Access surveillance form | ✅ Active | `access_surveillance_form.html` — linked from patient profile |
| Cardiac Output auto-calc | ✅ Active | LVOT×VTI×HR in `patient_cardiac` |
| Dietary phosphate pipeline | ⚠ Partial | Patient portal meal logs exist; aggregation to twin not yet wired |
| Doppler access flow Qa | ⚠ Partial | Form exists; needs Qa data for real patients |

---

## Known Bugs & Gotchas

### 1. Alembic Schema Inspection in Sandbox
**Problem**: Running `alembic` commands that introspect live schema during restricted execution can trigger access violations.  
**Workaround**: Use `sqlalchemy.inspect` or raw `psql` queries for schema investigation. Only run `alembic upgrade head` via `scripts/pre_deploy.py`.

### 2. IDH Model Heuristic Fallback (Expected Behaviour)
When `models/idh_model.joblib` does not exist or has no `ModelArtifact` registry row, the IDH model silently returns a heuristic UF-rate-based probability. This is by design, not a bug.  
**Resolution**: `POST /analytics/admin/train-idh-model` once ≥ 3 months of session data with BP nadir recordings are available.

### 3. Deterioration Model Gates
Inference is refused if `model_artifacts` has no row for `"deterioration_v1"` (even if the .pkl file exists on disk).  
**Why**: Prevents stale unversioned pkl from running after a Render container restart.  
**Fix**: `POST /admin/train-deterioration-model` to train and register the artifact.

### 4. Render Ephemeral Filesystem
Trained model .pkl files are lost on every Render container restart.  
**Mitigation in place**: `model_binary` (LargeBinary) column in `model_artifacts` stores joblib bytes.  
**Action needed**: Boot sequence must restore .pkl from `model_binary` if file is missing. This auto-restore is NOT yet implemented — models must be retrained after each restart OR the binary must be loaded directly without writing to disk.

### 5. ACM Residual MLP Cold Start
The residual MLP (`models/acm_residual_mlp.pkl`) only improves over population priors after ≥200 patient-months of data. With a small cohort, the ODE dominates.  
**This is expected and documented in `DIGITAL_TWIN_CONTEXT.md`.**

### 6. Indian Mortality Recalibration Parameters
`_INDIAN_CAL_SLOPE = 0.72`, `_INDIAN_CAL_INTERCEPT = -0.40` are literature approximations.  
**Must be replaced** with locally fitted Platt scaling once ≥50 mortality events are available.

### 7. Dietary Phosphate Not Yet Wired
Patient portal meal logs (`patient_meal_records.phosphorus_mg`) are saved but:
- Aggregation to daily average is in `services/nutrition_service.py`
- The Digital Twin phosphate model expects `dietary_phosphate_mg_day` in the scenario parameters
- **Wiring needed**: Aggregation result should auto-populate the Digital Twin scenario baseline when a patient has recent meal logs

### 8. Dashboard Warm-up Thread Race
`_DASHBOARD_WARM_EVENT.wait(timeout=8)` in the dashboard route means the first request after a cold start can stall up to 8 seconds if warm-up is slow.  
**Mitigation**: Render health probe waits for `_APP_READY` before routing traffic.

---

## Data Requirements for Full ML Performance

| Model | What's needed | Current state |
|-------|--------------|--------------|
| IDH XGBoost | ≥500 session records with `bp_nadir_sys` filled + IDH label | Unknown — depends on data entry completeness |
| Deterioration LR | ≥50 hospitalisation events in `monthly_records` | Unknown |
| ACM residual MLP | ≥200 patient-months of Hb + ESA + iron records | Unknown |
| Mortality recalibration | ≥50 confirmed deaths in `patient_outcomes` | Requires long follow-up |
| ACM ESA dose-response | ≥5 accepted ACM recommendations with 1-month follow-up | In progress |

---

## Phase 2 Roadmap (Prioritised)

### High Priority (Near-term)
1. **Auto-restore ML models from `model_binary` on boot** — critical for Render production stability
2. **Wire dietary phosphate aggregation** to Digital Twin scenario baseline
3. **Train IDH model** once sufficient BP nadir + IDH episode data is collected
4. **Collect local mortality outcomes** to replace literature recalibration parameters

### Medium Priority
5. **Conformal prediction intervals** (MAPIE) on IDH XGBoost — distribution-free 80% PI
6. **Bayesian MCMC** for phosphate ODE parameters (Bangsgaard et al. MBE 2023)
7. **Two-compartment fluid/volume model** (Abohtyra et al. IEEE TBE 2018) — real-time RBV tracking, proven 34% IDH reduction in closed-loop UF control

### Low Priority / Future
8. **Real-time MQTT streaming** from HD machine → intra-session IDH predictions every 15 min
9. **Vascular access aging model** (IoMT XGBoost, Hsieh et al. 2023, 90.7% precision)
10. **Acid-base kinetics module** (HCO₃⁻ optimisation)
11. **Multi-solute kinetic model** (Daugirdas Semin Dialysis 2025: urea/P/Cr/B2M)

---

## Technical Debt

| Item | File | Priority |
|------|------|---------|
| Delete `scratch/` directory (20 debug scripts, none imported) | `scratch/*.py` | Low |
| `FRONTEND_ARCHITECTURE.md` notes `frontend/INTEGRATION_STATUS.md` is dead weight | `frontend/` | Low |
| Legacy `/analytics/api/*` aliases still exist for Jinja2 backward compatibility | `routers/analytics.py` | Remove when Jinja2 dashboard templates deleted |
| `hd_dashboard.db`, `test.db`, `*.db` files in root — not used in production | root | Clean up |
| `dump_js.py`, `parse_scripts.py`, `test_div.py`, `test_jinja.py`, `test_js.py/js` — debug scripts | root | Clean up |

---

## Clinical Validation Targets (from Literature)

| Target | Publication | Our goal |
|--------|------------|---------|
| ACM: Hb MAE < 0.75 g/dL | Fuertinger et al. CJASN 2024 | Currently unknown |
| ACM: 25% ESA reduction | Fuertinger et al. (RCT result) | Long-term goal |
| IDH: AUROC > 0.85 | Zhang & Kotanko NDT 2023 (0.887) | Target once trained |
| Phosphate R² > 0.98 | Laursen et al. Physiol Rep 2023 (0.985) | Within-session validation needed |
| Calibration slope: 0.9–1.1 | HEMO Study calibration standard | Monitored weekly by Celery |

---

## Deployment Checklist (Before Production)

- [ ] `REQUIRED_DB_VERSION` in `main.py` matches `alembic_version` in production DB
- [ ] All env vars set in Render dashboard (DATABASE_URL, SECRET_KEY, REDIS_URL, SMTP_*, TWILIO_*, etc.)
- [ ] `COOKIE_SECURE=true` set (HTTPS in production)
- [ ] `scripts/pre_deploy.py` runs `alembic upgrade head` before app boots
- [ ] Celery worker dyno running with Redis accessible
- [ ] `POST /admin/train-deterioration-model` called after first data is collected
- [ ] `POST /analytics/admin/train-idh-model` called after sufficient session data

---

## Key Literature References

| Paper | What it proves | Where used |
|-------|--------------|-----------|
| Fuertinger et al. CJASN 2024 | 25% ESA reduction, 47% Hb target attainment | ACM validation target |
| Garbelli et al. Biomedicines 2024 | 74.3 vs 86.7 hospitalizations/100 person-years | ACM outcomes benchmark |
| Zhang & Kotanko NDT 2023 | AUROC 0.887 for IDH at 15–75 min horizon | IDH model validation target |
| Laursen et al. Physiol Rep 2023 | Phosphate 2-pool model R²=0.985 | Phosphate module validation |
| Xu et al. 2023 | XGBoost mortality risk | `ml_risk.py` mortality model |
| Bangsgaard et al. MBE 2023 | Bayesian MCMC for phosphate ODE | Phase 2 upgrade path |
| Abohtyra et al. IEEE TBE 2018 | 2-compartment fluid model, 34% IDH reduction | Phase 2 fluid module |
| Cheungpasitporn et al. CKJ 2026 | AI roadmap for nephrology | Overall architecture driver |
| KDIGO 2012 | Hb/iron targets | Alert rules, ACM thresholds |
| KDIGO 2015 HD Adequacy | Kt/V targets | Adequacy module |
| KDIGO CKD-MBD 2017 | Phosphate targets | Quality gate, phosphate model |
| HEMO Study (Daugirdas & Depner, NDT 2017) | Exclusion criteria | Quality gate thresholds |
