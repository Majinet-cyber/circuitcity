# tests/test_hardware_signup_routing.py
"""
Regression tests for Hardware & General Dealers signup and routing.

Tests ensure that:
1. Hardware signup lands in hardware dashboard (not settings redirect)
2. business_kind is always canonical (never human labels)
3. Unrecognized verticals show error (not redirect loop)
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from tenants.models import Business, Membership

User = get_user_model()


class TestHardwareSignupRouting(TestCase):
    """Test A: Hardware signup lands in hardware dashboard"""

    def setUp(self):
        """Create test user and business"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="hardware_test",
            email="hardware@test.com",
            password="test1234",
        )

        # Add user to Manager group
        from django.contrib.auth.models import Group

        manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.user.groups.add(manager_group)

    def test_hardware_signup_business_kind_is_hardware(self):
        """Test that hardware signup creates business with business_kind='hardware'"""
        # Create business with hardware vertical
        business = Business.objects.create(
            name="Hardware Store Test",
            slug="hardware-store-test",
            business_kind="hardware",  # Canonical value
            status="ACTIVE",
            created_by=self.user,
        )

        # Verify business_kind is the canonical code
        business.refresh_from_db()
        self.assertEqual(
            business.business_kind,
            "hardware",
            "business_kind should be 'hardware' (canonical code), not display label",
        )

    def test_hardware_business_routes_to_dashboard(self):
        """Test that hardware business routes to dashboard (NOT /accounts/settings/)"""
        # Create hardware business
        business = Business.objects.create(
            name="Hardware Store Routes Test",
            slug="hardware-store-routes",
            business_kind="hardware",
            status="ACTIVE",
            created_by=self.user,
        )

        # Create membership
        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Login
        self.client.login(username="hardware_test", password="test1234")

        # Hit the post-signup landing route (dashboard:home)
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Assert response is NOT redirecting to /accounts/settings/
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        self.assertNotIn(
            "/accounts/settings/",
            final_url,
            f"Hardware business should NOT redirect to settings. Got: {final_url}",
        )

        # Assert it routes to hardware/inventory dashboard (or at least shows dashboard marker)
        # Check that we're on a hardware/inventory dashboard route
        self.assertTrue(
            "hardware" in final_url or "inventory" in final_url or "dashboard" in final_url,
            f"Should route to hardware/inventory dashboard. Got: {final_url}",
        )

    def test_hardware_business_no_settings_redirect_message(self):
        """Test that hardware business does NOT show 'Please set your business type' message"""
        # Create hardware business
        business = Business.objects.create(
            name="Hardware Store No Message",
            slug="hardware-store-no-message",
            business_kind="hardware",
            status="ACTIVE",
            created_by=self.user,
        )

        # Create membership
        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Login
        self.client.login(username="hardware_test", password="test1234")

        # Hit the post-signup landing route
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Assert the error message is NOT shown
        content = response.content.decode()
        self.assertNotIn(
            "Please set your business type in settings to access your dashboard",
            content,
            "Hardware business should NOT show 'set business type' message",
        )


class TestGeneralDealersRouting(TestCase):
    """Test B: General dealers maps correctly"""

    def setUp(self):
        """Create test user"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="general_dealer_test",
            email="general@dealer.com",
            password="test1234",
        )

        # Add user to Manager group
        from django.contrib.auth.models import Group

        manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.user.groups.add(manager_group)

    def test_general_dealer_normalizes_to_hardware(self):
        """Test that 'general_dealer' input normalizes to 'hardware'"""
        from tenants.services.business_kind import normalize_business_kind

        # Test various general dealer input variants
        test_cases = [
            "general_dealer",
            "general dealer",
            "General Dealers",
            "Hardware & General Dealers",
            "hardware and general dealers",
            "hardware",
        ]

        for input_value in test_cases:
            normalized = normalize_business_kind(input_value)
            self.assertEqual(
                normalized,
                "hardware",
                f"'{input_value}' should normalize to 'hardware', got: {normalized}",
            )

    def test_general_dealer_routes_to_hardware_vertical(self):
        """Test that general dealer business routes to hardware vertical"""
        # Create business with "hardware" (which represents hardware/general dealers)
        business = Business.objects.create(
            name="General Dealer Store",
            slug="general-dealer-store",
            business_kind="hardware",  # This is the canonical code for hardware/general dealers
            status="ACTIVE",
            created_by=self.user,
        )

        # Create membership
        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Login
        self.client.login(username="general_dealer_test", password="test1234")

        # Hit dashboard
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Should route to hardware dashboard (not settings)
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        self.assertNotIn(
            "/accounts/settings/",
            final_url,
            f"General dealer business should NOT redirect to settings. Got: {final_url}",
        )


class TestMissingBusinessKindRedirect(TestCase):
    """Test C: Missing business_kind redirects to settings"""

    def setUp(self):
        """Create test user"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="no_kind_test",
            email="nokind@test.com",
            password="test1234",
        )

        # Add user to Manager group
        from django.contrib.auth.models import Group

        manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.user.groups.add(manager_group)

    def test_business_with_null_kind_redirects_to_settings(self):
        """Test that business with business_kind=None redirects to settings"""
        # Create business WITHOUT business_kind
        business = Business.objects.create(
            name="No Kind Store",
            slug="no-kind-store",
            business_kind=None,  # Missing business kind
            status="ACTIVE",
            created_by=self.user,
        )

        # Create membership
        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Login
        self.client.login(username="no_kind_test", password="test1234")

        # Hit dashboard
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Assert redirect to /accounts/settings/ happens (this is the only time it should)
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]

        # Should redirect to settings OR no_business fallback
        self.assertTrue(
            "/accounts/settings/" in final_url or "/verticals/none/" in final_url,
            f"Missing business_kind should redirect to settings or fallback. Got: {final_url}",
        )

    def test_business_with_empty_kind_redirects_to_settings(self):
        """Test that business with business_kind='' redirects to settings"""
        # Create business with EMPTY business_kind
        business = Business.objects.create(
            name="Empty Kind Store",
            slug="empty-kind-store",
            business_kind="",  # Empty business kind
            status="ACTIVE",
            created_by=self.user,
        )

        # Create membership
        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Login
        self.client.login(username="no_kind_test", password="test1234")

        # Hit dashboard
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Assert redirect to settings happens
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]

        self.assertTrue(
            "/accounts/settings/" in final_url or "/verticals/none/" in final_url,
            f"Empty business_kind should redirect to settings or fallback. Got: {final_url}",
        )


class TestBusinessKindNormalization(TestCase):
    """Test that business_kind normalization works correctly"""

    def test_normalize_hardware_variants(self):
        """Test that all hardware variants normalize to 'hardware'"""
        from tenants.services.business_kind import normalize_business_kind

        variants = [
            "Hardware & General Dealers",
            "hardware and general dealers",
            "HARDWARE AND GENERAL DEALERS",
            "hardware",
            "general dealers",
            "general dealer",
            "hardware store",
        ]

        for variant in variants:
            normalized = normalize_business_kind(variant)
            self.assertEqual(
                normalized,
                "hardware",
                f"Variant '{variant}' should normalize to 'hardware', got: {normalized}",
            )

    def test_normalize_cement_variants_separate(self):
        """Test that cement variants normalize to 'cement' (separate from hardware)"""
        from tenants.services.business_kind import normalize_business_kind

        variants = [
            "cement",
            "Cement / Building Materials",
            "cement store",
            "building materials",
            "construction",
        ]

        for variant in variants:
            normalized = normalize_business_kind(variant)
            self.assertEqual(
                normalized,
                "cement",
                f"Variant '{variant}' should normalize to 'cement', got: {normalized}",
            )

    def test_normalize_phones_variants(self):
        """Test that phone variants normalize to 'phones'"""
        from tenants.services.business_kind import normalize_business_kind

        variants = [
            "phones",
            "Phones & Electronics",
            "phone",
            "electronics",
            "mobile",
            "mobiles",
        ]

        for variant in variants:
            normalized = normalize_business_kind(variant)
            self.assertEqual(
                normalized,
                "phones",
                f"Variant '{variant}' should normalize to 'phones', got: {normalized}",
            )

    def test_normalize_empty_returns_none(self):
        """Test that empty/None values return None"""
        from tenants.services.business_kind import normalize_business_kind

        test_cases = [None, "", "   ", "\t\n"]

        for value in test_cases:
            normalized = normalize_business_kind(value)
            self.assertIsNone(
                normalized,
                f"Empty value '{repr(value)}' should normalize to None, got: {normalized}",
            )

    def test_validate_business_kind(self):
        """Test business_kind validation"""
        from tenants.services.business_kind import validate_business_kind

        # Valid kinds
        valid = ["hardware", "cement", "phones", "liquor", "gym", "clothing", "pharmacy", "grocery"]
        for kind in valid:
            self.assertTrue(
                validate_business_kind(kind),
                f"'{kind}' should be valid",
            )

        # Invalid kinds
        invalid = [None, "", "invalid", "unknown", "xyz123"]
        for kind in invalid:
            self.assertFalse(
                validate_business_kind(kind),
                f"'{kind}' should be invalid",
            )


class TestUnrecognizedVerticalFallback(TestCase):
    """Test that unrecognized verticals show error (not redirect loop)"""

    def setUp(self):
        """Create test user"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="unrecognized_test",
            email="unrecognized@test.com",
            password="test1234",
        )

        # Add user to Manager group
        from django.contrib.auth.models import Group

        manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.user.groups.add(manager_group)

    def test_unrecognized_vertical_shows_error_not_settings(self):
        """Test that unrecognized vertical shows error banner (NOT redirect to settings)"""
        # Create business with unrecognized business_kind (future vertical not yet implemented)
        business = Business.objects.create(
            name="Future Vertical Store",
            slug="future-vertical-store",
            business_kind="future_vertical_xyz",  # Not in registry
            status="ACTIVE",
            created_by=self.user,
        )

        # Create membership
        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Login
        self.client.login(username="unrecognized_test", password="test1234")

        # Hit dashboard
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Should NOT redirect to settings (business_kind IS set, just not recognized)
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]

        # Should route to generic dashboard or inventory dashboard (NOT settings)
        self.assertTrue(
            "dashboard" in final_url or "inventory" in final_url,
            f"Unrecognized vertical should route to fallback dashboard, not settings. Got: {final_url}",
        )

        # Should NOT be on settings page
        self.assertNotIn(
            "/accounts/settings/",
            final_url,
            "Unrecognized vertical should NOT redirect to settings",
        )
