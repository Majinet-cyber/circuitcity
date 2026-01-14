# tests/test_no_quick_links_regression.py
"""
REGRESSION TEST: No Quick Links on Dashboards

Purpose:
    Ensures that "Quick Links" panels are NEVER present on any dashboard pages.
    This feature was removed on 2026-01-14 per user request to keep UI clean.

What This Tests:
    1. Main dashboard (/dashboard/) does not contain "Quick Links"
    2. Vertical dashboards do not contain "Quick Links"
    3. None of the Quick Links button labels appear as a dedicated section

FAILURE = Quick Links section has been re-added = UI clutter = Must be removed again
"""
import pytest
from django.test import Client

from tests.critical.conftest import (
    ALL_VERTICALS,
    get_dashboard_url,
    setup_authenticated_client,
    bootstrap_business_with_user,
)

pytestmark = [pytest.mark.django_db]


# Markers that indicate Quick Links was re-added (case-insensitive patterns)
QUICK_LINKS_MARKERS = [
    "Quick Links",  # The section title itself
    ">Upgrade Plan</a>",  # The upgrade plan button in quick links
    ">Manage Agents</a>",  # The manage agents button in quick links
    ">Manage Trainers</a>",  # Gym variant of manage agents
]


class TestNoQuickLinksOnDashboards:
    """Regression tests to ensure Quick Links is never re-added to dashboards."""

    def test_main_dashboard_no_quick_links(self):
        """
        Main dashboard (/dashboard/) must NOT contain Quick Links section.
        
        This is the primary dashboard users see after login.
        """
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        response = client.get("/dashboard/", follow=True)
        
        # Should load successfully
        assert response.status_code == 200, \
            f"Main dashboard returned {response.status_code}"
        
        content = response.content.decode("utf-8", errors="ignore")
        
        # Check for Quick Links markers
        for marker in QUICK_LINKS_MARKERS:
            assert marker not in content, \
                f"REGRESSION: Main dashboard contains '{marker}' - Quick Links must be removed"

    def test_main_dashboard_no_quick_links_agent_view(self):
        """
        Main dashboard as AGENT must NOT contain Quick Links section.
        """
        user, business, location = bootstrap_business_with_user("phones", role="AGENT")
        client = setup_authenticated_client(user, business, location)
        
        response = client.get("/dashboard/", follow=True)
        
        # Should load successfully
        assert response.status_code in [200, 302], \
            f"Agent dashboard returned {response.status_code}"
        
        if response.status_code == 200:
            content = response.content.decode("utf-8", errors="ignore")
            
            # Check for Quick Links markers
            for marker in QUICK_LINKS_MARKERS:
                assert marker not in content, \
                    f"REGRESSION: Agent dashboard contains '{marker}' - Quick Links must be removed"

    @pytest.mark.parametrize("vertical", ALL_VERTICALS)
    def test_vertical_dashboards_no_quick_links(self, vertical):
        """
        ALL vertical dashboards must NOT contain Quick Links section.
        
        Tests all 10 verticals:
        phones, liquor, grocery, pharmacy, clothing, gym, hardware, cement, farm, welding
        """
        user, business, location = bootstrap_business_with_user(vertical)
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url(vertical)
        
        if not dashboard_url:
            pytest.skip(f"No dashboard URL for {vertical}")
        
        response = client.get(dashboard_url, follow=True)
        
        # Should load (200) or redirect (302), never 500
        assert response.status_code in [200, 302], \
            f"{vertical} dashboard returned {response.status_code}"
        
        if response.status_code == 200:
            content = response.content.decode("utf-8", errors="ignore")
            
            # Check for Quick Links markers
            for marker in QUICK_LINKS_MARKERS:
                assert marker not in content, \
                    f"REGRESSION: {vertical} dashboard contains '{marker}' - Quick Links must be removed"


class TestInventoryDashboardNoQuickLinks:
    """Test the inventory dashboard specifically."""
    
    def test_inventory_dashboard_no_quick_links(self):
        """
        Inventory dashboard must NOT contain Quick Links section.
        """
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        response = client.get("/inventory/dashboard/", follow=True)
        
        # Should load successfully or redirect
        assert response.status_code in [200, 302], \
            f"Inventory dashboard returned {response.status_code}"
        
        if response.status_code == 200:
            content = response.content.decode("utf-8", errors="ignore")
            
            for marker in QUICK_LINKS_MARKERS:
                assert marker not in content, \
                    f"REGRESSION: Inventory dashboard contains '{marker}' - Quick Links must be removed"


class TestGroceriesV2DashboardNoQuickLinks:
    """Test the Groceries V2 dashboard specifically (had its own Quick Links)."""
    
    def test_groceries_v2_dashboard_no_quick_links(self):
        """
        Groceries V2 dashboard must NOT contain Quick Links section.
        
        This dashboard had a specific bottom action bar that was removed.
        """
        user, business, location = bootstrap_business_with_user("grocery")
        client = setup_authenticated_client(user, business, location)
        
        # Try the V2 dashboard URL
        response = client.get("/verticals/groceries-v2/dashboard/", follow=True)
        
        if response.status_code == 404:
            # V2 dashboard might not exist in this setup
            pytest.skip("Groceries V2 dashboard not available")
        
        if response.status_code == 200:
            content = response.content.decode("utf-8", errors="ignore")
            
            # Check for specific Groceries V2 bottom links that were removed
            groceries_markers = [
                "View Leaderboard</a>",
                "View All Products</a>",
                "Old Dashboard</a>",
            ]
            
            for marker in groceries_markers + QUICK_LINKS_MARKERS:
                assert marker not in content, \
                    f"REGRESSION: Groceries V2 dashboard contains '{marker}' - bottom links must be removed"

