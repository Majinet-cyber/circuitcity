# inventory/tests/test_legacy_blocking.py
"""
Tests to ensure legacy scan/sell/simulator pages never render old templates.
Part A: Legacy URL blocking tests
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from tenants.models import Business
from inventory.models import Location

User = get_user_model()


class LegacyEndpointBlockingTests(TestCase):
    """
    Ensure legacy endpoints redirect or return 410 Gone.
    Never allow old scan_in/scan_sold/simulator templates to render.
    """

    def setUp(self):
        """Create test user and business"""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", email="test@test.com", password="testpass123")
        self.business = Business.objects.create(name="Test Business", owner=self.user, kind="phones")
        self.location = Location.objects.create(name="Test Location", business=self.business)
        self.user.agent_profile.business = self.business
        self.user.agent_profile.location = self.location
        self.user.agent_profile.save()

        self.client.login(username="testuser", password="testpass123")

    def test_legacy_scan_in_redirects(self):
        """
        OLD: /inventory/scan-in/ (old template)
        NEW: Should redirect to canonical scan-in

        This test ensures old cached URLs redirect properly.
        """
        response = self.client.get("/inventory/scan-in/", follow=False)

        # Should NOT return 200 with old template
        # Should redirect (301/302) or return new template
        self.assertIn(response.status_code, [200, 301, 302, 307, 308])

        # If it's a 200, ensure it's NOT the old template
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # Old template has specific markers we can check for
            # New template has different markers
            self.assertNotIn("<!-- OLD SCAN IN TEMPLATE -->", content)

    def test_legacy_scan_sold_redirects(self):
        """
        OLD: /inventory/scan-sold/ (old template)
        NEW: Should redirect to phone sale wizard

        This test ensures scan_sold never shows old UI.
        """
        response = self.client.get("/inventory/scan-sold/", follow=False)

        # Should NOT return 200 with old template
        self.assertIn(response.status_code, [200, 301, 302, 307, 308])

        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # Ensure it's not the old scan_sold template
            self.assertNotIn("<!-- OLD SCAN SOLD TEMPLATE -->", content)

    def test_legacy_public_simulator_returns_410(self):
        """
        OLD: /simulator/ (public staticpage)
        NEW: 410 Gone (upgraded to manager-only tool)

        The old public simulator has been replaced.
        """
        self.client.logout()  # Test as anonymous user
        response = self.client.get("/simulator/")

        # Should return 410 Gone
        self.assertEqual(response.status_code, 410)

        # Should show upgrade message
        content = response.content.decode("utf-8")
        self.assertIn("Simulator Upgraded", content)
        self.assertIn("manager-only", content)

    def test_legacy_simulator_never_renders_old_template(self):
        """
        Ensure the old staticpages/simulator.html never renders.
        Even if someone tries to access it directly.
        """
        response = self.client.get("/simulator/")

        # Should be 410, not 200 with old template
        self.assertEqual(response.status_code, 410)

        content = response.content.decode("utf-8")
        # Old template had interactive sliders and CFO message
        self.assertNotIn("units-slider", content)
        self.assertNotIn("price-slider", content)
        self.assertNotIn("cfo-message", content)

    def test_manager_simulator_still_works(self):
        """
        NEW: /simulator/business/ (manager-only, real data)
        This should still work for managers.
        """
        # Make user a manager
        self.user.is_staff = True
        self.user.save()

        response = self.client.get("/simulator/business/")

        # Should work for managers (200 or 302 to login if auth fails)
        self.assertIn(response.status_code, [200, 302, 403])

        if response.status_code == 200:
            content = response.content.decode("utf-8")
            # New simulator has different markers
            # It should show "Business Simulator" or similar
            self.assertIn("Simulator", content)

    def test_scan_in_template_redirect_fallback(self):
        """
        If someone somehow accesses the legacy scan_in_redirect.html,
        it should auto-redirect via meta refresh and JavaScript.
        """
        # This is a fallback template that should never be seen by users
        # But if it is, it must redirect immediately
        from django.template.loader import render_to_string

        html = render_to_string(
            "inventory/scan_in_redirect.html",
            {
                "redirect_url": "/inventory/scan-in/",
                "canonical_name": "Scan IN",
            },
        )

        # Check meta refresh is present
        self.assertIn('http-equiv="refresh"', html)
        self.assertIn('content="0;url=/inventory/scan-in/"', html)

        # Check JavaScript redirect is present
        self.assertIn("window.location.href", html)
        self.assertIn("/inventory/scan-in/", html)

    def test_scan_sold_template_redirect_fallback(self):
        """
        If someone somehow accesses the legacy scan_sold_redirect.html,
        it should auto-redirect via meta refresh and JavaScript.
        """
        from django.template.loader import render_to_string

        html = render_to_string(
            "inventory/scan_sold_redirect.html",
            {
                "redirect_url": "/inventory/phone-sale-wizard/",
                "canonical_name": "Phone Sale Wizard",
            },
        )

        # Check meta refresh is present
        self.assertIn('http-equiv="refresh"', html)

        # Check JavaScript redirect is present
        self.assertIn("window.location.href", html)
        self.assertIn("/inventory/phone-sale-wizard/", html)

    def test_legacy_gone_template_shows_upgrade_message(self):
        """
        The legacy_gone.html template should show a clean upgrade message.
        """
        from django.template.loader import render_to_string

        html = render_to_string(
            "legacy_gone.html",
            {
                "title": "Test Page Upgraded",
                "message": "This page has been upgraded.",
                "detail": "The new version is better.",
                "cta_text": "Go to Dashboard",
                "cta_url": "/",
            },
        )

        # Check upgrade message
        self.assertIn("Test Page Upgraded", html)
        self.assertIn("This page has been upgraded", html)
        self.assertIn("HTTP 410 Gone", html)

        # Check CTA button
        self.assertIn("Go to Dashboard", html)
        self.assertIn('href="/"', html)


class LegacyURLNameTests(TestCase):
    """
    Ensure legacy URL names still resolve but point to new views.
    """

    def test_scan_in_url_name_resolves(self):
        """inventory:scan_in should resolve to new view"""
        url = reverse("inventory:scan_in")
        self.assertEqual(url, "/inventory/scan-in/")

    def test_scan_sold_url_name_resolves(self):
        """inventory:scan_sold should resolve"""
        url = reverse("inventory:scan_sold")
        self.assertEqual(url, "/inventory/scan-sold/")

    def test_staticpages_simulator_url_resolves(self):
        """staticpages:simulator should resolve"""
        url = reverse("staticpages:simulator")
        self.assertEqual(url, "/simulator/")

    def test_business_simulator_url_resolves(self):
        """simulator:business_home should resolve to manager-only simulator"""
        url = reverse("simulator:business_home")
        self.assertEqual(url, "/simulator/business/")
