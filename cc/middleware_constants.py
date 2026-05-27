"""
Shared middleware constants for bypass/allowlist paths.

These paths are excluded from various gating middleware:
- Tenant resolution redirect
- Subscription gate
- 2FA gate
- Force password change

This ensures critical resources like service workers, static files,
and favicon are always accessible without authentication or tenant context.
"""

# Paths that should bypass ALL gating middleware
# These must be accessible regardless of auth, tenant, subscription, or 2FA state
BYPASS_PREFIXES = (
    "/sw.js",  # Service worker (MUST return 200 for PWA functionality)
    "/manifest.json",  # PWA manifest
    "/manifest.webmanifest",  # PWA manifest alternate extension
    "/favicon.ico",  # Browser tab icon
    "/static/",  # Static files (CSS, JS, images)
    "/media/",  # Uploaded media
    "/health/",  # Health check endpoints
    "/healthz",  # Health check endpoints
    "/robots.txt",  # SEO robots file
    "/sitemap.xml",  # SEO sitemap
)
