/**
 * entry_calc.js — Medical calculations for the HD entry form.
 * Covers: ESA/EPO, Kt/V + URR, Phosphate Binder, Desidustat, Vitamin D.
 *
 * All structured data (ESA description text, Desidustat dose string, VitD dose string)
 * is stored in and read from data-* attributes on the relevant hidden inputs,
 * eliminating fragile regex parsing of human-readable strings.
 */

/* ── Cached DOM refs (resolved once after DOMContentLoaded) ── */
let _epoUnitsInput, _esaTypeSelect, _mcgInputGroup, _esaMcgInput, _esaFreqSelect;

document.addEventListener('DOMContentLoaded', () => {
    _epoUnitsInput  = document.getElementById('epo_weekly_units');
    _esaTypeSelect  = document.getElementById('esa_type');
    _mcgInputGroup  = document.getElementById('mcg_input_group');
    _esaMcgInput    = document.getElementById('esa_mcg');
    _esaFreqSelect  = document.getElementById('esa_frequency');

    // ESA
    if (_esaTypeSelect) {
        _esaTypeSelect.addEventListener('change', () => toggleESACalculator(true));
        restoreESAFields();
        toggleESACalculator(false);
    }
    if (_epoUnitsInput) {
        _epoUnitsInput.addEventListener('input', updateConversionHint);
        updateConversionHint();
    }

    // Desidustat
    const desidToggle = document.getElementById('desidustat_toggle');
    if (desidToggle) {
        if (desidToggle.value === 'Yes') toggleDesidustatSection();
    }

    // Vitamin D
    restoreVitDFields();

    // Phosphate binder
    calculateTotalBinder();

    // Kt/V — attach listeners + initial run
    ['pre_dialysis_urea', 'post_dialysis_urea', 'last_prehd_weight'].forEach(name => {
        const el = document.querySelector(`input[name="${name}"]`);
        if (el) el.addEventListener('input', calculateKTV);
    });
    calculateKTV();

    // TSAT — attach listeners + initial run
    ['serum_iron', 'tibc'].forEach(name => {
        const el = document.querySelector(`input[name="${name}"]`);
        if (el) el.addEventListener('input', calculateTSAT);
    });
    calculateTSAT();

    // Transfusion hint
    document.querySelector('input[name="hb"]')?.addEventListener('input', updateTransfusionHint);
    updateTransfusionHint();
});




/* ════════════════════════════════════════════════════════════════
   ESA / EPO Calculator
   ════════════════════════════════════════════════════════════════ */

const ESA_CONFIG = {
    'Epoetin Alfa':  { unit: 'IU',  placeholder: 'e.g. 4000', freqs: [{v:'3',t:'Thrice Weekly (TIW)'},{v:'2',t:'Twice Weekly'},{v:'1',t:'Weekly'},{v:'0.5',t:'Every 2 Weeks'},{v:'0.25',t:'Monthly'}] },
    'Epoetin Beta':  { unit: 'IU',  placeholder: 'e.g. 4000', freqs: [{v:'3',t:'Thrice Weekly (TIW)'},{v:'2',t:'Twice Weekly'},{v:'1',t:'Weekly'},{v:'0.5',t:'Every 2 Weeks'},{v:'0.25',t:'Monthly'}] },
    'Darbepoetin':   { unit: 'mcg', placeholder: 'e.g. 40',   freqs: [{v:'1',t:'Weekly'},{v:'0.5',t:'Every 2 Weeks'},{v:'0.25',t:'Monthly'}] },
    'Mircera (CERA)':{ unit: 'mcg', placeholder: 'e.g. 75',   freqs: [{v:'1',t:'Weekly'},{v:'0.7',t:'Once in every 10 days'},{v:'0.5',t:'Every 2 Weeks'},{v:'0.25',t:'Monthly'}] },
    'PEG-EPO (Pegylated EPO)': { unit: 'mcg', placeholder: 'e.g. 50', freqs: [{v:'0.7',t:'Once in every 10 days'},{v:'0.5',t:'Every 2 Weeks'},{v:'0.25',t:'Monthly'}] },
};

function toggleESACalculator(shouldReset = true) {
    if (!_esaTypeSelect || !_mcgInputGroup || !_epoUnitsInput) return;
    const type = _esaTypeSelect.value;
    const mcgLabel = document.getElementById('mcg_label');
    const conversionHint = document.getElementById('conversionHint');

    if (!type || type === 'None') {
        _mcgInputGroup.style.display = 'none';
        _epoUnitsInput.value = '0';
        const descInput = document.getElementById('epo_mircera_dose');
        if (descInput && shouldReset) descInput.value = '';
        if (conversionHint) conversionHint.style.display = 'none';
        return;
    }

    _mcgInputGroup.style.display = 'block';
    const cfg = ESA_CONFIG[type];
    if (!cfg) return;

    if (mcgLabel) mcgLabel.textContent = `Dose (${cfg.unit})`;
    if (_esaMcgInput) _esaMcgInput.placeholder = cfg.placeholder;

    const prevFreq = _esaFreqSelect.value;
    _esaFreqSelect.innerHTML = cfg.freqs.map(f => `<option value="${f.v}">${f.t}</option>`).join('');

    if (!shouldReset && prevFreq) {
        const match = Array.from(_esaFreqSelect.options).find(o => o.value === prevFreq);
        if (match) _esaFreqSelect.value = prevFreq;
    }
    if (shouldReset) calculateWeeklyUnits();
}

function calculateWeeklyUnits() {
    if (!_esaTypeSelect || !_esaMcgInput || !_esaFreqSelect || !_epoUnitsInput) return;
    const type = _esaTypeSelect.value;
    const dose = parseFloat(_esaMcgInput.value);
    const freq = parseFloat(_esaFreqSelect.value);
    const descInput = document.getElementById('epo_mircera_dose');
    const cfg = ESA_CONFIG[type];

    if (isNaN(dose) || !cfg) {
        _epoUnitsInput.value = '';
        if (descInput) descInput.value = '';
        return;
    }

    const freqText = _esaFreqSelect.options[_esaFreqSelect.selectedIndex]?.text || '';
    let weeklyUnits;
    if (type === 'Epoetin Alfa' || type === 'Epoetin Beta') {
        weeklyUnits = Math.round(dose * freq);
    } else {
        weeklyUnits = Math.round(dose * freq * 200);
    }
    _epoUnitsInput.value = weeklyUnits;

    const desc = `${type} ${dose}${cfg.unit} ${freqText}`;
    if (descInput) {
        descInput.value = desc;
        // Store structured data to avoid regex on restore
        descInput.dataset.esaType = type;
        descInput.dataset.esaDose = dose;
        descInput.dataset.esaFreq = _esaFreqSelect.value;
    }

    if (typeof validate === 'function') validate('epo_weekly_units');
    updateConversionHint();
}

function restoreESAFields() {
    const descInput = document.getElementById('epo_mircera_dose');
    if (!descInput || !_esaTypeSelect || !_esaMcgInput || !_esaFreqSelect) return;

    // Prefer structured data-* attrs (set by calculateWeeklyUnits)
    if (descInput.dataset.esaType) {
        _esaTypeSelect.value = descInput.dataset.esaType;
        toggleESACalculator(false);
        _esaMcgInput.value   = descInput.dataset.esaDose || '';
        _esaFreqSelect.value = descInput.dataset.esaFreq || '';
        calculateWeeklyUnits();
        return;
    }

    // Fallback: parse the text description (legacy records without data attrs)
    const desc = descInput.value.trim();
    if (!desc) return;

    const typeEntry = Object.keys(ESA_CONFIG).find(t => desc.startsWith(t));
    if (!typeEntry) return;
    _esaTypeSelect.value = typeEntry;
    toggleESACalculator(false);

    const doseMatch = desc.match(/(\d+(?:\.\d+)?)\s*(?:mcg|IU)/i);
    if (doseMatch) _esaMcgInput.value = doseMatch[1];

    const cfg = ESA_CONFIG[typeEntry];
    if (cfg) {
        const matched = cfg.freqs.find(f => desc.includes(f.t));
        if (matched) _esaFreqSelect.value = matched.v;
    }
    calculateWeeklyUnits();
}

function updateConversionHint() {
    const hint = document.getElementById('conversionHint');
    if (!hint || !_epoUnitsInput) return;
    const units = parseFloat(_epoUnitsInput.value);
    if (isNaN(units)) { hint.style.display = 'none'; return; }

    const suggested = units < 8000 ? '100 mg thrice a week' : units <= 16000 ? '125 mg thrice a week' : '150 mg thrice a week';
    hint.innerHTML = `<strong>Suggested Oxemia (Desidustat) Conversion:</strong> ${suggested}<br><em style="opacity:0.8">(Based on ${units} IU/week Epoetin equivalent)</em>`;
    hint.style.display = 'block';
    hint.style.cssText += 'color:#0284c7;background:#f0f9ff;padding:10px 12px;border-radius:8px;border-left:4px solid #0ea5e9;';
}

/* ════════════════════════════════════════════════════════════════
   Kt/V + URR Auto-Calculation (Daugirdas II)
   ════════════════════════════════════════════════════════════════ */

function calculateKTV() {
    const preUrea   = parseFloat(document.querySelector('input[name="pre_dialysis_urea"]')?.value);
    const postUrea  = parseFloat(document.querySelector('input[name="post_dialysis_urea"]')?.value);
    const preWeight = parseFloat(document.querySelector('input[name="last_prehd_weight"]')?.value);
    const ktvInput  = document.querySelector('input[name="single_pool_ktv"]');
    const eKtvInput = document.querySelector('input[name="equilibrated_ktv"]');
    const urrInput  = document.querySelector('input[name="urr"]');

    if (!(preUrea > 0 && postUrea > 0 && preUrea > postUrea)) {
        if (ktvInput) ktvInput.value = '';
        if (eKtvInput) eKtvInput.value = '';
        if (urrInput) urrInput.value = '';
        return;
    }

    const R = postUrea / preUrea;
    if (urrInput) { urrInput.value = ((1 - R) * 100).toFixed(1); }

    const weight = preWeight || 0;
    if (weight > 0 && ktvInput && R > 0.03) {
        try {
            const ktv = -Math.log(R - 0.03) + (4 - 3.5 * R) * (0 / weight);
            if (isFinite(ktv) && ktv > 0) {
                ktvInput.value  = ktv.toFixed(2);
                if (eKtvInput) eKtvInput.value = (0.945 * ktv + 0.04).toFixed(2);
            }
        } catch(e) { /* log silently */ }
    }
}

/* ════════════════════════════════════════════════════════════════
   Phosphate Binder Daily Dose
   ════════════════════════════════════════════════════════════════ */

function calculateTotalBinder() {
    const rows = document.querySelectorAll('.pb-med-row');
    let grandTotal = 0;
    const multipliers = { OD: 1, BD: 2, TDS: 3, QID: 4 };
    const details = [];

    rows.forEach(row => {
        const typeEl = row.querySelector('[name="phosphate_binder_type"]');
        const strengthEl = row.querySelector('[name="pb_strength"]');
        const freqEl = row.querySelector('[name="phosphate_binder_freq"]');
        if (!typeEl || !strengthEl || !freqEl) return;

        const type = typeEl.value;
        const strength = parseFloat(strengthEl.value) || 0;
        const freq = freqEl.value;

        if (type && strength > 0 && freq) {
            const mult = multipliers[freq] || 0;
            const dose = strength * mult;
            grandTotal += dose;
            details.push(`${strength} mg ${freq} of ${type}`);
        }
    });

    const totalInput = document.getElementById('pb_total');
    const hint = document.getElementById('pb_calc_hint');

    if (totalInput) {
        totalInput.value = grandTotal > 0 ? grandTotal : '';
    }

    if (hint) {
        if (grandTotal > 0) {
            hint.textContent = `Total Daily Dose: ${grandTotal} mg (${details.join(' + ')})`;
            hint.style.color = 'var(--primary)';
        } else {
            hint.textContent = '';
            hint.style.color = '';
        }
    }
}

/* ════════════════════════════════════════════════════════════════
   Desidustat (HIF-PHI)
   Uses data-mg and data-freq attributes on the hidden input
   to avoid regex parsing of the stored string.
   ════════════════════════════════════════════════════════════════ */

function toggleDesidustatSection() {
    const val   = document.getElementById('desidustat_toggle')?.value;
    const group = document.getElementById('desidustat_group');
    if (!group) return;

    const modGroup = document.getElementById('desidustat_mod_date_group');
    if (val === 'Yes') {
        group.style.display = 'block';
        if (modGroup) modGroup.style.display = 'block';
        restoreDesidustatFields();
    } else {
        group.style.display = 'none';
        if (modGroup) modGroup.style.display = 'none';
        const mgEl   = document.getElementById('desidustat_mg');
        const freqEl = document.getElementById('desidustat_freq');
        const modEl  = document.getElementById('desidustat_modified_at');
        if (mgEl)   mgEl.value   = '';
        if (freqEl) freqEl.value = '';
        if (modEl)  modEl.value  = '';
        syncDesidustatDose();
    }
}

function syncDesidustatDose() {
    const mg      = document.getElementById('desidustat_mg')?.value;
    const freq    = document.getElementById('desidustat_freq')?.value;
    const hidden  = document.getElementById('desidustat_dose');
    const preview = document.getElementById('desidustat_preview');
    if (!hidden) return;

    if (mg && freq) {
        const val = `${mg}mg ${freq}`;
        hidden.value      = val;
        hidden.dataset.mg   = mg;
        hidden.dataset.freq = freq;
        if (preview) preview.textContent = `Saving: "${val}"`;
    } else {
        hidden.value = '';
        delete hidden.dataset.mg;
        delete hidden.dataset.freq;
        if (preview) preview.textContent = '';
    }
}

function restoreDesidustatFields() {
    const hidden = document.getElementById('desidustat_dose');
    if (!hidden || !hidden.value) return;

    // Prefer structured data-* attrs
    if (hidden.dataset.mg) {
        const mgEl   = document.getElementById('desidustat_mg');
        const freqEl = document.getElementById('desidustat_freq');
        if (mgEl)   mgEl.value   = hidden.dataset.mg;
        if (freqEl) freqEl.value = hidden.dataset.freq || '';
        const preview = document.getElementById('desidustat_preview');
        if (preview) preview.textContent = `Current: "${hidden.value}"`;
        return;
    }

    // Fallback: parse stored string for legacy records
    const stored = hidden.value;
    const mgMatch = stored.match(/(\d+)\s*mg/);
    if (mgMatch) {
        const mgEl = document.getElementById('desidustat_mg');
        if (mgEl) { mgEl.value = mgMatch[1]; hidden.dataset.mg = mgMatch[1]; }
    }
    const freqEl = document.getElementById('desidustat_freq');
    if (freqEl) {
        let fv = '';
        if (/thrice|TIW/i.test(stored))       fv = 'Thrice a week (TIW)';
        else if (/twice|BD/i.test(stored))     fv = 'Twice a week (BD)';
        else if (/daily|OD/i.test(stored))     fv = 'Once daily (OD)';
        freqEl.value = fv;
        hidden.dataset.freq = fv;
    }
    const preview = document.getElementById('desidustat_preview');
    if (preview) preview.textContent = `Current: "${stored}"`;
}

/* ════════════════════════════════════════════════════════════════
   Vitamin D Analogue
   Uses data-vitd-type, data-vitd-count, data-vitd-freq on
   the hidden input to avoid regex on restore.
   ════════════════════════════════════════════════════════════════ */

function toggleVitDFields(shouldReset = true) {
    const select     = document.getElementById('vit_d_analogue_select');
    const calcFields = document.getElementById('vit_d_calcitriol_fields');
    if (!select) return;

    const isCalcitriol = select.value === 'Calcitriol 0.25 mcg';
    if (calcFields) calcFields.style.display = isCalcitriol ? 'flex' : 'none';
    if (shouldReset && isCalcitriol) {
        const countEl = document.getElementById('vit_d_tablet_count');
        const freqEl  = document.getElementById('vit_d_freq_select');
        if (countEl) countEl.value = '1';
        if (freqEl)  freqEl.value  = 'OD';
    }
    compileVitDValue();
}

function compileVitDValue() {
    const select  = document.getElementById('vit_d_analogue_select');
    const hidden  = document.getElementById('vitamin_d_analog_dose');
    const preview = document.getElementById('vit_d_preview');
    if (!select || !hidden) return;

    const val = select.value;
    if (!val) {
        hidden.value = '';
        delete hidden.dataset.vitdType;
        if (preview) preview.textContent = '';
        return;
    }

    let compiled = val;
    hidden.dataset.vitdType = val;
    if (val === 'Calcitriol 0.25 mcg') {
        const count = document.getElementById('vit_d_tablet_count')?.value || '1';
        const freq  = document.getElementById('vit_d_freq_select')?.value  || 'OD';
        compiled = `Calcitriol 0.25 mcg ${count} tab ${freq}`;
        hidden.dataset.vitdCount = count;
        hidden.dataset.vitdFreq  = freq;
    }
    hidden.value = compiled;
    if (preview) preview.textContent = `Saving: "${compiled}"`;
}

function restoreVitDFields() {
    const hidden = document.getElementById('vitamin_d_analog_dose');
    if (!hidden || !hidden.value) return;

    const select     = document.getElementById('vit_d_analogue_select');
    const countInput = document.getElementById('vit_d_tablet_count');
    const freqSelect = document.getElementById('vit_d_freq_select');
    const preview    = document.getElementById('vit_d_preview');
    const val        = hidden.value.trim();

    // Prefer structured data-* attrs
    if (hidden.dataset.vitdType) {
        if (select) select.value = hidden.dataset.vitdType;
        if (hidden.dataset.vitdType === 'Calcitriol 0.25 mcg') {
            if (countInput) countInput.value = hidden.dataset.vitdCount || '1';
            if (freqSelect) freqSelect.value = hidden.dataset.vitdFreq  || 'OD';
        }
        toggleVitDFields(false);
        return;
    }

    // Fallback: parse stored string for legacy records
    if (val.includes('Calcitriol 0.25 mcg')) {
        if (select) select.value = 'Calcitriol 0.25 mcg';
        const countMatch = val.match(/(\d+)\s*tab/);
        if (countMatch && countInput) countInput.value = countMatch[1];
        if (freqSelect) {
            freqSelect.value = val.includes('BD') ? 'BD' : val.includes('Alternate day') ? 'Alternate day' : 'OD';
        }
    } else if (val.includes('Calcirol 60,000 Units/week')) {
        if (select) select.value = 'Calcirol 60,000 Units/week';
    } else if (val.includes('Calcirol 60,000 Units/month')) {
        if (select) select.value = 'Calcirol 60,000 Units/month';
    } else {
        if (preview) preview.textContent = `Stored: "${val}"`;
        return;
    }
    toggleVitDFields(false);
}

/* ════════════════════════════════════════════════════════════════
   Transfusion Hint
   ════════════════════════════════════════════════════════════════ */

function updateTransfusionHint() {
    const units  = parseInt(document.getElementById('blood_transfusion_units')?.value);
    const hintEl = document.getElementById('transfusion_hint');
    if (!hintEl) return;
    if (!units || units <= 0) { hintEl.style.display = 'none'; return; }

    const hbInput = document.querySelector('input[name="hb"]');
    const rawHb   = parseFloat(hbInput?.value);
    let note = '';
    if (!isNaN(rawHb)) {
        const corrected = Math.max(rawHb - units, 5.0).toFixed(1);
        note = ` Entered Hb: <strong>${rawHb} g/dL</strong> → Endogenous (corrected): <strong>${corrected} g/dL</strong>.`;
    }
    hintEl.innerHTML = `<strong>⚠ Transfusion Confounding Detected:</strong> ${units} unit(s) transfused.${note} The analytics engine will use the corrected Hb for ERI and Hb trajectory.`;
    hintEl.style.display = 'block';
}

/* ── TSAT Auto-Calculation ── */
function calculateTSAT() {
    const iron = parseFloat(document.querySelector('input[name="serum_iron"]')?.value);
    const tibc = parseFloat(document.querySelector('input[name="tibc"]')?.value);
    const tsatInput = document.querySelector('input[name="tsat"]');

    if (tsatInput) {
        if (iron > 0 && tibc > 0) {
            const tsat = (iron / tibc) * 100;
            if (isFinite(tsat) && tsat >= 0) {
                tsatInput.value = tsat.toFixed(2);
                return;
            }
        }
        tsatInput.value = '';
    }
}

