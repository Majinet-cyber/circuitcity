<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
/* ---------- Helpers ---------- */
const nf = new Intl.NumberFormat();

const $id   = (id)=>document.getElementById(id);
const show  = (id)=>$id(id)?.classList.remove('d-none');
const hide  = (id)=>$id(id)?.classList.add('d-none');
const cssVar=(name, fb)=> (getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fb);

const GRID_CLR = ()=> cssVar('--chart-grid', '#d8e3ff');
const BRAND    = ()=> cssVar('--cc-accent', '#3b82f6');

/* JSON fetch with legacy fallbacks (so it never returns the login HTML) */
async function fetchJSON(url, {legacy=[]}={}) {
  const doFetch = (u)=> fetch(u, {credentials:'same-origin', headers:{Accept:'application/json'}});
  const tryOnce = async (u)=>{
    const r = await doFetch(u);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const ct = (r.headers.get('content-type') || '').toLowerCase();
    if (!ct.includes('application/json')) throw new Error('Not JSON');
    return r.json();
  };
  try { return await tryOnce(url); }
  catch (e) {
    for (const alt of legacy) {
      try { return await tryOnce(alt); } catch(_) {}
    }
    throw e;
  }
}

/* Axis utilities */
function chooseMoneyStep(max){
  const choices = [100000,200000,250000,500000,1000000,2000000,5000000];
  for (const s of choices) if (max / s <= 6) return s;
  return Math.pow(10, Math.max(2, Math.ceil(Math.log10(max||1))-1));
}
function axisMoney(values){
  const m = Math.max(0, ...(values||[0]));
  const step = chooseMoneyStep(m || 100000);
  const niceMax = Math.max(step*2, Math.ceil((m || step*1.5)/step)*step);
  return {min:0, max:niceMax, stepSize:step};
}
function axisCount(values){
  const m = Math.max(0, ...(values||[0]));
  const nice = Math.max(1, Math.ceil(m));
  return {min:0, max:Math.max(1, nice), stepSize:1};
}

/* ---------- Sales Trend (left card) ---------- */
let invSalesChart = null;

async function loadInvSalesTrend(){
  const periodSel = $id('invTrendPeriod');
  const metricSel = $id('invTrendMetric');
  if (!periodSel || !metricSel) return;

  hide('invSalesEmpty'); hide('invSalesErr');

  const period = periodSel.value;           // '7d' | 'month'
  let metric   = metricSel.value;           // 'count' | 'amount'

  const getData = (m)=> fetchJSON(
    `/inventory/api/sales-trend/?period=${encodeURIComponent(period)}&metric=${encodeURIComponent(m)}`,
    { legacy:[`/inventory/api_sales_trend/?period=${encodeURIComponent(period)}&metric=${encodeURIComponent(m)}`] }
  );

  let resp;
  try { resp = await getData(metric); }
  catch (e) { show('invSalesErr'); $id('invSalesErr').textContent = `Sales trend error: ${e.message}`; return; }

  let labels = resp?.labels || [];
  let values = (resp?.values || []).map(v=>Number(v)||0);
  const isAmount = (metric === 'amount');
  const sign     = isAmount ? (resp?.currency?.sign || 'MK') : '';

  // if amount is all zero, automatically switch to count
  if (isAmount && labels.length && values.every(v=>v===0)) {
    try {
      const alt = await getData('count');
      const altVals = (alt?.values||[]).map(v=>Number(v)||0);
      if (alt?.labels?.length && altVals.some(v=>v>0)) {
        labels = alt.labels; values = altVals;
        metric = 'count'; metricSel.value = 'count';
      }
    } catch {}
  }

  const el = $id('invSalesTrend');
  invSalesChart?.destroy();

  if (!labels.length || values.every(v=>v===0)) { show('invSalesEmpty'); return; }

  const yCfg = (metric==='count') ? axisCount(values) : axisMoney(values);
  const blue = BRAND();

  invSalesChart = new Chart(el, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: metric==='count' ? 'Sales (count)' : `Sales (${sign})`,
        data: values,
        borderColor: blue,
        backgroundColor: blue + '20',
        fill: true,
        pointRadius: 2,
        tension: .35
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display:false } },
      animation: { duration: 500, easing: 'easeOutCubic' },
      scales: {
        x: {
          type: 'category',
          grid: { color: GRID_CLR() },
          ticks: { autoSkip:false, maxRotation:0 }
        },
        y: {
          min: yCfg.min, max: yCfg.max,
          grid: { color: GRID_CLR() },
          ticks: {
            stepSize: yCfg.stepSize,
            callback: (v)=> metric==='count' ? v : `${sign} ${nf.format(v)}`
          }
        }
      }
    }
  });
}

/* ---------- Top Models (right card) ---------- */
let invTopChart = null;

async function loadInvTopModels(){
  const pSel = $id('invTopPeriod');
  if (!pSel) return;

  hide('invTopEmpty'); hide('invTopErr');

  const period = pSel.value; // 'today' | 'month'
  let data;
  try {
    data = await fetchJSON(`/inventory/api/top-models/?period=${encodeURIComponent(period)}`,
            { legacy:[`/inventory/api_top_models/?period=${encodeURIComponent(period)}`] });
  } catch (e) {
    show('invTopErr'); $id('invTopErr').textContent = `Top models error: ${e.message}`;
    return;
  }

  const labels = data?.labels || [];
  const values = (data?.values || []).map(v=>Number(v)||0);

  invTopChart?.destroy();
  const el = $id('invTopModels');

  if (!labels.length || values.every(v=>v===0)) { show('invTopEmpty'); return; }

  const y = axisCount(values);
  const blue = BRAND();

  invTopChart = new Chart(el, {
    type: 'bar',
    data: { labels, datasets: [{ label:'Units', data:values, backgroundColor:blue, borderColor:blue }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display:false } },
      animation: { duration: 500, easing: 'easeOutCubic' },
      scales: {
        x: { type:'category', grid:{ display:false }, ticks:{ autoSkip:false, maxRotation:0 } },
        y: { min:y.min, max:y.max, grid:{ color:GRID_CLR() }, ticks:{ stepSize:y.stepSize } }
      }
    }
  });
}

/* ---------- Wire up ---------- */
$id('invTrendPeriod')?.addEventListener('change', loadInvSalesTrend);
$id('invTrendMetric')?.addEventListener('change', loadInvSalesTrend);
$id('invTopPeriod')?.addEventListener('change', loadInvTopModels);

(async function initList(){
  await Promise.allSettled([loadInvSalesTrend(), loadInvTopModels()]);
})();
</script>
