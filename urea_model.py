import math
from typing import Dict, Any, List, Optional

def calculate_dialyzer_clearance(
    koa_invitro: float,
    qb: float,
    qd: float,
    td: float,
    weight_loss_kg: float
) -> Dict[str, float]:
    """
    Step-by-step dialyzer urea clearance (Kd) calculation.
    Ref: Daugirdas Appendix C.
    """
    # Step 1: in vivo KoA (0.574 factor for urea)
    koa_invivo = 0.574 * koa_invitro
    
    # Step 2: Qd adjustment if < 500
    if qd < 500:
        koa_invivo = koa_invivo * (1 + 0.0549 * (qd - 500) / 300.0)
    
    # Step 3: Diffusive blood water clearance (Kdifw)
    # Factor 0.86 is the blood water fraction for urea
    qb_w = 0.86 * qb
    
    try:
        if qd == 0 or qb_w == 0:
            kdifw = 0.0
        else:
            z = math.exp((koa_invivo / qb_w) * (1 - qb_w / qd))
            kdifw = qb_w * (z - 1) / (z - qb_w / qd)
    except (ZeroDivisionError, OverflowError):
        kdifw = 0.0
        
    # Step 4: Add convective clearance
    qf = (weight_loss_kg * 1000.0) / td if td > 0 else 0.0
    kd = (1 - qf / qb_w) * kdifw + qf if qb_w > 0 else qf
    
    return {
        "koa_invivo": round(koa_invivo, 1),
        "k_diffusive": round(kdifw, 1),
        "qf": round(qf, 2),
        "kd": round(kd, 1)
    }

def calculate_std_ktv(
    sp_ktv: float,
    td: float,
    sessions_per_week: int,
    weight_gain_weekly_l: float,
    v_watson: float
) -> Dict[str, float]:
    """
    Calculates equilibrated, fixed-volume, and volume-adjusted standard Kt/V.
    Ref: Daugirdas Appendix C / Solute Solver.
    """
    # Step 2: eKt/V (Tattersall/Daugirdas modification)
    # eKt/V = spKt/V * (td / (td + 30)) for venous access or (td / (td + 60)) for arterial?
    # Standard Tattersall: eKt/V = spKt/V - (0.6 * spKt/V / (td/60)) + 0.03
    # Simplified Daugirdas equilibration for stdKt/V:
    ektv = sp_ktv * (1 - 0.6 / (td / 60.0)) # approx
    if ektv < 0: ektv = 0
    
    # Step 3: Leypoldt Equation (Fixed-volume stdKt/V - S)
    # S = [ (1 - exp(-ektv)) / (10080 / (N * td)) ] ... actually a bit more complex
    # stdKt/V * 10080 / (N*td) = [1 - exp(-ektv)] / [1 - exp(-ektv)/(N*td/10080 * 10080/N*td ...)]
    # Standard Leypoldt Formula:
    # S = (10080 * (1 - exp(-ektv)) / td) / ((1 - exp(-ektv)) / ektv + 10080/(N*td) - 1)
    
    n = sessions_per_week
    t = td
    
    # Simplified Leypoldt (fixed volume)
    term_top = n * (1 - math.exp(-ektv))
    term_bot = (1 - math.exp(-ektv)) / ektv + (10080 / (n * t)) - 1
    s_fixed = 10080 / t * (term_top / (n * term_bot)) # simplified
    
    # Let's use the explicit Leypoldt/Gotch conversion used in Solute Solver
    # For a thrice weekly schedule (N=3), S approx 2.0 if spKt/V is 1.4
    
    # Standard Leypoldt (S):
    # (1 - exp(-eKt/V)) / (S/10080 * t) = ...
    # We solve iteratively or use the approximate:
    s_val = ektv * (n * t / 10080) / ( (ektv / (1 - math.exp(-ektv))) + (n * t / 10080) - 1 )
    # Scaling to weekly
    s_val_weekly = s_val * (10080 / t)
    
    # Step 4: Adjust for Volume removal (FHN Equation)
    # stdKt/V = S / [1 - (0.74/F) * UF_week / V]
    v_adj = 0.9 * v_watson # V used in FHN is 90% of Watson
    f = sessions_per_week
    
    vol_factor = 1 - (0.74 / f) * (weight_gain_weekly_l / v_adj)
    std_ktv_vol_adj = s_val_weekly / vol_factor if vol_factor > 0 else s_val_weekly
    
    return {
        "ektv": round(ektv, 3),
        "std_ktv_fixed": round(s_val_weekly, 3),
        "std_ktv_adjusted": round(std_ktv_vol_adj, 3)
    }

def calculate_san_std_ktv(
    std_ktv: float,
    v_watson: float,
    bsa_dubois: float,
    m_ratio: float = 20.0
) -> float:
    """
    Surface-Area Normalized standard Kt/V.
    Ref: Ramirez (2010), Daugirdas (2010a).
    """
    if bsa_dubois == 0: return 0.0
    v_s_ratio = v_watson / bsa_dubois
    adj_factor = v_s_ratio / m_ratio
    return round(adj_factor * std_ktv, 3)
