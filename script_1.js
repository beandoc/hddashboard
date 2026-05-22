
    // ── Sticky Header Band Toggle ──
    window.addEventListener('scroll', () => {
        const header = document.querySelector('.profile-header');
        const band = document.getElementById('patientStickyBand');
        if (header && band) {
            const headerBottom = header.offsetTop + header.offsetHeight;
            if (window.scrollY > headerBottom) {
                band.classList.add('visible');
            } else {
                band.classList.remove('visible');
            }
        }
    });

    // ── Hb & ESA Trend Chart ─────────────────────────────────────────────────
    
    (function () {
        const labels = null;
        const hbData = null;
        const esaData = null;
        Plotly.newPlot('profileTrendChart', [
            {
                x: labels, y: hbData,
                name: 'Hemoglobin (g/dL)',
                type: 'scatter', mode: 'lines+markers',
                yaxis: 'y1',
                line: { color: '#0ea5e9', width: 3, shape: 'spline' },
                fill: 'tozeroy', fillcolor: 'rgba(14,165,233,0.08)',
                marker: { size: 7, color: '#fff', line: { color: '#0ea5e9', width: 2.5 } },
                connectgaps: true,
                hovertemplate: '%{x}<br>Hb: <b>%{y} g/dL</b><extra></extra>'
            },
            {
                x: labels, y: esaData,
                name: 'ESA Weekly Dose (Units)',
                type: 'scatter', mode: 'lines+markers',
                yaxis: 'y2',
                line: { color: '#ef4444', width: 2, dash: 'dot' },
                marker: { size: 5 },
                connectgaps: true,
                hovertemplate: '%{x}<br>ESA: <b>%{y} U/wk</b><extra></extra>'
            }
        ], {
            margin: { t: 30, r: 70, b: 50, l: 55 },
            legend: { orientation: 'h', y: 1.12, font: { family: 'Inter', size: 12 } },
            hovermode: 'x unified',
            xaxis: { showgrid: false, tickfont: { family: 'Inter', size: 11 } },
            yaxis: {
                title: { text: 'Hb (g/dL)', font: { family: 'Inter', size: 12, color: '#0ea5e9' } },
                range: [6, 16], dtick: 1,
                tickfont: { color: '#0ea5e9' }
            },
            yaxis2: {
                title: { text: 'ESA Dose (Units)', font: { family: 'Inter', size: 12, color: '#ef4444' } },
                overlaying: 'y', side: 'right', rangemode: 'tozero',
                tickfont: { color: '#ef4444' }, showgrid: false
            },
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { family: 'Inter' }
        }, { responsive: true, displayModeBar: false });
    })();
    

    // ── Weight / Albumin / IDWG Chart ────────────────────────────────────────
    
    (function () {
        const labels   = null;
        const wtData   = null;
        const albData  = null;
        const idwgRaw  = null;
        const hasIdwg  = idwgRaw.some(v => v !== null);

        const traces = [
            {
                x: labels, y: wtData,
                name: 'Prescribed Dry Weight (kg)',
                type: 'scatter', mode: 'lines+markers',
                yaxis: 'y1',
                line: { color: '#7c3aed', width: 3, shape: 'spline' },
                fill: 'tozeroy', fillcolor: 'rgba(124,58,237,0.06)',
                marker: { size: 6 },
                connectgaps: true,
                hovertemplate: '%{x}<br>Dry Wt: <b>%{y} kg</b><extra></extra>'
            },
            {
                x: labels, y: albData,
                name: 'Albumin (g/dL)',
                type: 'scatter', mode: 'lines+markers',
                yaxis: 'y2',
                line: { color: '#10b981', width: 3, shape: 'spline' },
                marker: { size: 6 },
                connectgaps: true,
                hovertemplate: '%{x}<br>Albumin: <b>%{y} g/dL</b><extra></extra>'
            }
        ];

        if (hasIdwg) {
            traces.push({
                x: labels, y: idwgRaw,
                name: 'Avg IDWG (kg)',
                type: 'scatter', mode: 'lines+markers',
                yaxis: 'y3',
                line: { color: '#f59e0b', width: 2, dash: 'dashdot' },
                marker: { size: 5, symbol: 'triangle-up' },
                connectgaps: true,
                hovertemplate: '%{x}<br>IDWG: <b>%{y} kg</b>%{customdata}<extra></extra>',
                customdata: idwgRaw.map(v => v > 2.5 ? ' ⚠️' : '')
            });
        }

        const layout = {
            margin: { t: 30, r: 100, b: 50, l: 65 },
            legend: { orientation: 'h', y: 1.12, font: { family: 'Inter', size: 11 } },
            hovermode: 'x unified',
            xaxis: { showgrid: false, tickfont: { family: 'Inter', size: 11 } },
            yaxis: {
                title: { text: 'Dry Weight (kg)', font: { color: '#7c3aed', size: 12 } },
                tickfont: { color: '#7c3aed' }
            },
            yaxis2: {
                title: { text: 'Albumin (g/dL)', font: { color: '#10b981', size: 12 } },
                overlaying: 'y', side: 'right', range: [2, 5],
                tickfont: { color: '#10b981' }, showgrid: false
            },
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { family: 'Inter' }
        };
        if (hasIdwg) {
            layout.yaxis3 = {
                title: { text: 'IDWG (kg)', font: { color: '#f59e0b', size: 11 } },
                overlaying: 'y', side: 'right', anchor: 'free', position: 1,
                range: [0, 6], tickfont: { color: '#f59e0b' }, showgrid: false
            };
        }
        Plotly.newPlot('weightStabilityChart', traces, layout, { responsive: true, displayModeBar: false });
    })();
    

    // ── KRCRw Trend Chart ────────────────────────────────────────────────────
    
    (function () {
        Plotly.newPlot('krcrTrendChart', [{
            x: null,
            y: null,
            name: 'KRCRw (mL/min)',
            type: 'scatter', mode: 'lines+markers',
            line: { color: '#059669', width: 4, shape: 'spline' },
            fill: 'tozeroy', fillcolor: 'rgba(5,150,105,0.10)',
            marker: { size: 7, color: '#059669' },
            connectgaps: true,
            hovertemplate: '%{x}<br>KRCRw: <b>%{y:.2f} mL/min</b><extra></extra>'
        }], {
            margin: { t: 20, r: 30, b: 45, l: 55 },
            showlegend: false,
            hovermode: 'x unified',
            xaxis: { showgrid: false, tickfont: { family: 'Inter', size: 11 } },
            yaxis: {
                title: { text: 'KRCRw (mL/min)', font: { family: 'Inter', size: 12 } },
                rangemode: 'tozero',
                gridcolor: 'rgba(0,0,0,0.06)', griddash: 'dot'
            },
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { family: 'Inter' }
        }, { responsive: true, displayModeBar: false });
    })();
    

    // ── Interim Lab Modal ────────────────────────────────────────────────────
    const UNITS = {
        hb: 'g/dL', potassium: 'mEq/L', calcium: 'mg/dL', phosphorus: 'mg/dL',
        albumin: 'g/dL', crp: 'mg/L', hba1c: '%', sodium: 'mmol/L',
        bicarbonate: 'mmol/L', urea: 'mg/dL', creatinine: 'mg/dL',
        ferritin: 'ng/mL', tsat: '%', ipth: 'pg/mL', vit_d: 'ng/mL'
    };

    function updateUnit(param) {
        document.getElementById('interimUnit').value = UNITS[param] || '';
    }

    function openInterimModal() {
        const d = document.getElementById('interimDate');
        if (d && !d.value) d.value = new Date().toISOString().slice(0, 10);
        const overlay = document.getElementById('interimModal');
        overlay.classList.add('open');
        // Focus first focusable element for accessibility
        const firstInput = overlay.querySelector('input, select, button');
        if (firstInput) firstInput.focus();
        // Trap focus within modal
        overlay.addEventListener('keydown', trapFocus);
        document.addEventListener('keydown', closeOnEsc);
    }

    function closeInterimModal() {
        const overlay = document.getElementById('interimModal');
        overlay.classList.remove('open');
        overlay.removeEventListener('keydown', trapFocus);
        document.removeEventListener('keydown', closeOnEsc);
        // Return focus to the trigger button safely
        const trigger = document.querySelector('[onclick="openInterimModal()"]');
        if (trigger) trigger.focus();
    }

    // Close on backdrop click
    document.getElementById('interimModal').addEventListener('click', function (e) {
        if (e.target === this) closeInterimModal();
    });

    function closeOnEsc(e) {
        if (e.key === 'Escape') closeInterimModal();
    }

    function trapFocus(e) {
        if (e.key !== 'Tab') return;
        const box = document.getElementById('interimModalBox');
        const focusable = box.querySelectorAll('button, input, select, textarea, [tabindex]:not([tabindex="-1"])');
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
            if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
            if (document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
    }

    // Auto-dismiss toast after animation completes
    const toast = document.getElementById('successToast');
    if (toast) setTimeout(() => toast.remove(), 4000);

    // ── CLINICAL REMINDER MODAL ──
    function openReminderModal() {
        document.getElementById('reminderModal').classList.add('open');
        document.getElementById('reminder_date').value = new Date().toISOString().slice(0, 10);
    }
    function closeReminderModal() {
        document.getElementById('reminderModal').classList.remove('open');
    }
