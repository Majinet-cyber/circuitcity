# tests/test_hardware_vertical_stability.py
"""
Comprehensive stability tests for Hardware & General Dealers vertical.

Ensures hardware vertical always behaves correctly and never gets stuck in settings.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from tenants.models import Business, Membership

User = get_user_model()


class TestHardwareCanonicalBehavior(TestCase):
    """Test 1: Ensure canonical business_kind is correct and stable"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="hardware_canonical",
            email="canonical@hardware.test",
            password="test1234",
        )
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.user.groups.add(manager_group)

    def test_businesskind_has_hardware_canonical_code(self):
        """Verify HARDWARE exists in BusinessKind choices"""
        choices_dict = dict(BusinessKind.choices)
        self.assertIn("hardware", choices_dict, "BusinessKind.HARDWARE should exist")
        self.assertEqual(
            choices_dict["hardware"],
            "Hardware & General Dealers",
            "Hardware display name should be correct",
        )

    def test_all_hardware_variants_normalize_to_hardware(self):
        """All hardware variants must normalize to 'hardware' (NOT cement)"""
        from tenants.services.business_kind import normalize_business_kind

        test_cases = [
            ("Hardware & General Dealers", "hardware"),
            ("Hardware and General Dealers", "hardware"),
            ("hardware and general dealers", "hardware"),
            ("General Dealers", "hardware"),
            ("general dealer", "hardware"),
            ("Hardware", "hardware"),
            ("hardware", "hardware"),
            ("hardware store", "hardware"),
        ]

        for input_value, expected in test_cases:
            result = normalize_business_kind(input_value)
            self.assertEqual(
                result,
                expected,
                f"'{input_value}' should normalize to '{expected}', got '{result}'",
            )

    def test_cement_stays_cement_not_hardware(self):
        """Cement variants must normalize to 'cement' (NOT hardware)"""
        from tenants.services.business_kind import normalize_business_kind

        cement_cases = [
            ("cement", "cement"),
            ("Cement / Building Materials", "cement"),
            ("cement store", "cement"),
            ("building materials", "cement"),
            ("construction", "cement"),
        ]

        for input_value, expected in cement_cases:
            result = normalize_business_kind(input_value)
            self.assertEqual(
                result,
                expected,
                f"'{input_value}' should normalize to '{expected}', got '{result}'",
            )


class TestHardwarePostLoginRouting(TestCase):
    """Test 2A: Post-login routing never misroutes Hardware"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="hardware_routing",
            email="routing@hardware.test",
            password="test1234",
        )
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.user.groups.add(manager_group)

    def test_hardware_business_routes_to_dashboard_not_settings(self):
        """Hardware business MUST route to dashboard (NOT /accounts/settings/)"""
        # Create hardware business
        business = Business.objects.create(
            name="Hardware Routing Test",
            slug="hardware-routing-test",
            business_kind="hardware",  # Canonical value
            status="ACTIVE",
            created_by=self.user,
        )

        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Login
        self.client.login(username="hardware_routing", password="test1234")

        # Hit dashboard
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # CRITICAL: Must NOT redirect to settings
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        self.assertNotIn(
            "/accounts/settings/",
            final_url,
            f"Hardware business MUST NOT redirect to /accounts/settings/. Got: {final_url}",
        )

        # Should route to inventory or dashboard
        self.assertTrue(
            "inventory" in final_url.lower() or "dashboard" in final_url.lower(),
            f"Hardware should route to inventory/dashboard. Got: {final_url}",
        )

    def test_hardware_business_no_settings_message(self):
        """Hardware business MUST NOT show 'Please set your business type' message"""
        business = Business.objects.create(
            name="Hardware No Message Test",
            slug="hardware-no-message",
            business_kind="hardware",
            status="ACTIVE",
            created_by=self.user,
        )

        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.client.login(username="hardware_routing", password="test1234")
        response = self.client.get(reverse("dashboard:home"), follow=True)

        content = response.content.decode()
        self.assertNotIn(
            "Please set your business type in settings to access your dashboard",
            content,
            "Hardware business MUST NOT show 'set business type' message",
        )

    def test_hardware_vertical_recognized_in_routing(self):
        """Hardware must be recognized in vertical routing registry"""
        from inventory.utils_verticals import get_vertical_dashboard_url, get_vertical_kind

        # Create hardware business
        business = Business.objects.create(
            name="Hardware Registry Test",
            slug="hardware-registry",
            business_kind="hardware",
            status="ACTIVE",
        )

        # Test get_vertical_kind
        vertical_kind = get_vertical_kind(business)
        self.assertEqual(
            vertical_kind,
            "hardware",
            f"get_vertical_kind should return 'hardware', got '{vertical_kind}'",
        )

        # Test get_vertical_dashboard_url
        dashboard_url = get_vertical_dashboard_url("hardware")
        self.assertIsNotNone(
            dashboard_url,
            "Hardware must have a dashboard URL in routing registry",
        )
        self.assertEqual(
            dashboard_url,
            "inventory:inventory_dashboard",
            f"Hardware should route to inventory dashboard, got '{dashboard_url}'",
        )


class TestOnlyNullRedirectsToSettings(TestCase):
    """Test 2B: Only NULL business_kind redirects to settings"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="null_test",
            email="null@test.com",
            password="test1234",
        )
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.user.groups.add(manager_group)

    def test_null_business_kind_redirects_to_settings(self):
        """business_kind=None SHOULD redirect to settings (this is correct)"""
        business = Business.objects.create(
            name="No Kind Business",
            slug="no-kind",
            business_kind=None,  # NULL - should trigger settings redirect
            status="ACTIVE",
            created_by=self.user,
        )

        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.client.login(username="null_test", password="test1234")
        response = self.client.get(reverse("dashboard:home"), follow=True)

        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]

        # Should redirect to settings OR no_business fallback
        self.assertTrue(
            "/accounts/settings/" in final_url or "/verticals/none/" in final_url,
            f"NULL business_kind should redirect to settings or fallback. Got: {final_url}",
        )

    def test_empty_string_business_kind_redirects_to_settings(self):
        """business_kind='' SHOULD redirect to settings (this is correct)"""
        business = Business.objects.create(
            name="Empty Kind Business",
            slug="empty-kind",
            business_kind="",  # Empty - should trigger settings redirect
            status="ACTIVE",
            created_by=self.user,
        )

        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.client.login(username="null_test", password="test1234")
        response = self.client.get(reverse("dashboard:home"), follow=True)

        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]

        # Should redirect to settings OR no_business fallback
        self.assertTrue(
            "/accounts/settings/" in final_url or "/verticals/none/" in final_url,
            f"Empty business_kind should redirect to settings or fallback. Got: {final_url}",
        )

    def test_hardware_with_value_does_not_redirect_to_settings(self):
        """Hardware business with business_kind='hardware' MUST NOT redirect to settings"""
        business = Business.objects.create(
            name="Hardware Has Value",
            slug="hardware-has-value",
            business_kind="hardware",  # Has value - should NOT redirect to settings
            status="ACTIVE",
            created_by=self.user,
        )

        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.client.login(username="null_test", password="test1234")
        response = self.client.get(reverse("dashboard:home"), follow=True)

        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]

        # MUST NOT redirect to settings
        self.assertNotIn(
            "/accounts/settings/",
            final_url,
            f"Hardware (with value) MUST NOT redirect to settings. Got: {final_url}",
        )


class TestOtherVerticalsUnchanged(TestCase):
    """Test 3: Smoke test - other verticals still route correctly"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="vertical_smoke",
            email="smoke@vertical.test",
            password="test1234",
        )
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.user.groups.add(manager_group)

    def test_phones_vertical_routes_correctly(self):
        """Phones vertical should still route correctly"""
        business = Business.objects.create(
            name="Phones Smoke Test",
            slug="phones-smoke",
            business_kind="phones",
            status="ACTIVE",
            created_by=self.user,
        )

        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.client.login(username="vertical_smoke", password="test1234")
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Should NOT redirect to settings
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        self.assertNotIn(
            "/accounts/settings/",
            final_url,
            "Phones vertical should NOT redirect to settings",
        )

    def test_gym_vertical_routes_correctly(self):
        """Gym vertical should still route correctly"""
        business = Business.objects.create(
            name="Gym Smoke Test",
            slug="gym-smoke",
            business_kind="gym",
            status="ACTIVE",
            created_by=self.user,
        )

        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.client.login(username="vertical_smoke", password="test1234")
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Should NOT redirect to settings
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        self.assertNotIn(
            "/accounts/settings/",
            final_url,
            "Gym vertical should NOT redirect to settings",
        )

    def test_clothing_vertical_routes_correctly(self):
        """Clothing vertical should still route correctly"""
        business = Business.objects.create(
            name="Clothing Smoke Test",
            slug="clothing-smoke",
            business_kind="clothing",
            status="ACTIVE",
            created_by=self.user,
        )

        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.client.login(username="vertical_smoke", password="test1234")
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Should NOT redirect to settings
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        self.assertNotIn(
            "/accounts/settings/",
            final_url,
            "Clothing vertical should NOT redirect to settings",
        )


class TestDataMigrationSafety(TestCase):
    """Test 4: Data migration normalization is safe and correct"""

    def test_normalization_function_is_safe(self):
        """Test that normalization handles all edge cases safely"""
        from tenants.services.business_kind import normalize_business_kind

        # Test None
        self.assertIsNone(normalize_business_kind(None))

        # Test empty strings
        self.assertIsNone(normalize_business_kind(""))
        self.assertIsNone(normalize_business_kind("   "))
        self.assertIsNone(normalize_business_kind("\t\n"))

        # Test valid values
        self.assertEqual(normalize_business_kind("hardware"), "hardware")
        self.assertEqual(normalize_business_kind("cement"), "cement")
        self.assertEqual(normalize_business_kind("phones"), "phones")

        # Test case insensitivity
        self.assertEqual(normalize_business_kind("HARDWARE"), "hardware")
        self.assertEqual(normalize_business_kind("HaRdWaRe"), "hardware")

        # Test whitespace handling
        self.assertEqual(normalize_business_kind("  hardware  "), "hardware")

    def test_validation_function_works(self):
        """Test that validation correctly identifies valid/invalid kinds"""
        from tenants.services.business_kind import validate_business_kind

        # Valid kinds
        valid = ["hardware", "cement", "phones", "liquor", "gym", "clothing", "pharmacy", "grocery"]
        for kind in valid:
            self.assertTrue(
                validate_business_kind(kind),
                f"'{kind}' should be valid",
            )

        # Invalid kinds
        invalid = [None, "", "invalid", "unknown", "xyz123", "   "]
        for kind in invalid:
            self.assertFalse(
                validate_business_kind(kind),
                f"'{kind}' should be invalid",
            )
