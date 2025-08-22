// v4 – network-first for HTML, safe static caching
const CACHE = 'cc-v4';
const STATIC_ASSETS = [
  '/static/css/app.css',
  '/static/css/polish.css',
  '/static/js/app.js',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
  // Chart.js can stay network since it’s cached by the CDN anyway
];

// install: pre-cache static only (NO HTML)
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC_ASSETS)));
});

// activate: take control immediately
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    // clean old caches
    const names = await caches.keys();
    await Promise.all(names.filter(n => n !== CACHE).map(n => caches.delete(n)));
    await self.clients.claim();
  })());
});

// helper: treat navigations/HTML specially
function isHTML(request) {
  return request.mode === 'navigate'
      || (request.headers.get('accept') || '').includes('text/html');
}

// fetch strategy:
// - HTML: network-first (fallback to cache/offline)
// - Static: cache-first (fallback to network, then cache)
self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Optional bypass: add ?nocache=1 to force network
  const url = new URL(req.url);
  const bypass = url.searchParams.has('nocache');

  if (isHTML(req) || bypass) {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req, { cache: 'no-store' });
        // Don’t cache HTML navigations to avoid staleness
        return fresh;
      } catch {
        const cached = await caches.match(req);
        return cached || new Response('Offline', { status: 503, statusText: 'Offline' });
      }
    })());
    return;
  }

  // Static assets: cache-first
  event.respondWith((async () => {
    const cached = await caches.match(req);
    if (cached) return cached;
    try {
      const resp = await fetch(req);
      const copy = resp.clone();
      const c = await caches.open(CACHE);
      c.put(req, copy);
      return resp;
    } catch (e) {
      return new Response('Offline', { status: 503 });
    }
  })());
});
