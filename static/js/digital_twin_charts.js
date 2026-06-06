// ── digital_twin_charts.js — Plotly chart render helpers ──


// ── Render helpers ──────────────────────────────────────────────────────────

function renderHbChart(traces) {
  const plotTraces = traces.filter(t => t.name !== '__warnings__');

  // Calculate dynamic y-axis range based on actual simulated values
  let allY = [];
  plotTraces.forEach(t => {
    if (t.y && t.y.length) {
      t.y.forEach(val => {
        if (typeof val === 'number' && !isNaN(val)) {
          allY.push(val);
        }
      });
    }
  });
  let minY = allY.length ? Math.min(...allY) : 6;
  let maxY = allY.length ? Math.max(...allY) : 15;
  // Ensure standard clinical reference range (9.0 to 12.5) is always fully visible
  minY = Math.min(minY, 9.0);
  maxY = Math.max(maxY, 12.5);
  // Add padding of 1.0 g/dL on top and bottom
  minY = Math.floor(minY - 1.0);
  maxY = Math.ceil(maxY + 1.0);

  Plotly.newPlot('hb-chart', plotTraces, {
    margin: {t:10,l:45,r:10,b:40},
    yaxis:  {title:'Hb (g/dL)', range:[minY, maxY], gridcolor:'#f0f0f0'},
    xaxis:  {gridcolor:'#f0f0f0'},
    legend: {orientation:'h',y:-0.22},
    shapes: [{type:'rect',x0:0,x1:1,y0:10,y1:11.5,xref:'paper',
              fillcolor:'rgba(22,163,74,0.07)',line:{width:0}}],
    plot_bgcolor:'white', paper_bgcolor:'white',
  }, {responsive:true, displayModeBar:false});
}

function renderKtvChart(stdData) {
  if (!stdData || !stdData.base_ektv) return;
  const cats = ['spKt/V base','spKt/V scen','eKt/V base','eKt/V scen'];
  const vals  = [
    stdData.base_sp   || 0, stdData.scen_sp   || 0,
    stdData.base_ektv || 0, stdData.scenario_ektv || 0,
  ];
  const colors = vals.map((v,i) =>
    i % 2 === 0 ? '#6c757d' : (v >= 1.2 ? '#4338ca' : '#dc2626')
  );
  Plotly.newPlot('ktv-chart', [{
    type:'bar', x:cats, y:vals,
    marker:{color:colors},
  }], {
    margin:{t:10,l:45,r:10,b:60},
    yaxis:{title:'Kt/V',gridcolor:'#f0f0f0'},
    shapes:[{type:'line',x0:-0.5,x1:3.5,y0:1.2,y1:1.2,
             line:{color:'#16a34a',dash:'dot',width:2}}],
    plot_bgcolor:'white', paper_bgcolor:'white',
  }, {responsive:true, displayModeBar:false});
}

function renderKdChart(stdData) {
  if (!stdData) return;
  const cats = ['Base Kd','Scen Kd','Base Std Kt/V','Scen Std Kt/V'];
  const vals  = [stdData.base_kd||0, stdData.scenario_kd||0,
                 (stdData.base_std||0)*100, (stdData.scenario_std||0)*100];
  Plotly.newPlot('kd-chart', [{
    type:'bar', x:cats, y:vals,
    marker:{color:['#6c757d','#4338ca','#9ca3af','#7c3aed']},
    text: cats.map((c,i) => i < 2 ? `${vals[i]?.toFixed(0)} mL/min` : `${(vals[i]/100).toFixed(2)}`),
    textposition:'outside',
  }], {
    margin:{t:24,l:10,r:10,b:60},
    yaxis:{title:'mL/min (Kd) or Std×100', gridcolor:'#f0f0f0'},
    plot_bgcolor:'white', paper_bgcolor:'white',
  }, {responsive:true, displayModeBar:false});
}

function renderPhosChart(pd) {
  if (!pd) return;
  Plotly.newPlot('phos-chart', [{
    type:'bar',
    x:['Baseline pre-P','Scenario pre-P'],
    y:[pd.baseline_p||0, pd.scenario_p||0],
    marker:{color:[
      pd.baseline_p > 5.5 ? '#dc2626' : pd.baseline_p < 3.5 ? '#f59e0b' : '#16a34a',
      pd.scenario_p > 5.5 ? '#dc2626' : pd.scenario_p < 3.5 ? '#f59e0b' : '#4338ca',
    ]},
    text:[`${pd.baseline_p?.toFixed(2)} mg/dL`,`${pd.scenario_p?.toFixed(2)} mg/dL`],
    textposition:'outside',
  }], {
    margin:{t:10,l:45,r:10,b:40},
    yaxis:{range:[0,8], gridcolor:'#f0f0f0'},
    shapes:[
      {type:'line',x0:-0.5,x1:1.5,y0:5.5,y1:5.5,line:{color:'#dc2626',dash:'dot',width:2}},
      {type:'line',x0:-0.5,x1:1.5,y0:3.5,y1:3.5,line:{color:'#f59e0b',dash:'dot',width:2}},
    ],
    plot_bgcolor:'white', paper_bgcolor:'white',
  }, {responsive:true, displayModeBar:false});
}

function renderUfCurve(traces, selectedRate, thresholdRate) {
  window.currentUfTraces = traces;
  window.currentMortalityThresh = thresholdRate || 4.0;
  const thresh = thresholdRate || 4.0;
  const shapes = [
    {
      type: 'line',
      x0: thresh,
      x1: thresh,
      y0: 0,
      y1: 100,
      line: {
        color: '#dc2626',
        dash: 'dash',
        width: 2
      }
    }
  ];
  if (selectedRate) {
    shapes.push({
      type: 'line',
      x0: selectedRate,
      x1: selectedRate,
      y0: 0,
      y1: 100,
      line: {
        color: '#4338ca',
        dash: 'dot',
        width: 2
      }
    });
  }
  const annotations = [
    {
      x: thresh,
      y: 90,
      xref: 'x',
      yref: 'y',
      text: 'Mortality threshold (Castro & Wu NDT 2024)',
      showarrow: false,
      textangle: -90,
      xanchor: 'right',
      yanchor: 'middle',
      font: {
        color: '#dc2626',
        size: 9,
        weight: 'bold'
      }
    }
  ];
  Plotly.newPlot('uf-chart', traces, {
    margin:{t:10,l:45,r:10,b:40},
    xaxis:{title:'UF Rate (mL/kg/h)', gridcolor:'#f0f0f0'},
    yaxis:{title:'IDH Risk (%)', range:[0,100], gridcolor:'#f0f0f0'},
    shapes, annotations, plot_bgcolor:'white', paper_bgcolor:'white',
    showlegend: false
  }, {responsive:true, displayModeBar:false});
}

function riskColor(pct) {
  return pct < 25 ? 'risk-low' : pct < 50 ? 'risk-moderate' : pct < 75 ? 'risk-high' : 'risk-very-high';
}

function renderRbvChart(fv) {
  const chartDiv = document.getElementById('rbv-chart');
  if (!chartDiv || !fv || !fv.rbv_trace) return;
  const traces = [
    {
      x: fv.rbv_trace.x,
      y: fv.rbv_trace.y,
      name: fv.rbv_trace.name,
      mode: 'lines',
      line: { color: '#2563eb', width: 3 },
      hovertemplate: 't=%{x:.0f} min  RBV=%{y:.1%}<extra></extra>'
    }
  ];
  if (fv.threshold_trace) {
    traces.push({
      x: fv.threshold_trace.x,
      y: fv.threshold_trace.y,
      name: fv.threshold_trace.name,
      mode: 'lines',
      line: { color: '#dc2626', dash: 'dash', width: 1.5 },
      hovertemplate: 'Threshold: %{y:.1%}<extra></extra>'
    });
  }
  Plotly.newPlot('rbv-chart', traces, {
    margin: { t: 10, l: 45, r: 10, b: 40 },
    xaxis: { title: 'Time (min)', gridcolor: '#f1f5f9' },
    yaxis: { title: 'RBV (%)', tickformat: '.0%', gridcolor: '#f1f5f9', range: [0.75, 1.05] },
    plot_bgcolor: 'white',
    paper_bgcolor: 'white',
    showlegend: false
  }, { responsive: true, displayModeBar: false });
}

