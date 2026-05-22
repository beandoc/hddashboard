/**
 * entry_wizard.js — Multi-step wizard state management for the HD entry form.
 *
 * Fixes:
 *  - Replaced the 300ms setTimeout race condition with an explicit isRestoring flag.
 *    Dirty tracking only activates after the restore loop completes, so sessionStorage
 *    restoration never triggers false "unsaved changes" warnings.
 *  - Wizard step count (WIZ_TOTAL) and names are the single source of truth here;
 *    the HTML tabs reference data-step attributes, no hardcoding in markup.
 */

const WIZ_TOTAL    = 4;
const WIZ_NAMES    = ['Parameters', 'Lab Values', 'Medications', 'Review'];
const WIZ_REQUIRED = { 1: [], 2: ['hb'], 3: [], 4: [] };

// WIZ_SS_KEY is injected by the template as a data attribute on the form element.
// e.g. <form data-wiz-key="hd_wiz_42_2026-05">
let WIZ_SS_KEY = '';

let wizStep    = 1;
const wizDone  = new Set();

/* ── sessionStorage helpers ──────────────────────────────────────────────── */

function wizSaveStep(s) {
    const panel = document.getElementById('wstep-' + s);
    if (!panel) return;
    const data = {};
    panel.querySelectorAll('input, select, textarea').forEach(el => {
        if (el.name && el.type !== 'hidden') data[el.name] = el.value;
    });
    try {
        const stored = JSON.parse(sessionStorage.getItem(WIZ_SS_KEY) || '{}');
        stored['s' + s] = data;
        sessionStorage.setItem(WIZ_SS_KEY, JSON.stringify(stored));
    } catch(e) { /* storage full or unavailable */ }
}

function wizRestoreAll(isOnError) {
    // For existing records (no error), don't overwrite server-prefilled values.
    const form = document.querySelector('form');
    if (!isOnError && form && form.dataset.hasRecord) return;
    try {
        const stored = JSON.parse(sessionStorage.getItem(WIZ_SS_KEY) || '{}');
        for (let s = 1; s <= WIZ_TOTAL; s++) {
            const data  = stored['s' + s];
            if (!data) continue;
            const panel = document.getElementById('wstep-' + s);
            if (!panel) continue;
            Object.entries(data).forEach(([name, val]) => {
                const inp = panel.querySelector(`[name="${name}"]`);
                if (!inp || val === undefined || val === null) return;
                if (isOnError || !inp.value) {
                    inp.value = val;
                    if (typeof validate === 'function') validate(inp.name);
                }
            });
        }
    } catch(e) { /* corrupt storage — ignore */ }
}

/* ── Required-field check ────────────────────────────────────────────────── */

function wizCheckRequired(s) {
    const reqs = WIZ_REQUIRED[s] || [];
    return reqs.every(name => {
        const el = document.querySelector(`[name="${name}"]`);
        return el && el.value.trim() !== '';
    });
}

/* ── UI update ───────────────────────────────────────────────────────────── */

function wizUpdateUI() {
    const s = wizStep;

    document.querySelectorAll('.wizard-tab').forEach((tab, i) => {
        const n = i + 1;
        tab.classList.toggle('wiz-active', n === s);
        tab.classList.toggle('wiz-done',   wizDone.has(n) && n !== s);
    });

    const fill = document.getElementById('wizard-progress-fill');
    if (fill) fill.style.width = ((s / WIZ_TOTAL) * 100) + '%';

    const lbl = document.getElementById('wizard-step-label');
    if (lbl) lbl.textContent = `Step ${s} of ${WIZ_TOTAL} · ${WIZ_NAMES[s - 1]}`;

    for (let n = 1; n <= WIZ_TOTAL; n++) {
        const panel = document.getElementById('wstep-' + n);
        if (panel) panel.classList.toggle('wiz-active', n === s);
    }

    const ind = document.getElementById('wiz-step-indicator');
    if (ind) ind.textContent = `Step ${s} of ${WIZ_TOTAL}`;

    const btnBack   = document.getElementById('btn-wiz-back');
    if (btnBack) btnBack.disabled = (s === 1);

    const btnNext    = document.getElementById('btn-wiz-next');
    const submitWrap = document.getElementById('wiz-submit-wrap');
    const reqHint    = document.getElementById('wiz-req-hint');

    if (s === WIZ_TOTAL) {
        if (btnNext)    btnNext.style.display    = 'none';
        if (ind)        ind.style.display        = 'flex';
        if (submitWrap) submitWrap.style.display = 'flex';
        if (reqHint)    reqHint.style.display    = 'none';
        if (typeof buildReviewSummary === 'function') buildReviewSummary();
    } else {
        if (btnNext) {
            btnNext.style.display = 'flex';
            btnNext.disabled      = !wizCheckRequired(s);
        }
        if (submitWrap) submitWrap.style.display = 'none';
        if (reqHint)    reqHint.style.display    = wizCheckRequired(s) ? 'none' : 'block';
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ── Navigation ──────────────────────────────────────────────────────────── */

function wizGoTo(target) {
    if (target < 1 || target > WIZ_TOTAL) return;

    if (target > wizStep && !wizCheckRequired(wizStep)) {
        (WIZ_REQUIRED[wizStep] || []).forEach(name => {
            const el = document.querySelector(`[name="${name}"]`);
            if (el && !el.value.trim()) {
                el.style.borderColor     = '#ef4444';
                el.style.backgroundColor = '#fef2f2';
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });
        const hint = document.getElementById('wiz-req-hint');
        if (hint) hint.style.display = 'block';
        return;
    }

    wizSaveStep(wizStep);
    if (target > wizStep) wizDone.add(wizStep);
    wizStep = target;
    wizUpdateUI();
}

function wizGoToStep(step) {
    wizSaveStep(wizStep);
    wizDone.add(wizStep);
    wizStep = step;
    wizUpdateUI();
}

function wizardNext() {
    if (typeof checkHardLimits === 'function' && !checkHardLimits()) return;
    const warnings = (typeof validateCurrentStepFields === 'function') ? validateCurrentStepFields() : 0;
    if (wizStep === 2 && warnings > 0) {
        const ok = confirm(
            `${warnings} clinical range warning(s) found on this step.\n\n` +
            `Fields in red are outside typical physiological ranges — possible unit error.\n\nAre the values correct?`
        );
        if (!ok) return;
    }
    wizGoTo(wizStep + 1);
}

function wizardBack() { wizGoTo(wizStep - 1); }

/* ── Review Summary Builder ──────────────────────────────────────────────── */

function buildReviewSummary() {
    const container = document.getElementById('review-summary-content');
    if (!container) return;

    const groups = [
        { title: 'Parameters', fields: [
            { name: 'residual_urine_output', label: 'Residual UO',    unit: 'mL/24h' },
            { name: 'last_prehd_weight',     label: 'Last Pre-HD Wt', unit: 'kg' },
        ]},
        { title: 'Lab Reports', fields: [
            { name: 'hb',                  label: 'Hemoglobin',    unit: 'g/dL' },
            { name: 'hct',                 label: 'Hematocrit',    unit: '%' },
            { name: 'wbc_count',           label: 'TLC/WBC' },
            { name: 'neutrophil_count',    label: 'Neutrophils',   unit: '%' },
            { name: 'platelet_count',      label: 'Platelets',     unit: 'lakh/cmm' },
            { name: 'serum_iron',          label: 'Serum Iron',    unit: 'µg/dL' },
            { name: 'tibc',                label: 'TIBC',          unit: 'µg/dL' },
            { name: 'serum_ferritin',      label: 'Ferritin',      unit: 'ng/mL' },
            { name: 'tsat',                label: 'TSAT',          unit: '%' },
            { name: 'calcium',             label: 'Calcium',       unit: 'mg/dL' },
            { name: 'phosphorus',          label: 'Phosphorus',    unit: 'mg/dL' },
            { name: 'alkaline_phosphate',  label: 'Alk Phos',      unit: 'U/L' },
            { name: 'ipth',                label: 'iPTH',          unit: 'pg/mL' },
            { name: 'vit_d',               label: 'Vit D',         unit: 'ng/mL' },
            { name: 'albumin',             label: 'Albumin',       unit: 'g/dL' },
            { name: 'pre_dialysis_urea',   label: 'Pre-HD Urea',   unit: 'mg/dL' },
            { name: 'post_dialysis_urea',  label: 'Post-HD Urea',  unit: 'mg/dL' },
            { name: 'serum_creatinine',    label: 'Creatinine',    unit: 'mg/dL' },
            { name: 'serum_sodium',        label: 'Sodium',        unit: 'mmol/L' },
            { name: 'serum_potassium',     label: 'Potassium',     unit: 'mmol/L' },
            { name: 'serum_bicarbonate',   label: 'Bicarbonate',   unit: 'mmol/L' },
            { name: 'serum_uric_acid',     label: 'Uric Acid',     unit: 'mg/dL' },
            { name: 'total_cholesterol',   label: 'Cholesterol',   unit: 'mg/dL' },
            { name: 'ast',                 label: 'AST',           unit: 'U/L' },
            { name: 'alt',                 label: 'ALT',           unit: 'U/L' },
            { name: 'crp',                 label: 'CRP',           unit: 'mg/L' },
        ]},
        { title: 'Medications', fields: [
            { name: 'esa_type',                 label: 'ESA Type' },
            { name: 'epo_mircera_dose',         label: 'ESA Dose' },
            { name: 'desidustat_dose',          label: 'Desidustat' },
            { name: 'iv_iron_product',          label: 'IV Iron Prod' },
            { name: 'iv_iron_dose',             label: 'IV Iron Dose', unit: 'mg' },
            { name: 'iv_iron_date',             label: 'IV Iron Date' },
            { name: 'vitamin_d_analog_dose',    label: 'Vit D Analogue' },
            { name: 'phosphate_binder_type',    label: 'PO4 Binder' },
            { name: 'phosphate_binder_dose_mg', label: 'PO4 Dose',     unit: 'mg' },
            { name: 'blood_transfusion_units',  label: 'Transfusion',  unit: 'units' },
            { name: 'transfusion_date',         label: 'Transfusion Date' },
        ]},
        { title: 'Dialysis Adequacy', fields: [
            { name: 'single_pool_ktv',  label: 'spKt/V' },
            { name: 'equilibrated_ktv', label: 'eKt/V' },
            { name: 'urr',              label: 'URR',   unit: '%' },
        ]},
    ];

    let html = '';
    let anyFilled = false;
    groups.forEach(group => {
        const filled = group.fields.filter(f => {
            const el = document.querySelector(`[name="${f.name}"]`);
            return el && el.value.trim() !== '';
        });
        if (!filled.length) return;
        anyFilled = true;
        const chips = filled.map(f => {
            const el   = document.querySelector(`[name="${f.name}"]`);
            const val  = el ? el.value.trim() : '';
            const unit = f.unit ? ` <span style="color:#94a3b8;font-size:0.75rem;">${f.unit}</span>` : '';
            return `<div class="review-chip"><strong>${f.label}:</strong> ${val}${unit}</div>`;
        }).join('');
        html += `<div class="review-group"><div class="review-group-head">${group.title}</div><div class="review-chips">${chips}</div></div>`;
    });

    container.innerHTML = anyFilled
        ? html
        : '<div class="review-empty">No values entered yet — go back to fill in the form sections.</div>';
}

/* ── Event binding ───────────────────────────────────────────────────────── */

function wizBindListeners() {
    Object.entries(WIZ_REQUIRED).forEach(([s, fields]) => {
        fields.forEach(name => {
            const el = document.querySelector(`[name="${name}"]`);
            if (!el) return;
            el.addEventListener('input', () => {
                if (wizStep !== parseInt(s)) return;
                const ok  = wizCheckRequired(parseInt(s));
                const btn = document.getElementById('btn-wiz-next');
                if (btn) btn.disabled = !ok;
                const hint = document.getElementById('wiz-req-hint');
                if (hint) hint.style.display = ok ? 'none' : 'block';
                if (el.value.trim()) {
                    el.style.borderColor     = '';
                    el.style.backgroundColor = '';
                }
            });
        });
    });

    document.querySelectorAll('.wizard-step input, .wizard-step select, .wizard-step textarea').forEach(el => {
        el.addEventListener('change', () => wizSaveStep(wizStep));
    });
}

/* ── Unsaved-data tracking ───────────────────────────────────────────────── */

let formDirty   = false;
let isRestoring = false;

document.querySelector('form')?.addEventListener('submit', () => { formDirty = false; });

window.addEventListener('beforeunload', e => {
    wizSaveStep(wizStep);
    if (formDirty) { e.preventDefault(); e.returnValue = ''; }
});

function bindDirtyTracking() {
    document.querySelectorAll(
        'form input:not([type=hidden]):not([readonly]), form select, form textarea'
    ).forEach(el => {
        el.addEventListener('input',  () => { if (!isRestoring) formDirty = true; });
        el.addEventListener('change', () => { if (!isRestoring) formDirty = true; });
    });
}

/* ── Init ────────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
    // Read the sessionStorage key injected by Jinja into the form's data attribute
    const form = document.querySelector('form');
    WIZ_SS_KEY = form ? (form.dataset.wizKey || 'hd_wiz_unknown') : 'hd_wiz_unknown';

    const isOnError = form ? form.dataset.formError === '1' : false;

    wizBindListeners();

    // Restore session data with dirty-tracking paused
    isRestoring = true;
    wizRestoreAll(isOnError);
    isRestoring = false;

    if (isOnError) {
        wizStep = WIZ_TOTAL;
        for (let s = 1; s < WIZ_TOTAL; s++) wizDone.add(s);
    }

    wizUpdateUI();

    if (isOnError) {
        const banner = document.getElementById('form-error-banner');
        if (banner) setTimeout(() => banner.scrollIntoView({ behavior: 'smooth', block: 'center' }), 200);
        setTimeout(() => {
            document.querySelectorAll('.wizard-step input[name]').forEach(inp => {
                if (inp.value && typeof validate === 'function') validate(inp.name);
            });
        }, 150);
    }

    // Month picker with dirty check
    const monthPicker = document.getElementById('month-picker-input');
    if (monthPicker) {
        monthPicker.addEventListener('change', function() {
            if (formDirty && !confirm('You have unsaved changes. Discard and change month?')) {
                this.value = this.dataset.current;
                return;
            }
            formDirty = false;
            location.href = '/entry/' + this.dataset.patientId + '?month=' + this.value;
        });
    }

    document.querySelectorAll('a[data-nav-link]').forEach(link => {
        link.addEventListener('click', e => {
            if (formDirty && !confirm('You have unsaved changes. Discard and navigate away?')) {
                e.preventDefault();
            }
        });
    });

    // Now bind dirty tracking — after restore is complete, no race condition
    bindDirtyTracking();

    // Mobile: hide action bar when virtual keyboard is open
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => {
            const actions = document.querySelector('.wizard-actions');
            if (actions) {
                actions.style.display = window.visualViewport.height < window.innerHeight * 0.75 ? 'none' : '';
            }
        });
    }

    // Success toast for ?saved=1 redirects
    if (new URLSearchParams(window.location.search).get('saved') === '1') {
        const toast = document.createElement('div');
        toast.textContent = '✅ Record saved. Next patient loaded.';
        toast.style.cssText = 'position:fixed;top:24px;right:24px;background:#10b981;color:#fff;padding:12px 20px;border-radius:12px;font-size:0.9rem;font-weight:600;z-index:1000;box-shadow:0 10px 25px rgba(0,0,0,0.1);animation:slideDown 0.3s ease-out;';
        document.body.appendChild(toast);
        setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.5s'; setTimeout(() => toast.remove(), 500); }, 3000);
    }
});
