/**
 * entry_validation.js — Client-side validation for the HD entry form.
 *
 * Hard limits are NOT duplicated here. They are injected by Jinja as a JSON
 * data attribute on the form element:
 *   <form data-hard-limits='{"hb":{"min":2.0,"max":22.0,"label":"Hemoglobin"}, ...}'>
 *
 * This ensures Python validators.py and the JS validator stay in sync automatically.
 */

/* ── Soft clinical thresholds (UI colour warnings, do not block save) ── */
const SOFT_THRESHOLDS = {
    hb:         { bad: 10,   warn: 11.5, type: 'low' },
    phosphorus: { bad: 5.5,  warn: 5.0,  type: 'high' },
    albumin:    { bad: 2.5,  warn: 3.5,  type: 'low' },
    tsat:       { bad: 20,   warn: 30,   type: 'low' },
    calcium:    { bad: 8.0,  warn: 8.5,  type: 'low' },
};

/* ── Physiological ranges (likely unit errors if outside) ── */
const PHYS_RANGES = {
    albumin:          { lo: 1.5,    hi: 6.0,    msg: 'Likely g/L error? Expected 1.5–6.0 g/dL' },
    hb:               { lo: 4.0,    hi: 18.0,   msg: 'Expected 4.0–18.0 g/dL' },
    phosphorus:       { lo: 1.0,    hi: 12.0,   msg: 'Expected 1.0–12.0 mg/dL' },
    serum_ferritin:   { lo: 5,      hi: 5000,   msg: 'Expected 5–5000 ng/mL' },
    wbc_count:        { lo: 1000,   hi: 30000,  msg: 'Expected 1000–30000 /cmm' },
    neutrophil_count: { lo: 10,     hi: 100,    msg: 'Expected 10–100%' },
    bp_sys:           { lo: 60,     hi: 260,    msg: 'Expected 60–260 mmHg' },
    bp_dia:           { lo: 30,     hi: 160,    msg: 'Expected 30–160 mmHg' },
};

/* ── Read hard limits from form data attribute ── */
function getHardLimits() {
    try {
        const form = document.querySelector('form[data-hard-limits]');
        return form ? JSON.parse(form.dataset.hardLimits) : {};
    } catch(e) { return {}; }
}

/* ── Per-field soft validation (colour coding + physiological range check) ── */
function validate(field) {
    const input = document.querySelector(`input[name="${field}"]`);
    if (!input) return;

    const val = parseFloat(input.value);

    // Reset state
    input.style.backgroundColor = '';
    input.style.borderColor     = '#e2e8f0';
    input.parentElement.querySelector('.phys-warning')?.remove();

    if (isNaN(val)) return;

    // 1. Physiological range check (likely unit error)
    const pr = PHYS_RANGES[field];
    if (pr && (val < pr.lo || val > pr.hi)) {
        input.style.backgroundColor = '#fff1f2';
        input.style.borderColor     = '#e11d48';
        const msg = document.createElement('div');
        msg.className = 'phys-warning';
        msg.style.cssText = 'color:#e11d48;font-size:0.75rem;font-weight:700;margin-top:4px;display:flex;align-items:center;gap:4px;';
        msg.innerHTML = `<i class="material-icons" style="font-size:1rem;">warning</i> ${pr.msg}`;
        input.parentElement.appendChild(msg);
        return; // physiological error takes priority
    }

    // 2. Clinical risk thresholds (colour hint only)
    const t = SOFT_THRESHOLDS[field];
    if (t) {
        if (t.type === 'low') {
            if (val < t.bad)       { input.style.backgroundColor = '#ffe6e6'; input.style.borderColor = '#dc3545'; }
            else if (val < t.warn) { input.style.backgroundColor = '#fff3e0'; input.style.borderColor = '#e67e22'; }
        } else {
            if (val > t.bad)       { input.style.backgroundColor = '#ffe6e6'; input.style.borderColor = '#dc3545'; }
            else if (val > t.warn) { input.style.backgroundColor = '#fff3e0'; input.style.borderColor = '#e67e22'; }
        }
    }
}

/* ── Hard limits check — blocks wizard navigation to next step ── */
function checkHardLimits() {
    const limits = getHardLimits();
    const activePanel = document.querySelector('.wizard-step.wiz-active');
    const inputs = activePanel
        ? activePanel.querySelectorAll('input[type="number"]')
        : document.querySelectorAll('input[type="number"]');

    for (const input of inputs) {
        const name = input.name;
        const val  = parseFloat(input.value);
        if (!name || isNaN(val)) continue;
        const lim = limits[name];
        if (!lim) continue;
        if (val < lim.min || val > lim.max) {
            alert(`Impossible value for ${lim.label}: ${val}.\nAllowed range: ${lim.min}–${lim.max}. Please verify units and re-enter.`);
            input.style.borderColor     = '#ef4444';
            input.style.backgroundColor = '#fef2f2';
            input.scrollIntoView({ behavior: 'smooth', block: 'center' });
            input.focus();
            return false;
        }
    }
    return true;
}

/* ── Validate all filled inputs on the current wizard step ── */
function validateCurrentStepFields() {
    const panel = document.getElementById('wstep-' + (typeof wizStep !== 'undefined' ? wizStep : 1));
    if (!panel) return 0;
    panel.querySelectorAll('input[name]').forEach(inp => {
        if (inp.value) validate(inp.name);
    });
    return panel.querySelectorAll('.phys-warning').length;
}

/* ── Bind live validation to all inputs on page load ── */
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('input').forEach(input => {
        input.addEventListener('input', () => validate(input.name));
        validate(input.name); // initial pass for pre-filled values
    });
});
