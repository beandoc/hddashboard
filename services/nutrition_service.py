import re

# Comprehensive dictionary of common Indian/Western foods eaten by patients
# Maps keywords to (calories_kcal, protein_g, phosphorus_mg) per standard serving
NUTRITION_DICT = {
    # Breads & Cereals
    r"\broti\b|\brotis\b|\bchapati\b|\bchapatis\b|\bphulka\b": (80.0, 2.5, 45.0),
    r"\brice\b|\bchawal\b": (180.0, 3.5, 80.0),
    r"\bdal\b|\bdals\b|\bsambhar\b|\blentils\b|\bcurry\b": (120.0, 6.0, 150.0),
    r"\bkhichdi\b": (160.0, 5.0, 110.0),
    r"\bbread\b|\bslice\b": (70.0, 2.0, 25.0),
    r"\bnaan\b|\bparatha\b": (220.0, 5.0, 90.0),
    
    # Dairy
    r"\bcurd\b|\byogurt\b|\bdahi\b": (70.0, 3.5, 95.0),
    r"\bpaneer\b": (260.0, 18.0, 250.0),
    r"\bmilk\b|\bdoodh\b": (100.0, 4.5, 140.0),
    r"\bcheese\b": (110.0, 6.0, 160.0),
    
    # Proteins & Non-veg
    r"\begg\b|\beggs\b|\bboiled egg\b": (75.0, 6.0, 90.0),
    r"\begg white\b|\beggwhites\b|\begg-white\b": (20.0, 4.0, 10.0),
    r"\bchicken\b|\bmurgh\b": (165.0, 25.0, 220.0),
    r"\bfish\b|\bmachli\b": (120.0, 20.0, 200.0),
    r"\bmutton\b|\bmeat\b": (250.0, 22.0, 240.0),
    
    # Snacks & Fast Food
    r"\bsamosa\b|\bsamosas\b": (250.0, 4.0, 50.0),
    r"\bpoha\b": (200.0, 4.0, 60.0),
    r"\bupma\b": (200.0, 4.0, 60.0),
    r"\bidli\b|\bidlis\b": (60.0, 1.5, 25.0),
    r"\bdosa\b|\bdosas\b": (120.0, 2.5, 40.0),
    r"\btea\b|\bchai\b": (60.0, 1.0, 30.0),
    r"\bcoffee\b": (70.0, 1.5, 40.0),
    
    # Vegetables & Fruits
    r"\bsabzi\b|\bsabji\b|\bveg\b|\bvegetables\b|\bsalad\b": (100.0, 2.0, 50.0),
    r"\bapple\b|\bbanana\b|\bpapaya\b|\bguava\b|\bfruit\b|\bfruits\b": (80.0, 1.0, 15.0),
    
    # Extras
    r"\bbutter\b|\bghee\b|\boil\b": (110.0, 0.0, 1.0),
}

# Number dictionary to convert text numbers to floats
NUMBER_MAP = {
    "one": 1.0, "a": 1.0, "an": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
    "half": 0.5, "quarter": 0.25, "double": 2.0, "triple": 3.0
}

def estimate_meal_nutrients(notes: str, meal_type: str) -> tuple[float, float, float]:
    """
    Estimates (calories_kcal, protein_g, phosphorus_mg) from a free-text meal description.
    Falls back to a standard baseline if no food items are detected.
    """
    if not notes or not notes.strip():
        # Fallback baselines per meal type
        if meal_type == "Breakfast":
            return (300.0, 8.0, 100.0)
        elif meal_type in ("Lunch", "Dinner"):
            return (500.0, 15.0, 200.0)
        else: # Snack / Beverage
            return (150.0, 3.0, 50.0)

    text = notes.lower().strip()
    
    # Splitting into clauses/phrases (e.g. by 'with', 'and', ',', '+')
    parts = re.split(r'\bwith\b|\band\b|,|\+|\.', text)
    
    total_cal = 0.0
    total_prot = 0.0
    total_phos = 0.0
    items_detected = 0

    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        # Try to find a quantity preceding the food item in this part
        # Look for numbers (e.g. 1.5, 2) or words (two, half)
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

        # Check which food items match
        matched_in_part = False
        for pattern, (cal, prot, phos) in NUTRITION_DICT.items():
            if re.search(pattern, part):
                total_cal += cal * qty
                total_prot += prot * qty
                total_phos += phos * qty
                matched_in_part = True
                items_detected += 1
        
        # If no specific match inside this clause, but there is a number/quantity,
        # we don't add anything to avoid double counting.

    if items_detected == 0:
        # Fallback baseline
        if meal_type == "Breakfast":
            return (300.0, 8.0, 100.0)
        elif meal_type in ("Lunch", "Dinner"):
            return (500.0, 15.0, 200.0)
        else: # Snack / Beverage
            return (150.0, 3.0, 50.0)

    return (round(total_cal, 1), round(total_prot, 1), round(total_phos, 1))
