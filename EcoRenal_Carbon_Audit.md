# EcoRenal Carbon Model — Scientific Audit

**Independent Scientific Review · Nephrology & Environmental Medicine**
**Centre context:** Pune, Maharashtra — ICHD unit
**Date:** June 2026

---

## Sources Compared

| Source | Details |
|--------|---------|
| **Barraclough et al. AJKD 2025** | Australian LCA, n=16 ICHD patients, Royal Melbourne Hospital, Victoria. Baxter AK98, Polyflux 210H dialyser, Novaline bloodline. 3×/week, 4 h, Qd 500 mL/min. |
| **IITK India Recalibration Study** | Lucknow cohort; adapted Barraclough by recalculating patient transport, consumable supply-chain transport, and APD prescription volume for Indian context. |
| **EcoRenal App** | `routers/sustainability.py` (backend) + `templates/sustainability.html` JS calculator (frontend) |

---

## Verdict Panel

| Category | Count |
|----------|-------|
| Critical errors (require immediate correction) | **4** |
| Moderate issues (materially affect outputs) | **4** |
| Minor issues (reduce scientific credibility) | **3** |
| **Overall verdict** | **Needs revision before clinical publication** |

---

## Emission Factor Comparison Panel

All key parameters compared against Barraclough 2025 (gold-standard LCA) and the IITK Indian recalibration.

| Parameter | EcoRenal App | Barraclough 2025 (Australia) | IITK India (Lucknow) | Error Direction | Severity |
|-----------|-------------|------------------------------|----------------------|-----------------|----------|
| Electricity EF | 0.71 kg CO₂e/kWh | ~0.65 kg/kWh (Vic grid) | 0.71 kg/kWh (CEA v19) | ✓ Correct for India | OK |
| Water EF | 0.30 kg CO₂e/m³ | Not separately cited | Retained from Barraclough | Consistent (RO electricity in meter) | OK |
| Yellow-bag waste (incinerated) | Backend: 1.85 kg/kg · Frontend: 1.85 kg/kg | Not disaggregated | Retained | Consistent; IPCC clinical waste range plausible | OK |
| Red-bag waste (autoclaved) | **Backend: 0.44 kg/kg · Frontend: 0.24 kg/kg** | Not disaggregated | Not separately stated | 83% divergence between own models | **CRITICAL** |
| Consumables per session (backend flat) | **7.5 kg CO₂e/session** | 14.2 kg/session (Table 3 ÷ 156) | ~13–14 kg/session (manufacture retained from AU) | 47% underestimate vs literature | **CRITICAL** |
| Patient transport per session (backend flat) | **5.0 kg CO₂e/session** | 11.3 kg/session (14.5 km by car) | 6.2 kg/session (12 km, mixed modes) | App between AU and India; flat ignores location/mode | MODERATE |
| Two-wheeler EF (frontend) | **0.06 kg CO₂e/km** | Car-only assumed (AU) | **0.10 kg CO₂e/km** (stated explicitly) | 40% underestimate vs IITK Indian data | **CRITICAL** |
| Auto-rickshaw EF (frontend) | 0.08 kg CO₂e/km | Not applicable (AU) | Implied ~0.09–0.12 from 0.55× correction | Plausible but at low end of Indian range | MODERATE |
| Session count (backend) | patients × 12/month | 3×/wk = 13.0/month | 156/year (3×/week) | Underestimates 3×/wk by 8%; overestimates 2×/wk by 39% | MODERATE |
| Per-session benchmark "Standard Indian Average" | **14–18.5 kg/session** | 30.9 kg/session (AU baseline) | **26.3 kg/session (Lucknow ICHD)** | Benchmark bands ~40% too low | **CRITICAL** |
| HD consumable transport (supply chain) | Not modeled | 18 kg CO₂e/patient/year | 100 kg/yr (Nashik→Lucknow, 1,250 km) · ~14 kg/yr for Pune (180 km) | Omitted; small for Pune, notable for distant units | MINOR |
| Tree sequestration equivalence | 22 kg CO₂/yr per tree | Not used | Not used | High end for Indian urban trees (range 10–25 kg/yr) | MINOR |

---

## ICHD Annual Carbon Footprint: Australia vs India (Lucknow)

The IITK study adapted Barraclough, replacing patient transport, consumable transport, and APD prescription volumes with Indian-calibrated values.

| Component | Australia (Barraclough Table 3) | India — Lucknow (IITK) | Δ India vs AU | App Backend (approx.) |
|-----------|--------------------------------|------------------------|---------------|----------------------|
| Consumable manufacture & disposal | 2,213 kg/yr (46.0%) | 2,213 kg/yr (retained) | — | 7.5 × 156 = **1,170 kg/yr** |
| RO electricity | 499 kg/yr (10.3%) | 499 kg/yr (retained) | — | Embedded in electricity meter ✓ |
| Dialysis machine electricity | 320 kg/yr (6.6%) | 320 kg/yr (retained) | — | Embedded in electricity meter ✓ |
| Patient transport | 1,764 kg/yr (36.6%) | 970 kg/yr (×0.55 correction) | −794 kg/yr | 5.0 × 156 = **780 kg/yr** |
| Consumable transport (supply chain) | 18 kg/yr (0.4%) | 100 kg/yr (Nashik→Lucknow) | +82 kg/yr | Not modeled (0) |
| **Total ICHD** | **4,814 kg CO₂e/yr** | **4,102 kg CO₂e/yr** | **−712 kg/yr** | **~1,950 kg/yr (severely underestimated)** |
| Per session (÷156) | 30.9 kg/session | 26.3 kg/session | | ~12.5 kg/session (excludes elec/water/waste) |

> **Note:** Even adding electricity (5.3 kWh × 0.71 × 156 = 587 kg/yr), the backend reaches only ~2,537 kg vs 4,102 kg IITK — a 38% underestimate.

---

## Detailed Findings

---

### Finding 1 — CRITICAL
**Wrong citation: CO₂E_CONS_PER_SESSION attributed to "Tables S5–S6"**

`sustainability.py : line 19`

The code comment states:
```python
CO2E_CONS_PER_SESSION = 7.5  # kg/session — LCI-validated (Tables S5-S6, Barraclough AJKD 2025)
```

This is a **factually incorrect citation**. Barraclough's Supplemental Tables S5 and S6 are:
- **S5** = Life cycle inventory assumptions for Extraneal icodextrin — a *peritoneal dialysis* fluid, not HD
- **S6** = Life cycle inventory assumptions for transport logistics (APD/CAPD supply chain)

Neither table contains any per-session HD consumable CO₂e figure.

**What the correct source is:**
> Barraclough 2025, **Main paper Table 3**: Consumable manufacture & disposal = 2,213 kg CO₂e/patient/year ÷ 156 sessions = **14.2 kg CO₂e/session** (Australian LCA).

This error does not automatically invalidate the numerical value (which may be defensible after India-domestic-manufacture adjustment — see Finding 2), but it is a scientific integrity issue: a claim of LCA validation supported by a specific citation must reference the cited source.

**Recommended fix:** Replace citation with: *"Derived from Barraclough et al. AJKD 2025, Table 3 (HD consumable manufacture = 2,213 kg CO₂e/patient/year ÷ 156 sessions = 14.2 kg/session, Australia), reduced for Indian domestic manufacture (Baxter Ahmedabad). No Indian LCA source currently exists for this adjustment — treat as working assumption pending independent Indian HD LCI."*

---

### Finding 2 — CRITICAL
**CO₂E_CONS_PER_SESSION = 7.5 kg underestimates the LCA benchmark by 47%**

`sustainability.py : line 19`

| Value | Figure | Source |
|-------|--------|--------|
| App (backend flat) | 7.5 kg CO₂e/session | No derivation documented |
| Barraclough Table 3 (AU LCA) | **14.2 kg/session** | 2,213 kg ÷ 156 sessions; includes all packaging & disposal |
| IITK India (Lucknow) | **~14.2 kg/session** | Retained unchanged from AU model — domestic manufacture = same industrial process |

The IITK Indian study explicitly states (Steps 1–4): *"consumable manufacturing emissions, electricity consumption, water use and waste disposal emissions were adopted from the Australian model."* This is because the same consumables (Polyflux 210H dialyser, Novaline bloodline, C298 Softpac dialysate) are manufactured by the same Baxter processes — simply at the Ahmedabad plant rather than the Toonbabbie (Australia) plant.

The frontend's item-by-item LCI approach arrives at roughly 6.5–8.5 kg/session depending on items entered — directionally consistent with the backend's 7.5 but still substantially below the LCA benchmark. The gap from 14.2 kg comes from missing consumables: Barraclough's Table 1 lists 17 items for an average in-center session (yellow bag, cotton wool ball, 2× chlorhexidine swabs, 10× Clinell wipes, blue pad, 2× paper towels, drawing-up needles). These items add approximately 0.3–0.8 kg CO₂e/session and are absent from the EcoRenal frontend form.

**Recommended fix:** If 7.5 kg is retained as a backend default, document the derivation explicitly and add the missing consumable items to the frontend form. Add a ±30% uncertainty band to reported totals — standard LCI uncertainty.

---

### Finding 3 — CRITICAL
**Backend and frontend use irreconcilable calculation models — producing different results from the same data**

`sustainability.py : lines 35–51` · `sustainability.html : JS calculateCF()`

The application contains two parallel and incompatible carbon models:

```python
# Backend (sustainability.py): flat factors
c  = session_count * 7.5    # consumables — no item breakdown
t  = session_count * 5.0    # transport — location-blind
wt = (bio_waste_kg * 1.85) + (gen_waste_kg * 0.44)  # gen_waste EF differs from frontend!
```

```javascript
// Frontend (JS): granular LCI
const wasteRed    = v('wasteRedQty') * 0.24   // 0.44 (backend) vs 0.24 (frontend) → 83% difference
const consumables = dialyser * 1.35 + tubing * 0.85 + ...   // per-item LCI
const travel      = bus * 0.04 + car * 0.17 + auto * 0.08 + bike * 0.06
```

**The red-bag waste discrepancy is the most egregious example:**

| Model | Red-bag factor | For 50 kg/month | Annual |
|-------|---------------|-----------------|--------|
| Backend | 0.44 kg CO₂e/kg | 264 kg CO₂e/month | 3,168 kg/yr |
| Frontend | 0.24 kg CO₂e/kg | 144 kg CO₂e/month | 1,728 kg/yr |
| **Difference** | **83%** | **120 kg/month** | **1,440 kg/yr** |

When a user saves a record, the backend calculates a different total than the screen shows. This is not a rounding issue — it is a fundamental methodological divergence within the same application.

**Recommended fix:** Choose one canonical model. The frontend's bottom-up LCI approach is scientifically superior and should be the single source of truth. Fix the red-bag discrepancy by adopting 0.24 kg/kg (CBWTF autoclave + shred/landfill is the correct process for red-bag waste under BMWM Rules 2016).

---

### Finding 4 — CRITICAL
**Per-session benchmark bands are calibrated ~40% too low for Indian ICHD reality**

`sustainability.html : JS BENCH array · lines 1957–1963`

| Band | App Threshold | IITK Lucknow Actual | Barraclough AU Actual |
|------|-------------|--------------------|-----------------------|
| Excellent | < 11 kg/session | — | — |
| Good/Optimised | 11–14 kg/session | — | — |
| Standard Indian Average | 14–18.5 kg/session | **26.3 kg/session** | 30.9 kg/session |
| High Impact | 18.5–24 kg/session | — | — |
| Action Required | > 24 kg/session | — | — |

The only published Indian-context ICHD LCA (IITK, Lucknow) gives **26.3 kg CO₂e/session** for a standard urban unit. Even with Pune's shorter supply chain (Nashik 180 km) and higher two-wheeler use, the estimated per-session figure for a non-reuse Pune ICHD unit is 20–24 kg/session.

Under current benchmarks, virtually every Indian ICHD unit would permanently read "Action Required" — creating a scientifically inaccurate and clinically demoralising output. The "Excellent" threshold of <11 kg/session requires simultaneously: near-zero grid electricity (solar), dialyser reuse ×4+, very short two-wheeler or bus travel. This is achievable by fewer than 1–2% of Indian units today.

**Recommended recalibration** (based on IITK and Barraclough data):

| Band | Proposed Threshold | Rationale |
|------|--------------------|-----------|
| Excellent | < 18 kg/session | Requires reuse + Qd reduction + efficient travel |
| Good | 18–22 kg/session | Urban unit with partial reuse |
| Indian Average | 22–28 kg/session | Standard no-reuse ICHD; IITK Lucknow = 26.3 |
| High Impact | 28–34 kg/session | |
| Action Required | > 34 kg/session | |

Include a caveat that these bands are provisional pending Indian multicentre LCA data.

---

### Finding 5 — MODERATE
**Two-wheeler emission factor (0.06 kg/km) underestimates Indian petrol two-wheelers by 40%**

`sustainability.html : JS calculateCF() · line 1581`

| Value | Figure | Source |
|-------|--------|--------|
| App frontend | 0.06 kg CO₂e/km | Not cited; appears to be European EF |
| IITK Indian study (explicit) | **0.10 kg CO₂e/km** | Table 5 scenario analysis |
| Published Indian fleet EF | 0.09–0.12 kg/km | 100–125cc petrol; ARAI/MoRTH fleet average |

The IITK study explicitly uses 0.10 kg CO₂e/km for two-wheelers — and finds two-wheeler transport is a major carbon reduction lever because it is so dominant among Indian ICHD patients. India's two-wheeler fleet is predominantly 100–125cc petrol (Hero Splendor, Honda Activa) operating in congested urban traffic — not European CNG or electric scooters.

The app uses two-wheelers as a key recommendation for reducing patient transport carbon. With 0.06 kg/km, two-wheelers appear 65% cleaner than cars (0.17 kg/km). With the correct IITK EF of 0.10 kg/km, the saving is 41% — still significant, but the carbon benefit in the savings badges is overstated by approximately 40%.

**Recommended fix:** Change `v('bikeQty') * 0.06` to `v('bikeQty') * 0.10`. Cite: IITK India Recalibration Study, Table 5 scenario analysis.

---

### Finding 6 — MODERATE
**Backend session count (patients × 12) introduces systematic ±8–39% error**

`sustainability.py : line 31`

```python
session_count = (record.total_sessions_override if record and record.total_sessions_override 
                 else (patient_count * 12)) or 1
```

| Frequency | Actual sessions/month | App assumption | Error |
|-----------|----------------------|----------------|-------|
| 3×/week (majority of ICHD patients) | **13.0** | 12 | **Underestimates by 8%** |
| 2×/week (15–25% in India) | **8.6** | 12 | **Overestimates by 39%** |

The frontend's `saveRecord()` function correctly calculates `(patients3x * 3 + patients2x * 2) * 4.33` but passes it as a sessions override. The backend ignores this override when `total_sessions_override` is NULL — falling back to the flat × 12 estimate. A unit with a mixed prescription profile has systematically incorrect per-session emissions in the backend summary card.

**Recommended fix:** Require the sessions override to always be populated from the frontend's correct formula, or derive it from `MonthlyRecord` frequency data. Do not use a flat per-patient monthly multiplier.

---

### Finding 7 — MODERATE
**Flat CO₂E_TRANS_PER_SESSION = 5.0 kg ignores the most variable driver in Indian ICHD carbon**

`sustainability.py : line 20`

The IITK study shows patient transport accounted for 36.6% of total ICHD carbon in Australia and 23.6% in their Indian model — and that this figure varies by a factor of 3–5× depending on transport mode and distance:

- **IITK Lucknow**: 970 kg/yr ÷ 156 sessions = **6.2 kg/session** (12 km one-way, 80% public transport/auto)
- **Two-wheeler scenario**: 374 kg/yr ÷ 156 = **2.4 kg/session** (same distance, all two-wheeler at 0.10 kg/km)
- **Rural referral unit** (50 km one-way, mixed car/auto): **~10–15 kg/session**

The flat 5.0 kg/session is not cited from any source and cannot represent both a compact urban unit and a district hospital. The frontend's data-driven km-by-mode calculation is correct; the backend's flat factor is not.

**Recommended fix:** Remove `CO2E_TRANS_PER_SESSION` from `sustainability.py`. Require transport data via the frontend form (which already collects km by mode correctly). Display "Not measured — enter patient travel data" in the backend summary if transport data is absent, rather than applying a phantom estimate.

---

### Finding 8 — MODERATE
**Auto-rickshaw EF (0.08 kg/km) likely underestimated; no Indian source cited**

`sustainability.html : JS calculateCF() · line 1581`

The IITK study applies a composite 0.55× correction to the full Australian car-based transport estimate, reflecting 12 km (vs 14.5 km) and 80% public transport + 20% auto-rickshaw use. Reverse-engineering this correction implies a combined effective EF of approximately 0.09–0.11 kg CO₂e/km for the Indian mixed-mode transport bundle.

CNG auto-rickshaws in congested Indian urban traffic operate less efficiently than highway-condition emission factors; ARAI data for L5N category vehicles in urban driving puts real-world EF at 0.09–0.13 kg CO₂e/km. The app's 0.08 kg/km is at the low end of this range, appears to originate from a European CNG vehicle database, and understates by approximately 12–38%.

**Recommended fix:** Change auto-rickshaw EF to 0.10 kg/km (consistent with IITK-implied factor and ARAI urban driving data). Cite: ARAI Annual Report or MoRTH Indian fuel economy norms for L5N category.

---

### Finding 9 — MINOR
**Consumable supply-chain transport is absent — adds 14 kg CO₂e/patient/year for Pune**

The IITK study adds 100 kg CO₂e/patient/year for HD consumable road transport from Nashik to Lucknow (1,250 km):

```
998 kg annual consumables × 1,250 km × 0.08 kg CO₂e/tonne-km = 100 kg CO₂e/year
```

For Pune specifically, Nashik is approximately 180 km:

```
998 kg × 0.180 km × 0.08 kg CO₂e/tonne-km ≈ 14 kg CO₂e/patient/year
```

This is small (0.3% of Pune ICHD total) but non-zero, and for government or district hospitals with longer supply chains it becomes substantial (5–8% of total).

**Recommended fix:** Add a fixed 14 kg CO₂e/patient/year as a pre-populated informational figure for Maharashtra units, with an input field for other distances. Use 0.08 kg CO₂e/tonne-km (IITK road freight EF) applied to 998 kg annual consumable weight.

---

### Finding 10 — MINOR
**Tree sequestration equivalence (22 kg/tree/yr) is optimistic for Indian urban context**

`sustainability.html : JS calculateCF() · line 1624`

| Context | Absorption Rate | Source |
|---------|----------------|--------|
| App assumption | 22 kg CO₂/tree/year | Code comment states "fully mature tropical tree at peak" |
| Published tropical forest trees | 15–50 kg CO₂/year | Depending on species, canopy, and soil |
| **Indian urban planted trees** (Pune street trees) | **10–15 kg CO₂/year** | Stressed by soil compaction, heat island, restricted root volume |

Using 22 kg/year overstates ecological equivalence for a Pune unit by approximately 47–120% compared to urban plantation context. The headline "X mature tree-years" will consistently read as more achievable than actual urban afforestation delivers.

The code correctly notes: *"NOT saplings to plant (year-1 saplings absorb ~1.2 kg and ~52% die within 3 years in Indian municipal drives)"* — this is a good caveat but the base figure is still high.

**Recommended fix:** Use 15 kg CO₂/year (conservative but defensible for Indian urban forest context), or express as a range: *"equivalent to 10–22 mature tree-years"* with a tooltip explaining the range (urban plantation trees at low end, mature forest trees at high end).

---

### Finding 11 — MINOR
**Significant emission categories absent from both models with no disclosure to user**

Both Barraclough (Figure 2, system boundary diagram) and the IITK study explicitly document their exclusions. The EcoRenal app presents results as a "total carbon footprint" without disclosing what is excluded.

**Categories absent from the model:**

| Category | Status | Scale |
|----------|--------|-------|
| HVAC/building energy | Excluded (Barraclough: excluded deliberately to generalise across climates) | Adds 15–25% to electricity in Indian summer |
| Pharmaceuticals | Excluded (Barraclough); was 37% of total in Lim 2013 AHR (Australian study) when included | Significant if included |
| Staff travel | Excluded (Barraclough); not disclosed here | Small but non-zero |
| Machine manufacture (dialysis machine, RO plant) | <2% per session; excluded by Barraclough | Negligible per session |
| **Diesel generator use** | **Not captured anywhere** | **0.27 kg CO₂e/kWh vs 0.71 grid** — higher! |

The diesel generator gap is particularly important for Indian government hospitals, where load-shedding and generator backup are routine. A unit running 4 hours of generator per day at 0.27 kg CO₂e/kWh would add approximately 240–480 kg CO₂e/year to its electricity footprint — not captured by the 0.71 grid EF.

**Recommended fix:**
1. Add a "What this calculator measures" disclosure card to the results panel listing included and excluded categories (consistent with Barraclough Figure 2).
2. Add a diesel generator input: *"% sessions using generator backup"* applied as a multiplier to the electricity entry.

---

## Strengths Worth Preserving

| Strength | Assessment |
|----------|-----------|
| **Electricity EF: 0.71 kg/kWh (CEA CO2 Baseline Database v19, Dec 2023)** | Correctly sourced, India-specific, and the most important single factor in the model. ✓ |
| **Frontend item-by-item LCI for consumables** | Correct methodology — bottom-up, auditable, expandable. Individual factors (dialyser 1.35, tubing 0.85, dialysate A 1.95, bicarb 1.10) are consistent with Barraclough Table 1 material weights. ✓ |
| **Yellow-bag (1.85) vs red-bag (0.24) waste split** | Scientifically correct under BMWM Rules 2016. More granular than most tools. Fix the backend's 0.44 to match. ✓ |
| **Qd reduction saving in What-If? simulator (0.14 kWh per 200 mL/min band)** | The single most accurately sourced number in the app. Measured on Baxter AK98 (same machine as Barraclough). ✓ |
| **Transport by mode with km input (frontend)** | Conceptually correct. Correctly separates patient travel from consumable supply-chain transport. ✓ |
| **Cool dialysate recommendation (35–36°C) and dialyser reuse protocol** | Clinically grounded, CPCB-compliant, carbon saving estimates are conservative and reasonable. ✓ |

---

## Priority Fix List

1. **[Critical]** Correct citation on `CO2E_CONS_PER_SESSION` — point to Barraclough Table 3, not S5/S6
2. **[Critical]** Fix red-bag EF in backend: `0.44 → 0.24 kg/kg` to match frontend
3. **[Critical]** Recalibrate benchmark BENCH array — current thresholds are ~40% below the only published Indian LCA
4. **[Critical]** Two-wheeler EF: `0.06 → 0.10 kg/km` (IITK India, Table 5)
5. **[Moderate]** Remove flat `CO2E_TRANS_PER_SESSION`; require frontend mode-by-mode data in saved records
6. **[Moderate]** Session count: replace `patient_count * 12` with frequency-correct formula
7. **[Moderate]** Auto-rickshaw EF: `0.08 → 0.10 kg/km`
8. **[Minor]** Add system-boundary disclosure to results panel
9. **[Minor]** Add diesel generator backup input field
10. **[Minor]** Add missing consumable items from Barraclough Table 1 to frontend form (cotton wool, chlorhexidine swabs, Clinell wipes, drawing-up needle, paper towels)
11. **[Minor]** Tree sequestration: 22 → 15 kg CO₂/yr or express as range

---

## Scope Note

This review covers only the carbon emission methodology in `routers/sustainability.py` and the frontend JavaScript calculator in `templates/sustainability.html`. It does not cover clinical alert logic, database schema, or other application components. All per-patient annual figures reference the Barraclough 2025 standard prescription: 3×/week, 4 hours, Qd 500 mL/min, Baxter AK98, Polyflux 210H dialyser, Novaline bloodline. Discrepancies may differ for units using different machines or protocols.

---

*Sources: Barraclough KA et al. Carbon Emissions From Different Dialysis Modalities: A Life Cycle Assessment. Am J Kidney Dis. 2025;86(4):465–474. doi:10.1053/j.ajkd.2025.04.019 · IITK India Recalibration Study (Lucknow cohort, adapted LCA). · CEA CO2 Baseline Database v19, Central Electricity Authority, Government of India, December 2023.*
