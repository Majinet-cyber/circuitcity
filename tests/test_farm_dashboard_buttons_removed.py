# tests/test_farm_dashboard_buttons_removed.py
"""
REGRESSION TEST: Farm Dashboard Quick Action Buttons REMOVED

This test ensures the 4 overlaying quick action buttons are NOT rendered
on the Farm dashboard:
  - Add Expense
  - Add Sale
  - Livestock Event
  - New Season

These actions should be accessed via sidebar navigation to their respective pages.
This test MUST FAIL if any of these buttons are re-added to the dashboard.

Related: Acceptance Criteria A (Jan 2026 Farm improvements)
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from tenants.models import Business, Membership

User = get_user_model()


class FarmDashboardNoQuickActionsTest(TestCase):
    """Test that Farm dashboard does NOT render the 4 quick action buttons."""

    def setUp(self):
        """Set up test data: Farm business + manager user."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_buttons_test@test.com",
            email="farm_buttons_test@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm Buttons",
            slug="test-farm-buttons",
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
        self.client.login(username="farm_buttons_test@test.com", password="SecurePass123!")
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()

    def test_dashboard_loads_successfully(self):
        """Farm dashboard must load without errors (HTTP 200)."""
        response = self.client.get("/verticals/farm/dashboard/")
        self.assertEqual(response.status_code, 200, "Farm dashboard must load successfully")

    def test_no_add_expense_button_on_dashboard(self):
        """Farm dashboard must NOT contain 'Add Expense' quick action button."""
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        
        # These are the specific patterns that indicate the quick action button
        self.assertNotIn(
            'data-testid="farm-add-expense"',
            content,
            "Farm dashboard must NOT have 'Add Expense' quick action button (data-testid)"
        )
        # Also check the quick-actions container is removed
        self.assertNotIn(
            'data-testid="farm-quick-actions"',
            content,
            "Farm dashboard must NOT have quick-actions container"
        )

    def test_no_add_sale_button_on_dashboard(self):
        """Farm dashboard must NOT contain 'Add Sale' quick action button."""
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        
        self.assertNotIn(
            'data-testid="farm-add-sale"',
            content,
            "Farm dashboard must NOT have 'Add Sale' quick action button (data-testid)"
        )

    def test_no_livestock_event_button_on_dashboard(self):
        """Farm dashboard must NOT contain 'Livestock Event' quick action button."""
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        
        self.assertNotIn(
            'data-testid="farm-add-livestock-event"',
            content,
            "Farm dashboard must NOT have 'Livestock Event' quick action button (data-testid)"
        )

    def test_no_new_season_button_on_dashboard(self):
        """Farm dashboard must NOT contain 'New Season' quick action button."""
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        
        self.assertNotIn(
            'data-testid="farm-add-season"',
            content,
            "Farm dashboard must NOT have 'New Season' quick action button (data-testid)"
        )

    def test_dashboard_still_has_core_elements(self):
        """Farm dashboard must still contain core elements (KPIs, charts, etc)."""
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        
        # These elements should still be present
        self.assertIn(
            'data-testid="farm-dashboard"',
            content,
            "Farm dashboard must have farm-dashboard testid"
        )
        self.assertIn(
            'data-testid="farm-kpis"',
            content,
            "Farm dashboard must have KPIs section"
        )

    def test_sidebar_has_navigation_alternatives(self):
        """Actions removed from dashboard are accessible via sidebar navigation."""
        # These URLs should still work - actions are in respective pages
        response = self.client.get("/verticals/farm/expenses/")
        self.assertEqual(response.status_code, 200, "Expenses page must be accessible via sidebar")
        
        response = self.client.get("/verticals/farm/sales/")
        self.assertEqual(response.status_code, 200, "Sales page must be accessible via sidebar")
        
        response = self.client.get("/verticals/farm/livestock/")
        self.assertEqual(response.status_code, 200, "Livestock page must be accessible via sidebar")
        
        response = self.client.get("/verticals/farm/crops/")
        self.assertEqual(response.status_code, 200, "Crops/Seasons page must be accessible via sidebar")


class FarmDashboardNoOverlayingPanelsTest(TestCase):
    """Test that Farm dashboard does not have unwanted overlaying panels."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="farm_panels_test@test.com",
            email="farm_panels_test@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Test Farm Panels",
            slug="test-farm-panels",
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
        self.client.login(username="farm_panels_test@test.com", password="SecurePass123!")
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()

    def test_no_bottom_quick_links_panel(self):
        """Farm dashboard must NOT have bottom quick-links panel."""
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        
        # Should not have quick-links panel at bottom
        self.assertNotIn(
            'class="quick-links',
            content,
            "Farm dashboard must NOT have quick-links panel"
        )

    def test_no_duplicate_action_buttons(self):
        """Farm dashboard must NOT have duplicate action button patterns."""
        response = self.client.get("/verticals/farm/dashboard/")
        content = response.content.decode("utf-8")
        
        # Count occurrences of specific button patterns - should be 0
        add_expense_count = content.count('Add Expense</span>')
        add_sale_count = content.count('Add Sale</span>')
        livestock_event_count = content.count('Livestock Event</span>')
        new_season_count = content.count('New Season</span>')
        
        self.assertEqual(
            add_expense_count, 0,
            f"Farm dashboard has {add_expense_count} 'Add Expense' buttons (expected 0)"
        )
        self.assertEqual(
            add_sale_count, 0,
            f"Farm dashboard has {add_sale_count} 'Add Sale' buttons (expected 0)"
        )
        self.assertEqual(
            livestock_event_count, 0,
            f"Farm dashboard has {livestock_event_count} 'Livestock Event' buttons (expected 0)"
        )
        self.assertEqual(
            new_season_count, 0,
            f"Farm dashboard has {new_season_count} 'New Season' buttons (expected 0)"
        )

