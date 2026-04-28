from typing import Optional

def calculate_cci(
    age: Optional[int], cad_status: bool, chf_status: bool, history_of_pvd: bool, history_of_stroke: bool,
    history_of_dementia: bool, history_of_cpd: bool, history_of_ctd: bool, history_of_pud: bool,
    liver_disease: str, dm_status: str, dm_end_organ_damage: bool, hemiplegia: bool,
    solid_tumor: str, leukemia: bool, lymphoma: bool, viral_hiv: str
) -> int:
    """Calculates the Charlson Comorbidity Index (CCI) score."""
    score = 0
    if age:
        if 50 <= age <= 59: score += 1
        elif 60 <= age <= 69: score += 2
        elif 70 <= age <= 79: score += 3
        elif age >= 80: score += 4
    if cad_status: score += 1
    if chf_status: score += 1
    if history_of_pvd: score += 1
    if history_of_stroke: score += 1
    if history_of_dementia: score += 1
    if history_of_cpd: score += 1
    if history_of_ctd: score += 1
    if history_of_pud: score += 1
    if liver_disease == "Mild": score += 1
    elif liver_disease == "Moderate to severe": score += 3
    if dm_status in ["Type 1", "Type 2", "Secondary"]:
        if dm_end_organ_damage: score += 2
        else: score += 1
    if hemiplegia: score += 2
    score += 2  # Moderate to severe CKD (all ESRD patients)
    if solid_tumor == "Localized": score += 2
    elif solid_tumor == "Metastatic": score += 6
    if leukemia: score += 2
    if lymphoma: score += 2
    if viral_hiv == "Positive": score += 6
    return score
