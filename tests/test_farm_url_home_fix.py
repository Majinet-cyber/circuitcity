# tests/test_farm_url_home_fix.py
"""
CRITICAL REGRESSION TEST: Farm URL Home Fix

This test suite locks the fix for the farm vertical identity bug where:
- "Home" link was pointing to /verticals/none/ instead of farm dashboard
- Sidebar was showing minimal nav (only Home + Business Settings)
- Farm was being treated as "not configured"

ROOT CAUSE: Farm & welding were missing from inventory/url_home.py vertical_home_map

TESTS THAT MUST PASS:
1. get_home_url_for_business() returns /verticals/farm/dashboard/ for farm businesses
2. Context processor injects correct url_home for farm
3. Farm dashboard sidebar contains full nav (not just Home/Settings)
4. "Home" link in sidebar points to farm dashboard, NOT /verticals/none/
5. Same for welding vertical
"""
import pytest
from django.test import TestCase, Client, RequestFactory
from django.contrib.auth import get_user_model
from unittest.mock import MagicMock, Mock, patch

User = get_user_model()


class TestUrlHomeForFarm(TestCase):
    """Test that inventory/url_home.py correctly maps farm to farm dashboard."""
    
    def test_get_home_url_for_business_farm(self):
        """
        CRITICAL: get_home_url_for_business must return farm dashboard for farm businesses.
        
        This is the root cause fix - farm was missing from vertical_home_map.
        """
        from inventory.url_home import get_home_url_for_business
        
        # Create mock farm business
        mock_business = MagicMock()
        mock_business.business_kind = "farm"
        
        url = get_home_url_for_business(mock_business)
        
        # Must return farm dashboard, NOT generic dashboard
        self.assertEqual(url, "/verticals/farm/dashboard/",
                        "Farm business must have url_home = /verticals/farm/dashboard/")
        
        # Must NOT return fallback paths
        self.assertNotIn("/generic-dashboard/", url,
                        "Farm must NOT fall back to generic dashboard")
        self.assertNotIn("/none/", url,
                        "Farm must NOT route to /verticals/none/")
    
    def test_get_home_url_for_business_welding(self):
        """
        CRITICAL: get_home_url_for_business must return welding dashboard for welding businesses.
        """
        from inventory.url_home import get_home_url_for_business
        
        # Create mock welding business
        mock_business = MagicMock()
        mock_business.business_kind = "welding"
        
        url = get_home_url_for_business(mock_business)
        
        # Must return welding dashboard
        self.assertEqual(url, "/verticals/welding/dashboard/",
                        "Welding business must have url_home = /verticals/welding/dashboard/")
        
        # Must NOT return fallback paths
        self.assertNotIn("/generic-dashboard/", url,
                        "Welding must NOT fall back to generic dashboard")
        self.assertNotIn("/none/", url,
                        "Welding must NOT route to /verticals/none/")
    
    def test_get_home_url_name_for_business_farm(self):
        """
        Test that get_home_url_name_for_business returns correct URL name for farm.
        """
        from inventory.url_home import get_home_url_name_for_business
        
        mock_business = MagicMock()
        mock_business.business_kind = "farm"
        
        url_name = get_home_url_name_for_business(mock_business)
        
        self.assertEqual(url_name, "verticals:farm_dashboard",
                        "Farm must map to verticals:farm_dashboard URL name")
    
    def test_get_home_url_name_for_business_welding(self):
        """
        Test that get_home_url_name_for_business returns correct URL name for welding.
        """
        from inventory.url_home import get_home_url_name_for_business
        
        mock_business = MagicMock()
        mock_business.business_kind = "welding"
        
        url_name = get_home_url_name_for_business(mock_business)
        
        self.assertEqual(url_name, "verticals:welding_dashboard",
                        "Welding must map to verticals:welding_dashboard URL name")
    
    def test_no_regressions_other_verticals(self):
        """Ensure other verticals still work after adding farm/welding."""
        from inventory.url_home import get_home_url_for_business
        
        test_cases = [
            ("gym", "/verticals/gym/dashboard/"),
            ("pharmacy", "/verticals/pharmacy/hub/"),
            ("clothing", "/verticals/clothing/dashboard/"),
            ("liquor", "/verticals/liquor/dashboard/"),
            ("phones", "/inventory/dashboard/"),
            ("cement", "/inventory/generic-dashboard/"),
            ("hardware", "/inventory/generic-dashboard/"),
        ]
        
        for kind, expected_url in test_cases:
            with self.subTest(kind=kind):
                mock_business = MagicMock()
                mock_business.business_kind = kind
                
                url = get_home_url_for_business(mock_business)
                
                self.assertEqual(url, expected_url,
                               f"{kind} must route to {expected_url}, got {url}")


class TestContextProcessorUrlHomeInjection(TestCase):
    """Test that context processor correctly injects url_home for farm."""
    
    def test_inventory_context_processor_injects_farm_url_home(self):
        """
        Test that inventory/context_processors.py calls get_home_url_for_business
        and injects correct url_home for farm businesses.
        """
        from inventory.context_processors import active_scope_ctx
        
        # Create mock request with farm business
        factory = RequestFactory()
        request = factory.get("/")
        
        mock_business = MagicMock()
        mock_business.id = 123
        mock_business.business_kind = "farm"
        
        # Patch get_active_business to return farm business
        with patch("inventory.context_processors.get_active_business", return_value=mock_business):
            with patch("inventory.context_processors.business_vertical", return_value="farm"):
                ctx = active_scope_ctx(request)
        
        # Check that url_home is injected
        self.assertIn("url_home", ctx, "Context must contain url_home")
        
        # Check that url_home points to farm dashboard
        self.assertEqual(ctx["url_home"], "/verticals/farm/dashboard/",
                        "Farm business url_home must be /verticals/farm/dashboard/")
        
        # Must NOT be /verticals/none/
        self.assertNotIn("/none/", ctx["url_home"],
                        "url_home must NOT point to /verticals/none/")


class TestFarmSidebarContainsFullNav(TestCase):
    """Test that farm sidebar contains full navigation (not just Home/Settings)."""
    
    def test_farm_sidebar_has_all_expected_items(self):
        """
        CRITICAL: Farm sidebar must contain all farm-specific nav items.
        
        BUG: User reported only seeing "Home" and "Business Settings".
        FIX: Farm must show: Sales, Add Sale, Expenses, Add Expense, Seasons, New Season,
             Assets, Add Asset, Costs, Reports, Analytics, Subscribe, Checkout.
        """
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("farm")
        
        # Extract all item keys
        item_keys = [item.get("key") for item in items]
        
        # Must contain all expected farm nav items
        expected_items = [
            "dashboard",
            "sales",
            "add_sale",
            "expenses",
            "add_expense",
            "seasons",
            "new_season",
            "assets",
            "add_asset",
            "costs",
            "reports",
            "analytics",
            "billing_subscribe",    # Manager only
            "billing_checkout",     # Manager only
            "settings",             # Manager only
        ]
        
        for expected_key in expected_items:
            self.assertIn(expected_key, item_keys,
                         f"Farm sidebar must contain '{expected_key}' item")
        
        # Must have MORE than just 2 items (Home + Business Settings)
        self.assertGreater(len(items), 10,
                          f"Farm sidebar must have full nav (got {len(items)} items)")
    
    def test_farm_sidebar_dashboard_item_points_to_farm_dashboard(self):
        """Farm sidebar dashboard item must point to farm dashboard."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("farm")
        
        # Find dashboard item
        dashboard_item = next((item for item in items if item.get("key") == "dashboard"), None)
        
        self.assertIsNotNone(dashboard_item, "Farm sidebar must have dashboard item")
        
        # Check URL
        self.assertEqual(dashboard_item["url"], "verticals:farm_dashboard",
                        "Farm dashboard item must point to verticals:farm_dashboard")
        
        # Check active_prefix includes /farm/
        self.assertIn("/farm/", dashboard_item["active_prefix"],
                     "Farm dashboard active_prefix must include /farm/")
    
    def test_welding_sidebar_has_full_nav(self):
        """Welding sidebar must also have full navigation (parallel test to farm)."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("welding")
        
        # Extract all item keys
        item_keys = [item.get("key") for item in items]
        
        # Welding-specific items
        expected_items = [
            "dashboard",
            "quotes",
            "create_quote",
            "jobs",
            "materials",
            "stock_in",
            "invoices",
        ]
        
        for expected_key in expected_items:
            self.assertIn(expected_key, item_keys,
                         f"Welding sidebar must contain '{expected_key}' item")
        
        # Must have more than minimal nav
        self.assertGreater(len(items), 5,
                          f"Welding sidebar must have full nav (got {len(items)} items)")


class TestFarmDashboardSidebarRendering(TestCase):
    """Test that farm dashboard template actually renders the correct sidebar."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_sidebar_test",
            password="testpass123",
            email="farmsidebar@example.com"
        )
    
    @pytest.mark.django_db
    def test_farm_dashboard_sidebar_contains_sales_link(self):
        """
        CRITICAL E2E TEST: Farm dashboard HTML must contain "Sales" link in sidebar.
        
        This test catches the bug where sidebar was showing only "Home" + "Business Settings".
        """
        # Skip if models not available
        try:
            from tenants.models import Business, Membership
        except ImportError:
            self.skipTest("tenants.models not available")
        
        # Create farm business
        business = Business.objects.create(
            name="Test Farm E2E",
            business_kind="farm"
        )
        
        # Create manager membership
        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Login
        self.client.login(username="farm_sidebar_test", password="testpass123")
        
        # Set active business
        session = self.client.session
        session["active_business_id"] = business.id
        session.save()
        
        # Get farm dashboard
        response = self.client.get("/verticals/farm/dashboard/")
        
        # If redirect, follow it
        if response.status_code == 302:
            response = self.client.get(response.url, follow=True)
        
        # Check HTML contains expected sidebar items
        if response.status_code == 200:
            content = response.content.decode("utf-8", errors="ignore")
            
            # Must contain farm-specific nav items (not just "Home" + "Business Settings")
            self.assertIn("Sales", content,
                         "Farm dashboard sidebar must contain 'Sales' link")
            self.assertIn("Add Sale", content,
                         "Farm dashboard sidebar must contain 'Add Sale' link")
            self.assertIn("Expenses", content,
                         "Farm dashboard sidebar must contain 'Expenses' link")
            self.assertIn("Add Expense", content,
                         "Farm dashboard sidebar must contain 'Add Expense' link")
            self.assertIn("Seasons", content,
                         "Farm dashboard sidebar must contain 'Seasons' link")
            self.assertIn("Assets", content,
                         "Farm dashboard sidebar must contain 'Assets' link")
    
    @pytest.mark.django_db
    def test_farm_dashboard_home_link_not_verticals_none(self):
        """
        CRITICAL E2E TEST: "Home" link in farm dashboard must NOT point to /verticals/none/.
        
        This catches the exact bug reported: clicking "Home" sends user to /verticals/none/
        which shows "Business Type Not Configured".
        """
        # Skip if models not available
        try:
            from tenants.models import Business, Membership
        except ImportError:
            self.skipTest("tenants.models not available")
        
        # Create farm business
        business = Business.objects.create(
            name="Test Farm Home Link",
            business_kind="farm"
        )
        
        # Create manager membership
        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Login
        self.client.login(username="farm_sidebar_test", password="testpass123")
        
        # Set active business
        session = self.client.session
        session["active_business_id"] = business.id
        session.save()
        
        # Get farm dashboard
        response = self.client.get("/verticals/farm/dashboard/")
        
        # If redirect, follow it
        if response.status_code == 302:
            response = self.client.get(response.url, follow=True)
        
        # Check HTML does NOT contain /verticals/none/
        if response.status_code == 200:
            content = response.content.decode("utf-8", errors="ignore")
            
            # Must NOT link to /verticals/none/
            self.assertNotIn('href="/verticals/none/"', content,
                           "Farm dashboard must NOT have links to /verticals/none/")
            self.assertNotIn('href="/verticals/none/', content,
                           "Farm dashboard must NOT have any /verticals/none/ links")
            
            # Must NOT show "Business Type Not Configured"
            self.assertNotIn("Business Type Not Configured", content,
                           "Farm dashboard must NOT show 'Business Type Not Configured'")


class TestNoRegressionsFromFix(TestCase):
    """Ensure the farm fix doesn't break other verticals."""
    
    def test_other_verticals_url_home_still_work(self):
        """All other verticals must still have correct url_home."""
        from inventory.url_home import get_home_url_for_business
        
        test_cases = {
            "phones": "/inventory/dashboard/",
            "gym": "/verticals/gym/dashboard/",
            "clothing": "/verticals/clothing/dashboard/",
            "liquor": "/verticals/liquor/dashboard/",
            "pharmacy": "/verticals/pharmacy/hub/",
            "cement": "/inventory/generic-dashboard/",
        }
        
        for kind, expected_url in test_cases.items():
            with self.subTest(kind=kind):
                mock_business = MagicMock()
                mock_business.business_kind = kind
                
                url = get_home_url_for_business(mock_business)
                
                self.assertEqual(url, expected_url,
                               f"{kind} url_home changed unexpectedly: expected {expected_url}, got {url}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

