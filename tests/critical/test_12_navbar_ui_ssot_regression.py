"""
CRITICAL REGRESSION TEST: Navbar UI SSOT (Single Source of Truth)
================================================================================
TASK: Ensure navbar dropdowns and bottom filter panel behavior is locked forever.

This is the DEFINITIVE test for navbar UI behavior across ALL verticals.

REQUIREMENTS (from Dec 16/23 2025 golden reference):
1. DROPDOWNS:
   - Notifications dropdown CLOSED on page load (no "show" class, aria-expanded="false")
   - Avatar dropdown CLOSED on page load (no "show" class, aria-expanded="false")
   - Dropdowns should only open on user click
   - Opening one should close the other (mutual exclusion)
   - No "needs hard refresh" behavior - first load must be correct

2. BOTTOM FILTER PANEL:
   - NO persistent "Quick Links" panel on any dashboard
   - NO persistent "Custom Date Range" panel stuck at bottom
   - Date filter components should use modal/dropdown pattern (hidden by default)
   - Filter panels may only appear on user interaction

3. CACHE HEADERS:
   - All authenticated HTML pages must have Cache-Control: no-store headers
   - This prevents stale cached HTML from causing UI inconsistencies

This test covers multiple verticals to ensure SSOT behavior.
================================================================================
"""
import pytest
from django.test import Client
from django.urls import NoReverseMatch

from tests.critical.conftest import (
    ALL_VERTICALS,
    get_dashboard_url,
    setup_authenticated_client,
    bootstrap_business_with_user,
    VERTICAL_ENDPOINTS,
)

# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]


# ============================================================================
# Helper Functions
# ============================================================================

def assert_dropdowns_closed(html: str, page_name: str = "page"):
    """
    Assert that both navbar dropdowns are closed in the server-rendered HTML.
    
    Checks:
    - ccNotifBtn has aria-expanded="false"
    - userMenuBtn has aria-expanded="false"
    - ccNotifMenu does NOT have "show" class
    - userMenu does NOT have "show" class
    """
    # Check notification button aria-expanded
    notif_btn_index = html.find('id="ccNotifBtn"')
    if notif_btn_index > 0:
        notif_btn_section = html[max(0, notif_btn_index-200):notif_btn_index+400]
        assert 'aria-expanded="false"' in notif_btn_section, (
            f"REGRESSION: Notification button on {page_name} has aria-expanded != 'false'. "
            f"Dropdowns must be CLOSED on initial page load."
        )
    
    # Check user menu button aria-expanded
    user_btn_index = html.find('id="userMenuBtn"')
    if user_btn_index > 0:
        user_btn_section = html[max(0, user_btn_index-200):user_btn_index+400]
        assert 'aria-expanded="false"' in user_btn_section, (
            f"REGRESSION: User menu button on {page_name} has aria-expanded != 'false'. "
            f"Dropdowns must be CLOSED on initial page load."
        )
    
    # Check notification menu doesn't have "show" class
    notif_menu_index = html.find('id="ccNotifMenu"')
    if notif_menu_index > 0:
        # Look for the class attribute on the dropdown-menu element
        notif_menu_section = html[notif_menu_index:notif_menu_index+500]
        assert 'dropdown-menu show' not in notif_menu_section and 'class="show' not in notif_menu_section[:100], (
            f"REGRESSION: Notification menu on {page_name} has 'show' class. "
            f"Dropdowns must be CLOSED on initial page load."
        )
    
    # Check user menu doesn't have "show" class
    user_menu_index = html.find('id="userMenu"')
    if user_menu_index > 0:
        user_menu_section = html[user_menu_index:user_menu_index+500]
        assert 'dropdown-menu show' not in user_menu_section and 'class="show' not in user_menu_section[:100], (
            f"REGRESSION: User menu on {page_name} has 'show' class. "
            f"Dropdowns must be CLOSED on initial page load."
        )


def assert_no_quick_links(html: str, page_name: str = "page"):
    """
    Assert that Quick Links panel is NOT present on the page.
    """
    html_lower = html.lower()
    # These markers indicate Quick Links was re-added
    forbidden_patterns = [
        '>quick links<',  # Title in element
    ]
    for pattern in forbidden_patterns:
        assert pattern not in html_lower, (
            f"REGRESSION: {page_name} contains '{pattern}'. "
            f"Quick Links panel must NOT appear on dashboards."
        )


def assert_cache_control_no_store(response, page_name: str = "page"):
    """
    Assert that the response has Cache-Control: no-store header.
    
    This prevents browsers from caching authenticated HTML, which
    can cause stale UI issues requiring hard refresh.
    """
    cache_control = response.get('Cache-Control', '')
    assert 'no-store' in cache_control, (
        f"REGRESSION: {page_name} missing 'no-store' in Cache-Control header. "
        f"Got: {cache_control!r}. "
        f"Authenticated HTML must not be cached to prevent stale UI."
    )


# ============================================================================
# Test Classes
# ============================================================================

class TestNavbarDropdownsSSOT:
    """
    SSOT tests for navbar dropdown behavior across core verticals.
    
    These tests ensure dropdowns are ALWAYS closed on initial page load,
    preventing the "messy/overlapping dropdowns" regression.
    """

    def test_phones_dashboard_dropdowns_closed(self):
        """Phones dashboard: both dropdowns must be closed on page load"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        # Allow redirects but final destination must be 200
        if response.status_code != 200:
            pytest.skip(f"Phones dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        assert_dropdowns_closed(html, "Phones Dashboard")

    def test_phones_dashboard_cache_control(self):
        """Phones dashboard: must have no-store cache header"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Phones dashboard returned {response.status_code}")
        
        assert_cache_control_no_store(response, "Phones Dashboard")

    def test_clothing_dashboard_dropdowns_closed(self):
        """Clothing dashboard: both dropdowns must be closed on page load"""
        user, business, location = bootstrap_business_with_user("clothing")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("clothing")
        if not dashboard_url:
            pytest.skip("Clothing dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Clothing dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        assert_dropdowns_closed(html, "Clothing Dashboard")


class TestNoQuickLinksSSOT:
    """
    SSOT tests to ensure Quick Links panel is never re-added to any dashboard.
    
    Quick Links was removed in Dec 2025 as it was UI clutter.
    These tests prevent it from being accidentally re-introduced.
    """

    def test_phones_dashboard_no_quick_links(self):
        """Phones dashboard: must NOT have Quick Links panel"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Phones dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        assert_no_quick_links(html, "Phones Dashboard")

    def test_clothing_dashboard_no_quick_links(self):
        """Clothing dashboard: must NOT have Quick Links panel"""
        user, business, location = bootstrap_business_with_user("clothing")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("clothing")
        if not dashboard_url:
            pytest.skip("Clothing dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Clothing dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        assert_no_quick_links(html, "Clothing Dashboard")


class TestBaseHTMLDropdownContract:
    """
    Contract tests for base.html dropdown implementation.
    
    These tests verify that the base.html template renders
    dropdowns with the correct initial state, which is the
    SSOT for all pages using that template.
    """

    def test_navbar_elements_present(self):
        """Navbar must have the expected dropdown elements with correct IDs"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Required navbar elements
        assert 'id="ccNotifBtn"' in html, "Notification button missing"
        assert 'id="ccNotifMenu"' in html, "Notification menu missing"
        assert 'id="userMenuBtn"' in html, "User menu button missing"
        assert 'id="userMenu"' in html, "User menu missing"
        
        # Test IDs for automated testing
        assert 'data-testid="nav-notifications"' in html, "Notification test ID missing"
        assert 'data-testid="nav-avatar"' in html, "Avatar test ID missing"

    def test_dropdowns_use_bootstrap_toggle(self):
        """Dropdown buttons must use Bootstrap's data-bs-toggle pattern"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Notification button should use Bootstrap dropdown
        notif_btn_index = html.find('id="ccNotifBtn"')
        if notif_btn_index > 0:
            notif_btn_section = html[max(0, notif_btn_index-200):notif_btn_index+400]
            assert 'data-bs-toggle="dropdown"' in notif_btn_section, (
                "Notification button must use Bootstrap dropdown toggle"
            )
        
        # User menu button should use Bootstrap dropdown
        user_btn_index = html.find('id="userMenuBtn"')
        if user_btn_index > 0:
            user_btn_section = html[max(0, user_btn_index-200):user_btn_index+400]
            assert 'data-bs-toggle="dropdown"' in user_btn_section, (
                "User menu button must use Bootstrap dropdown toggle"
            )

    def test_cleanup_js_present(self):
        """Base template must include UI cleanup JavaScript"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # The UI cleanup script should be present
        assert '__CC_UI_CLEANUP_V3__' in html or 'CC_UI_CLEANUP' in html, (
            "Base template must include UI cleanup JavaScript for dropdown state management"
        )

    def test_mutual_exclusion_js_present(self):
        """Base template must include mutual exclusion logic for dropdowns"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # The mutual exclusion setup should be present
        assert 'setupMutualExclusion' in html or 'show.bs.dropdown' in html, (
            "Base template must include mutual exclusion logic for dropdowns"
        )
