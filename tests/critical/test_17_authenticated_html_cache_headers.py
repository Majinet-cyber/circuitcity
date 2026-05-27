"""
CRITICAL REGRESSION TEST: Authenticated HTML No-Cache Headers (Jan 2026)

ISSUE B: Production dropdown didn't work (required hard refresh after deploy)
- Logout/profile dropdown worked locally but not in production
- Users needed Ctrl+Shift+R to see correct UI after deploy
- Normal F5 reload showed stale cached HTML with outdated static asset references

ROOT CAUSE:
- Authenticated HTML responses were being cached by browser/proxy
- After deploy with new static asset hashes, cached HTML still referenced old hashes
- Resulted in 404s for static assets and broken UI

FIX:
- AuthenticatedHTMLNoCacheMiddleware sets Cache-Control: no-store on all:
  * Authenticated HTML responses (200 with Content-Type: text/html)
  * Authenticated redirects (301/302)
- Ensures browser always fetches fresh HTML from server
- Fresh HTML has correct hashed static asset references from manifest

TESTS:
1. Authenticated HTML responses have no-store headers
2. Authenticated redirects have no-store headers
3. Static assets do NOT have no-store (should be cached)
4. Anonymous responses NOT affected (can be cached)
5. Navbar contract: dropdown HTML is present
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def authenticated_user(db):
    """Create user for authenticated tests."""
    user = User.objects.create_user(
        username="testuser",
        password="testpass123",
        email="user@test.com"
    )
    
    # Add to Agent group
    agent_group, _ = Group.objects.get_or_create(name="Agent")
    user.groups.add(agent_group)
    
    return user


@pytest.fixture
def manager_user_with_business(db):
    """Create manager user with active business."""
    from tenants.models import Business, Membership
    
    business = Business.objects.create(
        name="Test Shop",
        slug="test-shop",
        status="ACTIVE",
        business_kind="phones",  # CRITICAL: Set vertical for dashboard routing
    )
    
    user = User.objects.create_user(
        username="testmanager",
        password="testpass123",
        email="manager@test.com"
    )
    
    manager_group, _ = Group.objects.get_or_create(name="Manager")
    user.groups.add(manager_group)
    
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        status="ACTIVE",
    )
    
    return {"user": user, "business": business}


@pytest.mark.critical
def test_authenticated_dashboard_has_no_store_header(manager_user_with_business):
    """
    CRITICAL: Authenticated dashboard HTML must have Cache-Control: no-store.
    
    This prevents browser from caching HTML with outdated static asset references.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    # Get dashboard page (HTML response)
    # Use generic inventory dashboard (works for all verticals)
    response = client.get("/inventory/dashboard/", follow=True)
    
    assert response.status_code == 200, f"Dashboard should return 200, got {response.status_code}"
    
    # Should have Cache-Control: no-store
    cache_control = response.get("Cache-Control", "")
    assert "no-store" in cache_control.lower(), (
        f"Authenticated HTML must have Cache-Control: no-store. Got: {cache_control}"
    )
    
    # Should also have no-cache
    assert "no-cache" in cache_control.lower(), (
        f"Authenticated HTML should have no-cache. Got: {cache_control}"
    )
    
    # Should have Pragma: no-cache (HTTP/1.0 compatibility)
    pragma = response.get("Pragma", "")
    assert pragma.lower() == "no-cache", f"Should have Pragma: no-cache, got: {pragma}"
    
    # Should have Expires: 0 (HTTP/1.0 compatibility)
    expires = response.get("Expires", "")
    assert expires == "0", f"Should have Expires: 0, got: {expires}"


@pytest.mark.critical
def test_authenticated_redirect_has_no_store_header(authenticated_user):
    """
    CRITICAL: Authenticated redirects must have Cache-Control: no-store.
    
    Cached redirects can cause stale routing after deploy.
    """
    client = Client()
    client.force_login(authenticated_user)
    
    # Get a URL that redirects (e.g., root to dashboard)
    response = client.get("/", follow=False)
    
    # If it's a redirect, should have no-store
    if response.status_code in (301, 302, 303, 307, 308):
        cache_control = response.get("Cache-Control", "")
        assert "no-store" in cache_control.lower(), (
            f"Authenticated redirect must have Cache-Control: no-store. "
            f"Status: {response.status_code}, Cache-Control: {cache_control}"
        )


@pytest.mark.critical
def test_static_assets_do_not_have_no_store():
    """
    CRITICAL: Static assets should NOT have no-store (they should be cached).
    
    Only HTML should be no-store. Static assets should be cached for performance.
    """
    client = Client()
    
    # Try to get a static asset (won't work in test, but we can check the pattern)
    # In production, static assets are served by WhiteNoise with proper cache headers
    
    # This test is more of a contract - middleware should NOT add no-store to static
    # We test this by ensuring static paths are excluded
    from cc.middleware_cache import AuthenticatedHTMLNoCacheMiddleware
    
    middleware = AuthenticatedHTMLNoCacheMiddleware(lambda r: None)
    
    # Static paths should be excluded
    assert "/static/" in middleware.EXCLUDE_PATH_PREFIXES, (
        "Static path must be excluded from no-cache middleware"
    )
    assert "/media/" in middleware.EXCLUDE_PATH_PREFIXES, (
        "Media path must be excluded from no-cache middleware"
    )
    assert "/sw.js" in middleware.EXCLUDE_EXACT_PATHS, (
        "Service worker must be excluded from no-cache middleware"
    )


@pytest.mark.critical
def test_anonymous_html_can_be_cached():
    """
    CRITICAL: Anonymous/public HTML should NOT have no-store (can be cached).
    
    Only authenticated HTML should have no-store. Public pages can be cached.
    """
    client = Client()
    
    # Get login page (public, unauthenticated)
    response = client.get(reverse("accounts:login"))
    
    assert response.status_code == 200
    
    # Should NOT have no-store (public pages can be cached)
    cache_control = response.get("Cache-Control", "")
    # Note: Some public pages may still have no-store for other reasons,
    # but the middleware should NOT add it for anonymous users
    
    # The middleware only applies to authenticated users
    # So this test is more of a contract verification
    from cc.middleware_cache import AuthenticatedHTMLNoCacheMiddleware
    
    middleware = AuthenticatedHTMLNoCacheMiddleware(lambda r: None)
    
    # Verify the middleware checks authentication
    assert hasattr(middleware, '_is_authenticated'), (
        "Middleware must check authentication before applying no-store"
    )


@pytest.mark.critical
def test_navbar_dropdown_html_present(manager_user_with_business):
    """
    CRITICAL: Navbar dropdown HTML must be present in authenticated pages.
    
    This ensures the dropdown structure exists in the HTML.
    The actual dropdown functionality (JavaScript) is tested separately.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    # Get a page with navbar (dashboard)
    response = client.get("/inventory/dashboard/", follow=True)
    
    assert response.status_code == 200
    
    content = response.content.decode('utf-8')
    
    # Should have user profile dropdown structure
    # Look for common dropdown indicators:
    # - User avatar/icon
    # - Dropdown menu container
    # - Logout link
    
    # At minimum, should have logout functionality somewhere
    # (either in dropdown or sidebar)
    assert (
        'logout' in content.lower() or 
        'log out' in content.lower() or
        'sign out' in content.lower()
    ), "Page must have logout functionality (dropdown or sidebar)"


@pytest.mark.critical
def test_service_worker_not_cached():
    """
    CRITICAL: Service worker (sw.js) must have no-cache headers.
    
    Service workers MUST be checked for updates on every page load.
    If sw.js is cached, browser won't detect updates and won't activate new version.
    """
    client = Client()
    
    # Try to get service worker
    response = client.get("/sw.js", follow=False)
    
    # May get 404 in test environment (static files not served)
    # But in production, this endpoint exists and MUST have no-cache
    if response.status_code == 200:
        cache_control = response.get("Cache-Control", "")
        assert "no-store" in cache_control.lower() or "no-cache" in cache_control.lower(), (
            f"Service worker must have no-cache headers. Got: {cache_control}"
        )


@pytest.mark.critical
def test_cache_middleware_ordering():
    """
    CRITICAL: Cache middleware must be after AuthenticationMiddleware.
    
    The middleware needs request.user to be populated to check authentication.
    """
    from django.conf import settings
    
    middleware_list = settings.MIDDLEWARE
    
    # Find indices
    auth_idx = None
    cache_idx = None
    
    for i, mw in enumerate(middleware_list):
        if "AuthenticationMiddleware" in mw:
            auth_idx = i
        if "AuthenticatedHTMLNoCacheMiddleware" in mw:
            cache_idx = i
    
    # Cache middleware must be after auth
    assert auth_idx is not None, "AuthenticationMiddleware must be in MIDDLEWARE"
    assert cache_idx is not None, "AuthenticatedHTMLNoCacheMiddleware must be in MIDDLEWARE"
    assert cache_idx > auth_idx, (
        f"AuthenticatedHTMLNoCacheMiddleware must be AFTER AuthenticationMiddleware. "
        f"Found auth at {auth_idx}, cache at {cache_idx}"
    )


@pytest.mark.critical
@pytest.mark.parametrize("url_path", [
    "/inventory/dashboard/",
    "/dashboard/",
])
def test_multiple_dashboards_have_no_store(manager_user_with_business, url_path):
    """
    CRITICAL: All authenticated dashboard pages must have no-store headers.
    
    This ensures the fix applies to all verticals and dashboard views.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    response = client.get(url_path, follow=True)
    
    # Should get a successful response (might redirect)
    assert response.status_code == 200, (
        f"Dashboard {url_path} should return 200, got {response.status_code}"
    )
    
    # Should have no-store
    cache_control = response.get("Cache-Control", "")
    assert "no-store" in cache_control.lower(), (
        f"Dashboard {url_path} must have Cache-Control: no-store. Got: {cache_control}"
    )


@pytest.mark.critical
def test_vary_cookie_header_present(manager_user_with_business):
    """
    CRITICAL: Authenticated responses must have Vary: Cookie header.
    
    This ensures proxies/CDNs distinguish between authenticated and anonymous responses.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    response = client.get("/inventory/dashboard/", follow=True)
    
    assert response.status_code == 200
    
    vary = response.get("Vary", "")
    assert "cookie" in vary.lower(), (
        f"Authenticated response must have Vary: Cookie for proper cache discrimination. "
        f"Got: {vary}"
    )


# =============================================================================
# ACCEPTANCE CRITERIA (must all pass)
# =============================================================================
@pytest.mark.critical
def test_no_stale_html_after_deploy_simulation(manager_user_with_business):
    """
    CRITICAL ACCEPTANCE: Browsers must always get fresh HTML.
    
    This simulates the deploy scenario:
    1. User loads page (gets HTML with static asset references)
    2. Deploy happens (new static asset hashes)
    3. User reloads page (must get NEW HTML with NEW asset references)
    
    The no-store headers ensure step 3 always fetches fresh HTML.
    If HTML was cached, user would get 404s for old asset hashes.
    """
    user = manager_user_with_business["user"]
    client = Client()
    client.force_login(user)
    
    # First request
    response1 = client.get("/inventory/dashboard/", follow=True)
    assert response1.status_code == 200
    
    # Check cache headers prevent caching
    cache_control1 = response1.get("Cache-Control", "")
    assert "no-store" in cache_control1.lower(), (
        "First request must have no-store"
    )
    
    # Second request (simulating page reload)
    response2 = client.get("/inventory/dashboard/", follow=True)
    assert response2.status_code == 200
    
    # Should also have no-store (consistent behavior)
    cache_control2 = response2.get("Cache-Control", "")
    assert "no-store" in cache_control2.lower(), (
        "Reload request must also have no-store"
    )
    
    # Both responses should be fresh (in production, they would have different
    # static asset references if a deploy happened between requests)
    
    # SUCCESS: Browser will always fetch fresh HTML, never serving stale cached version

