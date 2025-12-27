# cc/middleware_seo.py
"""
SEO Middleware for Search Console Indexing Fix
================================================

Purpose: Fix Google Search Console "Page indexing" issues:
- "Indexed, though blocked by robots.txt"
- "Duplicate without user-selected canonical"

This middleware adds X-Robots-Tag headers to private app pages to prevent indexing
while allowing Google to crawl them to see the noindex directive.

Implementation: 2024-12-25
Reference: Search Console indexing fix task
"""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin


# Private app prefixes that should NEVER be indexed by search engines
# These are the same routes blocked in robots.txt
PRIVATE_PREFIXES = (
    "/login/",
    "/logout/",
    "/accounts/",
    "/password/",
    "/dashboard/",
    "/inventory/",
    "/sales/",
    "/reports/",
    "/admin/",
    "/hq/",
    "/tenants/",
    "/wallet/",
    "/billing/",
    "/simulator/",
    "/gym/",
    "/liquor/",
    "/pharmacy/",
    "/api/",
    "/verticals/",
    "/scan/",
    "/sell/",
    "/stock/",
    "/time/",
    "/layby/",
    "/support/",
    "/audit/",
    "/notifications/",
    "/backups/",
    "/debug/",
    "/exports/",
    "/imports/",
)


class SEONoIndexMiddleware(MiddlewareMixin):
    """
    Add X-Robots-Tag: noindex, nofollow, noarchive to private app pages.
    
    This solves the "Indexed, though blocked by robots.txt" issue by:
    1. Allowing Google to crawl these pages (so they can see the noindex directive)
    2. Telling Google explicitly NOT to index them via HTTP header
    3. Eventually Google will drop them from the index
    
    Why X-Robots-Tag header instead of meta tag?
    - Works for all content types (HTML, JSON, PDF, etc.)
    - Applied at HTTP level before rendering
    - More reliable than meta tags
    - Recommended by Google for programmatic control
    
    This does NOT affect user experience - only search engine behavior.
    """
    
    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """
        Add noindex header to private app pages.
        """
        try:
            # Get the request path
            path = getattr(request, 'path', '') or getattr(request, 'path_info', '') or '/'
            
            # Check if this is a private app page
            is_private = any(path.startswith(prefix) for prefix in PRIVATE_PREFIXES)
            
            if is_private:
                # Add X-Robots-Tag header to prevent indexing
                # noindex: Don't show in search results
                # nofollow: Don't follow links on this page
                # noarchive: Don't show cached version
                response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
        except Exception:
            # Never break the response if something goes wrong
            # SEO headers are non-critical for app functionality
            pass
        
        return response


class CanonicalURLMiddleware(MiddlewareMixin):
    """
    Enforce canonical domain and HTTPS for public pages.
    
    This solves the "Duplicate without user-selected canonical" issue by:
    1. Redirecting http → https (handled by Django's SECURE_SSL_REDIRECT)
    2. Redirecting www.emajinet.africa → emajinet.africa
    3. Normalizing trailing slashes (handled by Django's APPEND_SLASH)
    
    The canonical tag in templates will handle query string variations.
    
    IMPORTANT: This middleware runs AFTER SecurityMiddleware, so request.is_secure()
    will correctly detect HTTPS when SECURE_PROXY_SSL_HEADER is configured.
    We do NOT manually force http/https - that's SecurityMiddleware's job.
    """
    
    def process_request(self, request: HttpRequest):
        """
        Redirect www subdomain to non-www canonical domain.
        
        This middleware does NOT handle http → https redirects.
        That's handled by Django's SecurityMiddleware (SECURE_SSL_REDIRECT).
        We only handle www → non-www redirects.
        """
        try:
            # Get the host
            host = request.get_host().lower()
            
            # If request is to www subdomain, redirect to non-www
            if host.startswith('www.'):
                # Build the canonical URL without www
                canonical_host = host[4:]  # Remove 'www.'
                
                # Use request.is_secure() which will work correctly after SECURE_PROXY_SSL_HEADER
                # is set in production. Do NOT manually force http/https - let SecurityMiddleware
                # handle that to avoid redirect loops.
                protocol = 'https' if request.is_secure() else 'http'
                
                # Build full URL with path and query string
                path = request.get_full_path()
                canonical_url = f"{protocol}://{canonical_host}{path}"
                
                # 301 permanent redirect
                from django.http import HttpResponsePermanentRedirect
                return HttpResponsePermanentRedirect(canonical_url)
        except Exception:
            # Never break requests if something goes wrong
            pass
        
        return None


# Public marketing pages (prefix match) - these get UTM cleanup
PUBLIC_PAGE_PREFIXES = (
    "/landing/",
    "/pricing/",
    "/about/",
    "/contact/",
    "/docs/",
    "/",  # Root landing page (exact match handled separately)
)

# Tracking query parameters to strip (if ONLY these are present, redirect to clean URL)
TRACKING_PARAMS = frozenset({
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'gclid', 'fbclid', 'msclkid', 'ref'
})


class PublicQueryCleanupMiddleware(MiddlewareMixin):
    """
    Redirect public marketing pages with ONLY tracking parameters to clean canonical URLs.
    
    Purpose: Reduce Google crawl noise from UTM variants.
    Even with canonical tags, Google crawls tons of UTM combinations.
    This middleware 301-redirects to clean URLs to save crawl budget.
    
    Only applies to PUBLIC pages. Private app pages may use query params for filters/pagination.
    
    Example:
        /pricing/?utm_source=fb&utm_campaign=test → 301 /pricing/
        /inventory/?page=2 → no redirect (private page + functional param)
    
    Implementation: 2025-12-25
    """
    
    def process_request(self, request: HttpRequest):
        """
        Redirect public pages with only tracking params to clean canonical URL.
        """
        try:
            path = getattr(request, 'path', '') or getattr(request, 'path_info', '') or '/'
            
            # Only apply to GET requests
            if request.method != 'GET':
                return None
            
            # Check if this is a public page
            is_public = False
            if path == '/':
                is_public = True
            else:
                is_public = any(path.startswith(prefix) for prefix in PUBLIC_PAGE_PREFIXES)
            
            if not is_public:
                return None
            
            # Check if there are query parameters
            query_params = set(request.GET.keys())
            if not query_params:
                return None  # No params, nothing to clean
            
            # Check if ALL query params are tracking params
            if query_params.issubset(TRACKING_PARAMS):
                # All params are tracking params - redirect to clean URL
                # Use request.is_secure() which will work correctly after SECURE_PROXY_SSL_HEADER
                # is set in production. Do NOT manually force http/https.
                protocol = 'https' if request.is_secure() else 'http'
                host = request.get_host()
                clean_url = f"{protocol}://{host}{path}"
                
                # 301 permanent redirect to canonical clean URL
                from django.http import HttpResponsePermanentRedirect
                return HttpResponsePermanentRedirect(clean_url)
            
            # Has functional params (not just tracking) - don't redirect
            return None
            
        except Exception:
            # Never break requests if something goes wrong
            pass
        
        return None
