# tests/critical/test_09_navbar_ui_contract.py
"""
CRITICAL TEST 09: Navbar UI Contract (Notifications + Avatar)

This test ensures the navbar UI elements (notifications bell, avatar dropdown)
exist and are in the correct state on authenticated pages.

FAILURE HERE = Navbar regression = Users can't access notifications/settings = Critical UX failure

This test locks in the fix for:
1. Notifications not auto-opening on page load
2. Avatar dropdown being accessible
3. Test hooks being present for E2E tests
"""
import pytest
import re
from django.test import Client

from tests.critical.conftest import (
    bootstrap_business_with_user,
    setup_authenticated_client,
    get_dashboard_url,
)


# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]


class TestNavbarUIContract:
    """
    Verify that the navbar UI contract is stable and correct.
    
    The navbar MUST:
    1. Have stable test hooks (data-testid attributes)
    2. Render notifications bell
    3. Render avatar dropdown
    4. NOT show notifications panel by default
    5. NOT show avatar menu by default
    
    This prevents UI regressions that would break user workflows.
    """
    
    def test_navbar_has_stable_test_hooks(self):
        """
        Navbar must have stable data-testid attributes for testing.
        
        This ensures:
        1. E2E tests can find navbar elements
        2. Future refactoring doesn't break tests
        3. UI contract is explicit and enforced
        """
        # Setup: Create authenticated user and client
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        # Get phones dashboard URL
        dashboard_url = get_dashboard_url("phones")
        assert dashboard_url, "Phones dashboard URL must be configured"
        
        # Make request to authenticated page
        response = client.get(dashboard_url)
        assert response.status_code == 200, f"Dashboard returned {response.status_code}"
        
        # Get HTML content
        html = response.content.decode("utf-8")
        
        # CRITICAL: Assert all required test hooks are present
        required_testids = [
            "nav-notifications",  # Notifications bell button
            "nav-avatar",         # Avatar button
            "avatar-menu",        # Avatar dropdown menu
            "avatar-settings",    # Settings link in avatar menu
            "avatar-logout",      # Logout link in avatar menu
        ]
        
        for testid in required_testids:
            assert f'data-testid="{testid}"' in html, (
                f"MISSING TEST HOOK: data-testid='{testid}' not found in HTML. "
                f"This will break E2E tests and make regressions harder to detect."
            )
    
    def test_notifications_bell_is_rendered(self):
        """
        Notifications bell must be rendered on authenticated pages.
        
        This ensures users can access notifications.
        """
        # Setup: Create authenticated user and client
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        # Get phones dashboard URL
        dashboard_url = get_dashboard_url("phones")
        assert dashboard_url, "Phones dashboard URL must be configured"
        
        # Make request to authenticated page
        response = client.get(dashboard_url)
        assert response.status_code == 200
        
        # Get HTML content
        html = response.content.decode("utf-8")
        
        # Assert notifications bell is present
        assert 'data-testid="nav-notifications"' in html, (
            "Notifications bell is missing from navbar"
        )
        
        # Assert bell button is present (by id or testid) - flexible check
        has_bell = (
            'id="cc-bell"' in html or 
            'id="notificationDropdown"' in html or
            'id="ccNotifBtn"' in html
        )
        assert has_bell, (
            "Notifications bell button is missing (no recognized ID found)"
        )
    
    def test_avatar_dropdown_is_rendered(self):
        """
        Avatar dropdown must be rendered on authenticated pages.
        
        This ensures users can access profile settings and logout.
        """
        # Setup: Create authenticated user and client
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        # Get phones dashboard URL
        dashboard_url = get_dashboard_url("phones")
        assert dashboard_url, "Phones dashboard URL must be configured"
        
        # Make request to authenticated page
        response = client.get(dashboard_url)
        assert response.status_code == 200
        
        # Get HTML content
        html = response.content.decode("utf-8")
        
        # Assert avatar button is present
        assert 'data-testid="nav-avatar"' in html, (
            "Avatar button is missing from navbar"
        )
        
        # Assert avatar menu is present
        assert 'data-testid="avatar-menu"' in html, (
            "Avatar menu is missing from navbar"
        )
        
        # Assert menu contains required links
        assert 'data-testid="avatar-settings"' in html, (
            "Settings link is missing from avatar menu"
        )
        assert 'data-testid="avatar-logout"' in html, (
            "Logout link is missing from avatar menu"
        )
    
    def test_notifications_panel_not_shown_by_default(self):
        """
        CRITICAL: Notifications panel MUST NOT be shown by default.
        
        This is the regression test for the "auto-opening notifications" bug
        where notifications would be visible on page load due to server-side
        rendering or cached HTML.
        
        The panel should only open when the user clicks the bell.
        """
        # Setup: Create authenticated user and client
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        # Get phones dashboard URL
        dashboard_url = get_dashboard_url("phones")
        assert dashboard_url, "Phones dashboard URL must be configured"
        
        # Make request to authenticated page
        response = client.get(dashboard_url)
        assert response.status_code == 200
        
        # Get HTML content
        html = response.content.decode("utf-8")
        
        # CRITICAL: Assert notifications panel is NOT visible by default
        
        # If using Bootstrap dropdown, the dropdown-menu should NOT have "show" class
        # at initial render
        dropdown_pattern = r'data-testid="notifications-panel"[^>]*class="[^"]*\bshow\b'
        assert not re.search(dropdown_pattern, html, re.IGNORECASE), (
            "Notifications panel has 'show' class at initial render. "
            "This means notifications will auto-open on page load (CRITICAL BUG)."
        )
        
        # If using aria-expanded, it should be "false" on the bell button
        # (This is checked in the surrounding context of nav-notifications)
        bell_context_pattern = r'data-testid="nav-notifications"[^>]*aria-expanded="true"'
        assert not re.search(bell_context_pattern, html, re.IGNORECASE), (
            "Notifications bell has aria-expanded='true' at initial render. "
            "This indicates the panel is open (CRITICAL BUG)."
        )
        
        # Additional check: If there's a modal for notifications, it should NOT be shown
        # Look for common modal patterns with data-testid="notifications-modal"
        if 'data-testid="notifications-modal"' in html:
            modal_show_pattern = r'data-testid="notifications-modal"[^>]*class="[^"]*\bshow\b'
            assert not re.search(modal_show_pattern, html, re.IGNORECASE), (
                "Notifications modal has 'show' class at initial render. "
                "This means notifications will auto-open on page load (CRITICAL BUG)."
            )
            
            # Check aria-hidden attribute
            modal_visible_pattern = r'data-testid="notifications-modal"[^>]*aria-hidden="false"'
            assert not re.search(modal_visible_pattern, html, re.IGNORECASE), (
                "Notifications modal has aria-hidden='false' at initial render. "
                "This means the modal is visible on page load (CRITICAL BUG)."
            )
    
    def test_avatar_menu_not_shown_by_default(self):
        """
        Avatar menu should NOT be shown by default.
        
        The menu should only open when the user clicks the avatar button.
        """
        # Setup: Create authenticated user and client
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        # Get phones dashboard URL
        dashboard_url = get_dashboard_url("phones")
        assert dashboard_url, "Phones dashboard URL must be configured"
        
        # Make request to authenticated page
        response = client.get(dashboard_url)
        assert response.status_code == 200
        
        # Get HTML content
        html = response.content.decode("utf-8")
        
        # Assert avatar menu is NOT visible by default
        # The menu should NOT have "open" or "show" class at initial render
        menu_pattern = r'data-testid="avatar-menu"[^>]*class="[^"]*\b(open|show)\b'
        assert not re.search(menu_pattern, html, re.IGNORECASE), (
            "Avatar menu has 'open' or 'show' class at initial render. "
            "The menu should only open when clicked."
        )
        
        # Check aria-expanded on avatar button
        avatar_expanded_pattern = r'data-testid="nav-avatar"[^>]*aria-expanded="true"'
        assert not re.search(avatar_expanded_pattern, html, re.IGNORECASE), (
            "Avatar button has aria-expanded='true' at initial render. "
            "This indicates the menu is open."
        )
    
    def test_navbar_contract_on_multiple_pages(self):
        """
        Navbar contract must apply to all authenticated pages.
        
        This ensures the navbar is consistent across the app.
        """
        # Setup: Create authenticated user and client
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        # Test multiple authenticated pages
        authenticated_pages = [
            get_dashboard_url("phones"),  # Dashboard
            "/inventory/list/",            # Stock list
            "/inventory/scan-in/",         # Stock in
        ]
        
        for url in authenticated_pages:
            if not url:
                continue
            
            response = client.get(url, follow=True)
            
            # Skip if page doesn't exist or redirects to login
            if response.status_code == 404:
                continue
            if "login" in response.request.get("PATH_INFO", ""):
                continue
            
            # If we got a successful response, check navbar elements
            if response.status_code == 200:
                html = response.content.decode("utf-8")
                
                # Assert core navbar test hooks are present
                assert 'data-testid="nav-notifications"' in html or 'data-testid="nav-avatar"' in html, (
                    f"Page {url} is missing navbar test hooks. "
                    f"The navbar should be consistent across all authenticated pages."
                )
    
    def test_navbar_resilient_to_template_refactoring(self):
        """
        Regression guard: Navbar must remain stable across template refactoring.
        
        This test checks for the presence of navbar elements using multiple
        detection methods to ensure resilience.
        """
        # Setup: Create authenticated user and client
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        # Get phones dashboard URL
        dashboard_url = get_dashboard_url("phones")
        assert dashboard_url, "Phones dashboard URL must be configured"
        
        # Make request
        response = client.get(dashboard_url)
        assert response.status_code == 200
        
        # Get HTML content
        html = response.content.decode("utf-8")
        
        # Check for navbar using multiple detection methods
        # (This makes the test resilient to minor template changes)
        
        # Method 1: Check for test hooks
        has_testids = (
            'data-testid="nav-notifications"' in html or
            'data-testid="nav-avatar"' in html
        )
        
        # Method 2: Check for IDs
        has_ids = (
            'id="cc-bell"' in html or
            'id="ccUserBtn"' in html or
            'id="notificationDropdown"' in html
        )
        
        # Method 3: Check for navbar container classes
        has_navbar = (
            'cc-topbar' in html or
            'cc-topnav' in html or
            'navbar' in html
        )
        
        # At least two detection methods should succeed
        detection_count = sum([has_testids, has_ids, has_navbar])
        assert detection_count >= 2, (
            f"Navbar detection failed. Only {detection_count}/3 detection methods succeeded. "
            f"This could indicate a template regression or missing navbar. "
            f"Testids: {has_testids}, IDs: {has_ids}, Navbar: {has_navbar}"
        )

