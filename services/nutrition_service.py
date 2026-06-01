import re

# Comprehensive dictionary of common Indian/Western foods eaten by patients
# Maps keywords to (calories_kcal, protein_g, phosphorus_mg, potassium_mg, calcium_mg) per standard serving
NUTRITION_DICT = {
    # Breads & Cereals
    r"\broti\b|\brotis\b|\bchapati\b|\bchapatis\b|\bphulka\b": (80.0, 2.5, 45.0, 60.0, 28.0),
    r"\brice\b|\bchawal\b": (180.0, 3.5, 80.0, 55.0, 10.0),
    r"\bdal\b|\bdals\b|\bsambhar\b|\blentils\b|\bcurry\b": (120.0, 6.0, 150.0, 400.0, 30.0),
    r"\bkhichdi\b": (160.0, 5.0, 110.0, 200.0, 25.0),
    r"\bbread\b|\bslice\b": (70.0, 2.0, 25.0, 40.0, 30.0),
    r"\bnaan\b|\bparatha\b": (220.0, 5.0, 90.0, 80.0, 35.0),

    # Dairy
    r"\bcurd\b|\byogurt\b|\bdahi\b": (70.0, 3.5, 95.0, 234.0, 120.0),
    r"\bpaneer\b": (260.0, 18.0, 250.0, 150.0, 480.0),
    r"\bmilk\b|\bdoodh\b": (100.0, 4.5, 140.0, 320.0, 290.0),
    r"\bcheese\b": (110.0, 6.0, 160.0, 98.0, 200.0),

    # Proteins & Non-veg
    r"\begg\b|\beggs\b|\bboiled egg\b": (75.0, 6.0, 90.0, 63.0, 28.0),
    r"\begg white\b|\beggwhites\b|\begg-white\b": (20.0, 4.0, 10.0, 54.0, 2.0),
    r"\bchicken\b|\bmurgh\b": (165.0, 25.0, 220.0, 220.0, 11.0),
    r"\bfish\b|\bmachli\b": (120.0, 20.0, 200.0, 340.0, 15.0),
    r"\bmutton\b|\bmeat\b": (250.0, 22.0, 240.0, 270.0, 15.0),

    # Snacks & Fast Food
    r"\bsamosa\b|\bsamosas\b": (250.0, 4.0, 50.0, 150.0, 20.0),
    r"\bpoha\b": (200.0, 4.0, 60.0, 100.0, 15.0),
    r"\bupma\b": (200.0, 4.0, 60.0, 100.0, 20.0),
    r"\bidli\b|\bidlis\b": (60.0, 1.5, 25.0, 50.0, 15.0),
    r"\bdosa\b|\bdosas\b": (120.0, 2.5, 40.0, 90.0, 12.0),
    r"\btea\b|\bchai\b": (60.0, 1.0, 30.0, 88.0, 40.0),
    r"\bcoffee\b": (70.0, 1.5, 40.0, 116.0, 12.0),

    # Vegetables & Fruits
    r"\bsabzi\b|\bsabji\b|\bveg\b|\bvegetables\b|\bsalad\b": (100.0, 2.0, 50.0, 300.0, 40.0),
    r"\bapple\b|\bbanana\b|\bpapaya\b|\bguava\b|\bfruit\b|\bfruits\b": (80.0, 1.0, 15.0, 200.0, 15.0),

    # Extras
    r"\bbutter\b|\bghee\b|\boil\b": (110.0, 0.0, 1.0, 3.0, 2.0),
}

NUMBER_MAP = {
    "one": 1.0, "a": 1.0, "an": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
    "half": 0.5, "quarter": 0.25, "double": 2.0, "triple": 3.0
}


def load_dynamic_nutrition_dict(db=None) -> dict:
    """
    Loads custom food items from the PostgreSQL database table.
    Falls back to the static high-fidelity dictionary if database is not available.
    """
    if db is None:
        return NUTRITION_DICT

    try:
        from sqlalchemy import text
        res = db.execute(text(
            "SELECT synonyms, calories, protein, phosphorus, potassium, calcium FROM food_database_items;"
        )).fetchall()
        if not res:
            return NUTRITION_DICT

        dynamic_dict = {}
        for synonyms, cal, prot, phos, pot, calc in res:
            if not synonyms:
                continue
            keywords = [k.strip() for k in synonyms.split(",") if k.strip()]
            if not keywords:
                continue
            pattern_parts = []
            for kw in keywords:
                if kw.isalnum():
                    pattern_parts.append(rf"\b{kw}\b")
                else:
                    pattern_parts.append(re.escape(kw))
            pattern = "|".join(pattern_parts)
            dynamic_dict[pattern] = (
                float(cal),
                float(prot),
                float(phos),
                float(pot or 0),
                float(calc or 0),
            )

        return dynamic_dict
    except Exception as e:
        import logging
        logging.error(f"Error loading dynamic food database: {e}")
        return NUTRITION_DICT


def estimate_meal_nutrients(notes: str, meal_type: str, db=None) -> tuple[float, float, float, float, float]:
    """
    Estimates (calories_kcal, protein_g, phosphorus_mg, potassium_mg, calcium_mg)
    from a free-text meal description.
    Falls back to a standard baseline if no food items are detected.
    """
    # Fallback baselines per meal type
    def _baseline():
        if meal_type == "Breakfast":
            return (300.0, 8.0, 100.0, 250.0, 80.0)
        elif meal_type in ("Lunch", "Dinner"):
            return (500.0, 15.0, 200.0, 500.0, 60.0)
        else:  # Snack / Beverage
            return (150.0, 3.0, 50.0, 100.0, 20.0)

    if not notes or not notes.strip():
        return _baseline()

    text = notes.lower().strip()
    parts = re.split(r'\bwith\b|\band\b|,|\+|\.', text)

    total_cal = 0.0
    total_prot = 0.0
    total_phos = 0.0
    total_pot = 0.0
    total_calc = 0.0
    items_detected = 0

    active_dict = load_dynamic_nutrition_dict(db)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        qty = 1.0
        num_match = re.search(r'(\d+(?:\.\d+)?)', part)
        word_match = re.search(r'\b(one|two|three|four|five|half|quarter|a|an)\b', part)

        if num_match:
            try:
                qty = float(num_match.group(1))
            except ValueError:
                pass
        elif word_match:
            qty = NUMBER_MAP.get(word_match.group(1), 1.0)

        for pattern, vals in active_dict.items():
            if re.search(pattern, part):
                cal, prot, phos, pot, calc = vals
                total_cal += cal * qty
                total_prot += prot * qty
                total_phos += phos * qty
                total_pot += pot * qty
                total_calc += calc * qty
                items_detected += 1

    if items_detected == 0:
        return _baseline()

    return (
        round(total_cal, 1),
        round(total_prot, 1),
        round(total_phos, 1),
        round(total_pot, 1),
        round(total_calc, 1),
    )


def get_7day_rolling_mean_phosphate(db, patient_id: int) -> dict:
    """
    Query the patient's meal logs for the last 30 days.
    If the patient has >= 3 meal diary entries in the last 30 days,
    calculate the 7-day rolling mean phosphorus (mg/day) and return
    with source 'meal_logs'. Otherwise, return default 1200mg/day.
    """
    from datetime import date, timedelta
    from sqlalchemy import and_
    from database import PatientMealRecord
    
    today = date.today()
    start_30 = today - timedelta(days=30)
    
    records = db.query(PatientMealRecord).filter(
        and_(
            PatientMealRecord.patient_id == patient_id,
            PatientMealRecord.date >= start_30
        )
    ).all()
    
    if len(records) < 3:
        return {"value": 1200.0, "source": "default_1200mg"}
        
    daily_sums = {}
    for r in records:
        d = r.date
        p_val = r.phosphorus if r.phosphorus is not None else 0.0
        daily_sums[d] = daily_sums.get(d, 0.0) + p_val
        
    start_7 = today - timedelta(days=6)
    last_7_days_sums = [sum_val for d, sum_val in daily_sums.items() if d >= start_7]
    
    if last_7_days_sums:
        avg_val = sum(last_7_days_sums) / len(last_7_days_sums)
    else:
        avg_val = sum(daily_sums.values()) / len(daily_sums)
        
    if avg_val < 100:
        return {"value": 1200.0, "source": "default_1200mg"}
        
    return {"value": round(avg_val, 1), "source": "meal_logs"}
