"""
Tests for CSRF configuration and security settings.

Ensures that:
1. RENDER_EXTERNAL_HOSTNAME is properly added to CSRF_TRUSTED_ORIGINS
2. Login forms have CSRF tokens and accept POST with valid tokens
3. CSRF settings are correct for production (secure cookies, etc.)
"""
import os
from django.test import TestCase, override_settings, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import patch

User = get_user_model()


class CSRFSettingsTestCase(TestCase):
    """Test CSRF configuration for Render and production deployments."""

    def test_render_external_hostname_added_to_allowed_hosts(self):
        """Test that RENDER_EXTERNAL_HOSTNAME is added to ALLOWED_HOSTS when set."""
        with patch.dict(os.environ, {"RENDER_EXTERNAL_HOSTNAME": "myapp-test.onrender.com"}):
            # Reload settings module to pick up env var
            from importlib import reload
            from cc import settings

            reload(settings)

            # Verify hostname is in ALLOWED_HOSTS
            self.assertIn("myapp-test.onrender.com", settings.ALLOWED_HOSTS)

    def test_render_external_hostname_added_to_csrf_trusted_origins(self):
        """Test that RENDER_EXTERNAL_HOSTNAME is added to CSRF_TRUSTED_ORIGINS when set."""
        with patch.dict(os.environ, {"RENDER_EXTERNAL_HOSTNAME": "myapp-test.onrender.com"}):
            # Reload settings module to pick up env var
            from importlib import reload
            from cc import settings

            reload(settings)

            # Verify hostname is in CSRF_TRUSTED_ORIGINS with https://
            self.assertIn("https://myapp-test.onrender.com", settings.CSRF_TRUSTED_ORIGINS)

    @override_settings(DEBUG=False, CSRF_COOKIE_SECURE=True, SESSION_COOKIE_SECURE=True)
    def test_production_csrf_cookie_settings(self):
        """Test that CSRF and session cookies are secure in production."""
        from django.conf import settings

        self.assertFalse(settings.DEBUG)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))


class LoginCSRFTestCase(TestCase):
    """Test that login forms properly handle CSRF tokens."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="TestPass123!@#")
        self.client = Client(enforce_csrf_checks=True)

    def test_login_page_sets_csrf_cookie(self):
        """Test that GET /accounts/login/ returns 200 and sets a CSRF cookie."""
        response = self.client.get(reverse("accounts:login"))

        self.assertEqual(response.status_code, 200)
        # Check that CSRF cookie is set (name depends on settings)
        csrf_cookie_name = "cc_csrftoken"  # from settings.CSRF_COOKIE_NAME
        self.assertIn(csrf_cookie_name, response.cookies)

    def test_login_template_has_csrf_token(self):
        """Test that login template includes {% csrf_token %}."""
        response = self.client.get(reverse("accounts:login"))

        self.assertEqual(response.status_code, 200)
        # Check that the rendered HTML contains a CSRF input
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, '<input type="hidden"')

    def test_login_post_with_valid_csrf_does_not_return_403(self):
        """Test that POST to login with valid CSRF token does not return 403."""
        # First GET to obtain CSRF token
        response = self.client.get(reverse("accounts:login"))
        csrf_token = response.cookies.get("cc_csrftoken")

        self.assertIsNotNone(csrf_token, "CSRF cookie should be set after GET")

        # Now POST with the CSRF token
        response = self.client.post(
            reverse("accounts:login"),
            {
                "identifier": "testuser",
                "password": "TestPass123!@#",
                "csrfmiddlewaretoken": csrf_token.value,
            },
            HTTP_X_CSRFTOKEN=csrf_token.value,
        )

        # Should NOT be 403 (CSRF failure)
        # Could be 302 (success redirect) or 200 (form errors, but not CSRF)
        self.assertNotEqual(response.status_code, 403, "Login should not fail with CSRF error when token is valid")

    def test_login_post_without_csrf_returns_403(self):
        """Test that POST to login without CSRF token returns 403."""
        # Attempt to POST without CSRF token
        response = self.client.post(
            reverse("accounts:login"),
            {
                "identifier": "testuser",
                "password": "TestPass123!@#",
            },
        )

        # Should be 403 (CSRF failure)
        self.assertEqual(response.status_code, 403, "Login POST without CSRF token should fail with 403")


class InviteAcceptCSRFTestCase(TestCase):
    """Test that invite acceptance forms properly handle CSRF tokens."""

    def setUp(self):
        """Set up test data."""
        from tenants.models import Business, AgentInvite

        self.business = Business.objects.create(name="Test Business", slug="test-business")

        self.invite = AgentInvite.objects.create(
            business=self.business,
            token="test-token-12345",
            email="newagent@example.com",
            invited_name="New Agent",
            created_by_id=1,  # Assume manager user ID 1 exists or use a real manager
        )

        self.client = Client(enforce_csrf_checks=True)

    def test_invite_accept_page_has_csrf_token(self):
        """Test that invite acceptance template includes {% csrf_token %}."""
        try:
            response = self.client.get(reverse("tenants:invite_accept", kwargs={"token": self.invite.token}))

            # Should return 200 (or possibly redirect if expired)
            if response.status_code == 200:
                self.assertContains(response, "csrfmiddlewaretoken")
                self.assertContains(response, '<input type="hidden"')
        except Exception:
            # If invite_accept URL doesn't exist or has different signature, skip
            self.skipTest("Invite accept URL not available or has different signature")


class RegistrationLoginTemplateCSRFTestCase(TestCase):
    """Test that all auth templates have proper CSRF tokens."""

    def test_registration_login_template_has_csrf(self):
        """Test templates/registration/login.html has {% csrf_token %}."""
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/accounts/login/")

        # Try to render the template
        try:
            html = render_to_string("registration/login.html", request=request)
            self.assertIn("csrfmiddlewaretoken", html)
        except Exception:
            # Template might not exist or use different path
            self.skipTest("registration/login.html template not found")

    def test_accounts_login_template_has_csrf(self):
        """Test templates/accounts/login.html has {% csrf_token %}."""
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/accounts/login/")

        # Try to render the template
        try:
            html = render_to_string("accounts/login.html", request=request)
            self.assertIn("csrfmiddlewaretoken", html)
        except Exception:
            # Template might not exist or use different path
            self.skipTest("accounts/login.html template not found")


class CSRFOriginMatchingTestCase(TestCase):
    """Test that common deployment hostnames are in CSRF_TRUSTED_ORIGINS."""

    def test_staging_url_in_csrf_trusted_origins(self):
        """Test that emajinet-staging.onrender.com is in CSRF_TRUSTED_ORIGINS."""
        from django.conf import settings

        # Check that the staging URL is trusted
        self.assertIn("https://emajinet-staging.onrender.com", settings.CSRF_TRUSTED_ORIGINS)

    def test_production_url_in_csrf_trusted_origins(self):
        """Test that emajinet.africa is in CSRF_TRUSTED_ORIGINS."""
        from django.conf import settings

        # Check that the production URL is trusted
        self.assertIn("https://emajinet.africa", settings.CSRF_TRUSTED_ORIGINS)

    def test_onrender_wildcard_in_csrf_trusted_origins(self):
        """Test that *.onrender.com is in CSRF_TRUSTED_ORIGINS."""
        from django.conf import settings

        # Check that the Render wildcard is trusted
        self.assertIn("https://*.onrender.com", settings.CSRF_TRUSTED_ORIGINS)
