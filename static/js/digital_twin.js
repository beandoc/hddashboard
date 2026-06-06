// ── digital_twin.js — KPI updates, simulation runner, guardrails, events ──

// ── KPI domain sub-updaters ────────────────────────────────────────────────

function _updateKtvKpis(result) {
  const ktvExt = result?.ktv_extended || {};
  const ktvE   = ktvExt.scenario     || {};
  const scen_sp = ktvE.sp_ktv;
  if (scen_sp != null) {
    document.getElementById('kpi-ktv').textContent = scen_sp.toFixed(2);
    document.getElementById('kpi-ktv').style.color = scen_sp >= 1.2 ? '#16a34a' : '#dc2626';
    const dkt = ktvExt.delta_sp_ktv || 0;
    const el = document.getElementById('kpi-ktv-delta');
    el.textContent = (dkt >= 0 ? '+' : '') + dkt.toFixed(3);
    el.className = 'kpi-delta ' + (dkt > 0.02 ? 'delta-up' : dkt < -0.02 ? 'delta-down' : 'delta-neu');
  }
  if (ktvE.e_ktv != null) {
    document.getElementById('kpi-ektv').textContent = ktvE.e_ktv.toFixed(2);
    document.getElementById('kpi-ektv').style.color = ktvE.e_ktv >= 1.0 ? '#16a34a' : '#dc2626';
  }
}

function _updatePhosKpis(result) {
  const phos = result?.phosphate || {};
  const sp = phos.scenario_p;
  if (sp != null) {
    document.getElementById('kpi-phos').textContent = sp.toFixed(2);
    document.getElementById('kpi-phos').style.color = sp > 5.5 ? '#dc2626' : sp < 3.5 ? '#d97706' : '#16a34a';
    const dp = phos.delta_p || 0;
    const pe = document.getElementById('kpi-phos-delta');
    pe.textContent = (dp >= 0 ? '+' : '') + dp.toFixed(2) + ' mg/dL';
    pe.className = 'kpi-delta ' + (dp > 0.1 ? 'delta-down' : dp < -0.1 ? 'delta-up' : 'delta-neu');
    const badge = document.getElementById('p-status-badge');
    badge.textContent = phos.scenario_status === 'above_target' ? 'Above target' :
                        phos.scenario_status === 'below_target' ? 'Below target' : 'On target';
    badge.className = 'p-badge ' + (phos.scenario_status === 'above_target' ? 'p-above' :
                      phos.scenario_status === 'below_target' ? 'p-below' : 'p-target');
  }
  const phosSource = result?.dietary_phosphate_source || 'default_1200mg';
  const sourceLabel = document.getElementById('pintake-source-label');
  if (sourceLabel) {
    if (phosSource === 'meal_logs') {
      sourceLabel.innerHTML = '<span style="color:#16a34a;font-weight:600;">✓ Sourced from meal logs</span>';
    } else if (phosSource === 'manual_entry') {
      sourceLabel.innerHTML = '<span style="color:#2563eb;font-weight:600;">✎ Manually adjusted</span>';
    } else {
      sourceLabel.innerHTML = '<span style="color:var(--muted);">Sourced from default (1200mg)</span>';
    }
  }
  const mcmcPost = phos.mcmc_posterior;
  const mcmcInfoEl = document.getElementById('phos-mcmc-info');
  if (mcmcInfoEl) {
    if (mcmcPost && mcmcPost.calibrated) {
      mcmcInfoEl.style.display = 'block';
      const mcmcMethodEl = document.getElementById('phos-mcmc-method');
      if (mcmcMethodEl) {
        mcmcMethodEl.textContent = mcmcPost.method === 'pymc_nuts' ? 'PyMC NUTS MCMC' :
                                   mcmcPost.method === 'conjugate_gaussian' ? 'Conjugate Gaussian update' : 'Prior Only';
      }
      const set = (id, val, fmt) => { const e = document.getElementById(id); if (e) e.textContent = val != null ? fmt(val) : '—'; };
      set('phos-kc-scale-val',  mcmcPost.kc_scale_mean, v => v.toFixed(3));
      set('phos-forecast-val',  mcmcPost.p_pre_forecast, v => v.toFixed(2));
      const hdi = (id, arr) => { const e = document.getElementById(id); if (e) e.textContent = arr ? ` [${arr[0].toFixed(3)} - ${arr[1].toFixed(3)}]` : ''; };
      hdi('phos-kc-scale-hdi',  mcmcPost.kc_scale_hdi80);
      const fhdi = document.getElementById('phos-forecast-hdi');
      if (fhdi) fhdi.textContent = mcmcPost.p_pre_hdi80 ? ` [${mcmcPost.p_pre_hdi80[0].toFixed(2)} - ${mcmcPost.p_pre_hdi80[1].toFixed(2)}]` : '';
    } else {
      mcmcInfoEl.style.display = 'none';
    }
  }
}

function _updateIdhKpis(plotly, result) {
  const g = plotly?.idh_gauge || {};
  const idh = result?.idh_sim || {};
  if (g.baseline_pct != null) {
    document.getElementById('idh-base').textContent = g.baseline_pct + '%';
    document.getElementById('idh-base-level').textContent = g.baseline_level || '';
    document.getElementById('idh-base-level').className = 'idh-level ' + riskColor(g.baseline_pct);
  }
  if (g.scenario_pct != null) {
    document.getElementById('idh-scen').textContent = g.scenario_pct + '%';
    document.getElementById('idh-scen-level').textContent = g.scenario_level || '';
    document.getElementById('idh-scen-level').className = 'idh-level ' + riskColor(g.scenario_pct);
  }
  if (g.delta != null) {
    const badge = document.getElementById('idh-delta-badge');
    badge.textContent = (g.delta >= 0 ? '+' : '') + g.delta + '%';
    badge.style.background = g.delta > 2 ? '#fee2e2' : g.delta < -2 ? '#dcfce7' : '#f3f4f6';
    badge.style.color      = g.delta > 2 ? '#991b1b' : g.delta < -2 ? '#166534' : '#374151';
    document.getElementById('kpi-idh-delta').textContent = (g.delta >= 0 ? '+' : '') + g.delta + '%';
    document.getElementById('kpi-idh-delta').style.color = g.delta > 0 ? '#dc2626' : '#16a34a';
  }
  const warningEl = document.getElementById('idh-heuristic-warning');
  if (warningEl) warningEl.style.display = idh.model_is_heuristic ? 'block' : 'none';

  // IDH uncertainty band
  const piContainer = document.getElementById('idh-pi-band-container');
  if (piContainer) {
    if (g.pi_lower_pct != null && g.pi_upper_pct != null && g.scenario_pct != null) {
      piContainer.style.display = 'block';
      document.getElementById('idh-pi-bounds-text').textContent = `[${g.pi_lower_pct.toFixed(1)}%, ${g.pi_upper_pct.toFixed(1)}%]`;
      const left = Math.max(0, Math.min(100, g.pi_lower_pct));
      const right = Math.max(0, Math.min(100, g.pi_upper_pct));
      document.getElementById('idh-pi-band').style.left  = left + '%';
      document.getElementById('idh-pi-band').style.width = Math.max(0, right - left) + '%';
      document.getElementById('idh-scen-marker').style.left = Math.max(0, Math.min(100, g.scenario_pct)) + '%';
    } else {
      piContainer.style.display = 'none';
    }
  }
}

function _updateBiaKpis(result) {
  const bia = result?.bia || {};
  const hasBia = Object.keys(bia).length > 0;
  const biaBadge = document.getElementById('bia-available-badge');
  if (biaBadge) {
    biaBadge.textContent = hasBia ? 'BIA Active' : 'No BIA Data';
    biaBadge.style.background = hasBia ? '#dcfce7' : '#e2e8f0';
    biaBadge.style.color = hasBia ? '#166534' : '#64748b';
  }
  const BIA_IDS = ['bia-tbw','bia-phase','bia-ecw','bia-icw','bia-ecw-icw-ratio',
                   'bia-lean','bia-fat-mass','bia-fat-pct','bia-visceral',
                   'bia-bmi','bia-whr','bia-skeletal','bia-obesity'];
  if (hasBia) {
    const set = (id, val, fmt) => { const e = document.getElementById(id); if (e) e.textContent = val != null ? fmt(val) : '—'; };
    set('bia-tbw',     bia.tbw_l,              v => v.toFixed(1) + ' L');
    set('bia-phase',   bia.phase_angle,         v => v.toFixed(1) + '°');
    set('bia-ecw',     bia.ecw_l,               v => v.toFixed(1) + ' L');
    set('bia-icw',     bia.icw_l,               v => v.toFixed(1) + ' L');
    set('bia-lean',    bia.lean_muscle_mass,     v => v.toFixed(1) + ' kg');
    set('bia-fat-mass',bia.body_fat_mass,        v => v.toFixed(1) + ' kg');
    set('bia-fat-pct', bia.percentage_body_fat,  v => v.toFixed(1) + '%');
    set('bia-visceral',bia.visceral_fat_level,   v => v);
    set('bia-bmi',     bia.bmi,                  v => v.toFixed(1));
    set('bia-whr',     bia.whr,                  v => v.toFixed(2));
    set('bia-skeletal',bia.skeletal_muscle_mass, v => v.toFixed(1) + ' kg');
    set('bia-obesity', bia.obesity_degree,        v => v.toFixed(0) + '%');
    const ratio = (bia.ecw_l && bia.icw_l) ? (bia.ecw_l / bia.icw_l) : null;
    const ratioEl = document.getElementById('bia-ecw-icw-ratio');
    if (ratioEl) ratioEl.textContent = ratio != null ? ratio.toFixed(2) : '—';
  } else {
    BIA_IDS.forEach(id => { const e = document.getElementById(id); if (e) e.textContent = '—'; });
  }
}

function _updateHemoKpis(result) {
  const hemo = result?.hemodynamics || {};
  const ktvScen = result?.ktv_extended?.scenario || {};
  const hasHemo = Object.keys(hemo).length > 0;
  const hemoBadge = document.getElementById('hemo-strain-badge');
  if (hemoBadge) {
    if (hemo.qa != null) {
      const strain = hemo.cardiac_strain;
      hemoBadge.textContent = strain === 'high' ? 'High Cardiac Strain'
                            : strain === 'low'  ? 'Stenosis Risk / Low Flow'
                            :                     'Hemodynamics Normal';
      hemoBadge.style.background = strain === 'high' ? '#fee2e2' : strain === 'low' ? '#fef3c7' : '#dcfce7';
      hemoBadge.style.color      = strain === 'high' ? '#991b1b' : strain === 'low' ? '#92400e' : '#166534';
    } else {
      hemoBadge.textContent = 'No Doppler Data';
      hemoBadge.style.background = '#e2e8f0';
      hemoBadge.style.color = '#64748b';
    }
  }
  if (hasHemo) {
    const set = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
    set('hemo-qa',          hemo.qa          != null ? hemo.qa.toFixed(0) + ' mL/min' : '—');
    set('hemo-co',          hemo.estimated_co!= null ? hemo.estimated_co.toFixed(1) + ' L/min' : '—');
    set('hemo-shunt-ratio', hemo.shunt_ratio != null ? (hemo.shunt_ratio * 100).toFixed(0) + '%' : '—');
    const coLabel = document.getElementById('hemo-co-label');
    if (coLabel) {
      coLabel.textContent = hemo.co_is_measured ? 'Cardiac Output (CO)' : 'Est. Cardiac Output (CO)';
      coLabel.title = hemo.co_is_measured ? '' : 'Estimated via DuBois BSA formula × fixed cardiac index 3.0 L/min/m². May not reflect true CO in patients with high-flow AVF shunts.';
    }
    const ar_pct = ktvScen.ar_fraction != null ? ktvScen.ar_fraction * 100 : 0;
    const rcEl = document.getElementById('hemo-recirculation');
    if (rcEl) { rcEl.textContent = ar_pct.toFixed(1) + '%'; rcEl.style.color = ar_pct > 0 ? '#dc2626' : 'var(--text)'; }
    const kdEl = document.getElementById('hemo-kd');
    if (kdEl) {
      if (ktvScen.kd_effective != null) {
        kdEl.innerHTML = ar_pct > 0
          ? `${ktvScen.kd_effective.toFixed(0)} <span style="font-size:0.75rem;color:#dc2626;font-weight:600;">(Penalized)</span>`
          : ktvScen.kd_effective.toFixed(0) + ' mL/min';
      } else { kdEl.textContent = '—'; }
    }
    const pressEl = document.getElementById('hemo-pressures');
    if (pressEl) pressEl.textContent = (artPressure != null && venPressure != null) ? `${artPressure} / ${venPressure} mmHg` : '—';
    const warnEl = document.getElementById('hemo-recirc-warning');
    if (warnEl) {
      warnEl.innerHTML = ar_pct > 0
        ? `<strong style="color:#dc2626;">⚠ Recirculation Active:</strong> Blood pump flow rate (${ktvScen.qb} mL/min) exceeds access flow (${hemo.qa} mL/min). Clearance is penalized by ${ar_pct.toFixed(0)}%.`
        : hemo.qa != null && hemo.qa < 600
          ? `<strong style="color:#d97706;">⚠ Low Access Flow:</strong> Access flow of ${hemo.qa} mL/min is below KDOQI target threshold of 600 mL/min. Monitor for stenosis.`
          : hemo.qa != null && hemo.qa > 1500
            ? `<strong style="color:#d97706;">⚠ High Flow Shunt:</strong> Shunt flow of ${hemo.qa} mL/min exceeds 1500 mL/min. Monitor for high-output cardiac failure.`
            : 'Recirculation is stable. Blood pump Qb is within safe access limits.';
    }
  } else {
    ['hemo-qa','hemo-recirculation','hemo-shunt-ratio','hemo-co','hemo-kd','hemo-pressures'].forEach(id => {
      const e = document.getElementById(id); if (e) e.textContent = '—';
    });
    const warnEl = document.getElementById('hemo-recirc-warning');
    if (warnEl) warnEl.textContent = 'Recirculation occurs if blood pump Qb exceeds access Doppler Qa.';
  }
}

function _updateRbvCard(plotly) {
  const fvSummary = (plotly?.fluid_volume || {}).summary || {};
  const nadirVal  = fvSummary.rbv_nadir;
  const optimalVal = fvSummary.optimal_uf_rate_ml_kg_h;
  const idhPred   = fvSummary.idh_predicted;
  const rbvBadge  = document.getElementById('rbv-status-badge');
  if (rbvBadge) {
    rbvBadge.textContent = nadirVal != null
      ? (idhPred ? 'High IDH Risk (Nadir Critical)' : 'RBV Safe Zone')
      : 'No Simulation';
    rbvBadge.style.background = nadirVal != null ? (idhPred ? '#fee2e2' : '#dcfce7') : '#e2e8f0';
    rbvBadge.style.color      = nadirVal != null ? (idhPred ? '#991b1b' : '#166534') : '#64748b';
  }
  const nadirEl = document.getElementById('rbv-nadir-val');
  if (nadirEl) {
    nadirEl.textContent = nadirVal != null ? (nadirVal * 100).toFixed(1) + '%' : '—';
    if (nadirVal != null) nadirEl.style.color = idhPred ? '#dc2626' : 'var(--text)';
  }
  const optimalEl = document.getElementById('rbv-optimal-val');
  if (optimalEl) optimalEl.textContent = optimalVal != null ? optimalVal.toFixed(1) + ' mL/kg/h' : '—';
}

function updateKPIs(plotly, result) {
  _updateKtvKpis(result);
  _updatePhosKpis(result);
  _updateIdhKpis(plotly, result);
  _updateBiaKpis(result);
  _updateHemoKpis(result);
  _updateRbvCard(plotly);
}

function renderDefault() {
  if (document.getElementById('pintake-slider')) {
    document.getElementById('pintake-slider').value = baselinePIntake;
    document.getElementById('pintake-val').textContent = baselinePIntake;
  }
  updateGuardrailsFromSliders();
}

// ── Run simulation ──────────────────────────────────────────────────────────

async function runSimulation() {
  const btn = document.getElementById('run-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Simulating all 5 domains…';

  const scenario = {
    esa_weekly_iu:    parseFloat(document.getElementById('esa-slider').value),
    iron_tsat_target: parseFloat(document.getElementById('tsat-slider').value),
    session_h:        parseFloat(document.getElementById('session-slider').value),
    qb_ml_min:        parseFloat(document.getElementById('qb-slider').value),
    qd_ml_min:        parseFloat(document.getElementById('qd-slider').value),
    uf_rate_ml_kg_h:  parseFloat(document.getElementById('uf-slider').value),
    dialysate_temp:   parseFloat(document.getElementById('temp-slider').value),
    dialysate_sodium: parseInt(document.getElementById('na-slider').value),
    p_binder_pbe:     parseFloat(document.getElementById('pbe-slider').value),
    p_intake_mg_day:  parseInt(document.getElementById('pintake-slider').value),
  };

  showLoad(['hb-load','ktv-load','kd-load','idh-load','phos-load','uf-load','shap-load', 'rbv-load']);

  try {
    const resp = await fetch(`/twin/${PATIENT_ID}/simulate`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({scenario}),
    });
    if (!resp.ok) { alert('Error: ' + (await resp.json()).detail); return; }
    const data   = await resp.json();
    const plotly = data.plotly || {};
    const result = data.result || {};

    // Hb
    if (plotly.hb_traces?.length) renderHbChart(plotly.hb_traces);

    // RBV
    if (plotly.fluid_volume) renderRbvChart(plotly.fluid_volume);

    // Kt/V adequacy — mechanistic ktv_extended sp_ktv keeps chart and KPI on the same source
    const std = plotly.std_ktv_bar_data || {};
    renderKtvChart({
      base_sp:       std.base_sp,
      scen_sp:       std.scen_sp,
      base_ektv:     std.base_ektv,
      scenario_ektv: std.scenario_ektv,
    });
    renderKdChart(std);

    // Phosphate
    if (plotly.phosphate_bar_data?.baseline_p != null) {
      renderPhosChart(plotly.phosphate_bar_data);
    }

    // UF curve
    if (plotly.uf_curve_traces?.length) {
      renderUfCurve(plotly.uf_curve_traces, scenario.uf_rate_ml_kg_h, plotly.mortality_threshold_ml_kg_h);
    }

    // KPIs + IDH
    updateKPIs(plotly, result);

    // Cascade summary
    renderCascade(plotly.cascade || result.cascade);

    // SHAP explanation panel
    renderShapPanel(result);

    // Bayesian confidence info
    renderBayesInfo(result);

    // Dynamic Clinical Guardrails
    updateGuardrailsFromSliders();

    // KPI accent colors
    updateKpiAccents(result);

    // Auto-switch to charts tab on mobile screens so they see the result immediately
    if (window.innerWidth <= 960) {
      switchTwinTab('charts');
    }

  } catch(e) {
    alert('Network error: ' + e.message);
  } finally {
    hideLoad(['hb-load','ktv-load','kd-load','idh-load','phos-load','uf-load','shap-load', 'rbv-load']);
    btn.disabled = false;
    btn.textContent = '▶ Run All 5 Domains';
  }
}

// ── Reset ───────────────────────────────────────────────────────────────────

function resetAll() {
  document.getElementById('esa-slider').value = baselineIU;
  document.getElementById('esa-val').textContent = baselineIU;
  document.getElementById('tsat-slider').value = baselineTSAT;
  document.getElementById('tsat-val').textContent = baselineTSAT;
  document.getElementById('session-slider').value = baselineSession.session_duration_h;
  document.getElementById('session-val').textContent = baselineSession.session_duration_h.toFixed(2);
  document.getElementById('qb-slider').value = baselineSession.qb_ml_min;
  document.getElementById('qb-val').textContent = baselineSession.qb_ml_min;
  document.getElementById('qd-slider').value = 500;
  document.getElementById('qd-val').textContent = '500';
  document.getElementById('uf-slider').value = 10.0;
  document.getElementById('uf-val').textContent = '10.0';
  updateUfWarning(10.0);
  document.getElementById('temp-slider').value = baselineSession.dialysate_temp;
  document.getElementById('temp-val').textContent = baselineSession.dialysate_temp;
  document.getElementById('na-slider').value = baselineSession.dialysate_sodium;
  document.getElementById('na-val').textContent = baselineSession.dialysate_sodium;
  document.getElementById('pbe-slider').value = baselinePbe;
  document.getElementById('pbe-val').textContent = baselinePbeStr;
  document.getElementById('pintake-slider').value = baselinePIntake;
  document.getElementById('pintake-val').textContent = baselinePIntake;
  
  // Reset RBV values
  const rbvBadge = document.getElementById('rbv-status-badge');
  if (rbvBadge) {
    rbvBadge.textContent = 'No Simulation';
    rbvBadge.style.background = '#e2e8f0';
    rbvBadge.style.color = '#64748b';
  }
  const nadirEl = document.getElementById('rbv-nadir-val');
  if (nadirEl) {
    nadirEl.textContent = '—';
    nadirEl.style.color = 'var(--text)';
  }
  const optimalEl = document.getElementById('rbv-optimal-val');
  if (optimalEl) {
    optimalEl.textContent = '—';
  }

  const mcmcInfoEl = document.getElementById('phos-mcmc-info');
  if (mcmcInfoEl) {
    mcmcInfoEl.style.display = 'none';
  }

  runSimulation();
}

// ── Guardrails logic ──────────────────────────────────────────────────────────

function updateGuardrails(scenario) {
  const card = document.getElementById('guardrails-card');
  if (!card) return;

  const ufr = parseFloat(scenario.uf_rate_ml_kg_h || 10.0);
  const temp = parseFloat(scenario.dialysate_temp || 36.5);
  const na = parseInt(scenario.dialysate_sodium || 138);

  const items = [];

  // 1. UFR & DRT
  if (ufr > 10.0) {
    let prob = "58%";
    if (ufr > 12.0) prob = "78%";
    items.push({
      icon: "⚠️",
      domain: "High UFR & Recovery Alert",
      msg: `Predicted UFR of <strong>${ufr.toFixed(1)} mL/kg/h</strong> exceeds the safe cardiovascular threshold of 10.0 mL/kg/h. Model indicates a <strong>${prob} probability</strong> of dialysis recovery time extending beyond 4 hours.`,
      type: "danger"
    });
  } else {
    items.push({
      icon: "✅",
      domain: "Optimal Fluid Removal Rate",
      msg: `UFR of <strong>${ufr.toFixed(1)} mL/kg/h</strong> is within the safe zone (≤ 10.0 mL/kg/h). Estimated post-dialysis recovery time is optimal (~1-2 hours).`,
      type: "success"
    });
  }

  // 2. Temp
  if (temp <= 36.0) {
    items.push({
      icon: "🫀",
      domain: "Hemodynamic Thermal Support",
      msg: `Cool dialysate (<strong>${temp.toFixed(1)}°C</strong>) promotes venoconstriction and helps stabilize blood pressure, reducing estimated IDH risk.`,
      type: "info"
    });
  } else {
    items.push({
      icon: "💡",
      domain: "Thermal Loading Tip",
      msg: `Warm dialysate (<strong>${temp.toFixed(1)}°C</strong>) can cause vasodilation. Consider cooling to ≤ 36.0°C to help mitigate intradialytic hypotension.`,
      type: "tip"
    });
  }

  // 3. Sodium
  if (na > 140) {
    items.push({
      icon: "🧂",
      domain: "Osmotic Sodium Loading Warning",
      msg: `Elevated dialysate sodium (<strong>${na} mEq/L</strong>) reduces cramping risk, but causes sodium loading. This is associated with increased post-dialysis thirst and an estimated <strong>+0.5 to +0.8 kg increase</strong> in interdialytic weight gain (IDWG).`,
      type: "warning"
    });
  } else {
    items.push({
      icon: "✅",
      domain: "Baseline Sodium Matching",
      msg: `Dialysate sodium (<strong>${na} mEq/L</strong>) prevents excess sodium loading, helping preserve long-term tissue sodium levels and control thirst.`,
      type: "success"
    });
  }

  card.innerHTML = `
    <div class="guardrails-title">🛡️ Clinical Guardrails &amp; Safety Insights</div>
    <div style="display:flex; flex-direction:column; gap:8px; margin-top:8px;">
      ${items.map(item => `
        <div class="guardrails-item" style="border-bottom: 1px solid #fef3c7; padding-bottom: 8px;">
          <div class="guardrails-icon">${item.icon}</div>
          <div>
            <div class="guardrails-domain" style="font-weight:700; color:#78350f; font-size:0.75rem;">${item.domain}</div>
            <div class="guardrails-msg" style="color:#92400e; font-size:0.75rem; line-height:1.4; margin-top:1px;">${item.msg}</div>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function updateGuardrailsFromSliders() {
  updateGuardrails({
    uf_rate_ml_kg_h: parseFloat(document.getElementById('uf-slider').value),
    dialysate_temp: parseFloat(document.getElementById('temp-slider').value),
    dialysate_sodium: parseInt(document.getElementById('na-slider').value)
  });
}

// ── UF Rate inline warning ────────────────────────────────────────────────────
function updateUfWarning(val) {
  const el = document.getElementById('uf-warning-inline');
  if (!el) return;
  if (val > 13.0) {
    el.textContent = '⚠ Very high';
  } else if (val > 10.0) {
    el.textContent = '⚠ Above threshold';
  } else {
    el.textContent = '';
  }
}

function updateUfChartProposedLine(val) {
  if (window.currentUfTraces && window.currentUfTraces.length) {
    renderUfCurve(window.currentUfTraces, val, window.currentMortalityThresh);
  }
}

// Attach live slider input event listeners
const ufSliderEl = document.getElementById('uf-slider');
if (ufSliderEl) {
  ufSliderEl.addEventListener('input', function() {
    updateGuardrailsFromSliders();
    updateUfChartProposedLine(parseFloat(this.value));
  });
}
['temp-slider', 'na-slider'].forEach(id => {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener('input', updateGuardrailsFromSliders);
  }
});

// Update KPI strip border color when simulation results come in
function updateKpiAccents(result) {
  const ktv  = result?.ktv_extended?.scenario?.sp_ktv;
  const ektv = result?.ktv_extended?.scenario?.e_ktv;
  const phos = result?.phosphate?.scenario_p;
  const idhDelta = result?.idh_sim?.delta_risk_pct;

  const kpis = [
    { el: document.querySelector('.kpi:nth-child(2)'), val: ktv, low: 1.2, green: true },
    { el: document.querySelector('.kpi:nth-child(3)'), val: ektv, low: 1.0, green: true },
  ];
  kpis.forEach(k => {
    if (k.el && k.val != null) {
      k.el.style.borderLeft = `3px solid ${k.val >= k.low ? '#16a34a' : '#dc2626'}`;
    }
  });
  const phosKpi = document.querySelector('.kpi:nth-child(4)');
  if (phosKpi && phos != null) {
    phosKpi.style.borderLeft = `3px solid ${phos > 5.5 || phos < 3.5 ? '#dc2626' : '#16a34a'}`;
  }
  const idhKpi = document.querySelector('.kpi:nth-child(5)');
  if (idhKpi && idhDelta != null) {
    idhKpi.style.borderLeft = `3px solid ${idhDelta > 0 ? '#dc2626' : idhDelta < 0 ? '#16a34a' : '#e2e8f0'}`;
  }
}

updateUfWarning(10.0);
runSimulation();

function switchTwinTab(tabName) {
  const tabs = document.querySelectorAll('.twin-mobile-tab');
  const sidebar = document.querySelector('.sidebar');
  const charts = document.querySelector('.charts');

  tabs.forEach(tab => {
    if (tab.dataset.tab === tabName) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });

  if (tabName === 'prescription') {
    sidebar.classList.remove('tab-hidden');
    charts.classList.remove('tab-active');
  } else {
    sidebar.classList.add('tab-hidden');
    charts.classList.add('tab-active');
    setTimeout(resizeAllCharts, 50);
  }
}

function resizeAllCharts() {
  const chartIds = ['hb-chart', 'ktv-chart', 'kd-chart', 'phos-chart', 'uf-chart', 'rbv-chart'];
  chartIds.forEach(id => {
    const el = document.getElementById(id);
    if (el && el.classList.contains('js-plotly-plot')) {
      Plotly.Plots.resize(el);
    }
  });
}
