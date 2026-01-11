"""
Regression tests for Farm and Welding vertical routing.

CRITICAL: Ensures that farm and welding businesses:
1. NEVER land on /verticals/none/ (the generic fallback)
2. NEVER see "Business Type Not Configured" message
3. Route to their proper dashboards (/verticals/farm/dashboard/ and /verticals/welding/dashboard/)
4. Have proper sidebar navigation items

These tests verify the fix for the routing bug where farm/welding were being
treated as "not configured" despite having full implementations.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from tenants.models import Business, Membership

User = get_user_model()


class FarmVerticalRoutingTest(TestCase):
    """Test that farm businesses route correctly to farm dashboard."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_manager@test.com",
            email="farm_manager@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm",
            slug="test-farm",
            business_kind="farm",
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    def test_farm_vertical_not_none_and_not_generic(self):
        """
        CRITICAL: Farm business must NOT land on /verticals/none/ or show generic fallback.
        
        This test verifies:
        - GET request to farm dashboard returns 200
        - Response does NOT contain "Business Type Not Configured"
        - Response does NOT contain "not fully configured yet"
        - Response does NOT contain "/verticals/none/"
        - Response contains farm-specific marker (e.g., "Farm Manager")
        """
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        # Access farm dashboard directly
        response = self.client.get("/verticals/farm/dashboard/", follow=True)
        
        # Should return 200
        self.assertEqual(
            response.status_code,
            200,
            f"Farm dashboard should return 200, got {response.status_code}"
        )
        
        # Get page content
        content = response.content.decode("utf-8")
        
        # Should NOT contain generic fallback messages
        self.assertNotIn(
            "Business Type Not Configured",
            content,
            "Farm dashboard must NOT show 'Business Type Not Configured'"
        )
        self.assertNotIn(
            "not fully configured yet",
            content,
            "Farm dashboard must NOT show 'not fully configured yet'"
        )
        
        # Should NOT have been redirected to /verticals/none/
        final_url = response.request["PATH_INFO"]
        self.assertNotIn(
            "/verticals/none/",
            final_url,
            f"Farm business should NOT be on /verticals/none/, got: {final_url}"
        )
        
        # Should contain farm-specific content
        self.assertTrue(
            "Farm Manager" in content or "farm" in content.lower(),
            "Farm dashboard should contain farm-specific content"
        )

    def test_farm_business_redirects_to_farm_dashboard(self):
        """
        Test that after login, a farm business redirects to farm dashboard (not generic).
        """
        self.client.login(username="farm_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        # Access general dashboard
        response = self.client.get("/dashboard/", follow=True)
        
        # Should NOT end up on /verticals/none/
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        self.assertNotIn(
            "/verticals/none/",
            final_url,
            f"Farm business should NOT redirect to /verticals/none/, got: {final_url}"
        )

    def test_farm_get_vertical_kind_returns_farm(self):
        """Test that get_vertical_kind() correctly identifies farm businesses."""
        from inventory.utils_verticals import get_vertical_kind
        
        vertical_kind = get_vertical_kind(self.business)
        
        self.assertEqual(
            vertical_kind,
            "farm",
            f"get_vertical_kind should return 'farm', got: {vertical_kind}"
        )

    def test_farm_get_vertical_dashboard_url_returns_farm_dashboard(self):
        """Test that get_vertical_dashboard_url() returns farm dashboard URL."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        dashboard_url = get_vertical_dashboard_url("farm")
        
        self.assertEqual(
            dashboard_url,
            "verticals:farm_dashboard",
            f"get_vertical_dashboard_url should return 'verticals:farm_dashboard', got: {dashboard_url}"
        )

    def test_farm_sidebar_items_exist(self):
        """Test that farm has proper sidebar items (not generic fallback)."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("farm")
        
        # Should have multiple items
        self.assertGreater(
            len(sidebar_items),
            2,
            f"Farm sidebar should have more than 2 items, got: {len(sidebar_items)}"
        )
        
        # Should have farm-specific items
        item_keys = [item["key"] for item in sidebar_items]
        self.assertIn("dashboard", item_keys, "Farm sidebar should have dashboard")
        self.assertIn("ledger", item_keys, "Farm sidebar should have ledger")
        self.assertIn("livestock", item_keys, "Farm sidebar should have livestock")
        self.assertIn("crops", item_keys, "Farm sidebar should have crops")


class WeldingVerticalRoutingTest(TestCase):
    """Test that welding businesses route correctly to welding dashboard."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="welding_manager@test.com",
            email="welding_manager@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Welding Workshop",
            slug="test-welding",
            business_kind="welding",
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    def test_welding_vertical_not_none_and_not_generic(self):
        """
        CRITICAL: Welding business must NOT land on /verticals/none/ or show generic fallback.
        
        This test verifies:
        - GET request to welding dashboard returns 200
        - Response does NOT contain "Business Type Not Configured"
        - Response does NOT contain "not fully configured yet"
        - Response does NOT contain "/verticals/none/"
        - Response contains welding-specific marker (e.g., "Welding Manager")
        """
        self.client.login(username="welding_manager@test.com", password="SecurePass123!")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        # Access welding dashboard directly
        response = self.client.get("/verticals/welding/dashboard/", follow=True)
        
        # Should return 200
        self.assertEqual(
            response.status_code,
            200,
            f"Welding dashboard should return 200, got {response.status_code}"
        )
        
        # Get page content
        content = response.content.decode("utf-8")
        
        # Should NOT contain generic fallback messages
        self.assertNotIn(
            "Business Type Not Configured",
            content,
            "Welding dashboard must NOT show 'Business Type Not Configured'"
        )
        self.assertNotIn(
            "not fully configured yet",
            content,
            "Welding dashboard must NOT show 'not fully configured yet'"
        )
        
        # Should NOT have been redirected to /verticals/none/
        final_url = response.request["PATH_INFO"]
        self.assertNotIn(
            "/verticals/none/",
            final_url,
            f"Welding business should NOT be on /verticals/none/, got: {final_url}"
        )
        
        # Should contain welding-specific content
        self.assertTrue(
            "Welding Manager" in content or "welding" in content.lower(),
            "Welding dashboard should contain welding-specific content"
        )

    def test_welding_business_redirects_to_welding_dashboard(self):
        """
        Test that after login, a welding business redirects to welding dashboard (not generic).
        """
        self.client.login(username="welding_manager@test.com", password="SecurePass123!")
        
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        
        # Access general dashboard
        response = self.client.get("/dashboard/", follow=True)
        
        # Should NOT end up on /verticals/none/
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        self.assertNotIn(
            "/verticals/none/",
            final_url,
            f"Welding business should NOT redirect to /verticals/none/, got: {final_url}"
        )

    def test_welding_get_vertical_kind_returns_welding(self):
        """Test that get_vertical_kind() correctly identifies welding businesses."""
        from inventory.utils_verticals import get_vertical_kind
        
        vertical_kind = get_vertical_kind(self.business)
        
        self.assertEqual(
            vertical_kind,
            "welding",
            f"get_vertical_kind should return 'welding', got: {vertical_kind}"
        )

    def test_welding_get_vertical_dashboard_url_returns_welding_dashboard(self):
        """Test that get_vertical_dashboard_url() returns welding dashboard URL."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        dashboard_url = get_vertical_dashboard_url("welding")
        
        self.assertEqual(
            dashboard_url,
            "verticals:welding_dashboard",
            f"get_vertical_dashboard_url should return 'verticals:welding_dashboard', got: {dashboard_url}"
        )

    def test_welding_sidebar_items_exist(self):
        """Test that welding has proper sidebar items (not generic fallback)."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        sidebar_items = get_vertical_sidebar_items("welding")
        
        # Should have multiple items
        self.assertGreater(
            len(sidebar_items),
            2,
            f"Welding sidebar should have more than 2 items, got: {len(sidebar_items)}"
        )
        
        # Should have welding-specific items
        item_keys = [item["key"] for item in sidebar_items]
        self.assertIn("dashboard", item_keys, "Welding sidebar should have dashboard")
        self.assertIn("quotes", item_keys, "Welding sidebar should have quotes")
        self.assertIn("jobs", item_keys, "Welding sidebar should have jobs")
        self.assertIn("materials", item_keys, "Welding sidebar should have materials")


class VerticalRegistryIntegrationTest(TestCase):
    """Test that the vertical registry correctly handles farm and welding."""

    def test_farm_in_canonical_business_kinds(self):
        """Test that farm is in CANONICAL_BUSINESS_KINDS."""
        from tenants.services.business_kind import CANONICAL_BUSINESS_KINDS
        
        self.assertIn(
            "farm",
            CANONICAL_BUSINESS_KINDS,
            "Farm should be in CANONICAL_BUSINESS_KINDS"
        )
        self.assertEqual(
            CANONICAL_BUSINESS_KINDS["farm"]["display_name"],
            "Farm Manager",
            "Farm display name should be 'Farm Manager'"
        )

    def test_welding_in_canonical_business_kinds(self):
        """Test that welding is in CANONICAL_BUSINESS_KINDS."""
        from tenants.services.business_kind import CANONICAL_BUSINESS_KINDS
        
        self.assertIn(
            "welding",
            CANONICAL_BUSINESS_KINDS,
            "Welding should be in CANONICAL_BUSINESS_KINDS"
        )
        self.assertEqual(
            CANONICAL_BUSINESS_KINDS["welding"]["display_name"],
            "Welding Workshop",
            "Welding display name should be 'Welding Workshop'"
        )

    def test_farm_validate_business_kind(self):
        """Test that farm passes validation."""
        from tenants.services.business_kind import validate_business_kind
        
        self.assertTrue(
            validate_business_kind("farm"),
            "Farm should be a valid business kind"
        )

    def test_welding_validate_business_kind(self):
        """Test that welding passes validation."""
        from tenants.services.business_kind import validate_business_kind
        
        self.assertTrue(
            validate_business_kind("welding"),
            "Welding should be a valid business kind"
        )

    def test_farm_normalize_business_kind(self):
        """Test that farm variants normalize correctly."""
        from tenants.services.business_kind import normalize_business_kind
        
        self.assertEqual(normalize_business_kind("farm"), "farm")
        self.assertEqual(normalize_business_kind("Farm Manager"), "farm")
        self.assertEqual(normalize_business_kind("farming"), "farm")
        self.assertEqual(normalize_business_kind("agriculture"), "farm")

    def test_welding_normalize_business_kind(self):
        """Test that welding variants normalize correctly."""
        from tenants.services.business_kind import normalize_business_kind
        
        self.assertEqual(normalize_business_kind("welding"), "welding")
        self.assertEqual(normalize_business_kind("Welding Workshop"), "welding")
        self.assertEqual(normalize_business_kind("welder"), "welding")
        self.assertEqual(normalize_business_kind("fabrication"), "welding")


class PostAuthRedirectTest(TestCase):
    """Test that post-auth redirects work for farm and welding."""

    def test_farm_in_vertical_dashboards(self):
        """Test that farm is in VERTICAL_DASHBOARDS mapping."""
        from circuitcity.accounts.services.post_auth_redirect import _get_vertical_dashboard_url
        
        url = _get_vertical_dashboard_url("farm")
        
        # Should not be the default fallback
        self.assertNotIn(
            "inventory_dashboard",
            url,
            f"Farm should have specific dashboard, not inventory_dashboard. Got: {url}"
        )

    def test_welding_in_vertical_dashboards(self):
        """Test that welding is in VERTICAL_DASHBOARDS mapping."""
        from circuitcity.accounts.services.post_auth_redirect import _get_vertical_dashboard_url
        
        url = _get_vertical_dashboard_url("welding")
        
        # Should not be the default fallback
        self.assertNotIn(
            "inventory_dashboard",
            url,
            f"Welding should have specific dashboard, not inventory_dashboard. Got: {url}"
        )

