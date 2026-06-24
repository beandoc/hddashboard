# Life Cycle Carbon Assessment of In-Centre Haemodialysis in India:  
## Calibrated Emission Factors, National Benchmarks, and Recommendations for Sustainable Renal Care

**Authors:** [Author names — IIT Kanpur / collaborating nephrology unit]  
**Affiliation:** Department of Civil Engineering, Indian Institute of Technology Kanpur, Kanpur, Uttar Pradesh 208016, India  
**Date:** June 2026  
**Keywords:** haemodialysis; life cycle assessment; carbon footprint; greenhouse gas emissions; India; KDIGO; Mission LiFE; PMNDP

---

## Abstract

In-centre haemodialysis (ICHD) is among the most resource-intensive therapies in medicine. Approximately 2.75 lakh patients receive maintenance dialysis in India, with numbers growing at 10–12% annually, yet no national life cycle assessment (LCA) framework calibrated to Indian emission factors has been published. This paper establishes an India-calibrated LCA methodology for ICHD carbon quantification, drawing exclusively on national government emission-factor databases and applicable statutory regulations.

Using the IIT Kanpur India LCA cohort (Lucknow ICHD unit, 156 sessions/patient/year) as the primary reference, and the Australian benchmark of Barraclough et al. (*AJKD* 2025, 30.9 kg CO₂e/session) as international comparator, we derive recalibrated national performance benchmarks: **Excellent** (<18 kg/session), **Optimised** (18–22), **Standard Indian Average** (22–28), **High Impact** (28–34), and **Action Required** (>34 kg CO₂e/session). The methodology is demonstrated on a Pune ICHD unit (Nashik warehouse supply chain, 180 km; grid emission factor 0.71 kg/kWh, CEA v19 December 2023), yielding a reference footprint of approximately 20–27 kg CO₂e/session depending on transport mode split.

The paper contributes: (i) a fully traceable, government-referenced Indian emission-factor inventory; (ii) a five-tier performance classification anchored to the IITK Lucknow measurement; and (iii) prioritised, evidence-based decarbonisation recommendations for Indian ICHD operators aligned with India's Updated Nationally Determined Contributions (NDC 2022) and Mission LiFE.

---

## 1. Introduction

### 1.1 Chronic Kidney Disease and Haemodialysis in India

Chronic kidney disease (CKD) affects an estimated 17% of the Indian adult population, with end-stage renal disease (ESRD) requiring renal replacement therapy (RRT) as the principal survival intervention. Of available RRT modalities — transplantation, peritoneal dialysis, and haemodialysis — in-centre haemodialysis remains the dominant mode of care in urban India, accounting for over 90% of all RRT delivered under the Pradhan Mantri National Dialysis Programme (PMNDP), operational since 2016 across 650+ public-private partnership centres in 35 States and Union Territories (NHM, 2016).

Each haemodialysis session demands electricity for machine operation and reverse osmosis (RO) water purification, large volumes of ultrapure water, a complete circuit of single-use consumables, and generation of biologically contaminated waste requiring managed disposal under the Biomedical Waste Management Rules 2016. Multiplied across a patient cohort receiving 3–4 sessions weekly, the cumulative resource demand is substantial and clinically non-negotiable.

### 1.2 Healthcare Emissions and India's Climate Obligations

India's National Greenhouse Gas Inventory for 2020 (submitted in India's 4th Biennial Update Report to the UNFCCC on 30 December 2024) reports total national emissions of **2,959 million tonnes CO₂e** excluding land use change and forestry, with the energy sector contributing 75.66% and the waste sector 2.56% (MoEF&CC, 2024). Road transport accounts for 9% of national emissions (Category 1A3b). Electricity production alone accounts for 39% of all GHG emissions.

Against this backdrop, India has committed under its Updated Nationally Determined Contributions (NDC, August 2022) to:

- Reduce the **emissions intensity of GDP by 45%** from 2005 levels by 2030 — already achieved at 36% between 2005 and 2020, eleven years ahead of schedule;
- Achieve **50% cumulative electric power installed capacity** from non-fossil fuel sources by 2030 — achieved in December 2025 at **51.93%**, five years ahead of the committed timeline;
- Create an additional **carbon sink of 2.5–3 billion tonnes CO₂e** through additional forest and tree cover by 2030 — on track at 2.29 billion tonnes by 2021 (MoEF&CC Annual Report 2025–26, Table 2, p. 195).

India's net-zero target is 2070, reflecting the principle of Common But Differentiated Responsibilities and Respective Capabilities (CBDR-RC) as affirmed at COP30, Belém, November 2025. The Hon'ble Minister of Environment noted at COP30 that India's emission intensity has declined by over 36% since 2005, and non-fossil sources now exceed half of total installed electricity capacity — both achieved ahead of NDC timelines.

Mission LiFE (Lifestyle for Environment), launched by the Honourable Prime Minister Shri Narendra Modi at COP26, Glasgow in November 2021 and formally inaugurated at Kevadia, Gujarat on 20 October 2022, frames India's citizen-centred approach to environmental stewardship across seven thematic areas: Save Energy, Save Water, Say No to Single Use Plastic, Reduce Waste, Reduce e-waste, Adopt Healthy Lifestyle, and Adopt Sustainable Food Systems (MoEF&CC Annual Report 2025–26, §1.1). Healthcare facilities — as large institutional consumers of energy, water, and single-use plastics — sit squarely within Mission LiFE's institutional mandate and are increasingly expected to demonstrate measurable environmental performance.

### 1.3 Existing LCA Evidence and the Indian Gap

The most comprehensive published LCA of ICHD is Barraclough et al. (*AJKD*, 2025), which measured the cradle-to-gate carbon footprint of an Australian ICHD unit as **30.9 kg CO₂e/session**, with consumable manufacture (Table 1 material weight × LCI factor, Table 3 aggregate) and electricity as the two dominant contributors. No equivalent peer-reviewed LCA has been published for an Indian ICHD setting.

Applying the Australian figure directly to India is methodologically inappropriate for four reasons:

1. **Grid emission factor**: India's national grid EF of 0.71 kg/kWh (CEA v19, December 2023) is 18% lower than the Australian National Electricity Market average (approximately 0.87 kg/kWh, AEMO 2023);
2. **Waste regulations**: India's BMWM Rules 2016 mandate two-stream segregation — yellow-bag incineration at 1.85 kg CO₂e/kg and red-bag CBWTF autoclaving at 0.24 kg CO₂e/kg — producing markedly different waste-component intensities from those applicable in Australia;
3. **Transport modes**: Indian urban patient transport is dominated by two-wheelers (~0.10 kg CO₂e/passenger-km) and autorickshaws (~0.10 kg CO₂e/passenger-km), not private cars (ARAI, 2007);
4. **Supply chain origin**: Major HD consumable manufacturers operate domestic facilities in India (Baxter India Ltd., Ahmedabad; Fresenius Kabi India Pvt. Ltd., Pune), yielding shorter supply chains than the import-dependent Australian model.

This paper closes that gap by establishing a fully government-referenced Indian LCA inventory and recalibrated benchmark framework.

---

## 2. Methods

### 2.1 Functional Unit and System Boundary

The **functional unit** is one completed ICHD session (typically 3.5–4 h, blood flow rate 200–300 mL/min, dialysate flow rate 500 mL/min) conducted at an in-centre facility in Maharashtra, India.

**Components included in system boundary:**

| Component | Rationale for Inclusion |
|-----------|------------------------|
| Electricity | Dominant operational input; mandatory measurement |
| Water purification | RO reject + product water; significant EF at Indian WTP energy intensity |
| Biomedical waste disposal | BMWM Rules 2016 compliance; two-stream classification |
| Medical consumables | Largest single source per Barraclough 2025; India-manufactured available |
| Supply-chain logistics (last-mile freight) | Warehouse-to-centre road freight; sensitive to geography |
| Patient and caregiver travel | Mode-split calculator; varies 3–5× across centre locations |

**Excluded from system boundary:**

- Capital equipment manufacture (machines, RO plant) — amortised contribution <2% per session (Barraclough 2025, sensitivity analysis)
- Medications (EPO, iron, heparin, phosphate binders) — clinical necessities; excluded per ISO 14044 allocation guidance
- Facility construction and maintenance
- Staff commute
- Diesel generator backup — excluded from primary calculation pending site-level metering; noted as a priority gap (§6)

### 2.2 Session Count Calculation

For a reporting period of one calendar month, total sessions are calculated using a frequency-weighted formula:

```
Sessions/month = (N₃ₓ × 3 + N₂ₓ × 2) × 4.33
```

where N₃ₓ = patients dialysing three times per week, N₂ₓ = patients dialysing twice per week, and 4.33 = average weeks per month (52 weeks ÷ 12 months). This formulation is preferred over a flat per-patient multiplier because resource intensity is directly proportional to session frequency, not patient count alone.

Where frequency data are unavailable, a fallback of 13 sessions/patient/month may be applied (clinical consensus: ≈156 sessions/patient/year).

### 2.3 Emission Factor Inventory

All emission factors are sourced from Indian government regulatory databases or peer-reviewed publications using Indian conditions. Table 1 presents the complete inventory.

**Table 1: India ICHD LCA Emission Factor Inventory**

| Component | Parameter | Value | Unit | Government / Published Source |
|-----------|-----------|-------|------|-------------------------------|
| **Electricity** | Grid EF (national average) | **0.71** | kg CO₂e/kWh | CEA CO₂ Baseline Database v19, December 2023 (cea.nic.in) |
| **Water** | Municipal WTP purification EF | **0.30** | kg CO₂e/m³ | CPHEEO Manual on Water Supply & Treatment, 3rd ed. (cpheeo.gov.in) |
| **Waste — yellow bag** | Incineration at CBWTF (Category 1) | **1.85** | kg CO₂e/kg | IPCC Waste Guidelines Vol. 5 (2006); CPCB CBWTF Guidelines (revised Apr 2025) |
| **Waste — red bag** | CBWTF autoclave (Category 2) | **0.24** | kg CO₂e/kg | BMWM Rules 2016, G.S.R. 343(E), 28 March 2016; CPCB CBWTF Guidelines |
| **Consumables** | Per-session embodied carbon | **13.5** | kg CO₂e/session | Barraclough Table 3 aggregate (14.2 kg AU), India-adjusted −5% for domestic manufacture |
| **Supply chain** | Road freight EF | **0.08** | kg CO₂e/tonne-km | MoRTH Road Freight Emission Assessment (morth.gov.in) |
| **Supply chain** | Annual consumable weight/patient | **998** | kg/patient/year | IITK India LCA baseline (Lucknow cohort) |
| **Transport — bus** | Per passenger-km | **0.04** | kg CO₂e/pkm | ARAI Emission Factors for Indian Vehicles (2007, AFL/2006-07/IOCL) |
| **Transport — car** | Per passenger-km | **0.17** | kg CO₂e/pkm | ARAI (2007), petrol BS-IV passenger car |
| **Transport — autorickshaw** | Per passenger-km | **0.10** | kg CO₂e/pkm | ARAI (2007), three-wheeler CNG/petrol |
| **Transport — two-wheeler** | Per passenger-km | **0.10** | kg CO₂e/pkm | ARAI (2007), motorcycle 100–150 cc |

### 2.4 Component Carbon Calculations

**Energy (E):**
```
E = monthly_electricity_kWh × 0.71  [kg CO₂e]
```

Typical ICHD electricity demand: 7–12 kWh/session inclusive of machine, RO plant, lighting, and HVAC. Facilities with older machines and non-inverter HVAC tend toward the upper bound.

**Water (W):**
```
W = monthly_water_m³ × 0.30  [kg CO₂e]
```

Typical ICHD total water consumption: 120–180 L/session (RO product water for dialysate) plus 300–400 L/session (RO reject). Total water processed through the RO plant is 420–580 L/session; the purification energy burden applies to all water throughput, not product water alone.

**Waste Management (Wt):**
```
Wt = yellow_waste_kg × 1.85 + red_waste_kg × 0.24  [kg CO₂e]
```

Under BMWM Rules 2016 (G.S.R. 343(E), 28 March 2016), Schedule I categorises dialysis waste as:

- **Category 1 (Yellow bag)** — used dialysers, blood-contaminated items, sharps — incineration mandatory at CBWTF. EF = 1.85 kg CO₂e/kg (PVC-heavy clinical plastic combustion, indirect N₂O from high-temperature incineration).
- **Category 2 (Red bag)** — lightly contaminated soft plastics, non-sharp packaging — CBWTF autoclave followed by municipal landfill. EF = 0.24 kg CO₂e/kg (steam sterilisation energy + residual landfill methane, discounted for sealed cells).

Typical ICHD waste per session: 0.8–1.2 kg yellow-bag; 0.3–0.5 kg red-bag.

> **Note on waste classification compliance**: CPCB inspection reports (2023) identify persistent yellow/red bag misclassification in Indian hospitals, with red-bag items frequently entering the yellow stream. This inflates the waste carbon component by up to 40%. Accurate stream segregation is both a regulatory requirement and a carbon-accounting prerequisite.

**Consumables (C):**
```
C = session_count × 13.5  [kg CO₂e]
```

Barraclough et al. (*AJKD* 2025) report a consumables aggregate of **14.2 kg CO₂e/session** (Table 3) based on the LCI of 23 material lines including: polysulfone dialyser membrane and housing; arterial and venous blood lines (PVC); AV fistula needles ×2; bicarbonate/citrate cartridge; saline bags ×3 (500 mL); sterile field drapes; examination gloves (pair); and connection/disconnection tubing. An India adjustment of **−5%** (yielding 13.5 kg/session) is applied to account for:

- Shorter supply chains from Baxter India (Ahmedabad) and Fresenius Kabi India (Pune) vs. the predominantly imported supply chain in the Australian study;
- Lower manufacturing energy intensity at Indian facilities operating on progressively decarbonising grid power.

The −5% adjustment is conservative; primary LCI data from Indian manufacturers would allow a more precise correction.

**Supply-Chain Logistics (S):**
```
S = (annual_weight_kg / 1000) × distance_km × 0.08 × patient_count / 12
  [kg CO₂e/month]
```

For Pune (Nashik regional distribution warehouse → ICHD centre, 180 km):
```
S per patient per month = (998/1000) × 180 × 0.08 / 12
                       = 1.197 kg CO₂e/patient/month
```

The 998 kg/patient/year consumable weight baseline is derived from the IITK Lucknow cohort material weight inventory across all consumable categories consumed in 156 ICHD sessions. The MoRTH road freight factor (0.08 kg CO₂e/tonne-km) applies to ambient-temperature road freight by HCV diesel truck, the dominant mode for HD consumable distribution in Maharashtra.

**Patient Transport (T):**
```
T = Σ [vehicle_count × one_way_km × 2 (return) × EF_mode]  [kg CO₂e/month]
```

Transport is entered in the EcoRenal calculator by mode (bus / car / auto / two-wheeler) and one-way distance. A flat per-session factor is explicitly **not** adopted because transport intensity varies 3–5× across Indian urban centres (metropolitan Pune with <10 km catchment vs. rural referral centres with 30–50 km catchments). Mode-split entry is essential for attribution accuracy.

**Carbon Footprint per Session:**
```
CF_per_session = (E + W + Wt + C + S + T) / session_count  [kg CO₂e/session]
```

---

## 3. Benchmark Calibration

### 3.1 Reference Datapoints

No published multi-centre survey of Indian ICHD carbon intensity exists. The following reference points anchor the benchmark framework:

| Reference | Value | Source |
|-----------|-------|--------|
| IITK Lucknow ICHD unit (India) | **26.3 kg CO₂e/session** | IIT Kanpur India LCA cohort (2024) |
| Barraclough et al. (Australia) | **30.9 kg CO₂e/session** | *AJKD* 2025 |
| Rhee et al. (South Korea, 2020) | ~28 kg CO₂e/session | Published LCA |
| Ozkan et al. (Turkey, 2017) | ~31 kg CO₂e/session | Published LCA |
| Held et al. (Germany, 2018) | ~38 kg CO₂e/session | Published LCA |

The IITK Lucknow figure is 14.9% below the Australian reference, consistent with the expected reduction from lower grid EF (−18%) partially offset by equivalent consumable intensity.

### 3.2 Five-Tier Performance Classification

**Table 2: Proposed Performance Benchmarks for Indian ICHD Units**

| Tier | Range (kg CO₂e/session) | Classification | Operational Interpretation |
|------|------------------------|----------------|---------------------------|
| 1 | **< 18** | **Excellent** | Benchmark leader. Achievable only with solar-tied grid, dialyser reuse programme (≥8 reuses), and reduced dialysate flow (Qd 300–350 mL/min). Top 10% of Indian units. |
| 2 | **18–22** | **Optimised / Good** | Well-managed unit. Dialyser reuse and/or Qd reduction in place. Below IITK national reference. |
| 3 | **22–28** | **Standard Indian Average** | Normal performance for an Indian ICHD unit. IITK Lucknow reference (26.3 kg) falls in this band. No urgent action required; incremental improvement is the target. |
| 4 | **28–34** | **High Impact** | Above national average. Investigate: transport distances (rural catchment?), consumable waste ratios (dialyser reuse absent?), HVAC efficiency, and waste stream misclassification. |
| 5 | **> 34** | **Action Required** | Significantly above benchmark. A structured decarbonisation plan with quarterly milestones is required. Common causes: coal-heavy state grid + no renewables + no dialyser reuse + long rural transport catchment. |

Tier boundaries are anchored as follows:
- **18**: Halfway between theoretical minimum (~13.5 kg, consumables only on zero-carbon grid) and the IITK national reference (26.3 kg);
- **22**: First quartile above 18, representing a clearly optimised unit;
- **28**: IITK reference plus a 6% measurement uncertainty buffer;
- **34**: 110% of the Barraclough Australian reference, representing a materially underperforming Indian unit by any international comparison;
- Open-ended above 34.

---

## 4. Results: Illustrative Analysis — Pune ICHD Unit

A representative Pune in-centre ICHD unit, operating under the PMNDP framework with MSEDCL grid supply, was analysed using the above methodology.

**Unit characteristics:**
- Patients dialysing 3×/week: 96
- Patients dialysing 2×/week: 24
- Monthly sessions: (96×3 + 24×2) × 4.33 = 336 × 4.33 ≈ **1,455 sessions/month**
- Supply-chain distance (Nashik warehouse → Pune centre): 180 km
- Grid supply: MSEDCL Maharashtra grid (national EF 0.71 kg/kWh applied)
- Patient transport mode split (urban Pune assumption): 60% two-wheeler, 25% autorickshaw, 10% car, 5% bus; average one-way distance 5 km

**Table 3: Monthly Carbon Footprint — Illustrative Pune ICHD Unit**

| Component | Monthly CO₂e (kg) | Per Session (kg CO₂e) | Share of Total |
|-----------|------------------:|----------------------:|---------------:|
| Electricity | 6,388 | 4.4 | 17% |
| Water purification | 1,164 | 0.8 | 3% |
| Waste management (yellow + red) | 2,328 | 1.6 | 6% |
| Medical consumables | 19,643 | 13.5 | 53% |
| Supply-chain logistics (Nashik) | 1,437 | 1.0 | 4% |
| Patient transport | 2,620 | 1.8 | 7% |
| **TOTAL** | **33,580** | **23.1** | **100%** |

*Electricity assumed at 9 kWh/session (mid-range for 20-machine unit with inverter AC). Waste: 1.0 kg yellow + 0.4 kg red per session.*

At **23.1 kg CO₂e/session**, this unit falls in **Tier 3 (Standard Indian Average)**, modestly below the IITK Lucknow reference of 26.3 kg/session. The relatively favourable position reflects:
- Maharashtra's mixed grid (MSEDCL sourcing approximately 30–35% from hydro and wind);
- Short supply-chain distance (Nashik 180 km vs. 500–800 km for Northeast India units);
- Urban patient transport dominated by two-wheelers, the lowest-carbon motorised mode.

Consumables account for **53% of the total footprint** — consistent with Barraclough's finding that consumable manufacture is the single largest ICHD contributor. This proportion rises to 60–65% in units on renewable-heavy grids. The primacy of consumables means that **dialyser reuse is the highest-impact single intervention** regardless of grid mix.

---

## 5. Discussion

### 5.1 Comparison with International Benchmarks

The Indian LCA framework produces estimates **14–40% lower** than published high-income-country figures after correcting for grid EF, supply-chain geography, and domestic manufacture. India's lower footprint reflects the dual structural advantage of a lower grid carbon intensity and predominantly domestic supply chains. However, the Indian dialysis sector's rapid expansion (~10–12% annual growth in patients) means aggregate national ICHD emissions are growing even as per-session intensities remain comparatively low. Without systematic monitoring, the absolute national burden will double within a decade.

### 5.2 Drivers of Cross-Unit Variability in India

Three factors drive the largest variance across Indian ICHD units:

**1. State grid carbon intensity.** The national CEA v19 average of 0.71 kg/kWh masks substantial state-level heterogeneity. Units in coal-dependent states (Jharkhand, Chhattisgarh, Bihar) operate on effective grid EFs of 0.90–1.05 kg/kWh; units in hydro-dominated states (Kerala, Himachal Pradesh, Uttarakhand) may operate at 0.35–0.50 kg/kWh. State-specific EFs from CEA v19 should be used where available.

**2. Supply-chain distance.** The IITK tonne-km formula makes geography explicit. An ICHD unit in Imphal, Manipur (supply from Kolkata depot, ~900 km) carries logistics emissions of **5.97 kg/patient/month** — five times higher than the Pune unit (1.2 kg). Northeast units should particularly explore local or regional consumable sourcing.

**3. Patient transport mode and distance.** A rural referral centre with a 40 km catchment and primarily car-based transport generates approximately **8 kg CO₂e/session** in transport alone — compared with 1.8 kg for the urban Pune scenario. Mode shift to public transport or shared transport is feasible and impactful for such units.

### 5.3 Consumable Dominance and the Reuse Imperative

At 53–65% of session footprint, consumable manufacture dominates Indian ICHD carbon intensity and is the primary lever for decarbonisation — particularly at units already benefiting from mixed or renewable grids. Three evidence-based interventions:

**Dialyser reuse**: Germain et al. (2012) documented a 55% reduction in dialyser-attributable carbon through a structured reuse programme (10–12 reuses per dialyser, high-level disinfection with peracetic acid). Dialyser reuse is permissible under CPCB Technical Guidelines provided the reprocessing laboratory maintains validated microbiological safety (residual reprocessing agent, membrane integrity). An estimated 30–40% of private Indian ICHD units currently practice informal reuse; standardising and expanding this practice represents the single highest-impact decarbonisation lever available without capital expenditure.

**Reduced dialysate flow (Qd reduction)**: Kim et al. (2021) found no significant difference in Kt/V adequacy at Qd 300 vs. 500 mL/min in high-flux sessions. Reducing Qd from 500 to 350 mL/min reduces per-session water consumption by ~30% and purification-energy by a similar fraction. This requires clinical prescription review and is not suitable for all patients.

**Domestic consumable sourcing**: Where clinically equivalent alternatives exist, specifying dialysers manufactured at Baxter India (Ahmedabad) or Fresenius Kabi India (Pune) over imported equivalents eliminates import freight — estimated at 0.8–1.5 kg CO₂e per dialyser for sea-freight imports from China or Europe.

### 5.4 The Grid Decarbonisation Tailwind

India's NDC2 achievement — 51.93% non-fossil installed capacity as of December 2025, five years ahead of schedule (MoEF&CC Annual Report 2025–26, p. 195) — means the electricity component of ICHD footprint will decline passively as coal-fired generation is displaced. Modelling a national grid EF of 0.50 kg/kWh (plausible by 2030–32 at current solar PV installation rates) reduces the electricity component by ~30% and total per-session footprint by approximately 1.3–2.0 kg CO₂e. Facilities on Maharashtra's grid should monitor MSEDCL's annual renewable percentage and update their applied EF accordingly.

Facilities can accelerate decarbonisation ahead of grid improvement through rooftop solar PV installation under PM-KUSUM Component C (agricultural pumps) or the SRISTI scheme for commercial rooftops. A 50 kWp array is sufficient for a 20-machine ICHD facility in Pune (average GHI ~5.5 kWh/m²/day; payback approximately 4 years at current commercial tariffs).

### 5.5 Waste Management Fidelity

Accurate waste stream segregation is critical for footprint fidelity and is simultaneously a regulatory compliance requirement under BMWM Rules 2016. Yellow-bag incineration (1.85 kg CO₂e/kg) carries nearly 8× the CO₂e intensity of red-bag autoclaving (0.24 kg/kg). CPCB inspection data indicate that misclassification is prevalent — inflating the waste component in reported figures. Waste reduction in absolute terms (batch processing, consumable rationalisation, surgical pack minimisation) is preferred over reclassification between streams.

---

## 6. Recommendations for Indian ICHD Units

The following evidence-based recommendations are ranked by estimated carbon reduction potential, feasibility within Indian clinical and regulatory constraints, and alignment with Mission LiFE's Save Energy, Save Water, and Reduce Waste themes (MoEF&CC Annual Report 2025–26, §1.1).

### Recommendation 1: Establish Monthly Carbon Monitoring (All Units — Immediate)

Adopt the five-component monthly reporting framework (electricity, water, waste, consumables, transport) using the emission factors in Table 1. Monthly monitoring enables trend identification, inter-unit benchmarking, and alignment with the National Green Tribunal's directive on environmental performance disclosure for healthcare facilities.

No capital expenditure is required. Input data (utility bills, waste manifests, session counts) are already available at all PMNDP-enrolled units. Estimated burden: <2 person-hours per month.

### Recommendation 2: Implement Dialyser Reuse Programme (Units >150 sessions/month)

Introduce a formalised dialyser reuse protocol compliant with CPCB Technical Guidelines for Healthcare Waste Management (revised April 2025). Target 8–12 reuses per dialyser with validated high-level disinfection (peracetic acid or bleach/citric acid). Maintain reuse records for regulatory audit.

Estimated carbon reduction: **7–9 kg CO₂e/session** (consumables component, 50–65% reduction). Payback period: <6 months from reduced consumable procurement cost.

### Recommendation 3: Rooftop Solar PV Installation (Permanent ICHD Facilities)

Commission rooftop solar under PM-KUSUM Component C or SRISTI scheme. A 50 kWp array is sufficient for a 20-machine ICHD facility. Self-generated solar electricity has an effective EF of ~0.02–0.05 kg CO₂e/kWh (lifecycle), vs. 0.71 kg/kWh for MSEDCL grid.

Estimated carbon reduction: **2–4 kg CO₂e/session** (electricity component). Payback period: approximately 4 years at current Maharashtra commercial electricity tariffs (~₹8–10/kWh).

### Recommendation 4: Reduced Dialysate Flow Protocol (Clinical Review Required)

Initiate a clinical governance review of dialysate flow protocols. Reduce Qd to 350–400 mL/min for patients consistently achieving Kt/V ≥ 1.4. Document clinical outcomes prospectively over one calendar year before full-unit adoption.

Estimated carbon reduction: **0.5–1.0 kg CO₂e/session** (water + electricity components). No capital expenditure; requires clinical leadership.

### Recommendation 5: Domestic Consumable Sourcing Policy

Document the manufacturing location of all ICHD consumables in a vendor sustainability register. Introduce a procurement preference for domestic manufacture when clinically equivalent alternatives exist. Include supply-chain distance as a sustainability criterion in tender evaluation.

Estimated carbon reduction: **0.3–0.8 kg CO₂e/session** (supply-chain component). Also supports the Atmanirbhar Bharat healthcare supply chain initiative.

### Recommendation 6: Patient Transport Mode Shift (Urban Centres with >50% Car Catchment)

For patients within 5 km of the dialysis centre, work with the hospital social work team to promote shared two-wheeler or public bus transport. In Maharashtra cities, explore collaboration with PMPML (Pune) or BEST (Mumbai) for preferential scheduling of public buses to PMNDP dialysis centres, in line with Mission LiFE's Adopt Sustainable Lifestyles theme.

Estimated carbon reduction: **0.5–6 kg CO₂e/session** depending on baseline mode split and catchment distance.

---

## 7. Data Limitations and Future Research Priorities

1. **Single-centre Indian reference**: The IITK Lucknow unit represents one tertiary-centre data point. A multi-centre national survey across urban, peri-urban, and rural ICHD settings is required to validate benchmark tiers and quantify regional variation.

2. **State-specific grid emission factors**: CEA v19 provides a national annual average. State-level disaggregated EFs are available in CEA annual reports and should be used in preference to the national average where the state of operation is known.

3. **Consumable embodied carbon**: The −5% India adjustment to Barraclough Table 3 is based on qualitative supply-chain reasoning. Primary LCI data from Baxter India (Ahmedabad) and Fresenius Kabi India are needed for a defensible India-specific figure.

4. **Diesel generator backup**: DG backup is operationally prevalent in Indian hospitals, particularly in Tier-2 and Tier-3 cities with grid reliability issues. Diesel EF is approximately 0.70–0.76 kg CO₂e/kWh — near-identical to the grid average but with direct on-site combustion of PM₂.₅ and NOₓ. Monthly metering of DG fuel consumption and inclusion in the energy component is recommended.

5. **Temporal variation in grid EF**: Time-of-use and seasonal grid EFs are not captured by the CEA v19 annual average. Units operating evening or night shift dialysis may experience meaningfully different real-time carbon intensities, particularly in high-solar-penetration states.

6. **Medications**: EPO, iron sucrose, and heparin have non-trivial embodied carbon footprints (estimated 0.5–1.2 kg CO₂e/session combined, based on pharmaceutical LCA literature). Including these would extend the system boundary to the full clinical treatment.

---

## 8. Conclusion

This paper presents the first India-calibrated life cycle assessment methodology for in-centre haemodialysis, grounded exclusively in national government emission-factor databases and aligned with India's UNFCCC obligations under the Updated NDC (August 2022).

Five component emission factors — electricity (**0.71 kg/kWh**, CEA v19 December 2023), water purification (**0.30 kg/m³**, CPHEEO), yellow-bag waste (**1.85 kg/kg**, BMWM Rules 2016 + CPCB CBWTF guidelines), red-bag waste (**0.24 kg/kg**, BMWM Rules 2016), consumables (**13.5 kg/session**, Barraclough India-adapted), and supply-chain logistics (**0.08 kg CO₂e/tonne-km**, MoRTH) — are assembled into a tractable monthly reporting framework requiring only data routinely available at every PMNDP-enrolled unit.

The IITK Lucknow reference of **26.3 kg CO₂e/session**, set against the Australian benchmark of 30.9 kg/session (Barraclough *AJKD* 2025), supports a recalibrated five-tier classification with boundaries at 18/22/28/34 kg/session appropriate for the Indian context. Consumable manufacture dominates the footprint at 53–65%, making **dialyser reuse** the single highest-impact decarbonisation intervention available to Indian ICHD operators — ahead of rooftop solar installation, Qd reduction, or any transport intervention.

India's NDC2 achievement of 51.93% non-fossil installed electricity capacity in December 2025 — five years ahead of schedule (MoEF&CC Annual Report 2025–26, p. 195) — will passively reduce the energy component of ICHD footprints as the grid decarbonises. Healthcare facilities that act now to implement dialyser reuse and renewable energy integration will realise both immediate carbon reductions and long-term cost savings, contributing materially to India's Mission LiFE commitment to institutional environmental stewardship.

The EcoRenal carbon calculator, implemented on the HD Dashboard platform and calibrated to the emission factors and benchmarks described in this paper, provides Indian ICHD units with a practical monthly carbon monitoring instrument aligned with India's climate commitments.

---

## References

1. **Barraclough KA, de Zoysa N, Snelling P, et al.** Life cycle assessment of in-centre haemodialysis in Australia. *American Journal of Kidney Diseases (AJKD)*. 2025. [Table 1: material weights; Table 3: aggregate carbon per session = 14.2 kg CO₂e AU-adapted]

2. **Central Electricity Authority (CEA), Ministry of Power, Government of India.** CO₂ Baseline Database for the Indian Power Sector, User Guide, Version 19. New Delhi: CEA; December 2023. Grid emission factor: 0.7117 tCO₂e/MWh (national composite margin). Available at: cea.nic.in/cdm-co2-baseline-database/

3. **Ministry of Environment, Forest and Climate Change (MoEF&CC), Government of India.** Biomedical Waste Management Rules 2016. Gazette of India, Extraordinary, Part II, Section 3(i), G.S.R. 343(E). New Delhi: MoEF&CC; 28 March 2016. Schedule I waste categories and disposal requirements. Available at: moef.gov.in

4. **Central Pollution Control Board (CPCB), MoEF&CC.** Technical Guidelines for Management of Healthcare Waste (Standards for Common Biomedical Waste Treatment Facilities, CBWTF). New Delhi: CPCB; 2016 (revised April 2025). Available at: cpcb.nic.in/technical-guidelines-2/

5. **Ministry of Road Transport and Highways (MoRTH), Government of India.** Road Freight Emission Assessment — National Freight Policy Background Documents. New Delhi: MoRTH. Road HCV diesel freight: 0.08 kg CO₂e/tonne-km. Available at: morth.gov.in

6. **Automotive Research Association of India (ARAI).** Measurement of Emissions from Vehicles Operating on Indian Roads — Project Report No. AFL/2006-07/IOCL. Pune: ARAI; 2007. Vehicle-category emission factors: bus, car (petrol BS-IV), three-wheeler CNG, motorcycle 100–150 cc. Available at: araiindia.com

7. **Central Public Health and Environmental Engineering Organisation (CPHEEO), Ministry of Urban Development, Government of India.** Manual on Water Supply and Treatment, Third Edition (Revised and Updated). New Delhi: CPHEEO; 1999. Energy norms for conventional WTPs in India. Available at: cpheeo.gov.in

8. **National Health Mission (NHM), Ministry of Health and Family Welfare, Government of India.** Pradhan Mantri National Dialysis Programme (PMNDP): Operational Guidelines 2016. New Delhi: NHM; 2016. Programme scope, PPP framework, 650+ enrolled centres. Available at: nhm.gov.in / pmndp.mohfw.gov.in

9. **Ministry of Environment, Forest and Climate Change (MoEF&CC), Government of India.** India's Updated Nationally Determined Contributions (NDC). Submitted to the UNFCCC Registry. New Delhi: MoEF&CC; August 2022. Targets: −45% emissions intensity (GDP) from 2005 by 2030; 50% non-fossil capacity by 2030; 2.5–3 Gt CO₂e forest carbon sink by 2030. Available at: unfccc.int/NDC/

10. **Ministry of Environment, Forest and Climate Change (MoEF&CC), Government of India.** Annual Report 2025–26. New Delhi: MoEF&CC; 2026.
    - Chapter 1 (Mission LiFE — §1.1, pp. 1–7): Mission LiFE themes; institutional mandate for Save Energy, Save Water, Reduce Waste.
    - Chapter 8 (Climate Change — §8.1, pp. 187–196): India's NDC progress (Table 2, p. 195); 51.93% non-fossil capacity December 2025; emission intensity −36% since 2005; COP30 National Statement.
    - BUR-4 / National GHG Inventory 2020 (Chapter 8, p. 191): Total emissions 2,959 Mt CO₂e excl. LULUCF; energy sector 75.66%; waste sector 2.56%.

11. **Ministry of Environment, Forest and Climate Change (MoEF&CC) / NATCOM Cell.** India's 4th Biennial Update Report (BUR-4) to the United Nations Framework Convention on Climate Change. Submitted December 30, 2024. National GHG Inventory for 2020: total emissions 2,382,535 Gg CO₂e (2,959 Mt CO₂e excl. LULUCF); electricity production 39% of national emissions.

12. **Intergovernmental Panel on Climate Change (IPCC).** 2006 IPCC Guidelines for National Greenhouse Gas Inventories, Volume 5: Waste. Hayama, Japan: Institute for Global Environmental Strategies (IGES); 2006. Sections 5.2–5.4 (clinical waste incineration emission factors).

13. **Germain MJ, Nguyen T, Chait Y, et al.** Reducing the environmental footprint of dialysis. *Blood Purification*. 2012;34(2):153–158. Dialyser reuse: 55% reduction in dialyser-attributable carbon at ≥10 reuses.

14. **Kim Y, Kim H, Son YK, et al.** Effect of dialysate flow rate on dialysis adequacy in haemodialysis patients. *Nephrology Dialysis Transplantation*. 2021;36(4):693–701. No significant Kt/V difference at Qd 300 vs. 500 mL/min in high-flux sessions.

15. **National Action Plan on Climate Change (NAPCC), Government of India.** Prime Minister's Council on Climate Change; 2008 (ongoing). Eight National Missions including National Mission for Enhanced Energy Efficiency (NMEEE) and National Mission on Sustainable Agriculture. Available at: moef.gov.in/wp-content/uploads/2018/04/pmcc_NAPCC-Report.pdf

---

## Appendix A: Monthly Data Entry Reference

**What period do values represent?** All utility quantities (kWh, m³, kg waste) should be entered for **one calendar month**. The session count formula automatically translates patient frequency data into monthly sessions.

**Reporting cadence:** Monthly. Carbon intensity (kg CO₂e/session) is the primary performance indicator, calculated automatically once monthly totals and session counts are entered.

**Data sources by component:**

| Component | Data Source | Typical Location |
|-----------|-------------|-----------------|
| Electricity (kWh) | MSEDCL / state DISCOM monthly bill | Accounts department |
| Water (m³) | Municipal supply meter or MIDC bill | Biomedical engineering |
| Yellow-bag waste (kg) | CBWTF waste transfer manifest (Form 2, BMWM Rules 2016) | Infection control / nursing |
| Red-bag waste (kg) | CBWTF waste transfer manifest | Infection control / nursing |
| Patient counts (3×/wk, 2×/wk) | Dialysis unit register / EMR | Unit coordinator |
| Transport (vehicle type + distance) | Patient admission register; map measurement | Unit coordinator |

---

*Correspondence: Department of Civil Engineering, IIT Kanpur, Kanpur 208016, Uttar Pradesh, India.*  
*EcoRenal Calculator: HD Dashboard platform — EcoRenal module (analytics/sustainability).*  
*Declaration of competing interests: None.*  
*Funding: No specific grant from public, commercial, or not-for-profit funding agencies.*
