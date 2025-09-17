const NAME="cc-v1";
self.addEventListener("install", e=>{
  e.waitUntil(caches.open(NAME).then(c=>c.addAll([
    "/", "/static/css/mobile.css", "/static/js/mobile.js"
  ])));
});
self.addEventListener("fetch", e=>{
  e.respondWith(
    caches.match(e.request).then(r=> r || fetch(e.request).then(resp=>{
      const copy = resp.clone();
      caches.open(NAME).then(c=>c.put(e.request, copy));
      return resp;
    }).catch(()=> r))
  );
});
