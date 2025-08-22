const CACHE = 'cc-v1';
const ASSETS = [
  '/', '/static/css/app.css', '/static/js/app.js',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/chart.js'
];
self.addEventListener('install', e=> e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS))));
self.addEventListener('fetch', e=>{
  e.respondWith(
    caches.match(e.request).then(r=> r ||
      fetch(e.request).then(resp=>{
        const copy = resp.clone();
        caches.open(CACHE).then(c=> c.put(e.request, copy));
        return resp;
      }).catch(()=> caches.match('/'))
    )
  );
});
