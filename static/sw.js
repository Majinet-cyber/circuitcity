// ---- Circuit City SW (network-first for pages, SWR for static) ----
// Bump VERSION on every deploy to force a refresh for all users.
const VERSION = 'cc-v3-2025-08-22';
const STATIC_CACHE = `${VERSION}-static`;
const PAGE_CACHE   = `${VERSION}-pages`;
const CDN_CACHE    = `${VERSION}-cdn`;

const PRECACHE_ASSETS = [
  '/',                        // app shell
  '/static/css/tokens.css',
  '/static/css/app.css',
  '/static/css/polish.css',
  '/static/js/app.js',
  '/static/manifest.webmanifest',
  '/static/favicon.ico'
];

// Simple helpers
const isGET = (req) => req.method === 'GET';
const sameOrigin = (url) => url.origin === self.location.origin;
const isDoc = (req) =>
  req.mode === 'navigate' ||
  (req.headers.get('accept') || '').includes('text/html');
const isStatic = (url) => sameOrigin(url) && url.pathname.startsWith('/static/');
const isCDN = (url) => /(^|\.)(?:jsdelivr\.net|gstatic\.com|googleapis\.com|unpkg\.com|bootstrapcdn\.com)$/.test(url.hostname);

// Put response in cache (ok or opaque)
async function cachePut(cacheName, request, response) {
  try {
    const resClone = response.clone();
    if (resClone.ok || resClone.type === 'opaque') {
      const cache = await caches.open(cacheName);
      await cache.put(request, resClone);
    }
  } catch (_) {
    // ignore cache put errors
  }
}

// Stale-While-Revalidate
async function swr(cacheName, request) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request, { ignoreVary: true });
  const fetchPromise = fetch(request).then((res) => {
    cachePut(cacheName, request, res);
    return res.clone();
  }).catch(() => null);

  // Return cached immediately if present, else wait for network
  return cached || (await fetchPromise) || cached || Response.error();
}

// Network-First (with cache fallback)
async function networkFirst(cacheName, request) {
  try {
    const res = await fetch(request);
    cachePut(cacheName, request, res);
    return res.clone();
  } catch (_) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request, { ignoreVary: true });
    return cached || caches.match('/') || Response.error();
  }
}

// Install: precache app shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keep = new Set([STATIC_CACHE, PAGE_CACHE, CDN_CACHE]);
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => (keep.has(k) ? null : caches.delete(k))));
      await self.clients.claim();
    })()
  );
});

// Fetch strategy router
self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (!isGET(request)) return; // never intercept POST/PUT/etc.

  const url = new URL(request.url);

  // HTML & navigations -> network first (so new deploys show immediately)
  if (isDoc(request)) {
    event.respondWith(networkFirst(PAGE_CACHE, request));
    return;
  }

  // Same-origin static -> SWR (fast with background refresh)
  if (isStatic(url)) {
    event.respondWith(swr(STATIC_CACHE, request));
    return;
  }

  // CDN libraries -> SWR into a separate cache (responses may be opaque)
  if (isCDN(url)) {
    event.respondWith(swr(CDN_CACHE, request));
    return;
  }

  // Default: try network, fall back to cache
  event.respondWith(
    (async () => {
      try {
        const res = await fetch(request);
        return res;
      } catch {
        const cached = await caches.match(request);
        return cached || Response.error();
      }
    })()
  );
});
