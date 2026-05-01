import math
from typing import Dict, Any, List, Optional

def estimate_krcrw(
    sex: str,
    age: float,
    weight: float,
    g_creat_input: float,
    lab_day: int,
    schedule: str,
    pre_creat_measured: float,
    ivp2: float,
    qb: float,
    qd: float,
    td: float,
    weekly_fluid_l: float,
    k_code: str,
    koa: float,
    is_black: bool = False # Kept for API compatibility, but logic is now race-neutral
) -> Dict[str, Any]:
    """
    Estimating residual kidney (water) clearance for creatinine (KRCRw) (v1.40)
    Based on John T. Daugirdas model.
    Refined with "Race Neutral" Ix et al. modification:
    - Eliminates race term.
    - Adds 17 mg/day for all patients.
    """
    
    # 1. Creatinine Generation Rate (G_Cr) - Race Neutral Ix Equation
    if g_creat_input == 999:
        # Base GCr = 879.89 + 12.51 * weight(kg) - 6.19 * age - (379.42 if female) + 17.0
        g_mg_day = 879.89 + (12.51 * weight) - (6.19 * age) + 17.0
        if sex.lower().startswith('f'):
            g_mg_day -= 379.42
        g_mg_min = g_mg_day / 1440.0
    else:
        g_mg_day = g_creat_input
        g_mg_min = g_mg_day / 1440.0

    # 2. Volume Distribution (Two-Compartment)
    v_total_post = ivp2 * 1000.0  # mL
    vi = (2.0/3.0) * v_total_post
    ve_post = (1.0/3.0) * v_total_post
    
    # Intercompartmental (Kc) and Extrarenal (Kg) Clearances
    # Kc depends on weight, typically 8 * IVP2 for creatinine
    kc = 8.0 * ivp2 
    k_gut = (0.038 * weight * 1000.0) / 1440.0
    
    # 3. Dialyzer Clearance (Michaels/Daugirdas Equation)
    def get_k_dialyzer(q_f: float) -> float:
        # Effective Plasma Water Flow
        q_ecr = 0.623 * qb
        if q_ecr == 0 or qd == 0: return 0
        
        # In vivo KoA adjustment (0.360 for Creatinine)
        if k_code.lower() == "koaurea":
            # Adjust KoA for creatinine and in-vivo differences (Factor 0.360)
            # The v1.40 model uses 0.35979
            koa_adj = 0.35979 * koa * (1.0 + 0.0549 * (qd - 500) / 300.0 if qd < 500 else 1.0)
        else:
            koa_adj = koa

        # Diffusive Clearance (KDIF)
        try:
            z = (koa_adj / q_ecr) * (1.0 - q_ecr / qd)
            if abs(z) < 1e-9:
                kdif = koa_adj
            else:
                kdif = q_ecr * (math.exp(z) - 1.0) / (math.exp(z) - q_ecr / qd)
        except (ZeroDivisionError, OverflowError):
            kdif = koa_adj
            
        # Total Clearance (KDTOT)
        return kdif * (1.0 + q_f / q_ecr) - q_f

    # 4. Schedule and UF Logic
    days_in_schedule = [int(d) for d in str(schedule)]
    num_sessions = len(days_in_schedule)
    
    total_min_week = 7 * 24 * 60
    total_td_week = num_sessions * td
    total_id_min_week = total_min_week - total_td_week
    
    q_f_ingest = (weekly_fluid_l * 1000.0) / total_id_min_week
    
    # 5. Numerical Simulation (RK4)
    def simulate_steady_state(krcrw_guess: float) -> float:
        # Start with an initial concentration guess
        ce = pre_creat_measured
        ci = ce
        ve = ve_post
        dt = 10.0
        
        pre_creat_at_lab = 0.0
        
        # Run 3 weeks to reach stable steady state
        for day in range(1, 22):
            d_week = (day - 1) % 7 + 1
            is_dialysis = d_week in days_in_schedule
            
            if is_dialysis:
                # 1. Dialysis Period
                uf_session = (weekly_fluid_l * 1000.0) / num_sessions
                q_f_dial = -uf_session / td
                k_dial = get_k_dialyzer(q_f_dial)
                
                # Capture Pre-Dialysis (Week 3)
                if day > 14 and d_week == lab_day:
                    pre_creat_at_lab = ce
                
                for _ in range(0, int(td), int(dt)):
                    def derivs(y_ce, y_ci, y_ve):
                        dce = (g_mg_min - kc*(y_ce - y_ci) - y_ce*(k_dial + krcrw_guess + k_gut) - y_ce*q_f_dial) / y_ve
                        dci = (kc*(y_ce - y_ci)) / vi
                        dve = q_f_dial
                        return dce, dci, dve
                    
                    k1 = derivs(ce, ci, ve)
                    k2 = derivs(ce + k1[0]*dt/2, ci + k1[1]*dt/2, ve + k1[2]*dt/2)
                    k3 = derivs(ce + k2[0]*dt/2, ci + k2[1]*dt/2, ve + k2[2]*dt/2)
                    k4 = derivs(ce + k3[0]*dt, ci + k3[1]*dt, ve + k3[2]*dt)
                    
                    ce += (dt/6.0) * (k1[0] + 2*k2[0] + 2*k3[0] + k4[0])
                    ci += (dt/6.0) * (k1[1] + 2*k2[1] + 2*k3[1] + k4[1])
                    ve += (dt/6.0) * (k1[2] + 2*k2[2] + 2*k3[2] + k4[2])

                # 2. Post-Dialysis (Remainder of day)
                for _ in range(int(td), 1440, int(dt)):
                    def derivs_id(y_ce, y_ci, y_ve):
                        dce = (g_mg_min - kc*(y_ce - y_ci) - y_ce*(krcrw_guess + k_gut) - y_ce*q_f_ingest) / y_ve
                        dci = (kc*(y_ce - y_ci)) / vi
                        dve = q_f_ingest
                        return dce, dci, dve
                    
                    k1 = derivs_id(ce, ci, ve)
                    k2 = derivs_id(ce + k1[0]*dt/2, ci + k1[1]*dt/2, ve + k1[2]*dt/2)
                    k3 = derivs_id(ce + k2[0]*dt/2, ci + k2[1]*dt/2, ve + k2[2]*dt/2)
                    k4 = derivs_id(ce + k3[0]*dt, ci + k3[1]*dt, ve + k3[2]*dt)
                    
                    ce += (dt/6.0) * (k1[0] + 2*k2[0] + 2*k3[0] + k4[0])
                    ci += (dt/6.0) * (k1[1] + 2*k2[1] + 2*k3[1] + k4[1])
                    ve += (dt/6.0) * (k1[2] + 2*k2[2] + 2*k3[2] + k4[2])
            else:
                # Full Interdialytic Day
                for _ in range(0, 1440, int(dt)):
                    def derivs_id(y_ce, y_ci, y_ve):
                        dce = (g_mg_min - kc*(y_ce - y_ci) - y_ce*(krcrw_guess + k_gut) - y_ce*q_f_ingest) / y_ve
                        dci = (kc*(y_ce - y_ci)) / vi
                        dve = q_f_ingest
                        return dce, dci, dve
                    
                    k1 = derivs_id(ce, ci, ve)
                    k2 = derivs_id(ce + k1[0]*dt/2, ci + k1[1]*dt/2, ve + k1[2]*dt/2)
                    k3 = derivs_id(ce + k2[0]*dt/2, ci + k2[1]*dt/2, ve + k2[2]*dt/2)
                    k4 = derivs_id(ce + k3[0]*dt, ci + k3[1]*dt, ve + k3[2]*dt)
                    
                    ce += (dt/6.0) * (k1[0] + 2*k2[0] + 2*k3[0] + k4[0])
                    ci += (dt/6.0) * (k1[1] + 2*k2[1] + 2*k3[1] + k4[1])
                    ve += (dt/6.0) * (k1[2] + 2*k2[2] + 2*k3[2] + k4[2])
        
        return pre_creat_at_lab

    # 6. Convergence Loop (Bisection)
    low, high = 0.0, 45.0
    krcrw_est = 0.0
    for _ in range(30):
        mid = (low + high) / 2.0
        modeled = simulate_steady_state(mid)
        if modeled > pre_creat_measured:
            low = mid
        else:
            high = mid
        krcrw_est = mid
        if abs(modeled / pre_creat_measured - 1.0) < 0.0001:
            break

    return {
        "krcrw": round(krcrw_est, 3),
        "krcr": round(krcrw_est * 1.075, 3),
        "g_creat_mg_day": round(g_mg_day, 2),
        "pre_creat_modeled": round(simulate_steady_state(krcrw_est), 3),
        "kd_diffusive": round(get_k_dialyzer(0), 1),
        "uf_session_ml": round((weekly_fluid_l * 1000.0) / num_sessions, 1)
    }

def track_patient_krcrw_over_time(
    sex: str,
    age: int,
    weight: float,
    baseline_gcr: float,
    baseline_vdcr: float,
    hd_frequency: int,
    records: List[Any] # List of MonthlyRecord objects
) -> List[Dict[str, Any]]:
    """
    Calculates KRCRw for each month using baseline GCr/VdCr.
    Assumes standard dialysis parameters (QB 300, QD 500, TD 240) if session data is missing.
    """
    results = []
    
    # Map frequency to schedule string
    # 2 -> "14" (Mon/Thu), 3 -> "135" (MWF)
    schedule = "135" if hd_frequency == 3 else "14"
    lab_day = 1 # Assume Mon lab day
    
    for r in records:
        if not r.serum_creatinine:
            continue
            
        try:
            res = estimate_krcrw(
                sex=sex,
                age=age,
                weight=weight,
                g_creat_input=baseline_gcr,
                lab_day=lab_day,
                schedule=schedule,
                pre_creat_measured=r.serum_creatinine,
                ivp2=baseline_vdcr,
                qb=300, qd=500, td=240, # Standard defaults
                weekly_fluid_l=r.idwg * (3 if hd_frequency == 3 else 2) if r.idwg else 3.0,
                k_code="koaurea",
                koa=900
            )
            results.append({
                "month": r.record_month,
                "creatinine": r.serum_creatinine,
                "krcrw": res["krcrw"],
                "krcr": res["krcr"]
            })
        except:
            continue
            
    return results
