/* static/inventory/dashboard.js */
(function () {
  const log = (...a) => console.log('[charts]', ...a);
  const $ = (s, r = document) => r.querySelector(s);
  const on = (el, ev, cb) => el && el.addEventListener(ev, cb);

  // Register Chart.js parts (v3/v4)
  if (window.Chart && Chart.register) {
    const {
      CategoryScale, LinearScale, PointElement, LineElement,
      BarElement, Filler, Tooltip, Legend
    } = Chart;
    Chart.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Filler, Tooltip, Legend);
  }

  const BLUE = 'rgba(37,99,235,1)';
  const BLUE_FILL = 'rgba(37,99,235,.08)';
  const charts = {};

  function hasAnyValue(arr) {
    return Array.isArray(arr) && arr.some(v => (v ?? 0) !== 0);
  }

  function makeOptions(labels) {
    return {
      maintainAspectRatio: false,
      responsive: true,
      scales: {
        x: {
          type: 'category',
          ticks: {
            autoSkip: false,
            maxRotation: 0,
            callback: (idx) => labels?.[idx] ?? ''
          },
          grid: { display: false }
        },
        y: { beginAtZero: true, grace: '5%' }
      },
      plugins: { legend: { display: false } },
      elements: { point: { radius: 3 }, line: { tension: 0.25, borderWidth: 2 } }
    };
  }

  function renderLine(canvas, labels, data) {
    if (!canvas || !window.Chart) return;
    const id = canvas.id;
    charts[id]?.destroy();

    charts[id] = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels,
        datasets: [{ label: 'Value', data, borderColor: BLUE, backgroundColor: BLUE_FILL, fill: true }]
      },
      options: makeOptions(labels)
    });
  }

  async function getJSON(url) {
    const res = await fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' });
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      log('NON-JSON response for', url, '— likely a redirect to login.');
      return { ok: false, data: { labels: [], series: [] } };
    }
    return res.json();
  }

  async function loadSalesTrend() {
    const p = $('#sales-period')?.value || '7d';
    const m = $('#sales-metric')?.value || 'count';
    const url = `/inventory/api/sales-trend/?period=${encodeURIComponent(p)}&metric=${encodeURIComponent(m)}`;
    log('fetch', url);

    const payload = await getJSON(url);
    const labels = payload?.data?.labels ?? [];
    const series = payload?.data?.series?.[0]?.data ?? [];
    log('sales payload', { labels, series });

    const empty = $('#sales-empty');
    empty && (empty.style.display = hasAnyValue(series) ? 'none' : '');

    renderLine($('#salesTrendChart'), labels, series);
  }

  async function loadValueTrend() {
    const p = $('#value-period')?.value || '7d';
    const m = $('#value-metric')?.value || 'revenue';
    const url = `/inventory/api/value-trend/?metric=${encodeURIComponent(m)}&period=${encodeURIComponent(p)}`;
    log('fetch', url);

    const payload = await getJSON(url);
    const labels = payload?.data?.labels ?? [];
    const series = payload?.data?.series?.[0]?.data ?? [];
    log('value payload', { labels, series });

    const empty = $('#value-empty');
    empty && (empty.style.display = hasAnyValue(series) ? 'none' : '');

    renderLine($('#valueTrendChart'), labels, series);
  }

  document.addEventListener('DOMContentLoaded', () => {
    log('init');
    on($('#sales-period'), 'change', loadSalesTrend);
    on($('#sales-metric'), 'change', loadSalesTrend);
    on($('#value-period'), 'change', loadValueTrend);
    on($('#value-metric'), 'change', loadValueTrend);

    loadSalesTrend();
    loadValueTrend();
  });
})();
