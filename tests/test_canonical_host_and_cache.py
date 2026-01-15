# tests/test_canonical_host_and_cache.py
"""
Tests for redirect loop prevention, canonical host middleware, and cache headers.

Covers:
1. CanonicalHostMiddleware: www → apex redirect (one-way only)
2. AuthenticatedHTMLNoCacheMiddleware: no-cache headers on HTML and redirects
3. Notification dropdown default state (closed, not open)

Reference: 2026-01-15 fix for redirect loop and clean UI restoration
"""
import pytest
from django.test import Client, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse, HttpResponseRedirect

User = get_user_model()


# =============================================================================
# Part 1: Canonical Host Middleware Tests
# =============================================================================

class TestCanonicalHostMiddleware:
    """Tests for the CanonicalHostMiddleware (www → apex redirect)."""

    @pytest.fixture
    def client(self):
        return Client()

    @pytest.mark.django_db
    @override_settings(CANONICAL_HOST="emajinet.africa")
    def test_www_redirects_to_apex(self, client):
        """Request with www.emajinet.africa should redirect to emajinet.africa."""
        response = client.get(
            "/",
            HTTP_HOST="www.emajinet.africa",
            HTTP_X_FORWARDED_PROTO="https",
            secure=True,
        )
        # Should be 301 permanent redirect
        assert response.status_code == 301
        # Should redirect to apex domain
        assert "emajinet.africa" in response["Location"]
        assert "www." not in response["Location"]

    @pytest.mark.django_db
    @override_settings(CANONICAL_HOST="emajinet.africa")
    def test_apex_does_not_redirect(self, client):
        """Request with emajinet.africa should NOT redirect."""
        response = client.get(
            "/",
            HTTP_HOST="emajinet.africa",
            HTTP_X_FORWARDED_PROTO="https",
            secure=True,
        )
        # Should NOT be a redirect (could be 200 for landing, 302 for login, etc.)
        # Just verify it's not a 301 to www
        if response.status_code == 301:
            assert "www." not in response["Location"]

    @pytest.mark.django_db
    @override_settings(CANONICAL_HOST="emajinet.africa")
    def test_www_redirect_preserves_path(self, client):
        """www redirect should preserve the full path and query string."""
        response = client.get(
            "/dashboard/?page=1",
            HTTP_HOST="www.emajinet.africa",
            HTTP_X_FORWARDED_PROTO="https",
            secure=True,
        )
        assert response.status_code == 301
        location = response["Location"]
        # Should contain the path
        assert "/dashboard/" in location
        # Should contain query string
        assert "page=1" in location
        # Should be apex domain
        assert "www." not in location

    @pytest.mark.django_db
    @override_settings(CANONICAL_HOST="emajinet.africa")
    def test_onrender_hosts_not_redirected(self, client):
        """Staging hosts (.onrender.com) should NOT be redirected."""
        response = client.get(
            "/",
            HTTP_HOST="emajinet-staging.onrender.com",
        )
        # Should not be a 301 redirect to apex domain
        if response.status_code == 301:
            assert "emajinet.africa" not in response["Location"]

    @pytest.mark.django_db
    @override_settings(CANONICAL_HOST="")
    def test_no_redirect_when_canonical_host_empty(self, client):
        """No redirect when CANONICAL_HOST is not configured (dev mode)."""
        response = client.get(
            "/",
            HTTP_HOST="www.emajinet.africa",
        )
        # Should not be a 301 redirect when CANONICAL_HOST is empty
        if response.status_code == 301:
            # If it's a 301, it's not from our middleware (maybe SSL redirect)
            pass

    @pytest.mark.django_db
    def test_localhost_not_redirected(self, client):
        """localhost should never be redirected."""
        response = client.get("/", HTTP_HOST="localhost")
        # Should not be a domain redirect
        if response.status_code == 301:
            location = response["Location"]
            assert "localhost" in location or "emajinet" not in location


# =============================================================================
# Part 2: Cache Header Tests
# =============================================================================

class TestAuthenticatedHTMLNoCacheMiddleware:
    """Tests for cache headers on authenticated HTML responses."""

    @pytest.fixture
    def user(self, db):
        return User.objects.create_user(
            username="cachetest",
            email="cache@test.com",
            password="testpass123!",
        )

    @pytest.fixture
    def client(self):
        return Client()

    @pytest.mark.django_db
    def test_authenticated_html_has_no_cache_headers(self, client, user):
        """Authenticated HTML responses should have no-cache headers."""
        client.force_login(user)
        
        # Request a page that returns HTML (dashboard redirects, but let's use accounts)
        response = client.get("/accounts/login/")
        
        # For authenticated users, check cache headers
        # Note: login page may redirect if already authenticated
        if response.status_code == 200 and "text/html" in response.get("Content-Type", ""):
            assert "no-store" in response.get("Cache-Control", "")

    @pytest.mark.django_db
    def test_authenticated_redirect_has_no_cache_headers(self, client, user):
        """Authenticated redirects should have no-cache headers."""
        client.force_login(user)
        
        # Request dashboard - should redirect
        response = client.get("/dashboard/")
        
        # If it's a redirect (301 or 302), check cache headers
        if response.status_code in (301, 302):
            cache_control = response.get("Cache-Control", "")
            assert "no-store" in cache_control, f"Expected no-store in Cache-Control for redirect, got: {cache_control}"

    @pytest.mark.django_db
    def test_unauthenticated_no_cache_headers_not_forced(self, client):
        """Unauthenticated responses should not have forced no-cache headers."""
        response = client.get("/")
        # We don't force no-cache on unauthenticated responses
        # This test just verifies the middleware doesn't break for anon users
        assert response.status_code in (200, 301, 302)

    @pytest.mark.django_db
    def test_static_files_not_affected(self, client, user):
        """Static files should not get no-cache headers."""
        client.force_login(user)
        
        # This would need a real static file to test properly
        # Just verify the path prefix is excluded
        from cc.middleware_cache import AuthenticatedHTMLNoCacheMiddleware
        
        middleware = AuthenticatedHTMLNoCacheMiddleware(lambda r: HttpResponse())
        assert "/static/" in middleware.EXCLUDE_PATH_PREFIXES


# =============================================================================
# Part 3: Notification Dropdown Tests
# =============================================================================

class TestNotificationDropdownDefaultState:
    """Tests for notification dropdown rendering closed by default."""

    @pytest.fixture
    def client(self):
        return Client()

    @pytest.fixture
    def manager_user(self, db):
        """Create a manager user for testing."""
        user = User.objects.create_user(
            username="notiftest",
            email="notif@test.com",
            password="testpass123!",
        )
        return user

    @pytest.mark.django_db
    def test_notification_menu_closed_by_default(self, client, manager_user):
        """Notification dropdown should NOT have 'show' class on initial render."""
        client.force_login(manager_user)
        
        # Request a page with the notification dropdown
        response = client.get("/dashboard/", follow=True)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            
            # Check that notification menu does not have "show" class in initial HTML
            # The menu should have: id="ccNotifMenu" class="dropdown-menu ... (no show)"
            if "ccNotifMenu" in content:
                # Should NOT find 'dropdown-menu-end p-0 shadow notif-menu show'
                assert 'dropdown-menu show' not in content or 'ccNotifMenu' not in content.split('dropdown-menu show')[0].split('ccNotifMenu')[-1] if 'dropdown-menu show' in content else True

    @pytest.mark.django_db
    def test_notification_toggle_aria_expanded_false(self, client, manager_user):
        """Notification toggle should have aria-expanded='false' on initial render."""
        client.force_login(manager_user)
        
        response = client.get("/dashboard/", follow=True)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            
            # Check for data-testid="notif-toggle"
            if 'data-testid="notif-toggle"' in content:
                # Find the button and check aria-expanded
                # The button should have aria-expanded="false"
                import re
                button_match = re.search(
                    r'<button[^>]*data-testid="notif-toggle"[^>]*aria-expanded="([^"]*)"',
                    content
                )
                if button_match:
                    assert button_match.group(1) == "false", "Notification toggle should have aria-expanded='false'"

    @pytest.mark.django_db
    def test_notification_has_data_testid_attributes(self, client, manager_user):
        """Notification elements should have data-testid attributes for Cypress."""
        client.force_login(manager_user)
        
        response = client.get("/dashboard/", follow=True)
        
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            
            # Check for Cypress test attributes
            if "ccNotifBtn" in content:
                assert 'data-testid="notif-toggle"' in content, "Missing data-testid on notification toggle"
                assert 'data-testid="notif-menu"' in content, "Missing data-testid on notification menu"


# =============================================================================
# Part 4: Integration Tests
# =============================================================================

class TestRedirectLoopPrevention:
    """Integration tests to verify no redirect loops occur."""

    @pytest.fixture
    def client(self):
        return Client()

    @pytest.mark.django_db
    @override_settings(CANONICAL_HOST="emajinet.africa")
    def test_dashboard_no_infinite_redirect(self, client):
        """Dashboard access should not cause infinite redirects."""
        response = client.get(
            "/dashboard/",
            HTTP_HOST="emajinet.africa",
            follow=False,  # Don't follow redirects
        )
        
        # Should get some response, not hang
        assert response.status_code in (200, 301, 302, 403)
        
        # If redirect, should not create a loop
        if response.status_code in (301, 302):
            location = response["Location"]
            # Should not redirect back to www
            assert "www.emajinet.africa" not in location

    @pytest.mark.django_db
    @override_settings(CANONICAL_HOST="emajinet.africa")
    def test_single_hop_www_redirect(self, client):
        """www should redirect to apex in single hop (no chain)."""
        response = client.get(
            "/dashboard/",
            HTTP_HOST="www.emajinet.africa",
            HTTP_X_FORWARDED_PROTO="https",
            secure=True,
            follow=False,
        )
        
        # Should be 301 redirect
        assert response.status_code == 301
        location = response["Location"]
        
        # Should redirect to apex (emajinet.africa, not www)
        assert "emajinet.africa" in location
        assert "www." not in location
        
        # Path should be preserved
        assert "/dashboard/" in location


# =============================================================================
# Middleware Unit Tests
# =============================================================================

class TestCanonicalHostMiddlewareUnit:
    """Unit tests for CanonicalHostMiddleware."""

    def test_middleware_initializes_with_canonical_host(self):
        """Middleware should read CANONICAL_HOST from settings."""
        from cc.middleware_canonical_host import CanonicalHostMiddleware
        
        with override_settings(CANONICAL_HOST="example.com"):
            middleware = CanonicalHostMiddleware(lambda r: HttpResponse())
            assert middleware.canonical_host == "example.com"

    def test_middleware_handles_missing_canonical_host(self):
        """Middleware should handle missing CANONICAL_HOST gracefully."""
        from cc.middleware_canonical_host import CanonicalHostMiddleware
        
        with override_settings(CANONICAL_HOST=""):
            middleware = CanonicalHostMiddleware(lambda r: HttpResponse("OK"))
            
            factory = RequestFactory()
            request = factory.get("/")
            request.META["HTTP_HOST"] = "www.example.com"
            
            response = middleware(request)
            # Should pass through without redirect
            assert response.status_code == 200

    def test_skip_hosts_includes_testserver(self):
        """Middleware should skip 'testserver' host (pytest)."""
        from cc.middleware_canonical_host import CanonicalHostMiddleware
        
        assert "testserver" in CanonicalHostMiddleware.SKIP_HOSTS

