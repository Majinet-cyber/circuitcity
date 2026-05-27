# cc/middleware_canonical_host.py
"""
Canonical Host Middleware - Single-direction www → apex redirect.

Purpose:
Fix redirect loops caused by competing canonicalization systems.
This middleware provides a single, consistent redirect: www.example.com → example.com.

Key design principles:
1. ONE direction only: www → apex (never apex → www)
2. Never fights with Render's host redirect settings
3. Safe no-op when CANONICAL_HOST is not set
4. Preserves full path and query string
5. Uses 301 permanent redirect for SEO

Implementation: 2026-01-15
Reference: Fix redirect loop and restore clean UI
"""
from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponsePermanentRedirect


class CanonicalHostMiddleware:
    """
    Redirect www.{canonical_host} → {canonical_host} (one-way only).

    This ensures a single canonical domain for:
    - SEO (no duplicate content across www and non-www)
    - Cookie consistency (session/CSRF work on both via domain cookie)
    - No redirect loops (only redirects in ONE direction)

    Configuration:
        CANONICAL_HOST = "emajinet.africa"  # The apex domain (no www)

    Behavior:
        - www.emajinet.africa → 301 → emajinet.africa (preserves path/query)
        - emajinet.africa → no redirect (already canonical)
        - *.onrender.com → no redirect (staging/dev)
        - localhost/127.0.0.1 → no redirect (local dev)

    IMPORTANT: This middleware must be placed AFTER SecurityMiddleware
    so that request.is_secure() correctly detects HTTPS behind proxies.
    """

    # Hosts to never redirect (local dev, staging, etc.)
    SKIP_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "testserver"})

    def __init__(self, get_response):
        self.get_response = get_response
        self.canonical_host = getattr(settings, "CANONICAL_HOST", None)

    def __call__(self, request: HttpRequest):
        """
        Process request and redirect www → apex if needed.
        """
        # Skip if no canonical host configured (local dev, testing)
        if not self.canonical_host:
            return self.get_response(request)

        try:
            # Get host without port
            host = request.get_host().split(":")[0].lower()
            canonical = self.canonical_host.lower()

            # Skip local dev hosts
            if host in self.SKIP_HOSTS:
                return self.get_response(request)

            # Skip .onrender.com (staging/dev)
            if host.endswith(".onrender.com"):
                return self.get_response(request)

            # Only redirect www.{canonical} → {canonical}
            www_host = f"www.{canonical}"
            if host == www_host:
                # Build canonical URL preserving protocol, path, and query
                protocol = "https" if request.is_secure() else "http"
                path = request.get_full_path()
                canonical_url = f"{protocol}://{canonical}{path}"
                return HttpResponsePermanentRedirect(canonical_url)

        except Exception:
            # Never break requests on middleware errors
            pass

        return self.get_response(request)


__all__ = ["CanonicalHostMiddleware"]

