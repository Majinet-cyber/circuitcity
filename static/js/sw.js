// DEPRECATED: This service worker is no longer used.
// See /static/sw.js for the active service worker.
// This file is kept for backwards compatibility to allow unregistration.

// Immediately uninstall this SW and clear its caches
self.addEventListener('install', (e) => {
  console.log('[OLD SW] Deprecated SW installed - will clean up');
  self.skipWaiting();
});

self.addEventListener('activate', async (e) => {
  console.log('[OLD SW] Cleaning up deprecated SW caches');
  // Delete all caches from this old SW
  const keys = await caches.keys();
  await Promise.all(keys.filter(k => k.startsWith('cc-')).map(k => caches.delete(k)));
  await self.clients.claim();
});

// Never intercept fetch - let everything go to network
self.addEventListener('fetch', () => {
  // Do nothing - fallback to network
});
