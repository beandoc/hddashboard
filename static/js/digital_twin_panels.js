// ── digital_twin_panels.js — SHAP, Bayesian confidence & cascade panels ──

function renderBayesInfo(result) {
  const hbSim  = result?.hb_sim || {};
  const ci     = hbSim.credible_interval || {};
  const label  = hbSim.confidence_label || '';
  const conf   = hbSim.confidence || '';

  const infoEl   = document.getElementById('hb-bayes-info');
  const badgeEl  = document.getElementById('hb-confidence-badge');
  const ciLabelEl= document.getElementById('hb-ci-label');

  if (!infoEl) return;

  // Colour the badge by confidence level
  let badgeBg = '#dbeafe', badgeColor = '#1d4ed8', icon = '\uD83E\uDDE0';
  if (conf === 'patient-calibrated') {
    badgeBg = '#dcfce7'; badgeColor = '#166534'; icon = '\u2705';
  } else if (conf === 'bayes-informed') {
    badgeBg = '#fef9c3'; badgeColor = '#854d0e'; icon = '\u26A0\uFE0F';
  } else if (conf === 'prior-only') {
    badgeBg = '#fee2e2'; badgeColor = '#991b1b'; icon = '\uD83D\uDEA8';
  }
  badgeEl.style.background = badgeBg;
  badgeEl.style.color      = badgeColor;
  badgeEl.textContent      = icon + '  ' + (label || conf);

  // Credible interval for k_gain (most clinically meaningful)
  if (ci.k_gain) {
    if (ci.k_gain.startsWith("0.0000")) {
      ciLabelEl.innerHTML = `<span style="color:#dc2626; font-weight:700; background:#fee2e2; padding:2px 6px; border-radius:4px;">⚠️ ESA response k_gain: ${ci.k_gain} (ESA hyporesponsive or above target)</span>`;
    } else {
      ciLabelEl.innerHTML = 'ESA response k_gain: ' + ci.k_gain;
    }
  } else {
    ciLabelEl.innerHTML = '';
  }

  infoEl.style.display = '';
}

function renderCascade(cascade) {
  const card = document.getElementById('cascade-card');
  if (!cascade || cascade.length === 0) return;
  const dirIcon = d => d === 'up' ? '↑' : d === 'down' ? '↓' : '↔';
  card.innerHTML = `
    <div class="cascade-title">⛓ Cross-domain cascade — ${cascade.length} domain${cascade.length > 1 ? 's' : ''} affected</div>
    ${cascade.map(c => `
      <div class="cascade-item">
        <div class="cascade-icon">${dirIcon(c.direction)}</div>
        <div>
          <div class="cascade-domain">${c.domain}</div>
          <div class="cascade-msg">${c.message}</div>
        </div>
      </div>
    `).join('')}
  `;
}

function showLoad(ids) { ids.forEach(id => { const e=document.getElementById(id); if(e) e.classList.add('active'); }); }
function hideLoad(ids) { ids.forEach(id => { const e=document.getElementById(id); if(e) e.classList.remove('active'); }); }

// ── SHAP Explanation ────────────────────────────────────────────────────────

const SHAP_FEATURE_LABELS = {
  age:                         'Age',
  dm:                          'Diabetes mellitus',
  chf:                         'Congestive heart failure',
  cad:                         'Coronary artery disease',
  pvd:                         'Peripheral vascular disease',
  af:                          'Atrial fibrillation',
  liver_disease:               'Liver disease',
  lvef:                        'Left ventricular EF (%)',
  diastolic_dysfunction_grade: 'Diastolic dysfunction grade',
  albumin:                     'Serum albumin (g/dL)',
  antihypertensive_count:      'No. of antihypertensives',
  pre_hd_sbp:                  'Pre-HD systolic BP (mmHg)',
  idwg_kg:                     'Interdialytic weight gain (kg)',
  uf_volume_ml:                'Prescribed UF volume (mL)',
  uf_rate_ml_kg_h:             'UF rate (mL/kg/h)',
  dialysate_temp:              'Dialysate temperature (°C)',
  dialysate_sodium:            'Dialysate sodium (mEq/L)',
  uf_achievement_ratio:        'UF achievement ratio',
  antihypertensive_prehd:      'BP meds taken pre-session',
  intradialytic_meals:         'Intradialytic meals',
  prior_idh_count_7sess:       'Prior IDH episodes (last 7)',
  prior_idh_rate_7sess:        'Prior IDH rate (last 7 sess)',
  prior_nadir_sbp_mean:        'Mean nadir SBP — last 7 sess',
  pre_hd_sbp_slope_7sess:      'Pre-HD SBP trend (7 sess)',
  albumin_slope_3mo:           'Albumin trend (3 months)',
  uf_rate_albumin_ratio:       'UF rate / Albumin ratio',
  hd_frequency:                'HD frequency (sessions/wk)',
  dialysis_vintage:            'Dialysis vintage (days)',
  hb:                          'Hemoglobin (g/dL)',
  calcium:                     'Serum calcium (mg/dL)',
  phosphorus:                  'Serum phosphorus (mg/dL)',
  prev_muscle_cramps:          'Cramps — last session',
  prev_nausea_vomiting:        'Nausea/vomiting — last sess',
  prev_giddiness:              'Dizziness — last session',
  prev_recovery_time:          'Recovery time — last sess (min)',
  prev_blood_flow_rate:        'Blood flow rate — last sess',
  prev_arterial_pressure:      'Arterial pressure — last sess',
  prev_venous_pressure:        'Venous pressure — last sess',
  heart_rate_variation:        'Heart rate variation',
  prior_dialysate_temp_mean:   'Mean dialysate temp (7 sess)',
  prior_dialysate_sodium_mean: 'Mean dialysate Na (7 sess)',
};

let _shapActiveTab = 'base';

function switchShapTab(tab) {
  _shapActiveTab = tab;
  document.getElementById('shap-bars-base').style.display = tab === 'base' ? '' : 'none';
  document.getElementById('shap-bars-scen').style.display = tab === 'scen' ? '' : 'none';
  document.getElementById('shap-tab-base').classList.toggle('active', tab === 'base');
  document.getElementById('shap-tab-scen').classList.toggle('active', tab === 'scen');
}

function formatShapValue(v) {
  if (v === null || v === undefined) return '—';
  const sign = v >= 0 ? '+' : '';
  return sign + (v * 100).toFixed(1) + '%';
}

function formatFeatureValue(feat, val) {
  if (val === null || val === undefined) return 'N/A';
  const binaryFeats = ['dm','chf','cad','pvd','af','liver_disease',
    'antihypertensive_prehd','intradialytic_meals','prev_muscle_cramps',
    'prev_nausea_vomiting','prev_giddiness'];
  if (binaryFeats.includes(feat)) return val ? 'Yes' : 'No';
  if (['prior_idh_rate_7sess','uf_achievement_ratio'].includes(feat))
    return (val * 100).toFixed(0) + '%';
  return parseFloat(val).toFixed(1);
}

function renderShapBars(containerId, shapValues) {
  const container = document.getElementById(containerId);
  if (!shapValues || !shapValues.length) {
    container.innerHTML = '<div class="shap-unavail">SHAP values not available — model is using heuristic scoring.</div>';
    return;
  }

  // Max absolute SHAP value for scaling bars (cap at 0.3 for visual clarity)
  const maxAbs = Math.min(0.30, Math.max(...shapValues.map(r => Math.abs(r.shap_value))));

  const html = shapValues.map(row => {
    const label    = SHAP_FEATURE_LABELS[row.feature] || row.feature;
    const sv       = row.shap_value;
    const isPos    = sv >= 0;
    const pct      = maxAbs > 0 ? Math.abs(sv) / maxAbs * 100 : 0;
    const valStr   = formatFeatureValue(row.feature, row.value);
    const svStr    = formatShapValue(sv);
    return `
      <div class="shap-bar-row" title="${label}: SHAP = ${svStr}, Value = ${valStr}">
        <div class="shap-feat-label">${label}</div>
        <div class="shap-bar-track">
          <div class="shap-bar-fill ${isPos ? 'pos' : 'neg'}" style="width:${pct.toFixed(1)}%"></div>
        </div>
        <div class="shap-val-label" style="color:${isPos ? '#dc2626' : '#4338ca'}">${svStr}</div>
        <div class="shap-feat-val">${valStr}</div>
      </div>
    `;
  }).join('');
  container.innerHTML = html;
}

function renderShapPanel(result) {
  const idhSim  = result?.idh_sim;
  const baseShap = idhSim?.baseline_full?.data?.shap_values;
  const scenShap = idhSim?.scenario_full?.data?.shap_values;

  const unavailEl = document.getElementById('shap-unavail');
  const tabsEl    = document.getElementById('shap-tabs-container');

  if (!baseShap && !scenShap) {
    unavailEl.style.display = '';
    unavailEl.textContent   = 'SHAP explanations not available — model is using rule-based scoring (train the IDH model to enable this).';
    tabsEl.style.display    = 'none';
    return;
  }

  unavailEl.style.display = 'none';
  tabsEl.style.display    = '';
  renderShapBars('shap-bars-base', baseShap);
  renderShapBars('shap-bars-scen', scenShap);
}

// ── Default render ──────────────────────────────────────────────────────────

