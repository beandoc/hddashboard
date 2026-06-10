# Annexure A: Technical and Clinical Review of the Existing Digital Dialysis Twin

**Document type**: Supporting Annexure — PhD Research Proposal  
**Subject**: Haemodialysis Digital Twin — Architecture, Clinical Validity, and Research Gap Positioning  
**Version**: 1.0  

---

## Abstract

This annexure presents a detailed technical and clinical review of a proprietary Digital Dialysis Twin (DDT) developed as part of a clinical decision-support dashboard for haemodialysis (HD) management. The system constitutes a multi-domain mechanistic simulation engine integrating eight physiological sub-models — covering erythropoiesis, dialysis adequacy, intradialytic hypotension (IDH) risk, phosphate kinetics, haemodynamics, fluid volume dynamics, and cross-domain cascade reasoning. Each sub-model is grounded in published clinical equations and calibrated using Bayesian inference where patient-specific data permits. The review establishes the technical rigour and clinical validity of this system as a research substrate, documents its structural data limitations relative to real-time physiological monitoring, and formally positions the research gap that the proposed doctoral programme addresses.

---

## 1. Introduction

Digital twins in medicine represent computational replicas of a patient's physiology that can simulate the effect of treatment interventions in silico before clinical implementation (Björnsson et al., 2020; Laubenbacher et al., 2021). In haemodialysis, where treatment parameters (session duration, blood flow rate, ultrafiltration volume, dialysate composition, pharmacotherapy) are adjusted at least three times per week per patient, a digital twin capable of predicting individualised outcomes across multiple physiological domains simultaneously offers substantial clinical utility.

The system under review — hereafter the Digital Dialysis Twin (DDT) — was developed as a clinical scenario sandbox for nephrologists and specialist nurses. It runs a parallel simulation for each patient across eight physiological domains, produces point estimates and uncertainty intervals for each, and persists the scenario parameters and outcomes for longitudinal outcome tracking. The DDT is embedded within a broader haemodialysis management platform (HD Dashboard) that encompasses patient demographics, clinical records, monthly biochemistry, session-level data, vascular access surveillance, body composition assessment, and patient-reported outcomes.

This review is structured as follows: Section 2 provides an architectural overview; Section 3 presents domain-by-domain technical specifications; Section 4 describes the underlying data architecture; Section 5 evaluates clinical validity; Section 6 identifies current limitations; and Section 7 positions the research gap for the proposed doctoral programme.

---

## 2. System Architecture Overview

### 2.1 High-Level Design

The DDT follows a service-oriented architecture comprising:

- **Simulation orchestrator** (`ml_twin.py`): Coordinates execution of all eight sub-models, aggregates results, and manages persistence
- **Domain service modules** (`services/twin_*.py`): Independent, unit-testable simulation functions for each physiological domain
- **Machine learning module** (`ml_idh.py`): XGBoost IDH classifier with calibrated fallback, trained on session-level historical data
- **REST API router** (`routers/twin.py`): HTTP endpoints exposing simulation capabilities to the frontend
- **Persistence layer**: PostgreSQL via SQLAlchemy ORM, storing full scenario inputs, domain outputs, and actual outcomes for retrospective validation
- **Frontend interface** (`templates/digital_twin.html`, `static/js/digital_twin*.js`): Interactive prescription sandbox with Plotly visualisations

### 2.2 Operational Workflow

The simulation lifecycle follows a three-stage pattern:

1. **Pre-simulation loading**: Patient clinical history is queried across six database entities (monthly records, session records, dry weight assessments, access surveillance, cardiac data, nutrition records), establishing baseline parameters for all eight domains

2. **Scenario execution**: A clinician adjusts one or more prescription parameters (ESA dose, session duration, blood flow rate, UF volume, dialysate composition, phosphate binder dose) via an interactive interface; the orchestrator passes the complete scenario dictionary to each domain service in sequence

3. **Result persistence and outcome tracking**: Full scenario parameters, baseline state, and all domain outputs are stored in the `twin_simulations` table; subsequent session and monthly records back-fill an `actual_outcomes_json` field, enabling retrospective accuracy assessment

### 2.3 Uncertainty Quantification Philosophy

A defining characteristic of the DDT is its explicit treatment of prediction uncertainty. Each domain producing a probabilistic output returns not only a point estimate but a quantified uncertainty interval:

- 80% posterior predictive intervals (Hb kinetics) using closed-form Bayesian posteriors
- 80% Mondrian split-conformal prediction intervals (IDH risk) providing marginal coverage guarantees without distributional assumptions
- 80% highest density intervals (phosphate kinetics) from PyMC NUTS sampling where MCMC calibration is available
- Heuristic fallback with broader uncertainty bands when primary models cannot be calibrated

This reflects the clinically critical distinction between *model certainty* and *epistemic uncertainty*: the twin communicates not only what it predicts but how much the clinician should trust that prediction for a given patient.

---

## 3. Domain Technical Specifications

### 3.1 Domain 1 — Haemoglobin (Hb) Kinetics

**Clinical objective**: Forecast the 3-month Hb trajectory under a modified erythropoiesis-stimulating agent (ESA) and iron protocol.

**Mathematical model**: Bayesian conjugate Gaussian regression with population-level priors updated by patient-specific observation history.

**Model equation**:
```
ΔHb ≈ k_gain × (ESA_IU_normalised × 10³) + k_iron × ΔTSAT + ε
ε ~ N(0, σ_ε²)
```

**Prior distributions** (population-level, informed by published ESA pharmacokinetics):
```
k_gain ~ N(μ₀ = 1.0×10⁻⁵, σ₀² = (4×10⁻⁶)²)   [g/dL per IU/kg/wk × 10³]
k_iron ~ N(μ₀ = 0.015, σ₀² = (0.006)²)          [g/dL per % TSAT increase/month]
σ_ε = 0.25 g/dL                                   [observation noise, biological + assay variability]
```

**Posterior update** (closed-form conjugate Gaussian):
```
Posterior precision = Prior precision + Σ(xᵢ²) / σ_ε²
Posterior mean      = (Prior precision × μ₀ + Σ(xᵢyᵢ) / σ_ε²) / Posterior precision
```

**Prediction interval**: 80% PI with z = 1.282, predictive variance:
```
σ²_pred ≈ σ_ε² + σ²_k_gain × x²_gain + σ²_k_iron × x²_iron
```

**Confidence calibration**: When n < 3 observation pairs, the prior dominates and the posterior mean approximates the population response. The system flags low-data confidence explicitly rather than producing spuriously narrow intervals.

**Clinical basis**: The model structure follows the ESA pharmacodynamic framework described by Fishbane and Nissenson (2010) and is consistent with KDIGO 2012 anaemia guidelines which specify ESA dose response as a function of normalised dose per unit weight.

---

### 3.2 Domain 2 — Single-Pool Dialysis Adequacy (spKt/V)

**Clinical objective**: Estimate dialysis dose under a modified prescription and compare against the minimum adequacy target (spKt/V ≥ 1.2, per KDOQI guidelines).

**Mathematical model**: Daugirdas second-generation single-pool variable-volume formula (Daugirdas, 1993):

```
spKt/V = −ln(R − 0.008 × t) + (4 − 3.5R) × (UF / W)

where:
  R = post-dialysis BUN / pre-dialysis BUN
  t = session duration (hours)
  UF = ultrafiltration volume (litres)
  W = post-dialysis weight (kg)
  BUN = blood urea nitrogen (converted from serum urea: BUN = urea × 28/60)
```

**Validation constraints**: R ∈ (0, 1.5); pre-dialysis BUN > 0; session time > 0; post-weight > 0. Values outside these bounds return `None` with `available: False` in the simulation output.

**Clinical basis**: The Daugirdas second-generation formula is the internationally validated standard for spKt/V calculation (Daugirdas, 1993; KDOQI Clinical Practice Guidelines, 2006) and is in routine clinical use across dialysis networks globally.

---

### 3.3 Domain 3 — Extended Urea Kinetics (eKt/V, std Kt/V, Dialyzer Clearance)

**Clinical objective**: Characterise dialyzer performance and normalised clearance beyond the single-pool approximation.

**Sub-models**:

**(a) Dialyzer clearance (Kd)** — Daugirdas Appendix C from in-vitro KoA:
```
Kd = KoA × ln[(1 − exp(−KoA × (1/Qb − 1/Qd))) / (1 − (Qb/Qd) × exp(−KoA × (1/Qb − 1/Qd)))]
```

**(b) Equilibrated Kt/V (eKt/V)** — Leypoldt correction accounting for post-dialysis urea rebound (Leypoldt et al., 1996):
```
eKt/V = spKt/V − 0.6 × (spKt/V / t) + 0.03
```

**(c) Standardised Kt/V (std Kt/V)** — Tattersall formula normalised for three-times-weekly HD (Tattersall et al., 1996):
```
std Kt/V = (Kt/V × 10080/t) / (Kt/V / ln(1 − Kt/V) + Kt/V / (t/7))
```

---

### 3.4 Domain 4 — Intradialytic Hypotension (IDH) Risk Prediction

**Clinical objective**: Estimate the probability of IDH (defined as symptomatic systolic BP drop ≥ 20 mmHg or nadir SBP < 90 mmHg) for a given session prescription.

**Primary model**: XGBoost gradient boosting classifier (Chen & Guestrin, 2016) with 41-feature input vector, calibrated via isotonic regression (Platt scaling equivalent). Fallback model: calibrated logistic regression. Secondary fallback: physiologically-informed heuristic.

**Feature vector composition** (41 features, grouped):

| Category | Features | Count |
|---|---|---|
| Patient demographics | Age, sex, BMI | 3 |
| Comorbidities | DM, CHF, CAD, AF, PVD | 5 |
| Body composition | BIA phase angle, fluid overload, TBW | 3 |
| Monthly biochemistry | Albumin, Hb, sodium, CRP, NT-proBNP | 5 |
| Session prescription | Pre-HD SBP, IDWG, UF volume, UFR, duration, dialysate temp, sodium | 7 |
| Dialysis vintage | Years on HD, residual urine output | 2 |
| Temporal features (7-session rolling) | Prior IDH burden, nadir SBP mean, pre-HD SBP slope | 3 |
| Access characteristics | Access type, Doppler flow | 2 |
| Extended clinical | Ejection fraction, troponin, dialyzer flux | 3 |
| **Placeholder (unfilled)** | **Heart rate variability (feature #38)** | **1** |
| Interaction terms | UFR × albumin, BP × IDWG | 7 |

**Critical structural observation**: Feature #38 (`heart_rate_variation`) is defined in the feature vector specification but is explicitly set to `None` at both training and inference pathways (lines 520 and 782, `ml_idh.py`). This constitutes a pre-designed architectural socket for autonomic nervous system input that is unpopulated in the current implementation, representing the primary structural gap addressed by the proposed doctoral research.

**Uncertainty quantification**: Mondrian split-conformal prediction (Venn-Abers approach), providing 80% coverage guarantees marginalised over IDH outcome class. This method makes no distributional assumptions about the underlying feature space and is valid for any XGBoost model post hoc (Shafer & Vovk, 2008; Angelopoulos & Bates, 2023).

**IDH label generation** (for training): Algorithmic from session records:
```
IDH = True  if  (pre_SBP − nadir_SBP ≥ 20 mmHg)  OR  (nadir_SBP < 90 mmHg)
IDH = False  otherwise
Fallback: idh_episode boolean from nursing record when nadir BP is absent
```

**Clinical basis**: IDH definition follows Flythe et al. (2011) and KDOQI guidelines. The UFR mortality threshold (4.0 mL/kg/h reference line in the UF sweep visualisation) references Castro and Wu (2024). IDH incidence of 20–30% of HD sessions is consistent with published epidemiology (Flythe et al., 2015).

---

### 3.5 Domain 5 — UF Rate Sweep (IDH Risk Curve)

**Clinical objective**: Characterise the IDH risk profile across a range of UF rates to identify the safe operating zone for a given patient.

**Method**: The IDH model (Domain 4) is re-evaluated at eight discrete UF rate values spanning 6–16 mL/kg/h at equal intervals, producing an IDH risk curve. A reference line at 4.0 mL/kg/h marks the mortality-risk threshold per observational evidence.

---

### 3.6 Domain 6 — Phosphate Kinetics

**Clinical objective**: Forecast pre-dialysis phosphate under a modified combination of session duration, phosphate binder dose, and dietary phosphate intake.

**Primary model**: Two-pool Runge-Kutta 4th-order (RK4) ordinary differential equation solver implementing the Daugirdas/Laursen phosphate distribution model, run to 14-day steady state.

**Compartmental structure**:
```
Accessible pool (plasma + rapidly equilibrating):  V_A  (fraction of TBW)
Sequestered pool (intracellular/bone):             V_S  (remaining fraction)

dP_A/dt = k_in − k_c × P_A − k_dialysis(t) × P_A − k_AB × P_A + k_BA × P_S
dP_S/dt = k_AB × P_A − k_BA × P_S

where:
  k_in         = dietary phosphate absorption rate (from PBE dose + dietary phosphate mg/day)
  k_c          = endogenous clearance (residual renal + faecal)
  k_dialysis   = dialytic clearance, active during session windows only
                 Kd_phosphate ≈ 0.5 × Kd_urea  (empirical ratio, Daugirdas 2025)
  k_AB, k_BA   = inter-compartmental transfer rate constants
```

**MCMC calibration** (when historical phosphate data is available): PyMC implementation using No-U-Turn Sampler (NUTS), fitting patient-specific `kc_scale` (endogenous clearance scaling) and `koa_ratio` (phosphate-to-urea KoA ratio). Outputs: posterior mean, 80% HDI for pre-dialysis phosphate forecast.

**Fallback model** (when RK4 diverges or data is insufficient): Linear approximation:
```
ΔP = −0.3 × Δsession_h − 0.1 × ΔPBE + 0.2 × Δdietary_P_200mg
```

**Clinical targets**: 3.5–5.5 mg/dL per KDIGO mineral metabolism guidelines (KDIGO, 2017).

---

### 3.7 Domain 7 — Haemodynamic and Cardiac Strain

**Clinical objective**: Quantify the cardiovascular demand imposed by vascular access on cardiac function.

**Model**:
```
Shunt ratio = Qa / CO

where:
  Qa  = vascular access flow (mL/min, from Doppler surveillance record)
  CO  = cardiac output (L/min); measured if available, else estimated from 
        demographics (Fick approximation with Dubois body surface area)

Cardiac strain:
  High      if Qa > 1500 mL/min  OR  shunt_ratio > 0.30
  Moderate  if 600 ≤ Qa ≤ 1500   OR  0.20 ≤ shunt_ratio ≤ 0.30
  Low       if Qa < 600 mL/min   OR  shunt_ratio < 0.20
```

**Clinical basis**: Thresholds reference the access flow limits associated with high-output cardiac failure in HD patients (MacRae et al., 2004; Basile et al., 2008).

---

### 3.8 Domain 8 — Fluid Volume Dynamics

**Clinical objective**: Model intra-session fluid compartment shifts under ultrafiltration.

**Mathematical model**: Two-compartment fluid distribution with Starling force-driven plasma refilling.

**Core equations** (Landis-Pappenheimer oncotic pressure approximation):
```
π(albumin) = 0.47 × albumin^1.6   [mmHg, Landis-Pappenheimer approximation]

Plasma refilling rate (k_r):
  k_r = f(σ, ΔP_hydrostatic, Δπ, L_p)

where:
  σ = 0.90    (Staverman reflection coefficient for albumin)
  L_p         = hydraulic conductivity of capillary membrane
```

The model integrates the fluid balance ODE across the session, producing ICW/ECW compartment trajectories and a safe UF rate ceiling based on the patient's oncotic pressure capacity.

---

### 3.9 Domain 9 — Cross-Domain Cascade Reasoning

**Clinical objective**: Generate human-interpretable interdependency messages when multiple prescription parameters are changed simultaneously.

**Method**: Rule-based cascade logic (`services/twin_cascade.py`) detecting parameter change directions and producing clinically meaningful consequence messages. Examples:

- Session duration ↑ → spKt/V ↑, phosphate removal ↑, effective UF rate ↓ (same volume, more time)
- Blood flow rate (Qb) ↑ → dialyzer Kd ↑, urea/phosphate clearance ↑
- Dialysate temperature ↓ → IDH risk ↓ (peripheral vasoconstriction maintained)
- Phosphate binder ↑ → dietary phosphate absorption ↓ → pre-dialysis phosphate ↓

Output format is a structured array with domain, direction, delta, and message fields, rendered as a cascade timeline in the clinical interface.

---

## 4. Data Architecture

### 4.1 Primary Data Sources

The simulation engine draws from six primary data entities:

| Entity | Key Variables | Temporal Resolution |
|---|---|---|
| `MonthlyRecord` | Hb, TSAT, ferritin, phosphorus, albumin, urea (pre/post), ESA/iron doses, spKt/V | Monthly |
| `SessionRecord` | Pre/post BP (single-point snapshots), IDWG, UF volume (planned), session duration, Qb (prescribed), IDH boolean, nadir SBP | Per session |
| `DryWeightAssessment` | BIA phase angle, fluid overload, TBW, ECW/ICW | Episodic |
| `AccessSurveillanceRecord` | Doppler access flow (Qa), PSV, stenosis % | Quarterly/episodic |
| `PatientCardiac` | LVEF, diastolic function grade, measured cardiac output (where available) | Episodic |
| `PatientSymptomReport` | Post-HD fatigue, cognitive, physical, psychological domains (39-item PDS scale) | Session-optional |

### 4.2 Simulation Persistence

The `TwinSimulation` database entity captures:
- `scenario_json`: Full input prescription parameter set
- `baseline_session_json`: Session plan at time of simulation (for reproducibility)
- `hb_sim_json`, `ktv_sim_json`, `idh_sim_json`, `phosphate_json`, etc.: Full domain outputs
- `adopted`: Boolean — whether clinician implemented the simulated scenario
- `clinician_notes`: Free-text clinical reasoning
- `actual_outcomes_json`: Back-filled from subsequent records for retrospective accuracy assessment

This architecture supports prospective accuracy tracking: every simulation is a testable prediction against a future observable outcome.

---

## 5. Clinical Validity Assessment

### 5.1 Alignment with Published Evidence

Each simulation domain is grounded in published, validated clinical methodology:

| Domain | Primary Source(s) | Validation Status |
|---|---|---|
| spKt/V (Daugirdas) | Daugirdas (1993) JASN | Internationally validated; KDOQI/KDIGO endorsed |
| eKt/V (Leypoldt) | Leypoldt et al. (1996) JASN | Validated in prospective cohorts |
| Std Kt/V (Tattersall) | Tattersall et al. (1996) NDT | Incorporated in European guidelines |
| Phosphate kinetics (two-pool) | Daugirdas/Laursen model | Peer-reviewed ODE framework; MCMC calibration adds patient specificity |
| Fluid dynamics (Starling/oncotic) | Landis-Pappenheimer; Abohtyra (2018) | Published approximation; simplified for real-time computation |
| IDH risk (XGBoost, 41 features) | Feature set consistent with Flythe et al. (2015) | System-trained on internal cohort; external validation pending |
| Hb kinetics (Bayesian conjugate) | ESA pharmacodynamics (Fishbane & Nissenson, 2010) | Internally consistent with KDIGO 2012 targets |
| Cardiac strain (shunt ratio) | MacRae et al. (2004); Basile et al. (2008) | Thresholds from published observational data |

### 5.2 Uncertainty Quantification Validity

The choice of Mondrian split-conformal prediction for IDH uncertainty intervals is methodologically sound. Unlike bootstrap or Monte Carlo methods, split-conformal prediction provides **distribution-free, finite-sample marginal coverage guarantees** — meaning the stated 80% interval contains the true outcome with exactly 80% frequency asymptotically, regardless of the underlying data distribution (Angelopoulos & Bates, 2023). This is a stronger claim than standard confidence intervals, which rely on parametric assumptions that may not hold for clinical data.

For the Hb kinetics domain, the closed-form Bayesian update provides interpretable posterior uncertainty: when patient data is sparse (n < 3 observation pairs), the predictive interval widens explicitly rather than collapsing to a spurious point estimate. This honest uncertainty communication is a design principle of the system.

### 5.3 Clinical Threshold Calibration

The system implements clinically validated decision thresholds throughout:
- spKt/V ≥ 1.2: KDOQI minimum adequacy target
- Phosphate: 3.5–5.5 mg/dL: KDIGO 2017 mineral metabolism targets
- QTc (proposed integration): > 470 ms (men) / > 480 ms (women): advisory; > 500 ms: critical — per AHA/ACC cardiac safety thresholds
- UF rate mortality reference: 4.0 mL/kg/h: Castro and Wu (2024) observational threshold
- Cardiac strain (shunt ratio > 0.30 / Qa > 1500 mL/min): MacRae et al. (2004) high-output failure thresholds

---

## 6. Current Limitations

### 6.1 Temporal Resolution Mismatch

The DDT's most significant limitation is a **fundamental mismatch between simulation granularity and data input granularity**. The simulation engine implements minute-level physiological physics (ODE integration, Bayesian updating) but is fed data at monthly (biochemistry, ESA dosing), per-session (single BP snapshots, binary IDH outcome), and episodic (BIA, Doppler) temporal resolution.

Specifically:
- **Intra-session blood pressure**: Captured only at four time points (pre, nadir, peak, post). The 30-minute intervals between standard manual BP checks represent a clinical blind spot during which IDH may develop, partially compensate, and resolve without structured capture.
- **Blood flow rate**: The twin assumes prescribed Qb equals delivered Qb in the Daugirdas formula. Session-level Qb is recorded as a single end-of-session value; intra-session flow variations due to access compression, needle positioning, or clotting are not captured.
- **Ultrafiltration**: Planned and actual UF volume may diverge due to haemodynamic intolerance or session abbreviation. This discrepancy is not systematically structured in the current data model.
- **Electrolytes**: Serum potassium, calcium, and bicarbonate are measured at monthly frequency only. Intra-session electrolyte kinetics — clinically critical for both cardiac electrical safety and phosphate modelling — are invisible to the twin.

### 6.2 Structural Feature Gaps in the IDH Model

Feature #38 of the 41-feature IDH model (`heart_rate_variation`) is **permanently set to** `None` **in both training and inference code paths**, representing an unimplemented placeholder for autonomic nervous system input. This is the most consequential single gap in the system: HRV (specifically RMSSD) is a validated leading indicator of IDH by 8–15 minutes via parasympathetic withdrawal (Ranpuria et al., 2008; Rubinger et al., 2004), and its absence means the IDH model is predicting a physiological event through a mechanism it cannot observe.

### 6.3 Absence of Cardiac Electrical Monitoring

The twin has no representation of cardiac electrical state. The rapid electrolyte flux that characterises every dialysis session — notably K⁺ removal, Ca²⁺ shifts, and pH correction — produces measurable and clinically significant changes in cardiac repolarisation (QTc interval prolongation) that are wholly absent from the current simulation. QTc prolongation during HD is associated with sudden cardiac death risk (Genovesi et al., 2008; Buiten et al., 2017), and sudden cardiac death accounts for approximately 25% of mortality in the dialysis population (Jadoul et al., 2017). This represents a complete domain gap.

### 6.4 Open-Loop Architecture

The current system is **entirely open-loop**. The simulation runs pre-session, produces a forecast, and is then disconnected from the session's actual progression. The IDH model does not update as a session evolves; the fluid model does not recalibrate as fluid removal proceeds; the phosphate model does not incorporate intra-session information. In control theory terms, the twin has no feedback pathway from plant (patient) to controller (simulation) during the process it is modelling.

### 6.5 Patient-Reported Outcome Sparsity

The `PatientSymptomReport` entity implements a comprehensive 39-item Post-Dialysis Syndrome (PDS) scale but is **session-optional** rather than session-mandatory. Analysis of the data architecture confirms it is populated in a minority of sessions. This means the most direct measure of patient-experienced treatment burden — which correlates with dialysis adequacy, fluid removal tolerance, and haemodynamic instability — is systematically sparse in the training data available to refine the IDH and Hb models.

### 6.6 External Validation Absence

The IDH classifier is trained on an internal patient cohort. No external validation against an independent institutional dataset has been documented. While the Mondrian conformal prediction intervals provide theoretical coverage guarantees on the training distribution, external validity — the degree to which predictions hold in patients from different dialysis units, demographics, or clinical management protocols — remains unestablished.

---

## 7. Research Gap Positioning

### 7.1 Summary of Identified Gaps

The review identifies five converging gaps that constrain the DDT's clinical utility:

1. **Autonomic signal absence**: Feature #38 is permanently null; parasympathetic withdrawal before IDH is unobservable
2. **Volumetric feedback absence**: Plasma refilling dynamics during UF are untracked; the fluid model runs open-loop
3. **Cardiac electrical domain absence**: QTc kinetics during electrolyte flux are not modelled
4. **Temporal resolution**: Four BP snapshots per 4-hour session; single Qb value; no intra-session electrolytes
5. **Patient-reported signal sparsity**: PRO data incomplete; subjective pre-IDH indicators (dizziness, cramps) are binary flags without temporal context

### 7.2 Proposed Sensor Integration and Research Contribution

The proposed doctoral programme addresses these gaps through integration of two sensor modalities and four structured data enhancements:

**Sensor Modality 1 — Wireless ECG monitoring**:  
Provides continuous RR interval time series → enables computation of all HRV metrics (SDNN, RMSSD, pNN50, LF/HF power) throughout the 4-hour session. Fills feature #38 with a real-time signal. Additionally provides QT and QTc interval monitoring, enabling the first integration of cardiac electrical safety monitoring within a multi-domain HD digital twin.

**Sensor Modality 2 — Optical hematocrit and relative blood volume (RBV) monitoring via the Nagler formula**:
```
RBV(t) = [Hct(0) × (1 − Hct(t))] / [Hct(t) × (1 − Hct(0))]
```
Provides a continuous volumetric signal representing the balance between UF-driven plasma volume contraction and interstitial plasma refilling. The rate of change dRBV/dt — plasma refill capacity — is patient-specific and constitutes a novel continuous model input for the fluid volume domain.

**Structured data enhancements**:
1. **NIBP every 15 minutes during session**: Converts the IDH label from a binary session outcome to a BP trajectory, enabling slope-based early prediction
2. **Actual delivered Qb per session**: Removes the prescribed = delivered assumption from Daugirdas formula and phosphate ODE
3. **Actual vs prescribed UF volume recorded at session end**: Enables fluid model validation and provides UFR accuracy signal
4. **Mandatory patient symptom login post-session**: Converts PRO data from sparse to complete, enabling symptom trajectory analysis as a model feature

### 7.3 Primary Research Questions

The doctoral programme proposes to investigate:

**RQ1 (Primary)**: Does a fused autonomic (HRV) + volumetric (RBV) + haemodynamic (NIBP trajectory) digital twin model predict intradialytic hypotension with statistically superior sensitivity, specificity, and lead time compared to the static pre-session XGBoost model and compared to any single sensor modality alone?

**RQ2**: Can a mechanistic kinetic model linking real-time Kt/V accumulation rate to predicted QTc trajectory — integrated within the existing DDT architecture — prospectively identify patients at risk of exceeding cardiac electrical safety thresholds during a haemodialysis session?

**RQ3**: Does Bayesian per-patient personalisation of the plasma refill capacity parameter (dRBV/dt curve shape), updated session-by-session via the Nagler RBV signal, produce statistically significant improvement in fluid model accuracy and IDH prediction compared to population-level parameters?

**RQ4 (Secondary)**: What is the minimum sensor data quality — expressed as sampling completeness and dropout tolerance — required for the integrated twin to maintain clinically actionable predictions, as assessed by conformal prediction coverage under simulated signal degradation?

### 7.4 Scientific Novelty

The proposed research is scientifically novel on three independent dimensions:

**Dimension 1 — Integration architecture**: No existing digital twin for haemodialysis integrates autonomic, volumetric, and cardiac electrical signals within a single unified mechanistic simulation framework. Existing RBV monitoring systems (e.g., Crit-Line, BCM) operate as standalone alert devices with no coupling to multi-domain physiological simulation. Existing HRV analyses in HD (Ranpuria et al., 2008) demonstrate associations but do not embed the signal in a predictive modelling architecture with personalised Bayesian updating.

**Dimension 2 — QTc kinetic modelling**: The association between HD-related electrolyte flux and QTc prolongation is published (Genovesi et al., 2008; Buiten et al., 2017; Jadoul et al., 2017). The formal mechanistic model linking Kt/V accumulation rate → K⁺ clearance kinetics → predicted QTc trajectory within a clinical digital twin framework has not been published. This constitutes an original mechanistic model with direct patient safety implications.

**Dimension 3 — Closed-loop personalisation**: The proposed architecture converts the existing open-loop DDT into a closed-loop system in which intra-session sensor data continuously updates simulation predictions, and post-session outcomes update patient-specific model parameters for subsequent sessions. The Bayesian framework already implemented for Hb kinetics (Domain 1) provides the architectural template; extending it to plasma refill capacity and IDH prediction personalisation is novel.

### 7.5 Clinical Translation Pathway

The research substrate — a working production system embedded in an active clinical dashboard — provides an unusually direct translation pathway. The simulation engine, database, API, and clinical interface exist and are operationally deployed. Sensor integration targets an existing architectural socket (IDH feature #38), adds two new domains (cardiac electrical safety, real-time fluid dynamics), and extends three existing domains (IDH, adequacy, fluid volume) with higher-resolution inputs. The proposed research therefore advances a system already in clinical use, rather than developing a parallel research prototype with uncertain translation prospects.

---

## 8. Conclusion

The Digital Dialysis Twin reviewed in this annexure represents a technically rigorous and clinically grounded multi-domain simulation engine, founded on internationally validated clinical equations (Daugirdas, Leypoldt, Tattersall, Laursen), probabilistic reasoning frameworks (Bayesian conjugate updating, Mondrian split-conformal prediction, MCMC calibration), and a comprehensive clinical data architecture covering the principal determinants of haemodialysis outcome. Its design reflects a deliberate commitment to honest uncertainty quantification, clinically interpretable outputs, and longitudinal outcome tracking.

The system's identified limitations are structural rather than incidental: they arise from the absence of real-time physiological monitoring during the haemodialysis session, leaving a fundamental temporal resolution gap between the minute-level physics modelled by the simulation and the monthly or per-session data that currently feeds it. A pre-designed but unpopulated feature socket for autonomic input in the IDH model (feature #38), combined with the complete absence of cardiac electrical domain modelling, identifies specific architectural opportunities that the proposed doctoral research is positioned to address.

The convergence of two sensor modalities (wireless ECG and optical RBV monitoring), four structured data enhancements (NIBP trajectory, actual Qb, actual UF volume, mandatory PRO), and the Bayesian personalisation architecture already embedded in the system creates a defensible and practically realisable doctoral research programme with direct clinical utility and clear scientific novelty across three independent dimensions: sensor fusion architecture, QTc kinetic modelling, and closed-loop personalised prediction.

---

## References

Angelopoulos, A.N. & Bates, S. (2023). Conformal prediction: A gentle introduction. *Foundations and Trends in Machine Learning*, 16(4), 494–591.

Basile, C., Lomonte, C., Vernaglione, L., Casucci, F., Antonelli, M. & Losurdo, N. (2008). The relationship between the flow of arteriovenous fistula and cardiac output in haemodialysis patients. *Nephrology Dialysis Transplantation*, 23(1), 282–287.

Buiten, M.S., de Bie, M.K., Rotmans, J.I., Gabreëls, B.A., van Dorp, W., Wolterbeek, R., … & Jukema, J.W. (2017). The dialysate potassium level is associated with the QTc interval. *Heart Rhythm*, 14(2), 248–254.

Chen, T. & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, 785–794.

Daugirdas, J.T. (1993). Second generation logarithmic estimates of single-pool variable volume Kt/V: an analysis of error. *Journal of the American Society of Nephrology*, 4(5), 1205–1213.

Fishbane, S. & Nissenson, A.R. (2010). Anemia management in chronic kidney disease. *Kidney International Supplements*, 78(S117), S3–S9.

Flythe, J.E., Kimmel, S.E. & Brunelli, S.M. (2011). Rapid fluid removal during dialysis is associated with cardiovascular morbidity and mortality. *Kidney International*, 79(2), 250–257.

Flythe, J.E., Chang, T.I., Gallaher, M.M., Lindley, E., Mohiuddin, G., Mooney, A. & Parker, K. (2015). Clinical applications of intradialytic blood pressure monitoring. *Kidney International Reports*, 1(2), 85–101.

Genovesi, S., Valsecchi, M.G., Rossi, E., Pogliani, D., Acquistapace, I., DeVecchi, A., … & Stella, A. (2008). Sudden death and associated factors in a historical cohort of chronic haemodialysis patients. *Nephrology Dialysis Transplantation*, 24(8), 2529–2536.

Jadoul, M., Thumma, J., Fuller, D.S., Tentori, F., Li, Y., Morgenstern, H., … & Robinson, B.M. (2017). Modifiable practices associated with sudden death among haemodialysis patients in the Dialysis Outcomes and Practice Patterns Study. *Clinical Journal of the American Society of Nephrology*, 7(5), 765–774.

KDIGO (2017). KDIGO 2017 Clinical Practice Guideline Update for the Diagnosis, Evaluation, Prevention, and Treatment of Chronic Kidney Disease-Mineral and Bone Disorder (CKD-MBD). *Kidney International Supplements*, 7(1), 1–59.

KDOQI (2006). KDOQI Clinical Practice Guidelines and Clinical Practice Recommendations for 2006 Updates: Hemodialysis Adequacy, Peritoneal Dialysis Adequacy and Vascular Access. *American Journal of Kidney Diseases*, 48(S1), S1–S322.

Leypoldt, J.K., Jaber, B.L. & Zimmerman, D.L. (2003). Predicting treatment dose for novel therapies using urea standard Kt/V. *Seminars in Dialysis*, 17(2), 142–145.

MacRae, J.M., Levin, A. & Belenkie, I. (2004). The cardiovascular effects of arteriovenous fistulas in chronic kidney disease: A cause for concern? *Seminars in Dialysis*, 19(5), 349–352.

Ranpuria, R., Hall, M., Chan, C.T. & Unruh, M. (2008). Heart rate variability (HRV) in kidney failure: measurement and consequences of reduced HRV. *Nephrology Dialysis Transplantation*, 23(2), 444–449.

Rubinger, D., Sapoznikov, D., Pollak, A., Popovtzer, M.M. & Luria, M.H. (2004). Heart rate variability during chronic hemodialysis and after renal transplantation: studies in patients without and with systemic amyloidosis. *Journal of the American Society of Nephrology*, 15(4), 1065–1072.

Shafer, G. & Vovk, V. (2008). A tutorial on conformal prediction. *Journal of Machine Learning Research*, 9, 371–421.

Tattersall, J.E., DeTakats, D., Chamney, P., Greenwood, R.N. & Farrington, K. (1996). The post-hemodialysis rebound: predicting and quantifying its effect on Kt/V. *Kidney International*, 50(6), 2094–2102.

---

*End of Annexure A*

*Document prepared to accompany the PhD research proposal: "Real-Time Sensor Fusion in a Multi-Domain Haemodialysis Digital Twin: Towards Closed-Loop Personalised Prediction of Intradialytic Cardiovascular Events"*
