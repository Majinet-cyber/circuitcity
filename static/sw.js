// ---- Emajinet Service Worker (PWA) ----
// CRITICAL: Never cache HTML navigation responses
// HTML always goes to network (no cache fallback)
// This prevents stale templates from persisting after deploys
// 
// Static assets use Stale-While-Revalidate for performance
//
// VERSION changes on each deploy to bust old caches
const VERSION = 'emajinet-v2-20260114';
const STATIC_CACHE = `${VERSION}-static`;
const CDN_CACHE    = `${VERSION}-cdn`;
const OFFLINE_PAGE = '/offline/';

const PRECACHE_ASSETS = [
  '/',                                          // app shell
  '/home/',                                     // home/dashboard
  '/inventory/dashboard/',                      // main dashboard
  '/static/css/tokens.css',
  '/static/css/app.css',
  '/static/css/polish.css',
  '/static/css/mobile.css',
  '/static/js/app.js',
  '/static/manifest.webmanifest',
  '/static/favicon.ico',
  '/static/icons/icon-192.png',
  '/static/img/majn.png'
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

// Network-Only for HTML (NEVER cache HTML to prevent stale templates)
async function networkOnlyHtml(request) {
  try {
    const res = await fetch(request);
    // CRITICAL: Do NOT cache HTML responses
    // This ensures template changes are visible immediately after deploy
    return res;
  } catch (_) {
    // If network fails, try to serve offline page
    const offlinePage = await caches.match(OFFLINE_PAGE);
    if (offlinePage) return offlinePage;
    
    // Last resort: return a minimal error response
    return new Response(
      '<html><body><h1>Offline</h1><p>Please check your internet connection.</p></body></html>',
      { status: 503, headers: { 'Content-Type': 'text/html' } }
    );
  }
}

// Install: precache app shell and key assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(STATIC_CACHE);
      // Try to cache all assets, but don't fail if some don't exist yet
      try {
        await cache.addAll(PRECACHE_ASSETS);
      } catch (e) {
        console.warn('Some precache assets failed to load:', e);
        // Cache what we can individually
        for (const asset of PRECACHE_ASSETS) {
          try {
            await cache.add(asset);
          } catch (_) {
            console.warn('Failed to cache:', asset);
          }
        }
      }
    })()
  );
  self.skipWaiting();
});

// Activate: clean ALL old caches (cache busting)
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      // Only keep current version caches - delete ALL old caches
      const keep = new Set([STATIC_CACHE, CDN_CACHE]);
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => (keep.has(k) ? null : caches.delete(k))));
      // Take control of all clients immediately
      await self.clients.claim();
      console.log(`[SW] Activated version ${VERSION}, cleaned old caches`);
    })()
  );
});

// Fetch strategy router
self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (!isGET(request)) return; // never intercept POST/PUT/etc.

  const url = new URL(request.url);

  // CRITICAL: HTML & navigations -> NETWORK ONLY (never cache HTML)
  // This is the fix for stale template issues
  if (isDoc(request)) {
    event.respondWith(networkOnlyHtml(request));
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
