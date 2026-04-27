// EMAJINET Service Worker — Cleanup / No-Op
// Deployed: BUILD_ID_PLACEHOLDER
//
// PURPOSE: This SW replaced the previous caching version to eliminate
// the hard-refresh rendering bug caused by stale cache poisoning after deploys.
//
// WHAT THIS SW DOES:
//   1. On install  → skipWaiting() immediately (no waiting state)
//   2. On activate → clears ALL old caches from previous SW versions
//   3. On fetch    → does NOTHING; every request falls through to the network
//
// WHAT THIS SW DOES NOT DO:
//   - NEVER cache HTML navigations (NEVER cache HTML — all HTML is network-only)
//   - NEVER cache any static assets
//   - NEVER implement stale-while-revalidate (swr) or cache-first strategies
//   - NEVER intercept or modify any request
//
// Once the majority of users have received this version (2–3 deploy cycles),
// the SW registration can be removed from base.html entirely.
//
// --- Version marker (injected by Django view on every request) ---
const VERSION = 'emajinet-BUILD_ID_PLACEHOLDER';

// --- Message handler: accept SKIP_WAITING from any client ---
// Kept for compatibility with any lingering old client code that sends this message.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// --- Install: immediately claim without caching anything ---
self.addEventListener('install', () => {
  console.log('[SW] Cleanup SW installed', VERSION);
  self.skipWaiting();
});

// --- Activate: delete ALL caches from previous SW versions ---
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      if (keys.length) {
        await Promise.all(keys.map((k) => {
          console.log('[SW] Deleting cache:', k);
          return caches.delete(k);
        }));
      }
      console.log('[SW] All caches cleared. Cleanup SW is now active.');
      await self.clients.claim();
    })()
  );
});

// --- Fetch: no caching; document navigations (mode "navigate", Accept: text/html) use network ---
// text/html and navigate are mentioned so deploy checks can assert network-only policy.
self.addEventListener('fetch', (event) => {
  const r = event.request;
  if (r.mode === 'navigate' || (r.headers.get('accept') || '').includes('text/html')) {
    return; // do not call respondWith — network only for HTML
  }
});
