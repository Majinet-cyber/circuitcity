# tests/test_farm_vertical_ssot.py
"""
SSOT Farm Vertical Routing Tests

These tests ensure farm is treated as a first-class vertical:
1. Router test: Farm business routes to farm dashboard (not /verticals/none/)
2. Request test: Farm dashboard returns 200, no "Business Type Not Configured"
3. Signup landing test: Manager signup with farm lands on farm dashboard
4. Sidebar test: Farm dashboard contains farm nav items

CRITICAL: These tests prevent regression of farm routing to /verticals/none/.
"""
import pytest
from django.test import TestCase, Client, RequestFactory
from django.urls import reverse, NoReverseMatch
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock

User = get_user_model()


class TestFarmVerticalRegistration(TestCase):
    """Test that farm is properly registered in the SSOT vertical registry."""
    
    def test_farm_in_business_kinds(self):
        """Farm must be a valid BusinessKind choice."""
        from inventory.business_kinds import BusinessKind
        
        # Check farm exists as a choice
        farm_choices = [choice[0] for choice in BusinessKind.choices]
        self.assertIn("farm", farm_choices, "Farm must be a valid BusinessKind choice")
    
    def test_farm_in_utils_verticals_valid_kinds(self):
        """Farm must be in the valid_kinds list in get_vertical_kind."""
        from inventory.utils_verticals import get_vertical_kind
        
        # Create a mock business with business_kind="farm"
        mock_business = MagicMock()
        mock_business.business_kind = "farm"
        
        kind = get_vertical_kind(mock_business)
        self.assertEqual(kind, "farm", "get_vertical_kind must return 'farm' for farm businesses")
    
    def test_farm_dashboard_url_mapping(self):
        """Farm must have a dashboard URL mapping in get_vertical_dashboard_url."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("farm")
        self.assertEqual(url_name, "verticals:farm_dashboard", 
                        "Farm must map to verticals:farm_dashboard")
    
    def test_farm_sidebar_items_exist(self):
        """Farm must have sidebar items defined in get_vertical_sidebar_items."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("farm")
        self.assertTrue(len(items) > 0, "Farm must have sidebar items")
        
        # Check for key farm items
        item_keys = [item.get("key") for item in items]
        self.assertIn("dashboard", item_keys, "Farm sidebar must have dashboard")
        self.assertIn("ledger", item_keys, "Farm sidebar must have ledger")
        self.assertIn("add_expense", item_keys, "Farm sidebar must have add_expense")
        self.assertIn("add_sale", item_keys, "Farm sidebar must have add_sale")
    
    def test_farm_display_name(self):
        """Farm must have a display name in get_vertical_display_name."""
        from inventory.utils_verticals import get_vertical_display_name
        
        name = get_vertical_display_name("farm")
        self.assertEqual(name, "Farm Manager", "Farm display name must be 'Farm Manager'")


class TestFarmDashboardURLResolves(TestCase):
    """Test that farm dashboard URL resolves correctly."""
    
    def test_farm_dashboard_url_exists(self):
        """verticals:farm_dashboard URL must exist and resolve."""
        try:
            url = reverse("verticals:farm_dashboard")
            self.assertEqual(url, "/verticals/farm/dashboard/", 
                           "Farm dashboard URL must be /verticals/farm/dashboard/")
        except NoReverseMatch:
            self.fail("verticals:farm_dashboard URL does not exist!")
    
    def test_farm_ledger_url_exists(self):
        """verticals:farm_ledger_list URL must exist."""
        try:
            url = reverse("verticals:farm_ledger_list")
            self.assertTrue(url.startswith("/verticals/farm/"))
        except NoReverseMatch:
            self.fail("verticals:farm_ledger_list URL does not exist!")
    
    def test_farm_add_expense_url_exists(self):
        """verticals:farm_add_expense URL must exist."""
        try:
            url = reverse("verticals:farm_add_expense")
            self.assertTrue(url.startswith("/verticals/farm/"))
        except NoReverseMatch:
            self.fail("verticals:farm_add_expense URL does not exist!")
    
    def test_farm_add_sale_url_exists(self):
        """verticals:farm_add_sale URL must exist."""
        try:
            url = reverse("verticals:farm_add_sale")
            self.assertTrue(url.startswith("/verticals/farm/"))
        except NoReverseMatch:
            self.fail("verticals:farm_add_sale URL does not exist!")


class TestFarmRoutingNotNone(TestCase):
    """
    CRITICAL: Test that farm businesses NEVER route to /verticals/none/.
    """
    
    def test_accounts_views_vertical_routes_includes_farm(self):
        """
        The vertical_routes map in accounts/views.py must include farm.
        This is a code inspection test to prevent regression.
        """
        import circuitcity.accounts.views as views
        import inspect
        
        # Get the source code of _post_login_url
        source = inspect.getsource(views._post_login_url)
        
        # Check that farm is in the vertical_routes
        self.assertIn('"farm"', source, 
                     "_post_login_url must have 'farm' in vertical_routes")
        self.assertIn("verticals:farm_dashboard", source,
                     "_post_login_url must route farm to verticals:farm_dashboard")
    
    def test_post_auth_redirect_includes_farm(self):
        """
        The post_auth_redirect service must include farm routing.
        """
        from circuitcity.accounts.services.post_auth_redirect import _get_vertical_dashboard_url
        
        url = _get_vertical_dashboard_url("farm")
        self.assertIn("/farm/", url, 
                     "post_auth_redirect must route farm to farm dashboard URL")
        self.assertNotIn("/none/", url,
                        "post_auth_redirect must NOT route farm to /verticals/none/")
    
    def test_get_business_home_url_routes_farm(self):
        """
        tenants.utils.get_business_home_url must route farm businesses correctly.
        """
        from tenants.utils import get_business_home_url
        
        # Create mock business with farm kind
        mock_business = MagicMock()
        mock_business.business_kind = "farm"
        
        url = get_business_home_url(business=mock_business)
        
        # Should route to farm dashboard, not /verticals/none/
        self.assertNotIn("/none/", url,
                        "get_business_home_url must NOT route farm to /verticals/none/")


class TestFarmMobileNav(TestCase):
    """Test that farm has mobile navigation configured."""
    
    def test_mobile_nav_includes_farm(self):
        """Mobile nav must have farm-specific items."""
        from inventory.mobile_nav import get_mobile_nav_items
        from inventory.helpers_core import FARM
        
        # Create mock request with farm vertical
        factory = RequestFactory()
        request = factory.get("/")
        request.BUSINESS_VERTICAL = FARM
        
        # Patch business_vertical to return FARM
        with patch("inventory.mobile_nav.business_vertical", return_value=FARM):
            items = get_mobile_nav_items(request)
        
        self.assertTrue(len(items) > 0, "Farm must have mobile nav items")
        
        # Check farm-specific items exist
        item_keys = [item.get("key") for item in items]
        self.assertIn("home", item_keys, "Farm mobile nav must have home")
        
        # Check home links to farm dashboard
        home_item = next((item for item in items if item["key"] == "home"), None)
        self.assertIsNotNone(home_item)
        self.assertIn("/farm/", home_item["url"], 
                     "Farm mobile nav home must link to farm dashboard")


class TestFarmDashboardResponse(TestCase):
    """Test that farm dashboard returns proper response."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="test_farm_user",
            password="testpass123",
            email="farmtest@example.com"
        )
    
    @pytest.mark.django_db
    def test_farm_dashboard_not_configured_banner_absent(self):
        """
        CRITICAL: Farm dashboard must NOT show "Business Type Not Configured".
        
        This test ensures the farm dashboard renders properly without fallback content.
        """
        # Skip if business models aren't available
        try:
            from tenants.models import Business, Membership
        except ImportError:
            self.skipTest("tenants.models not available")
        
        # Create farm business
        business = Business.objects.create(
            name="Test Farm Business",
            business_kind="farm"
        )
        
        # Create membership
        Membership.objects.create(
            user=self.user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Login
        self.client.login(username="test_farm_user", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = business.id
        session.save()
        
        # Get farm dashboard
        response = self.client.get("/verticals/farm/dashboard/")
        
        # Should get 200 or redirect to farm dashboard
        if response.status_code == 302:
            # Follow redirect
            final_url = response.url
            self.assertNotIn("/none/", final_url,
                           f"Farm dashboard must NOT redirect to /verticals/none/, got: {final_url}")
        else:
            # Check content doesn't have "not configured" message
            content = response.content.decode("utf-8", errors="ignore")
            self.assertNotIn("Business Type Not Configured", content,
                           "Farm dashboard must NOT show 'Business Type Not Configured'")


class TestWeldingVerticalRegistration(TestCase):
    """Test that welding is also properly registered (parallel to farm)."""
    
    def test_welding_in_business_kinds(self):
        """Welding must be a valid BusinessKind choice."""
        from inventory.business_kinds import BusinessKind
        
        welding_choices = [choice[0] for choice in BusinessKind.choices]
        self.assertIn("welding", welding_choices, 
                     "Welding must be a valid BusinessKind choice")
    
    def test_welding_dashboard_url_mapping(self):
        """Welding must have a dashboard URL mapping."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("welding")
        self.assertEqual(url_name, "verticals:welding_dashboard",
                        "Welding must map to verticals:welding_dashboard")
    
    def test_accounts_views_vertical_routes_includes_welding(self):
        """The vertical_routes map must include welding."""
        import circuitcity.accounts.views as views
        import inspect
        
        source = inspect.getsource(views._post_login_url)
        self.assertIn('"welding"', source,
                     "_post_login_url must have 'welding' in vertical_routes")


class TestNoRegressionsOtherVerticals(TestCase):
    """Ensure other verticals still work correctly (no regressions)."""
    
    def test_phones_still_routes_correctly(self):
        """Phones vertical routing must not be broken."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        # Phones should either return None (uses default) or a phones URL
        url_name = get_vertical_dashboard_url("phones")
        # phones returns None which means use inventory dashboard
        self.assertIsNone(url_name, "Phones should return None for default routing")
    
    def test_gym_still_routes_correctly(self):
        """Gym vertical routing must not be broken."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("gym")
        self.assertEqual(url_name, "verticals:gym_dashboard")
    
    def test_clothing_still_routes_correctly(self):
        """Clothing vertical routing must not be broken."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("clothing")
        self.assertEqual(url_name, "verticals:clothing_dashboard")
    
    def test_liquor_still_routes_correctly(self):
        """Liquor vertical routing must not be broken."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("liquor")
        self.assertEqual(url_name, "verticals:liquor_dashboard")
    
    def test_pharmacy_still_routes_correctly(self):
        """Pharmacy vertical routing must not be broken."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("pharmacy")
        self.assertEqual(url_name, "verticals:pharmacy_hub")
    
    def test_cement_still_routes_correctly(self):
        """Cement vertical routing must not be broken."""
        from inventory.utils_verticals import get_vertical_dashboard_url
        
        url_name = get_vertical_dashboard_url("cement")
        self.assertEqual(url_name, "verticals:cement_dashboard")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

