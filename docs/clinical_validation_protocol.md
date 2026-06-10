# Clinical Validation Protocol: Implementing the Digital Dialysis Twin

This protocol outlines the step-by-step procedure for validating and integrating the **Digital Dialysis Twin (DDT)** and **Anemia Control Model (ACM)** into a clinical hemodialysis (HD) unit workflow. 

The validation program is structured into four progressive phases, designed to establish data integrity, build clinician trust, verify local prediction accuracy, and audit safety outcomes.

---

## Phase 1 — Setup Before First Patient (Week 1)

### 1. Verify Your Data is Complete for Each Patient
Every patient needs these specific fields filled in the system before the physiological twin can generate reliable outputs:

| Field | Where to Enter | Why it Matters (Physiological Basis) |
| :--- | :--- | :--- |
| **Pre-HD weight** (last 3 months) | Monthly records | Required for Kt/V volume of distribution and ultrafiltration (UF) rate calculations. |
| **Pre/Post dialysis urea** | Monthly records | Serves as the Kt/V anchor using the **Daugirdas second-generation formula**. |
| **Blood flow rate (Qb)** | Session records | Baseline parameter for the dialyzer urea clearance ($K_d$) mathematical model. |
| **Actual session time** | Session records | Essential for time scaling of clearance and intradialytic risk calculations. |
| **UF volume per session** | Session records | Determines the ultrafiltration rate and is the primary driver of intradialytic hypotension (IDH) risk. |
| **Dialysate flow (Qd)** | Session records | Sets the baseline on the Qd prescribing slider and affects dialyzer clearance capacity. |
| **ESA dose + TSAT** | Monthly records | Baseline values for the erythropoiesis ordinary differential equation (ODE) to predict Hb trajectory. |
| **Phosphorus + binder type** | Monthly records | Inputs for the two-compartment Runge-Kutta 4th-order (RK4) phosphate kinetics simulator. |

### 2. Run the Twin on 5 Well-Documented Patients First
Select a calibration cohort of 5 patients to verify setup. These patients must meet the following criteria:
* **$\ge 6$ months** of complete monthly and session records in the system.
* **No major prescription changes** (Qb, Qd, session time, or dry weight adjustments) in the last 3 months.
* A representative clinical mix:
  * 2 patients with historically adequate dialysis dose ($\text{spKt/V} \ge 1.2$).
  * 2 patients with inadequate dialysis dose ($\text{spKt/V} < 1.2$).
  * 1 patient with a high intradialytic hypotension (IDH) risk profile.

---

## Phase 2 — Parallel Shadow Validation (Weeks 2–4)

**Objective**: Verify prediction accuracy and build clinical familiarity *without* modifying active patient prescriptions.

```mermaid
graph TD
    A[Load Patient Profile in DDT Sandbox] --> B[Run Baseline Simulation (Current Prescription)]
    B --> C[Record Twin Predictions & Uncertainty Bands]
    C --> D[Log Shadow Scenarios via 'Adopt' Button]
    D --> E[Wait 30 Days & Gather Real Outcomes]
    E --> F[Run Outcome Backfill & Audit MAE]
    F --> G{MAE within limits?<br>Hb < 0.75 g/dL}
    G -- Yes --> H[Proceed to Phase 3: Active Support]
    G -- No --> I[Recalibrate Patient-Specific Parameters]
```

### 1. Log Baseline Predictions
For each of your 5 validation cohort patients:
1. Navigate to the **Digital Dialysis Twin** screen (`/twin/{patient_id}`).
2. Verify that the current prescription matches the values prepopulated in the sliders (Qb, Qd, session hours, UF volume, etc.).
3. Run the simulation to view the baseline predicted trajectories:
   * **Hb Trajectory**: Note the 3-month point prediction and the shaded **80% Prediction Interval** (uncertainty band).
   * **Pre-dialysis Phosphorus**: Note the steady-state predicted value and verify if it matches the latest lab test.
   * **spKt/V and eKt/V**: Verify that the calculated baseline matches standard clinical calculations.
   * **IDH Risk**: Note the baseline risk percentage and the conformal prediction interval bounds.

### 2. Run and Log "Shadow" Prescription Scenarios
When clinicians conduct regular monthly patient reviews:
1. Use the prescribing sliders to test alternative options (e.g., increasing session time by 30 minutes, increasing Qb, or adjusting phosphate binders).
2. Click **Run Simulation** and review the **Cross-Domain Cascade Card**. Observe how changes propagate:
   * *Example*: $\text{Session Duration} \uparrow \implies \text{spKt/V} \uparrow \text{, Phosphate Removal} \uparrow \text{, and IDH Risk} \downarrow$ (due to lower implied UF rate).
3. If an adjustment is clinically desirable, click **Adopt Proposed Prescriptions** in the dashboard.
4. **Important**: Do *not* apply this change to the patient's actual clinic prescription. In the clinician notes field, enter: `"SHADOW TEST: [Description of prescription change]"`. This saves the simulation state to the database (`twin_simulations` table) with the `adopted` flag for prospective evaluation.

### 3. Measure Prediction Error
At the end of the 4-week shadow block, run the validation audit:
1. Trigger the outcome backfill service (which executes `services/twin_feedback.py::backfill_twin_outcomes`).
2. Run the unit analytics report from the terminal:
   ```bash
   python validation_engine.py
   ```
3. Evaluate the **Mean Absolute Error (MAE)** of the twin's predictions:
   * **Hb Trajectory MAE Target**: $< 0.75\text{ g/dL}$ (aligns with the Fresenius ACM benchmark).
   * **spKt/V MAE Target**: $< 0.10$.
   * **Pre-dialysis Phosphate MAE Target**: $< 0.8\text{ mg/dL}$.
4. If errors exceed these boundaries, check the patient records for data entry omissions, acute inflammatory events (high CRP), or blood transfusions.

---

## Phase 3 — Active Clinical Decision Support (Weeks 5–8)

**Objective**: Use the Digital Twin to guide active clinical adjustments for patients with suboptimal therapy.

### 1. Identify Optimization Candidates
Review your unit census to select 5–10 patients who are out of target:
* **Adequacy**: $\text{spKt/V} < 1.2$ or $\text{eKt/V} < 1.0$.
* **Phosphate**: Pre-dialysis serum phosphorus $> 5.5\text{ mg/dL}$.
* **IDH**: Symptomatic systolic BP drop $\ge 20\text{ mmHg}$ or nadir SBP $< 90\text{ mmHg}$ in $\ge 20\%$ of sessions.
* **Anemia**: Hb fluctuating outside the $10.0\text{--}11.5\text{ g/dL}$ target window.

### 2. Formulate Optimized Prescriptions in the Sandbox
Load each patient in the DDT sandbox and adjust parameters to solve clinical deficiencies:

* **To resolve inadequate Kt/V**:
  * Gradually increase Qb by $20\text{--}50\text{ mL/min}$ or extend session time by $15\text{--}30\text{ minutes}$.
  * Review the predicted dialyzer clearance ($K_d$) shift.
* **To resolve hyperphosphatemia**:
  * Adjust the Phosphate Binder Dose (PBE) slider or dietary intake estimate.
  * If the RK4 kinetic model indicates persistent elevations, simulate extending the session duration to allow for tissue-to-plasma phosphate refilling.
* **To mitigate IDH risk**:
  * Maintain the ultrafiltration rate below the purple reference line ($4.0\text{ mL/kg/h}$).
  * Reduce dialysate temperature (e.g., from $37.0^\circ\text{C}$ to $36.0^\circ\text{C}$) to support peripheral vasoconstriction.
  * Adjust dialysate sodium if the patient experiences post-dialysis thirst.

### 3. Review Cross-Domain Safety Flags
Before adopting any prescription change, inspect the safety modules:
* **Vascular Access Flow ($Q_a$)**: Review the hemodynamic shunt ratio. If the access shunt ratio exceeds $0.30$ or $Q_a > 1500\text{ mL/min}$, there is high cardiac output strain. **Do not increase blood flow (Qb) without cardiology clearance.**
* **Fluid Volume Dynamics**: Check the two-compartment trajectory. If the relative blood volume (RBV) is projected to fall below the patient's plasma refill threshold, reduce the target UF volume or extend session duration.

### 4. Implement and Log Decisions
1. Upon clinician agreement, update the prescription in the unit's EMR.
2. In the DDT interface, click **Adopt Proposed Prescriptions**.
3. Log the decision rationale in the clinician notes field (e.g., `"Implemented Qb 350 and Qd 800 per DDT simulation to correct Kt/V from 1.08 to predicted 1.22"`).

---

## Phase 4 — Quality Audit & Safety Evaluation (Week 12 and Beyond)

**Objective**: Assess clinical outcomes, monitor model calibration, and maintain safety guardrails.

### 1. Run the Calibration Audits
Models can drift over time as patient demographics and clinical practices change.
* **Unit Calibration**: Run the validation engine monthly via CLI (`python validation_engine.py`) to confirm that Harrell's C-index for the 1-year mortality prediction model remains above **0.70**.
* **Anemia Model Audit**: Access the **ACM Audit Dashboard** (`/acm/audit`) to monitor:
  * **Reliability Diagram**: Confirms that predicted probabilities align with observed outcomes.
  * **ESA Dose-Response Calibration**: Assesses the cohort's sensitivity to erythropoietin changes.

### 2. Measure Clinical Outcome Metrics
Compare your unit's baseline metrics (pre-DDT implementation) with the outcomes at Week 12:

| Metric | Target | Source / Reference |
| :--- | :--- | :--- |
| **Hb Target Attainment** | $\ge 70\%$ of patients within $10.0\text{--}11.5\text{ g/dL}$ | KDIGO 2012 Guidelines |
| **Dose Reduction** | $\sim 20\text{--}25\%$ reduction in overall weekly ESA dose | Fuertinger et al. (CJASN 2024) |
| **Adequacy Rate** | $\ge 90\%$ of patients achieving $\text{spKt/V} \ge 1.2$ | KDOQI Adequacy Target |
| **Phosphate Control** | $\ge 75\%$ of patients within $3.5\text{--}5.5\text{ mg/dL}$ | KDIGO CKD-MBD Guidelines |
| **IDH Incidence** | $\ge 30\%$ relative reduction in IDH-complicated sessions | Flythe et al. (2015) |

### 3. Continuous Data Quality Surveillance
* Ensure that the input **Quality Gate** (`ml_quality_gate.py`) is never bypassed. If a transcription error occurs (e.g., post-dialysis BUN is higher than pre-dialysis BUN), the system must reject the input.
* Perform weekly reviews of the **Ward Alerts Panel** (`/alerts`) to address patient deterioration alerts, critical QTc prolongations, or rapid albumin declines ($>0.3\text{ g/dL/month}$).

---

*This protocol serves as a practical clinical integration guide. The Digital Dialysis Twin is a clinical decision-support tool; final prescription authority and patient safety responsibility remain with the attending nephrologist.*
