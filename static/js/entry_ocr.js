/**
 * entry_ocr.js — OCR scan modal: upload, review, and apply lab values to the entry form.
 */

const OCR_RANGES = {
    hb:{min:3,max:20}, hct:{min:10,max:60}, serum_ferritin:{min:0,max:5000},
    tsat:{min:0,max:100}, serum_iron:{min:20,max:400}, tibc:{min:100,max:600},
    calcium:{min:5,max:15}, phosphorus:{min:1,max:15},
    alkaline_phosphate:{min:10,max:2000}, ipth:{min:0,max:3000},
    vit_d:{min:0,max:200}, serum_sodium:{min:110,max:165},
    serum_potassium:{min:2,max:8}, serum_bicarbonate:{min:10,max:42},
    serum_creatinine:{min:0.5,max:30}, serum_uric_acid:{min:1,max:20},
    pre_dialysis_urea:{min:10,max:500}, post_dialysis_urea:{min:5,max:200},
    albumin:{min:1,max:6}, prealbumin:{min:1,max:60},
    total_cholesterol:{min:50,max:500}, ldl_cholesterol:{min:20,max:400},
    hdl_cholesterol:{min:10,max:120}, triglycerides:{min:30,max:1000},
    total_protein:{min:3,max:10},
    bs_fasting:{min:40,max:500}, bs_pp:{min:50,max:600},
    wbc_count:{min:1,max:100},
    // platelet in lakh/cmm (1.5–4.5 normal; allow 0.1–15 for CKD range)
    platelet_count:{min:0.1,max:15},
    // neutrophil as differential %
    neutrophil_count:{min:20,max:95},
    hba1c:{min:3,max:18}, ast:{min:5,max:3000}, alt:{min:5,max:3000},
    crp:{min:0,max:500},
};

const OCR_FIELD_LABELS = {
    hb:'Hemoglobin', hct:'Hematocrit', serum_ferritin:'Ferritin', tsat:'TSAT',
    serum_iron:'Serum Iron', tibc:'TIBC', calcium:'Calcium', phosphorus:'Phosphorus',
    alkaline_phosphate:'ALP', ipth:'Parathyroid hormone(iPTH)', vit_d:'Vitamin D', serum_sodium:'Sodium',
    serum_potassium:'Potassium', serum_bicarbonate:'Bicarbonate',
    serum_creatinine:'Creatinine', serum_uric_acid:'Uric Acid',
    pre_dialysis_urea:'Pre-HD Urea', post_dialysis_urea:'Post-HD Urea',
    albumin:'Albumin', prealbumin:'Prealbumin', total_cholesterol:'Total Cholesterol',
    ldl_cholesterol:'LDL', hdl_cholesterol:'HDL', triglycerides:'Triglycerides',
    total_protein:'Total Protein',
    bs_fasting:'Blood Sugar Fasting', bs_pp:'Blood Sugar PP',
    wbc_count:'WBC / TLC', neutrophil_count:'Neutrophils %', platelet_count:'Platelets',
    hba1c:'HbA1c', ast:'AST (SGOT)', alt:'ALT (SGPT)', crp:'CRP',
};

const OCR_FIELD_UNITS = {
    hb:'g/dL', hct:'%', serum_ferritin:'ng/mL', tsat:'%', serum_iron:'µg/dL',
    tibc:'µg/dL', calcium:'mg/dL', phosphorus:'mg/dL', alkaline_phosphate:'U/L',
    ipth:'pg/mL', vit_d:'ng/mL', serum_sodium:'mEq/L', serum_potassium:'mEq/L',
    serum_bicarbonate:'mEq/L', serum_creatinine:'mg/dL', serum_uric_acid:'mg/dL',
    pre_dialysis_urea:'mg/dL', post_dialysis_urea:'mg/dL', albumin:'g/dL',
    prealbumin:'mg/dL', total_cholesterol:'mg/dL', ldl_cholesterol:'mg/dL',
    hdl_cholesterol:'mg/dL', triglycerides:'mg/dL', total_protein:'g/dL',
    bs_fasting:'mg/dL', bs_pp:'mg/dL',
    wbc_count:'×10³/µL', neutrophil_count:'%', platelet_count:'lakh/cmm',
    hba1c:'%', ast:'U/L', alt:'U/L', crp:'mg/L',
};

function _isOutOfRange(field, val) {
    const r = OCR_RANGES[field];
    if (!r) return false;
    const n = parseFloat(val);
    return isNaN(n) || n < r.min || n > r.max;
}

function _confidenceBadge(conf) {
    const map = {
        high:   { bg:'#dcfce7', cl:'#16a34a', ic:'verified' },
        medium: { bg:'#fef9c3', cl:'#ca8a04', ic:'help_outline' },
        low:    { bg:'#fee2e2', cl:'#dc2626', ic:'error_outline' },
    };
    const s = map[conf] || map.medium;
    return `<span style="display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:20px;font-size:0.7rem;font-weight:700;background:${s.bg};color:${s.cl};">
        <i class="material-icons" style="font-size:0.8rem;">${s.ic}</i>${conf || 'medium'}</span>`;
}

function updateSelectedCount() {
    const count = document.querySelectorAll('.ocr-check:checked').length;
    const el = document.getElementById('ocr_selected_count');
    if (el) el.textContent = count;
}

function selectAllOCR(v) {
    document.querySelectorAll('.ocr-check').forEach(cb => cb.checked = v);
    updateSelectedCount();
}

function closeOCRModal() {
    const modal = document.getElementById('ocr_modal');
    if (modal) modal.style.display = 'none';
    document.body.style.overflow = '';
}

function onRangeInput(input, field) {
    input.style.borderColor = _isOutOfRange(field, input.value) ? '#f97316' : '#6366f1';
}

function showOCRModal(data) {
    const fields = data.extracted_fields || {};
    const conf   = data.confidence || {};

    let subtitle = `${Object.keys(fields).length} field(s) found`;
    if (data.report_date) subtitle += ' · ' + data.report_date;
    if (data.report_type && data.report_type !== 'unknown') subtitle += ' · ' + data.report_type;
    const subtitleEl = document.getElementById('ocr_modal_subtitle');
    if (subtitleEl) subtitleEl.textContent = subtitle;

    const list = document.getElementById('ocr_fields_list');
    if (!list) return;

    if (Object.keys(fields).length === 0) {
        list.innerHTML = `<div style="padding:32px;text-align:center;color:#64748b;">
            <i class="material-icons" style="font-size:2.5rem;color:#cbd5e1;">search_off</i>
            <div style="margin-top:8px;font-weight:600;">No lab values found in this image.</div>
            <div style="font-size:0.82rem;margin-top:4px;">Try a clearer, well-lit photo of the full report page.</div>
        </div>`;
    } else {
        list.innerHTML = Object.entries(fields).map(([key, val]) => {
            const c   = conf[key] || 'medium';
            const oor = _isOutOfRange(key, val);
            const lbl = OCR_FIELD_LABELS[key] || key;
            const unit = OCR_FIELD_UNITS[key] ? ` (${OCR_FIELD_UNITS[key]})` : '';
            const existingInput = document.querySelector(`[name="${key}"]`);
            const alreadyFilled = existingInput && existingInput.value.trim() !== '';
            const autoCheck = c !== 'low' && !oor && !alreadyFilled;
            const rowBg    = oor ? '#fff7ed' : '#fff';
            const borderC  = oor ? '#fed7aa' : '#f1f5f9';
            const rangeR   = OCR_RANGES[key];
            const rangeHint = rangeR ? `Expected ${rangeR.min}–${rangeR.max}` : '';

            return `
            <div style="display:flex;align-items:flex-start;gap:12px;padding:12px 20px;border-bottom:1px solid ${borderC};background:${rowBg};">
                <div style="padding-top:3px;">
                    <input type="checkbox" class="ocr-check" data-field="${key}"
                        ${autoCheck ? 'checked' : ''} onchange="updateSelectedCount()"
                        style="width:18px;height:18px;accent-color:#6366f1;cursor:pointer;">
                </div>
                <div style="flex:1;">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px;">
                        <span style="font-weight:700;font-size:0.88rem;color:#1e293b;">${lbl}${unit}</span>
                        ${_confidenceBadge(c)}
                        ${oor ? '<span style="background:#fff7ed;color:#c2410c;font-size:0.7rem;font-weight:700;padding:2px 8px;border-radius:20px;border:1px solid #fed7aa;">⚠ Out of Range</span>' : ''}
                    </div>
                    <div style="display:flex;align-items:center;gap:10px;">
                        <input type="number" class="ocr-val" data-field="${key}" value="${val}" step="any"
                            style="width:110px;padding:7px 10px;border:1.5px solid ${oor?'#fbbf24':'#e2e8f0'};border-radius:8px;font-size:1rem;font-weight:700;color:#1e293b;"
                            oninput="onRangeInput(this,'${key}')">
                        <span style="font-size:0.78rem;color:#94a3b8;">${rangeHint}</span>
                    </div>
                    ${oor ? `<div style="margin-top:6px;display:flex;align-items:center;gap:4px;font-size:0.75rem;color:#c2410c;"><i class="material-icons" style="font-size:0.9rem;">report_problem</i>Value outside expected clinical range — verify before applying.</div>` : ''}
                    ${c === 'low' ? `<div style="margin-top:5px;font-size:0.75rem;color:#dc2626;"><i class="material-icons" style="font-size:0.9rem;vertical-align:middle;">visibility_off</i> Low AI confidence — verify from original report.</div>` : ''}
                </div>
            </div>`;
        }).join('');
    }

    updateSelectedCount();
    const modal = document.getElementById('ocr_modal');
    if (modal) modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
}

function applyOCRValues() {
    let count = 0;
    document.querySelectorAll('.ocr-check:checked').forEach(cb => {
        const field = cb.dataset.field;
        const valEl = document.querySelector(`.ocr-val[data-field="${field}"]`);
        const val   = valEl ? valEl.value : null;
        if (val === null || val === '') return;
        const formEl = document.querySelector(`[name="${field}"]`);
        if (!formEl) return;
        formEl.value = val;
        formEl.style.background    = '#ecfdf5';
        formEl.style.borderColor   = '#10b981';
        formEl.style.transition    = 'all 0.5s';
        setTimeout(() => { formEl.style.background = ''; formEl.style.borderColor = ''; }, 6000);
        count++;
    });
    closeOCRModal();

    // Recalculate Kt/V if urea values were applied
    if (typeof calculateKTV === 'function') calculateKTV();

    const t = document.createElement('div');
    t.innerHTML = `<div style="position:fixed;top:20px;right:20px;background:#fff;padding:16px 20px;border-radius:12px;box-shadow:0 10px 25px rgba(0,0,0,0.1);border-left:4px solid #10b981;display:flex;align-items:center;gap:12px;z-index:9999;">
        <i class="material-icons" style="color:#10b981;">check_circle</i>
        <div><div style="font-weight:700;color:#1e293b;">Applied ${count} value(s)</div>
        <div style="font-size:0.8rem;color:#64748b;">Highlighted green — verify then click Save.</div></div>
    </div>`;
    document.body.appendChild(t);
    setTimeout(() => document.body.removeChild(t), 4000);
}

async function handleOCRUpload(event, patientId) {
    const file = event.target.files[0];
    if (!file) return;

    const toast = document.createElement('div');
    toast.innerHTML = `
        <div style="position:fixed;top:20px;right:20px;background:#fff;padding:16px 20px;border-radius:12px;box-shadow:0 10px 25px rgba(0,0,0,0.1);border-left:4px solid #8b5cf6;display:flex;align-items:center;gap:12px;z-index:9999;">
            <div style="width:24px;height:24px;border:3px solid #e2e8f0;border-top-color:#8b5cf6;border-radius:50%;animation:spin 1s linear infinite;"></div>
            <div><div style="font-weight:700;color:#1e293b;">Gemini AI is scanning...</div>
            <div style="font-size:0.8rem;color:#64748b;">Extracting lab values from report</div></div>
        </div>`;
    document.body.appendChild(toast);

    const fd = new FormData();
    fd.append('file', file);
    fd.append('patient_id', patientId);

    try {
        const res  = await fetch('/ocr/extract-report', { method: 'POST', body: fd });
        const data = await res.json();
        document.body.removeChild(toast);
        if (data.error) { alert('OCR Error: ' + data.error); return; }
        showOCRModal(data);
    } catch(err) {
        document.body.removeChild(toast);
        alert('Network error during OCR. Ensure backend is running.');
        console.error(err);
    }
    event.target.value = '';
}
