import math
from typing import Dict, Any, List, Optional

def calculate_pbe(binders: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculates Phosphate Binder Equivalent (PBE) and Calcium Load.
    - Calcium Acetate: 1.0 PBE, 25% Calcium
    - Sevelamer: 0.75 PBE, 0% Calcium
    - Lanthanum: 1.25 PBE, 0% Calcium
    - Calcium Carbonate: 1.0 PBE (as per img), 40% Calcium
    - Sucroferric/Ferric: 1.0 PBE
    """
    pbe_coeffs = {
        "calcium_acetate": 1.0,
        "sevelamer": 0.75,
        "lanthanum": 1.25,
        "calcium_carbonate": 1.0,
        "sucroferric": 2.5,  # Adjusted to match Ferric Citrate potency example
        "ferric_citrate": 2.5  # 1g Ferric Citrate = 2.5g PBED per user example
    }
    ca_content = {
        "calcium_acetate": 0.25,
        "calcium_carbonate": 0.40
    }
    
    total_pbe = 0.0
    total_ca_mg = 0.0
    
    for b in binders:
        type_key = b.get("type", "").lower()
        mg = b.get("mg", 0.0)
        
        pbe_coeff = pbe_coeffs.get(type_key, 0.0)
        total_pbe += (mg / 1000.0) * pbe_coeff
        
        ca_coeff = ca_content.get(type_key, 0.0)
        total_ca_mg += mg * ca_coeff
        
    return {
        "total_pbe": round(total_pbe, 2),
        "total_ca_mg": round(total_ca_mg, 1)
    }

def estimate_phosphate_kinetics(
    sex: str,
    weight: float,
    v_urea: float,
    koa_urea: float,
    qb: float,
    qd: float,
    td: float,
    schedule: str,
    p_pre_measured: float,
    p_intake_mg_day: float,
    p_binder_pbe: float,
    krp_ml_min: float,
    solve_for: str = "p_pre", # p_pre, p_intake, or p_binder
    koa_p_ratio: float = 0.5,
    hdf_pre: float = 0.0,
    hdf_post: float = 0.0
) -> Dict[str, Any]:
    """
    Phosphate Kinetic Model (Two-Pool) with variable intercompartmental clearance.
    Enhanced with HDF support and KoA P/U ratio calibration.
    """
    
    # 1. Volume Distribution
    v_total = v_urea * 2.0 # L
    ve_post = v_urea / 3.0
    vi = v_total - ve_post
    
    # 2. Intercompartmental Clearance (Kc)
    kc_base = (90.0 * weight / 70.0) if sex.lower().startswith('m') else (80.0 * weight / 70.0)
    
    # 3. Dialyzer Clearance (Michaels for Phosphate + HDF)
    def get_k_dialyzer(q_f: float) -> float:
        q_p = 0.93 * qb # Plasma flow approx
        # KoA for phosphate is calibrated by the ratio (0.4-0.6)
        koa_p = koa_p_ratio * koa_urea
        
        # Dialysate flow adjusted for HDF pre-dilution
        qd_adj = qd + (hdf_pre * 1000.0 / td if td > 0 else 0)
        
        try:
            z = (koa_p / q_p) * (1.0 - q_p / qd_adj)
            if abs(z) < 1e-9:
                kdif = koa_p
            else:
                kdif = q_p * (math.exp(z) - 1.0) / (math.exp(z) - q_p / qd_adj)
        except:
            kdif = koa_p
            
        # Add convective clearance (approx 0.8 sieving coefficient for P)
        # q_f here is total fluid removal + HDF post-dilution
        q_f_total = q_f + (hdf_post * 1000.0 / td if td > 0 else 0)
        
        return kdif * (1.0 + 0.8 * q_f_total / q_p) - q_f_total

    # 4. Solute Removal Logic
    absorption_coeff = 0.66 # 2/3 absorbed
    # P removal by binder: Each PBE unit removes ~30-40mg of P? 
    # Actually, binder effect is often modeled as reduction in absorption or a negative generation.
    # In this model, we'll use: Net Intake = (Intake * 0.66) - (PBE * BinderEfficiency)
    # Binder efficiency approx 45mg P per 1.0 PBE (Calcium Acetate 667mg ref)
    p_removal_binder_mg_day = p_binder_pbe * 45.0
    net_p_gen_mg_min = (p_intake_mg_day * absorption_coeff - p_removal_binder_mg_day) / 1440.0

    # 5. Numerical Simulation (RK4)
    def simulate_p(guess_val: float, solve_target: str) -> float:
        # Adjust target variable
        s_p_pre = p_pre_measured
        s_p_intake = p_intake_mg_day
        s_p_binder = p_binder_pbe
        
        if solve_target == "p_intake": s_p_intake = guess_val
        elif solve_target == "p_binder": s_p_binder = guess_val
        
        net_gen = (s_p_intake * absorption_coeff - s_p_binder * 45.0) / 1440.0
        
        # Start simulation
        ce = p_pre_measured if solve_target != "p_pre" else 5.0
        if solve_target == "p_pre": ce = guess_val
        
        ci = ce
        ve = ve_post
        dt = 10.0
        
        days_in_schedule = [int(d) for d in str(schedule)]
        num_sessions = len(days_in_schedule)
        q_f_ingest = 3.0 / ((7*24*60) - (num_sessions*td)) # Assume 3L fluid
        
        for day in range(1, 15): # 2 weeks steady state
            d_week = (day - 1) % 7 + 1
            is_dialysis = d_week in days_in_schedule
            
            if is_dialysis:
                q_f_dial = -3000.0 / td # 3L removal
                k_dial = get_k_dialyzer(q_f_dial)
                
                for _ in range(0, int(td), int(dt)):
                    # Variable Kc logic
                    current_kc = kc_base if ce > 3.0 else kc_base * 4.0
                    
                    def derivs(y_ce, y_ci, y_ve):
                        dce = (net_gen - current_kc*(y_ce - y_ci) - y_ce*(k_dial + krp_ml_min) - y_ce*q_f_dial) / y_ve
                        dci = (current_kc*(y_ce - y_ci)) / vi
                        dve = q_f_dial
                        return dce, dci, dve
                    
                    k1 = derivs(ce, ci, ve)
                    k2 = derivs(ce + k1[0]*dt/2, ci + k1[1]*dt/2, ve + k1[2]*dt/2)
                    k3 = derivs(ce + k2[0]*dt/2, ci + k2[1]*dt/2, ve + k2[2]*dt/2)
                    k4 = derivs(ce + k3[0]*dt, ci + k3[1]*dt, ve + k3[2]*dt)
                    
                    ce += (dt/6.0) * (k1[0] + 2*k2[0] + 2*k3[0] + k4[0])
                    ci += (dt/6.0) * (k1[1] + 2*k2[1] + 2*k3[1] + k4[1])
                    ve += (dt/6.0) * (k1[2] + 2*k2[2] + 2*k3[2] + k4[2])

            # Interdialytic period
            for _ in range(int(td) if is_dialysis else 0, 1440, int(dt)):
                current_kc = kc_base if ce > 3.0 else kc_base * 4.0
                def derivs_id(y_ce, y_ci, y_ve):
                    dce = (net_gen - current_kc*(y_ce - y_ci) - y_ce*(krp_ml_min) - y_ce*q_f_ingest) / y_ve
                    dci = (current_kc*(y_ce - y_ci)) / vi
                    dve = q_f_ingest
                    return dce, dci, dve
                
                k1 = derivs_id(ce, ci, ve)
                k2 = derivs_id(ce + k1[0]*dt/2, ci + k1[1]*dt/2, ve + k1[2]*dt/2)
                k3 = derivs_id(ce + k2[0]*dt/2, ci + k2[1]*dt/2, ve + k2[2]*dt/2)
                k4 = derivs_id(ce + k3[0]*dt, ci + k3[1]*dt, ve + k3[2]*dt)
                
                ce += (dt/6.0) * (k1[0] + 2*k2[0] + 2*k3[0] + k4[0])
                ci += (dt/6.0) * (k1[1] + 2*k2[1] + 2*k3[1] + k4[1])
                ve += (dt/6.0) * (k1[2] + 2*k2[2] + 2*k3[2] + k4[2])
                
        return ce

    # 6. Solver
    result_val = 0.0

    if solve_for == "p_pre":
        # Forward simulation: iterate until the cycle is self-consistent (steady state).
        # Start from the measured value and re-simulate until convergence.
        ce_guess = p_pre_measured if p_pre_measured and p_pre_measured > 0 else 5.0
        for _ in range(10):
            ce_next = simulate_p(ce_guess, "p_pre")
            if abs(ce_next - ce_guess) < 0.01:
                ce_guess = ce_next
                break
            ce_guess = ce_next
        result_val = round(ce_guess, 2)
    else:
        # Bisection: find the intake or binder dose that produces the observed pre-P.
        low, high = 0.0, 5000.0
        if solve_for == "p_binder":
            high = 50.0

        for _ in range(25):
            mid = (low + high) / 2.0
            modeled_p_pre = simulate_p(mid, solve_for)

            if solve_for == "p_intake":
                if modeled_p_pre < p_pre_measured: low = mid
                else: high = mid
            else:  # p_binder
                if modeled_p_pre > p_pre_measured: low = mid
                else: high = mid

            result_val = mid

    return {
        "result_value": round(result_val, 2),
        "solve_for": solve_for,
        "modeled_p_pre": round(simulate_p(result_val, solve_for), 2),
        "total_v_dist": round(v_total, 1),
        "net_gen_mg_day": round(result_val * absorption_coeff if solve_for == "p_intake" else p_intake_mg_day * absorption_coeff, 1)
    }
