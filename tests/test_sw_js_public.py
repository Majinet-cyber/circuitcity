"""
Test suite for /sw.js endpoint to ensure it's always public and non-gated.

Priority 1 requirement: /sw.js MUST always return 200 and never redirect,
regardless of auth state, tenant resolution, subscription status, or 2FA.
"""
import pytest
from django.test import Client, TestCase
from django.urls import reverse


class ServiceWorkerPublicAccessTestCase(TestCase):
    """
    Test that /sw.js is always accessible without authentication or tenant context.

    This is critical for PWA functionality - service workers must be served
    with 200 status and correct content-type, or the browser will reject them.
    """

    def setUp(self):
        """Set up test client."""
        self.client = Client()

    def test_sw_js_returns_200_anonymous(self):
        """
        Test that /sw.js returns 200 for anonymous users.

        Service workers must be accessible without authentication.
        """
        response = self.client.get("/sw.js")
        self.assertEqual(
            response.status_code,
            200,
            f"Expected /sw.js to return 200 for anonymous user, got {response.status_code}",
        )

    def test_sw_js_content_type_is_javascript(self):
        """
        Test that /sw.js has correct content-type header.

        Browsers require service workers to be served with
        content-type: application/javascript (or text/javascript).
        """
        response = self.client.get("/sw.js")
        content_type = response.get("Content-Type", "")
        self.assertIn(
            "javascript",
            content_type.lower(),
            f"Expected /sw.js content-type to include 'javascript', got '{content_type}'",
        )

    def test_sw_js_contains_service_worker_code(self):
        """
        Test that /sw.js contains valid service worker code.

        Should contain standard service worker event listeners.
        """
        response = self.client.get("/sw.js")
        content = response.content.decode("utf-8")

        # Service workers must have at least one of these standard event listeners
        has_service_worker_code = (
            "addEventListener" in content or "self.addEventListener" in content or "skipWaiting" in content
        )

        self.assertTrue(
            has_service_worker_code,
            "Expected /sw.js to contain service worker code (addEventListener, skipWaiting, etc.)",
        )

    def test_sw_js_does_not_redirect(self):
        """
        Test that /sw.js never redirects (no 301/302/303/307/308).

        Redirects break service worker registration in browsers.
        """
        response = self.client.get("/sw.js")
        self.assertNotIn(
            response.status_code,
            [301, 302, 303, 307, 308],
            f"Expected /sw.js to never redirect, got {response.status_code}",
        )

    def test_sw_js_bypasses_tenant_resolution(self):
        """
        Test that /sw.js works without tenant context.

        Should not require active business or tenant session.
        """
        # Clear any session data
        self.client.cookies.clear()
        response = self.client.get("/sw.js")
        self.assertEqual(
            response.status_code,
            200,
            "Expected /sw.js to work without tenant context",
        )

    def test_sw_js_has_no_cache_header(self):
        """
        Test that /sw.js has no-cache header.

        Service workers should not be cached by the browser
        to ensure updates are picked up immediately.
        """
        response = self.client.get("/sw.js")
        cache_control = response.get("Cache-Control", "")
        self.assertIn(
            "no-cache",
            cache_control,
            f"Expected /sw.js to have no-cache header, got '{cache_control}'",
        )


@pytest.mark.django_db
class ServiceWorkerMiddlewareBypassTest:
    """
    Pytest-style tests for service worker middleware bypass.

    Ensures /sw.js bypasses all gating middleware:
    - Tenant resolution
    - Subscription gate
    - 2FA gate
    - Force password change
    """

    def test_sw_js_bypasses_all_middleware(self, client):
        """
        Test that /sw.js is accessible regardless of middleware state.

        This test ensures BYPASS_PREFIXES is working correctly
        across all gating middleware.
        """
        # Anonymous request (no auth, no tenant, no subscription)
        response = client.get("/sw.js")
        assert (
            response.status_code == 200
        ), f"Expected /sw.js to bypass all middleware and return 200, got {response.status_code}"

        # Check content type
        content_type = response.get("Content-Type", "")
        assert "javascript" in content_type.lower(), f"Expected javascript content-type, got '{content_type}'"

        # Check content is not empty
        content = response.content.decode("utf-8")
        assert len(content) > 0, "Expected /sw.js to return non-empty content"

    def test_bypass_prefixes_constant_exists(self):
        """
        Test that shared BYPASS_PREFIXES constant exists and includes /sw.js.
        """
        from cc.middleware_constants import BYPASS_PREFIXES

        assert "/sw.js" in BYPASS_PREFIXES, f"Expected /sw.js in BYPASS_PREFIXES, got {BYPASS_PREFIXES}"

        # Also check other critical paths
        assert "/manifest.json" in BYPASS_PREFIXES
        assert "/favicon.ico" in BYPASS_PREFIXES
        assert "/static/" in BYPASS_PREFIXES
        assert "/media/" in BYPASS_PREFIXES
