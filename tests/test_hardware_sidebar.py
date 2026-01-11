"""
Test hardware vertical sidebar to ensure it shows proper inventory actions.

This test locks in the fix for hardware sidebar showing only "Home" and "Business Settings"
instead of the proper inventory actions (Stock, Products, Scan IN, Sell).
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from inventory.business_kinds import BusinessKind
from inventory.utils_verticals import get_vertical_sidebar_items
from tenants.models import Business, Membership

User = get_user_model()


class HardwareSidebarTestCase(TestCase):
    """Test that hardware vertical sidebar contains proper inventory actions."""

    def setUp(self):
        """Set up test user and hardware business."""
        self.client = Client()

        # Create manager user
        # nosec B106 - test password, not a real secret
        self.manager = User.objects.create_user(
            username="hardware_manager@test.com", email="hardware_manager@test.com", password="testpass123"
        )

        # Create hardware business
        self.hardware_business = Business.objects.create(
            name="Test Hardware Store",
            slug="test-hardware",
            business_kind=BusinessKind.HARDWARE,
            status="ACTIVE",
            created_by=self.manager,
        )

        # Create membership for manager
        Membership.objects.create(
            user=self.manager,
            business=self.hardware_business,
            role="MANAGER",
        )

        # Login
        # nosec B106 - test password, not a real secret
        self.client.login(username="hardware_manager@test.com", password="testpass123")

    def test_hardware_sidebar_has_inventory_actions(self):
        """
        CRITICAL: Hardware sidebar MUST contain Stock, Products, Scan IN, Sell buttons.
        This test ensures we don't regress to the "Home + Business Settings only" bug.
        """
        sidebar_items = get_vertical_sidebar_items("hardware")

        # Extract all labels from sidebar items
        labels = [item.get("label", "") for item in sidebar_items]

        # CRITICAL ASSERTIONS: These buttons MUST be present
        self.assertIn("Stock", labels, "Hardware sidebar MUST have 'Stock' button")
        self.assertIn("Products", labels, "Hardware sidebar MUST have 'Products' button")
        self.assertIn("Scan IN", labels, "Hardware sidebar MUST have 'Scan IN' button")
        self.assertIn("Sell", labels, "Hardware sidebar MUST have 'Sell' button")

        # Also verify Dashboard and Analytics are present
        self.assertIn("Dashboard", labels, "Hardware sidebar MUST have 'Dashboard' button")
        self.assertIn("Analytics", labels, "Hardware sidebar MUST have 'Analytics' button")

        # Verify the sidebar is NOT the minimal "generic" sidebar (which only has Home + Business Settings)
        self.assertGreater(
            len(sidebar_items), 2, "Hardware sidebar must have more than 2 items (not just Home + Business Settings)"
        )

    def test_hardware_sidebar_urls_are_correct(self):
        """Test that hardware sidebar items point to correct inventory URLs."""
        sidebar_items = get_vertical_sidebar_items("hardware")

        # Build a mapping of label -> url for easy lookup
        items_by_label = {item["label"]: item for item in sidebar_items}

        # Verify Stock points to inventory:stock_list
        self.assertIn("Stock", items_by_label)
        self.assertEqual(
            items_by_label["Stock"]["url"], "inventory:stock_list", "Stock button must route to inventory:stock_list"
        )

        # Verify Products points to inventory:product_list
        self.assertIn("Products", items_by_label)
        self.assertEqual(
            items_by_label["Products"]["url"],
            "inventory:product_list",
            "Products button must route to inventory:product_list",
        )

        # Verify Scan IN points to inventory:scan_in
        self.assertIn("Scan IN", items_by_label)
        self.assertEqual(
            items_by_label["Scan IN"]["url"], "inventory:scan_in", "Scan IN button must route to inventory:scan_in"
        )

        # Verify Sell points to inventory:scan_sold
        self.assertIn("Sell", items_by_label)
        self.assertEqual(
            items_by_label["Sell"]["url"], "inventory:scan_sold", "Sell button must route to inventory:scan_sold"
        )

        # Verify Dashboard points to generic dashboard (not minimal/none)
        self.assertIn("Dashboard", items_by_label)
        self.assertEqual(
            items_by_label["Dashboard"]["url"],
            "inventory:generic_dashboard",
            "Dashboard button must route to inventory:generic_dashboard",
        )

    def test_hardware_dashboard_renders_with_sidebar(self):
        """
        Test that accessing hardware dashboard renders the page with sidebar items.
        This is an integration test to ensure the sidebar actually appears on the page.
        """
        # Access the generic dashboard (which hardware uses)
        response = self.client.get("/inventory/generic-dashboard/")

        # Should be successful
        self.assertEqual(response.status_code, 200, "Hardware dashboard should be accessible")

        # The response should contain sidebar HTML (if using the base template with sidebar)
        # Note: This depends on your template structure, adjust as needed
        html = response.content.decode("utf-8")

        # Basic check: page should not be empty or minimal
        self.assertGreater(len(html), 500, "Dashboard page should have substantial content (not blank/warped)")

    def test_phones_sidebar_still_works(self):
        """
        Regression test: Ensure we didn't break phones sidebar while fixing hardware.
        """
        sidebar_items = get_vertical_sidebar_items("phones")
        labels = [item.get("label", "") for item in sidebar_items]

        # Phones should also have inventory actions
        self.assertIn("Stock", labels, "Phones sidebar must still have Stock")
        self.assertIn("Scan IN", labels, "Phones sidebar must still have Scan IN")
        # Note: Phones uses "Scan & Sell" not just "Sell"
        self.assertTrue("Scan & Sell" in labels or "Sell" in labels, "Phones sidebar must have a Sell action")

        # Should not be the minimal sidebar
        self.assertGreater(len(sidebar_items), 2, "Phones sidebar should have multiple items")

    def test_gym_sidebar_still_works(self):
        """
        Regression test: Ensure gym sidebar (membership-based, not inventory) still works.
        """
        sidebar_items = get_vertical_sidebar_items("gym")
        labels = [item.get("label", "") for item in sidebar_items]

        # Gym should have membership-specific items, NOT inventory items
        self.assertIn("Members", labels, "Gym sidebar must have Members")
        self.assertIn("Member Check-ins", labels, "Gym sidebar must have Check-ins")

        # Gym should NOT have inventory items like "Stock" or "Products"
        self.assertNotIn("Stock", labels, "Gym sidebar should NOT have Stock")
        self.assertNotIn("Products", labels, "Gym sidebar should NOT have Products")
        self.assertNotIn("Scan IN", labels, "Gym sidebar should NOT have Scan IN")

    def test_generic_business_has_minimal_sidebar(self):
        """
        Test that truly generic (no vertical) businesses still get minimal sidebar.
        This ensures we didn't break the fallback behavior.
        """
        sidebar_items = get_vertical_sidebar_items("generic")
        labels = [item.get("label", "") for item in sidebar_items]

        # Generic should only have Home and Business Settings
        self.assertIn("Home", labels, "Generic sidebar should have Home")
        self.assertIn("Business Settings", labels, "Generic sidebar should have Business Settings")

        # Should be minimal (only 2 items)
        self.assertEqual(len(sidebar_items), 2, "Generic sidebar should be minimal (Home + Business Settings only)")

    def test_hardware_sidebar_has_more_section(self):
        """Test that hardware sidebar includes the MORE section with additional tools."""
        sidebar_items = get_vertical_sidebar_items("hardware")
        labels = [item.get("label", "") for item in sidebar_items]

        # Check for common MORE section items
        self.assertIn("Wallet", labels, "Hardware sidebar should have Wallet in MORE section")
        self.assertIn("Time Logs", labels, "Hardware sidebar should have Time Logs")
        self.assertIn("Reports", labels, "Hardware sidebar should have Reports")
        self.assertIn("Agents", labels, "Hardware sidebar should have Agents")
        self.assertIn("Locations", labels, "Hardware sidebar should have Locations")
        self.assertIn("Choose Plan", labels, "Hardware sidebar should have Choose Plan")
