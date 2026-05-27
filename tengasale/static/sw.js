/**
 * TengaSale Service Worker
 * Cache-first for static assets, network-first for HTML pages.
 * Offline fallback for navigation requests.
 */

const CACHE_NAME = "tengasale-v1";
const STATIC_CACHE = "tengasale-static-v1";

// Static assets to precache
const PRECACHE_ASSETS = [
  "/static/css/style.css",
  "/static/css/website.css",
  "/static/manifest.webmanifest",
];

// Offline fallback page (served for failed navigation requests)
const OFFLINE_URL = "/offline/";

// Install: precache static shell
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME && key !== STATIC_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Fetch strategy
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) return;

  // Skip Django admin, API endpoints, and media uploads
  if (
    url.pathname.startsWith("/admin/") ||
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/media/")
  ) {
    return;
  }

  // Cache-first for static assets (CSS, JS, images, fonts)
  if (
    url.pathname.startsWith("/static/") ||
    request.destination === "image" ||
    request.destination === "font" ||
    request.destination === "style" ||
    request.destination === "script"
  ) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(STATIC_CACHE).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // Network-first for HTML navigation — fall back to offline page
  if (request.mode === "navigate" || request.headers.get("accept")?.includes("text/html")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Cache successful HTML responses briefly
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() =>
          caches.match(request).then(
            (cached) => cached || caches.match(OFFLINE_URL) || new Response("Offline", { status: 503 })
          )
        )
    );
    return;
  }
});
