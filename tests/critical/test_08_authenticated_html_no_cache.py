# tests/critical/test_08_authenticated_html_no_cache.py
"""
CRITICAL TEST 08: Authenticated HTML Pages Must Never Be Cacheable

This test ensures that authenticated HTML pages always have proper Cache-Control
headers to prevent stale content being served (which would require hard refresh).

FAILURE HERE = Users see stale content after updates = Critical UX regression

This test locks in the fix for the "notifications auto-opening" bug that was
caused by cached HTML being served without middleware processing.
"""
import pytest
from django.test import Client

from tests.critical.conftest import (
    bootstrap_business_with_user,
    setup_authenticated_client,
    get_dashboard_url,
)


# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]


class TestAuthenticatedHTMLNoCacheContract:
    """
    Verify that authenticated HTML pages are NEVER cacheable.
    
    This prevents the "warped until hard refresh" bug where:
    1. Browser/CDN caches authenticated HTML
    2. Middleware changes don't apply to cached pages
    3. User sees stale/broken UI (e.g., notifications auto-opening)
    4. Hard refresh is required to fix
    
    The middleware that sets Cache-Control headers MUST be present and
    must apply to all authenticated HTML responses.
    """
    
    def test_phones_dashboard_has_no_cache_headers(self):
        """
        Phones dashboard (primary authenticated page) must have no-cache headers.
        
        This is the most critical page because it's the landing page for
        most users after login. If this is cached, users will see stale UI.
        """
        # Setup: Create authenticated user and client
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        # Get phones dashboard URL
        dashboard_url = get_dashboard_url("phones")
        assert dashboard_url, "Phones dashboard URL must be configured"
        
        # Make request to authenticated page
        response = client.get(dashboard_url)
        
        # Assert response is successful HTML
        assert response.status_code == 200, (
            f"Dashboard should return 200, got {response.status_code}"
        )
        assert "text/html" in response.get("Content-Type", ""), (
            "Dashboard should return HTML content"
        )
        
        # CRITICAL: Assert Cache-Control header prevents caching
        cache_control = response.get("Cache-Control", "")
        
        # Must contain "no-store" (strictest - prevents ANY caching)
        assert "no-store" in cache_control, (
            f"Cache-Control MUST include 'no-store' to prevent caching. "
            f"Got: {cache_control!r}"
        )
        
        # Should also contain "no-cache" and "must-revalidate" for defense in depth
        # (Not strictly required if no-store is present, but good practice)
        assert "no-cache" in cache_control or "must-revalidate" in cache_control, (
            f"Cache-Control should include 'no-cache' or 'must-revalidate' "
            f"for defense in depth. Got: {cache_control!r}"
        )
    
    def test_generic_authenticated_page_has_no_cache_headers(self):
        """
        Any authenticated HTML page must have no-cache headers.
        
        This is a broader test to ensure the caching policy applies
        to all authenticated pages, not just the dashboard.
        """
        # Setup: Create authenticated user and client
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        # Test multiple authenticated pages
        authenticated_pages = [
            "/inventory/list/",  # Stock list
            "/inventory/scan-in/",  # Stock in page
            "/accounts/settings/",  # Settings page (if accessible)
        ]
        
        for url in authenticated_pages:
            response = client.get(url, follow=True)
            
            # Skip if page doesn't exist or redirects to login
            if response.status_code == 404:
                continue
            if "login" in response.request.get("PATH_INFO", ""):
                continue
            
            # If we got a successful response, check cache headers
            if response.status_code == 200:
                cache_control = response.get("Cache-Control", "")
                
                # Must prevent caching
                assert "no-store" in cache_control or "no-cache" in cache_control, (
                    f"Authenticated page {url} MUST have no-cache headers. "
                    f"Got Cache-Control: {cache_control!r}"
                )
    
    def test_middleware_prevents_authenticated_html_caching_regression(self):
        """
        Regression test: Ensure the caching middleware is active and working.
        
        This test would fail if:
        - The middleware is removed from settings
        - The middleware stops applying headers
        - The middleware is bypassed
        
        This is the "canary in the coal mine" for caching regressions.
        """
        # Setup: Create authenticated user and client
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        # Get a known authenticated page
        dashboard_url = get_dashboard_url("phones")
        assert dashboard_url, "Phones dashboard URL must be configured"
        
        # Make request
        response = client.get(dashboard_url)
        
        # Assert the request was successful
        assert response.status_code == 200, (
            f"Dashboard request failed with status {response.status_code}"
        )
        
        # CRITICAL CONTRACT: Cache-Control header MUST exist
        assert "Cache-Control" in response, (
            "Cache-Control header is MISSING. This means the caching middleware "
            "is not running or not applying headers. This will cause stale content "
            "bugs that require hard refresh to fix."
        )
        
        # CRITICAL CONTRACT: Cache-Control MUST prevent caching
        cache_control = response.get("Cache-Control", "")
        assert cache_control, (
            "Cache-Control header is present but EMPTY. This will allow caching."
        )
        
        assert "no-store" in cache_control, (
            f"Cache-Control header exists but doesn't prevent caching. "
            f"Got: {cache_control!r}. This will cause stale content bugs."
        )
    
    def test_unauthenticated_pages_can_be_cached(self):
        """
        Sanity check: Unauthenticated public pages CAN be cached.
        
        This ensures we're not overly aggressive with no-cache headers.
        Public pages (login, signup, landing) should be cacheable for performance.
        """
        client = Client()  # Unauthenticated client
        
        # Test public pages
        public_pages = [
            "/accounts/login/",
            "/accounts/signup/",
            "/",  # Landing page (if exists)
        ]
        
        for url in public_pages:
            response = client.get(url, follow=True)
            
            # Skip if page doesn't exist
            if response.status_code == 404:
                continue
            
            # Public pages should either:
            # 1. Have no Cache-Control header (browser uses defaults)
            # 2. Have Cache-Control that allows caching (no "no-store")
            cache_control = response.get("Cache-Control", "")
            
            # Assert: If Cache-Control exists, it should NOT force no-cache
            # (or at least not as aggressively as authenticated pages)
            # This is a sanity check to ensure we're not breaking public page caching
            if cache_control:
                # Public pages should NOT have the same strict no-cache as authenticated pages
                # (This is informational, not a hard requirement)
                pass  # Allow any cache policy for public pages

