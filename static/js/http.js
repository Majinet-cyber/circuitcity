// static/js/http.js (or wherever your helper lives)
function getCSRFCookie() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export async function api(url, opts = {}) {
  const headers = new Headers(opts.headers || {});
  const token = getCSRFCookie();
  if (token) headers.set("X-CSRFToken", token);   // <- exact header name
  if (opts.body && !(opts.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");

  return fetch(url, {
    method: opts.method || "GET",
    credentials: "same-origin",                  // <- carry session cookies
    headers,
    body:
      opts.body && !(opts.body instanceof FormData)
        ? JSON.stringify(opts.body)
        : opts.body ?? null,
  });
}
