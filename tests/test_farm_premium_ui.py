# tests/test_farm_premium_ui.py
"""
Regression tests for Farm Manager premium UI/IA changes.
Ensures no regressions in:
- Sidebar structure (no "Add..." duplicates)
- Dashboard (no quick action buttons)
- Filter functionality
- URL routing
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.utils_verticals import get_vertical_sidebar_items
from inventory.services.farm_filters import parse_farm_filters, FilterState
from datetime import date, timedelta

User = get_user_model()


class FarmSidebarRegressionTest(TestCase):
    """Test that Farm sidebar contains NO 'Add...' duplicate links."""
    
    def test_sidebar_no_add_sale_link(self):
        """Farm sidebar must NOT contain separate 'Add Sale' link."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertNotIn("add_sale", keys, "Farm sidebar must NOT include 'add_sale' key")
    
    def test_sidebar_no_add_expense_link(self):
        """Farm sidebar must NOT contain separate 'Add Expense' link."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertNotIn("add_expense", keys, "Farm sidebar must NOT include 'add_expense' key")
    
    def test_sidebar_no_new_season_link(self):
        """Farm sidebar must NOT contain separate 'New Season' link."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertNotIn("new_season", keys, "Farm sidebar must NOT include 'new_season' key")
    
    def test_sidebar_no_add_asset_link(self):
        """Farm sidebar must NOT contain separate 'Add Asset' link."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        self.assertNotIn("add_asset", keys, "Farm sidebar must NOT include 'add_asset' key")
    
    def test_sidebar_has_clean_structure(self):
        """Farm sidebar should have clean structure with section links only."""
        items = get_vertical_sidebar_items("farm")
        keys = [item.get("key") for item in items]
        
        # Must have these section links
        required_keys = ["dashboard", "sales", "expenses", "livestock", "seasons", "assets", "locations", "reports"]
        for key in required_keys:
            self.assertIn(key, keys, f"Farm sidebar must include '{key}' key")
        
        # Count of items should be reasonable (not bloated with "Add..." duplicates)
        self.assertLessEqual(len(items), 12, "Farm sidebar should have ≤12 items (clean structure)")


class FarmDashboardRenderingTest(TestCase):
    """Test that Farm dashboard renders with premium UI elements."""
    
    def setUp(self):
        self.user = User.objects.create_user(username="farmmanager", password="test123")
        self.business = Business.objects.create(
            name="Test Farm",
            business_kind="farm",
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
        )
        self.client = Client()
        self.client.login(username="farmmanager", password="test123")
    
    def test_dashboard_has_testid_markers(self):
        """Dashboard should have data-testid markers for testing."""
        response = self.client.get(reverse("verticals:farm_dashboard"))
        content = response.content.decode("utf-8")
        
        # Premium UI testid markers
        self.assertIn('data-testid="farm-dashboard"', content)
        self.assertIn('data-testid="farm-kpis"', content)
        self.assertIn('data-testid="farm-filter-button"', content)
    
    def test_dashboard_has_filter_button(self):
        """Dashboard should have a filter button."""
        response = self.client.get(reverse("verticals:farm_dashboard"))
        content = response.content.decode("utf-8")
        
        # Filter button should be present
        self.assertIn('farm-filter-btn', content)
        self.assertIn('bi-funnel', content)


class FarmFilterIntegrationTest(TestCase):
    """Test that Farm filter infrastructure works correctly."""
    
    def setUp(self):
        self.user = User.objects.create_user(username="farmuser", password="test123")
        self.business = Business.objects.create(
            name="Test Farm",
            business_kind="farm",
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
        )
        self.client = Client()
        self.client.login(username="farmuser", password="test123")
    
    def test_filter_preset_today(self):
        """Filter preset 'today' should resolve to today's date."""
        from django.test import RequestFactory
        from django.utils import timezone
        
        factory = RequestFactory()
        request = factory.get("/farm/dashboard/?range=today")
        
        filter_state = parse_farm_filters(request, self.business)
        
        today = timezone.now().date()
        self.assertEqual(filter_state.start_date, today)
        self.assertEqual(filter_state.end_date, today)
        self.assertEqual(filter_state.range_preset, "today")
        self.assertEqual(filter_state.range_label, "Today")
    
    def test_filter_preset_mtd(self):
        """Filter preset 'mtd' should resolve to month-to-date."""
        from django.test import RequestFactory
        from django.utils import timezone
        
        factory = RequestFactory()
        request = factory.get("/farm/dashboard/?range=mtd")
        
        filter_state = parse_farm_filters(request, self.business)
        
        today = timezone.now().date()
        month_start = today.replace(day=1)
        
        self.assertEqual(filter_state.start_date, month_start)
        self.assertEqual(filter_state.end_date, today)
        self.assertEqual(filter_state.range_preset, "mtd")
        self.assertIn("Month", filter_state.range_label)
    
    def test_filter_custom_date_range(self):
        """Filter with custom start/end dates should parse correctly."""
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get("/farm/dashboard/?range=custom&start=2026-01-01&end=2026-01-15")
        
        filter_state = parse_farm_filters(request, self.business)
        
        self.assertEqual(filter_state.start_date, date(2026, 1, 1))
        self.assertEqual(filter_state.end_date, date(2026, 1, 15))
        self.assertEqual(filter_state.range_preset, "custom")


class FarmURLRoutingTest(TestCase):
    """Test that new Farm URL routes resolve correctly."""
    
    def test_sales_landing_url_resolves(self):
        """Farm sales landing URL should resolve."""
        url = reverse("verticals:farm_sales")
        self.assertEqual(url, "/verticals/farm/sales/")
    
    def test_sales_crops_url_resolves(self):
        """Farm sales crops URL should resolve."""
        url = reverse("verticals:farm_sales_crops")
        self.assertEqual(url, "/verticals/farm/sales/crops/")
    
    def test_sales_livestock_url_resolves(self):
        """Farm sales livestock URL should resolve."""
        url = reverse("verticals:farm_sales_livestock")
        self.assertEqual(url, "/verticals/farm/sales/livestock/")
    
    def test_sales_record_url_resolves(self):
        """Farm sales record URL should resolve."""
        url = reverse("verticals:farm_sales_record")
        self.assertEqual(url, "/verticals/farm/sales/record/")
    
    def test_expenses_landing_url_resolves(self):
        """Farm expenses landing URL should resolve."""
        url = reverse("verticals:farm_expenses")
        self.assertEqual(url, "/verticals/farm/expenses/")
    
    def test_expenses_record_url_resolves(self):
        """Farm expenses record URL should resolve."""
        url = reverse("verticals:farm_expenses_record")
        self.assertEqual(url, "/verticals/farm/expenses/record/")
    
    def test_expenses_export_url_resolves(self):
        """Farm expenses export URL should resolve."""
        url = reverse("verticals:farm_expenses_export")
        self.assertEqual(url, "/verticals/farm/expenses/export/")


class OtherVerticalsUnaffectedTest(TestCase):
    """Smoke tests to ensure other verticals are unaffected by Farm changes."""
    
    def test_phones_sidebar_still_works(self):
        """Phones vertical sidebar should still work."""
        items = get_vertical_sidebar_items("phones")
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0, "Phones sidebar should have items")
    
    def test_clothing_sidebar_still_works(self):
        """Clothing vertical sidebar should still work."""
        items = get_vertical_sidebar_items("clothing")
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0, "Clothing sidebar should have items")
    
    def test_gym_sidebar_still_works(self):
        """Gym vertical sidebar should still work."""
        items = get_vertical_sidebar_items("gym")
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0, "Gym sidebar should have items")
    
    def test_cement_sidebar_still_works(self):
        """Cement vertical sidebar should still work."""
        items = get_vertical_sidebar_items("cement")
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0, "Cement sidebar should have items")
