# circuitcity/accounts/tests/test_e2e_login.py
"""
Tests for E2E testing endpoints (whoami, e2e_test_login, idempotency).
"""
import json
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from inventory.models import Location
from tenants.models import Business, Membership

from ..models import UserTwoFactor, get_or_create_twofactor

User = get_user_model()


class WhoamiEndpointTests(TestCase):
    """Test __whoami__ endpoint."""

    def test_whoami_unauthenticated_returns_401(self):
        """Unauthenticated requests should return 401 JSON."""
        # Test both slash and no-slash
        for url in ["/__whoami__", "/__whoami__/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 401, f"Failed for {url}")
            data = response.json()
            self.assertFalse(data["is_authenticated"])
            self.assertEqual(data["error"], "UNAUTHENTICATED")

    def test_whoami_authenticated_returns_200(self):
        """Authenticated requests should return 200 JSON with user info."""
        user = User.objects.create_user(username="test@example.com", email="test@example.com", password="testpass123")
        self.client.force_login(user)

        # Test both slash and no-slash
        for url in ["/__whoami__", "/__whoami__/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"Failed for {url}")
            data = response.json()
            self.assertTrue(data["ok"])
            self.assertTrue(data["is_authenticated"])
            self.assertEqual(data["email"], "test@example.com")
            self.assertEqual(data["username"], "test@example.com")
            self.assertEqual(data["user_id"], user.id)

    def test_whoami_authenticated_with_business(self):
        """Authenticated requests with business should include business info."""
        user = User.objects.create_user(username="test@example.com", email="test@example.com", password="testpass123")
        business = Business.objects.create(
            name="Test Business", business_kind="clothing", status="ACTIVE", created_by=user
        )
        Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")
        self.client.force_login(user)

        # Test both slash and no-slash
        for url in ["/__whoami__", "/__whoami__/"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"Failed for {url}")
            data = response.json()
            self.assertTrue(data["ok"])
            self.assertTrue(data["is_authenticated"])
            self.assertEqual(data["business_id"], business.id)
            self.assertEqual(data["business_name"], "Test Business")
            self.assertEqual(data["business_kind"], "clothing")
            self.assertEqual(data["role"], "MANAGER")

    def test_whoami_never_raises_exceptions(self):
        """Whoami should never raise exceptions, even if business lookup fails."""
        user = User.objects.create_user(username="test@example.com", email="test@example.com", password="testpass123")
        self.client.force_login(user)

        # Mock get_active_business to raise an exception
        with patch("tenants.utils.get_active_business", side_effect=Exception("Test exception")):
            # Test both slash and no-slash
            for url in ["/__whoami__", "/__whoami__/"]:
                response = self.client.get(url)
                # Should still return 200, just without business info
                self.assertEqual(response.status_code, 200, f"Failed for {url}")
                data = response.json()
                self.assertTrue(data["ok"])
                self.assertTrue(data["is_authenticated"])
                self.assertNotIn("business_id", data)


class E2ETestLoginEndpointTests(TestCase):
    """Test e2e_test_login endpoint."""

    def setUp(self):
        """Set up test environment with ALLOW_TEST_LOGIN enabled."""
        self.original_debug = os.environ.get("DEBUG", "")
        self.original_allow = os.environ.get("ALLOW_TEST_LOGIN", "")
        os.environ["ALLOW_TEST_LOGIN"] = "true"

    def tearDown(self):
        """Restore environment."""
        if self.original_debug:
            os.environ["DEBUG"] = self.original_debug
        elif "DEBUG" in os.environ:
            del os.environ["DEBUG"]
        if self.original_allow:
            os.environ["ALLOW_TEST_LOGIN"] = self.original_allow
        elif "ALLOW_TEST_LOGIN" in os.environ:
            del os.environ["ALLOW_TEST_LOGIN"]

    @override_settings(DEBUG=True)
    def test_e2e_test_login_enabled_returns_200(self):
        """When enabled, e2e_test_login should work."""
        # Test both slash and no-slash
        for url in ["/accounts/__e2e__/test-login", "/accounts/__e2e__/test-login/"]:
            response = self.client.post(
                url,
                data=json.dumps({"email": "test@example.com", "password": "testpass123", "kind": "clothing"}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, f"Failed for {url}")
            data = response.json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["email"], "test@example.com")
            self.assertIn("business_id", data)
            self.assertIn("location_id", data)
            self.assertIn("kind", data)
            self.assertEqual(data["kind"], "clothing")

    @override_settings(DEBUG=False)
    def test_e2e_test_login_disabled_in_production_returns_404(self):
        """When ENV=production, e2e_test_login should return 404 (not 403)."""
        os.environ["ENV"] = "production"
        os.environ["ALLOW_TEST_LOGIN"] = "true"

        # TestClient sets REMOTE_ADDR automatically to 127.0.0.1
        response = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"email": "test@example.com", "password": "testpass123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

        # Cleanup
        if "ENV" in os.environ and os.environ["ENV"] == "production":
            del os.environ["ENV"]

    @override_settings(DEBUG=False)
    def test_e2e_test_login_enabled_on_localhost_even_if_debug_false(self):
        """When localhost, should work automatically even if DEBUG=False and no ALLOW_TEST_LOGIN."""
        # Don't set ALLOW_TEST_LOGIN - localhost should work automatically
        os.environ["ENV"] = "dev"
        if "ALLOW_TEST_LOGIN" in os.environ:
            del os.environ["ALLOW_TEST_LOGIN"]

        # TestClient sets REMOTE_ADDR automatically to 127.0.0.1 (localhost)
        # Test both slash and no-slash
        for url in ["/accounts/__e2e__/test-login", "/accounts/__e2e__/test-login/"]:
            response = self.client.post(
                url,
                data=json.dumps({"email": "localhost@example.com", "password": "testpass123", "kind": "clothing"}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200, f"Failed for {url}")
            data = response.json()
            self.assertTrue(data["ok"])

    @override_settings(DEBUG=True)
    def test_e2e_test_login_creates_user_and_business(self):
        """First call should create user and business."""
        response = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"email": "newuser@example.com", "password": "testpass123", "kind": "clothing"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify user was created
        user = User.objects.get(email="newuser@example.com")
        self.assertEqual(user.username, "newuser@example.com")

        # Verify business was created
        business = Business.objects.get(business_kind="clothing", slug__startswith="cypress-clothing")
        self.assertEqual(data["business_id"], business.id)

        # Verify membership was created
        membership = Membership.objects.get(user=user, business=business)
        self.assertEqual(membership.role, "MANAGER")
        self.assertEqual(membership.status, "ACTIVE")

        # Verify location was created
        location = Location.objects.get(business=business, is_default=True)
        self.assertEqual(data["location_id"], location.id)

    @override_settings(DEBUG=True)
    def test_e2e_test_login_idempotent_no_duplicates(self):
        """Second call should not create duplicates."""
        # First call
        response1 = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"email": "idempotent@example.com", "password": "testpass123", "kind": "clothing"}),
            content_type="application/json",
        )
        self.assertEqual(response1.status_code, 200)
        data1 = response1.json()

        initial_user_count = User.objects.filter(email="idempotent@example.com").count()
        initial_business_count = Business.objects.filter(slug__startswith="cypress-clothing").count()
        initial_membership_count = Membership.objects.filter(user__email="idempotent@example.com").count()
        initial_location_count = Location.objects.filter(business_id=data1["business_id"]).count()

        # Second call
        response2 = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"email": "idempotent@example.com", "password": "testpass123", "kind": "clothing"}),
            content_type="application/json",
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()

        # Verify counts didn't increase
        self.assertEqual(User.objects.filter(email="idempotent@example.com").count(), initial_user_count)
        self.assertEqual(Business.objects.filter(slug__startswith="cypress-clothing").count(), initial_business_count)
        self.assertEqual(
            Membership.objects.filter(user__email="idempotent@example.com").count(), initial_membership_count
        )
        self.assertEqual(Location.objects.filter(business_id=data1["business_id"]).count(), initial_location_count)

        # Verify same business_id and location_id
        self.assertEqual(data1["business_id"], data2["business_id"])
        self.assertEqual(data1["location_id"], data2["location_id"])

    @override_settings(DEBUG=True)
    def test_e2e_test_login_clothing_seeds_defaults(self):
        """Clothing kind should seed defaults."""
        response = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"email": "seedtest@example.com", "password": "testpass123", "kind": "clothing"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify seeding occurred (may be True or False depending on whether ExchangeRate exists)
        self.assertIn("seeded", data)

        # Verify ExchangeRate exists (if model exists)
        try:
            from core.models import ExchangeRate

            rate = ExchangeRate.get_current_rate()
            # Should exist (may have been created or already existed)
            self.assertIsNotNone(rate)
        except ImportError:
            # ExchangeRate model doesn't exist, skip
            pass

    @override_settings(DEBUG=True)
    def test_e2e_test_login_invalid_credentials_returns_401(self):
        """Invalid credentials should return 401."""
        # Create user first
        User.objects.create_user(username="existing@example.com", email="existing@example.com", password="correctpass")

        response = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"email": "existing@example.com", "password": "wrongpass"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("error", data)

    def test_404_safety_never_crashes(self):
        """404 pages must never crash (500), even for non-existent routes."""
        # Test that visiting a non-existent URL returns 404, not 500
        response = self.client.get("/this-route-does-not-exist")
        self.assertEqual(response.status_code, 404)
        # Should not raise exception or return 500

    @override_settings(DEBUG=True)
    def test_kind_defaults_to_unique_email_when_email_missing(self):
        """When kind is provided and email is missing, should use kind-specific email."""
        # First call - no email provided
        response = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"password": "Passw0rd!Test", "kind": "clothing"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["email"], "cypress.manager+clothing@example.com")

        # Second call - should be idempotent (same user, no duplicates)
        response2 = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"password": "Passw0rd!Test", "kind": "clothing"}),
            content_type="application/json",
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertEqual(data["user_id"], data2["user_id"])
        self.assertEqual(data["business_id"], data2["business_id"])

    @override_settings(DEBUG=True)
    def test_manager_business_lock_returns_409_when_vertical_mismatch(self):
        """When user is already manager on different vertical, return 409 with MANAGER_BUSINESS_LOCK."""
        # Create user + business A + MANAGER membership with phones vertical
        user = User.objects.create_user(
            username="locked@example.com", email="locked@example.com", password="testpass123"
        )
        business_a = Business.objects.create(
            name="Business A",
            slug="business-a-test",
            business_kind="phones",
            status="ACTIVE",
            created_by=user,
        )
        Membership.objects.create(
            user=user,
            business=business_a,
            role="MANAGER",
            status="ACTIVE",
        )

        # Try to call e2e_test_login with same email but different kind (clothing)
        response = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps(
                {"email": "locked@example.com", "password": "testpass123", "kind": "clothing"}  # Different vertical
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "MANAGER_BUSINESS_LOCK")
        self.assertEqual(data["existing_vertical"], "phones")
        self.assertEqual(data["requested_kind"], "clothing")
        self.assertIn("existing_business_id", data)
        self.assertIn("detail", data)
        self.assertIn("hint", data)

    @override_settings(DEBUG=True)
    def test_existing_manager_reuses_business_no_500(self):
        """Existing MANAGER user should reuse business and return 200 (not 500)."""
        email = "reuse-test@example.com"
        password = "testpass123"

        # Create user + business + MANAGER membership explicitly
        user = User.objects.create_user(username=email, email=email, password=password)
        business = Business.objects.create(
            name=f"Cypress Clothing ({email})",
            slug="cypress-clothing-reuse-test",
            business_kind="clothing",
            status="ACTIVE",
            created_by=user,
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Call e2e_test_login with explicit email - should reuse existing business
        response = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"email": email, "password": password, "kind": "clothing"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        # Should reuse same business
        self.assertEqual(data["business_id"], business.id)
        self.assertEqual(data["user_id"], user.id)
        self.assertTrue(data.get("reused_existing_business", False))

    @override_settings(DEBUG=True)
    def test_business_creation_case_insensitive_idempotent(self):
        """Business creation must be idempotent even with different case names (uniq_business_name_ci)."""
        email = "case-test@example.com"
        password = "testpass123"

        # Create Business with lowercase name matching the format "Cypress Clothing (email)"
        business = Business.objects.create(
            name=f"cypress clothing ({email})",  # lowercase
            slug="cypress-clothing-case-test",
            business_kind="clothing",
            status="ACTIVE",
        )

        # Call e2e_test_login which generates "Cypress Clothing (email)" (title case)
        # Should find existing business case-insensitively, not raise IntegrityError
        response = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"email": email, "password": password, "kind": "clothing"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        # Should return the existing business_id (case-insensitive match)
        self.assertEqual(data["business_id"], business.id)

        # Verify no duplicate business was created
        business_count = Business.objects.filter(name__iexact=f"Cypress Clothing ({email})").count()
        self.assertEqual(business_count, 1, "Should not create duplicate business with case-insensitive name")

    @override_settings(DEBUG=True)
    def test_e2e_test_login_disables_2fa_safely(self):
        """e2e_test_login should disable 2FA safely even if UserTwoFactor has different field shapes."""
        email = "twofa-test@example.com"
        password = "testpass123"

        # Create user
        user = User.objects.create_user(username=email, email=email, password=password)

        # Create UserTwoFactor with 2FA enabled (use the field that exists)
        # Try to detect which field exists, default to sms_enabled
        tf = get_or_create_twofactor(user)
        enabled_field = None

        # Detect which 2FA field exists and enable it
        candidate_fields = ["sms_enabled", "email_enabled", "totp_enabled", "app_enabled", "enabled"]
        for field_name in candidate_fields:
            if hasattr(tf, field_name):
                setattr(tf, field_name, True)
                enabled_field = field_name
                break

        if enabled_field:
            tf.save(update_fields=[enabled_field])
            # Verify 2FA is enabled
            self.assertTrue(tf.is_enabled, f"2FA should be enabled via {enabled_field}")

        # Call e2e_test_login endpoint
        response = self.client.post(
            "/accounts/__e2e__/test-login/",
            data=json.dumps({"email": email, "password": password, "kind": "clothing"}),
            content_type="application/json",
        )

        # Should return 200 (not 500)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])

        # Refresh from DB and verify 2FA is disabled
        tf.refresh_from_db()
        self.assertFalse(tf.is_enabled, "2FA should be disabled after e2e_test_login")

        # Verify the specific field that was enabled is now False
        if enabled_field:
            self.assertFalse(getattr(tf, enabled_field), f"{enabled_field} should be False")
