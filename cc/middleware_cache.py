# cc/middleware_cache.py
"""
Cache Control Middleware for authenticated HTML responses.

PROBLEM SOLVED:
Users often need hard refresh (Ctrl+Shift+R) to see correct UI after deploys.
Normal reload (F5) shows stale cached content from browser or proxy cache.

SOLUTION:
Set Cache-Control: no-store, no-cache, must-revalidate on all authenticated
HTML responses. This ensures the browser always fetches fresh HTML from the
server, which then references the correct hashed static assets.

The middleware is surgical - applies ONLY when ALL conditions are true:
- request.user exists and is authenticated
- response.status_code == 200 (OK)
- Content-Type starts with text/html
- request.path is NOT /static/*, /media/*, or /sw.js
- Response is NOT a download (Content-Disposition: attachment)

Headers set:
- Cache-Control: no-store, no-cache, must-revalidate, max-age=0
- Pragma: no-cache (HTTP/1.0 compatibility)
- Expires: 0 (HTTP/1.0 compatibility)
- Vary: Cookie (appended safely, for proper cache key discrimination)

IMPORTANT: This middleware MUST be positioned AFTER AuthenticationMiddleware
in settings.MIDDLEWARE so that request.user is properly initialized.
"""
from __future__ import annotations

from django.utils.cache import patch_vary_headers


class AuthenticatedHTMLNoCacheMiddleware:
    """
    Sets strict no-cache headers on HTML responses for authenticated users.

    This prevents browsers and proxies from caching authenticated pages,
    ensuring users always get the latest templates with correct static
    asset references after deployments.

    Applies ONLY when ALL conditions are true:
    - request.user exists and is authenticated
    - response.status_code == 200 (success, not redirect/error)
    - Content-Type starts with text/html
    - request.path is NOT excluded (static, media, sw.js, etc.)
    - Response is NOT a download (Content-Disposition: attachment)

    Headers set:
    - Cache-Control: no-store, no-cache, must-revalidate, max-age=0
    - Pragma: no-cache (HTTP/1.0 compatibility)
    - Expires: 0 (HTTP/1.0 compatibility)
    - Vary: Cookie (appended for correct cache discrimination)

    IMPORTANT: Must be positioned AFTER AuthenticationMiddleware in MIDDLEWARE.
    """

    # Paths to exclude from no-cache headers (static assets, service worker)
    EXCLUDE_PATH_PREFIXES = (
        "/static/",
        "/media/",
        "/favicon.ico",
        "/_/",  # Health checks
        "/api/",  # API endpoints (JSON, not HTML)
        "/admin/jsi18n/",  # Django admin JS
    )

    # Exact paths to exclude (not just prefixes)
    EXCLUDE_EXACT_PATHS = (
        "/sw.js",  # Service worker (has its own cache headers)
    )

    # Content types that should get no-cache headers
    HTML_CONTENT_TYPES = (
        "text/html",
        "application/xhtml+xml",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Skip if not authenticated
        if not self._is_authenticated(request):
            return response

        # Skip non-200 responses (redirects, errors, etc.)
        if response.status_code != 200:
            return response

        # Skip excluded path prefixes
        path = request.path
        if path.startswith(self.EXCLUDE_PATH_PREFIXES):
            return response

        # Skip exact excluded paths (like /sw.js)
        if path in self.EXCLUDE_EXACT_PATHS:
            return response

        # Skip if not HTML content type
        content_type = response.get("Content-Type", "")
        if not self._is_html_content_type(content_type):
            return response

        # Skip download responses (Content-Disposition: attachment)
        if "attachment" in response.get("Content-Disposition", ""):
            return response

        # Skip streaming responses (no body modification possible)
        if getattr(response, "streaming", False):
            return response

        # Set strict no-cache headers
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"

        # Add Vary: Cookie for proper cache discrimination (append, don't overwrite)
        patch_vary_headers(response, ["Cookie"])

        return response

    def _is_authenticated(self, request) -> bool:
        """Check if user is authenticated, safely handling missing attributes."""
        try:
            user = getattr(request, "user", None)
            if user is None:
                return False
            return getattr(user, "is_authenticated", False)
        except Exception:
            return False

    def _is_html_content_type(self, content_type: str) -> bool:
        """Check if content type is HTML (ignoring charset and other params)."""
        if not content_type:
            return False
        # Extract the MIME type (before semicolon if present)
        mime_type = content_type.split(";")[0].strip().lower()
        return mime_type in self.HTML_CONTENT_TYPES


class ServiceWorkerNoCacheMiddleware:
    """
    Sets no-cache headers specifically for service worker requests.

    Service workers MUST always be checked for updates on every page load.
    The browser will only check for updates if the sw.js file is not cached.

    This middleware ensures:
    - /sw.js always has no-cache headers
    - Service-Worker-Allowed header is set to "/" for proper scope
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only apply to service worker path
        if request.path == "/sw.js":
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
            response["Service-Worker-Allowed"] = "/"
            # Ensure correct content type
            if "javascript" not in response.get("Content-Type", ""):
                response["Content-Type"] = "application/javascript"

        return response


__all__ = ["AuthenticatedHTMLNoCacheMiddleware", "ServiceWorkerNoCacheMiddleware"]

