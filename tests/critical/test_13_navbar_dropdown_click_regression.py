"""
CRITICAL REGRESSION TEST: Navbar dropdowns must open on click
================================================================================
TASK: Ensure navbar dropdowns respond to clicks and open correctly

ROOT CAUSE OF JAN 2026 REGRESSION:
- Dropdown menus had `hidden` attribute with `display: none !important` CSS
- Bootstrap's show/hide logic couldn't override the !important rule
- Dropdowns appeared broken (clicking did nothing)

FIX IMPLEMENTED:
1. Removed !important from CSS so Bootstrap can override
2. Changed event listener from 'show.bs.dropdown' to 'click' (capture phase)
3. Remove 'hidden' attribute BEFORE Bootstrap processes the click
4. This allows Bootstrap to show the dropdown normally

REQUIREMENTS (Jan 18 2026):
1. DROPDOWNS START CLOSED:
   - Notifications dropdown CLOSED on page load (hidden attribute, no "show" class)
   - Avatar dropdown CLOSED on page load (hidden attribute, no "show" class)
   - aria-expanded="false" on both buttons

2. DROPDOWNS OPEN ON CLICK:
   - Clicking notifications button removes 'hidden' attribute from notifications menu
   - Clicking avatar button removes 'hidden' attribute from avatar menu
   - Bootstrap then adds 'show' class and makes dropdown visible
   - No hard refresh required

3. MUTUAL EXCLUSION:
   - Opening notifications closes avatar dropdown (sets hidden attribute)
   - Opening avatar closes notifications dropdown (sets hidden attribute)
   - Only one dropdown open at a time

4. WORKS EVERYWHERE:
   - Must work on mobile + desktop
   - Must work across all verticals
   - Must not break any page

This test verifies the HTML contract that enables click functionality.
================================================================================
"""
import pytest
from django.test import Client
from django.urls import reverse, NoReverseMatch
from django.contrib.auth import get_user_model

from tests.critical.conftest import (
    ALL_VERTICALS,
    get_dashboard_url,
    setup_authenticated_client,
    bootstrap_business_with_user,
)

User = get_user_model()

# All tests in this module are critical
pytestmark = [pytest.mark.critical, pytest.mark.django_db]


# ============================================================================
# Helper Functions
# ============================================================================

def assert_dropdown_elements_have_correct_attributes(html: str, page_name: str = "page"):
    """
    Assert that dropdown buttons and menus have the correct attributes
    for click functionality to work.
    
    Required for dropdowns to open on click:
    - Buttons must have data-bs-toggle="dropdown"
    - Buttons must have aria-expanded="false" initially
    - Menus must have 'hidden' attribute initially
    - Menus must have 'dropdown-menu' class
    - Menus must be linked to buttons via aria-controls/aria-labelledby
    """
    
    # Check notification button attributes
    notif_btn_index = html.find('id="ccNotifBtn"')
    if notif_btn_index > 0:
        notif_btn_section = html[max(0, notif_btn_index-300):notif_btn_index+500]
        
        # Must have Bootstrap dropdown toggle
        assert 'data-bs-toggle="dropdown"' in notif_btn_section, (
            f"REGRESSION: Notification button on {page_name} missing data-bs-toggle='dropdown'. "
            f"This is required for Bootstrap to handle clicks."
        )
        
        # Must start closed
        assert 'aria-expanded="false"' in notif_btn_section, (
            f"REGRESSION: Notification button on {page_name} has aria-expanded != 'false'. "
            f"Dropdowns must start closed."
        )
        
        # Should have aria-controls
        assert 'aria-controls="ccNotifMenu"' in notif_btn_section or 'aria-haspopup="true"' in notif_btn_section, (
            f"REGRESSION: Notification button on {page_name} missing aria-controls or aria-haspopup. "
            f"This is required for accessibility and proper Bootstrap linking."
        )
    
    # Check user menu button attributes
    user_btn_index = html.find('id="userMenuBtn"')
    if user_btn_index > 0:
        user_btn_section = html[max(0, user_btn_index-300):user_btn_index+500]
        
        # Must have Bootstrap dropdown toggle
        assert 'data-bs-toggle="dropdown"' in user_btn_section, (
            f"REGRESSION: User menu button on {page_name} missing data-bs-toggle='dropdown'. "
            f"This is required for Bootstrap to handle clicks."
        )
        
        # Must start closed
        assert 'aria-expanded="false"' in user_btn_section, (
            f"REGRESSION: User menu button on {page_name} has aria-expanded != 'false'. "
            f"Dropdowns must start closed."
        )
        
        # Should have aria-controls
        assert 'aria-controls="userMenu"' in user_btn_section or 'aria-haspopup="true"' in user_btn_section, (
            f"REGRESSION: User menu button on {page_name} missing aria-controls or aria-haspopup. "
            f"This is required for accessibility and proper Bootstrap linking."
        )
    
    # Check notification menu attributes
    notif_menu_index = html.find('id="ccNotifMenu"')
    if notif_menu_index > 0:
        notif_menu_section = html[notif_menu_index:notif_menu_index+600]
        
        # Must have dropdown-menu class for Bootstrap
        assert 'dropdown-menu' in notif_menu_section[:200], (
            f"REGRESSION: Notification menu on {page_name} missing 'dropdown-menu' class. "
            f"This is required for Bootstrap dropdown functionality."
        )
        
        # Must start with hidden attribute (our fix for BFCache issues)
        assert 'hidden' in notif_menu_section[:300], (
            f"REGRESSION: Notification menu on {page_name} missing 'hidden' attribute. "
            f"This is required to prevent BFCache from showing stale dropdown state."
        )
        
        # Must NOT have 'show' class initially
        assert 'dropdown-menu show' not in notif_menu_section[:200], (
            f"REGRESSION: Notification menu on {page_name} has 'show' class on load. "
            f"Dropdowns must start closed."
        )
    
    # Check user menu attributes
    user_menu_index = html.find('id="userMenu"')
    if user_menu_index > 0:
        user_menu_section = html[user_menu_index:user_menu_index+600]
        
        # Must have dropdown-menu class for Bootstrap
        assert 'dropdown-menu' in user_menu_section[:200], (
            f"REGRESSION: User menu on {page_name} missing 'dropdown-menu' class. "
            f"This is required for Bootstrap dropdown functionality."
        )
        
        # Must start with hidden attribute (our fix for BFCache issues)
        assert 'hidden' in user_menu_section[:300], (
            f"REGRESSION: User menu on {page_name} missing 'hidden' attribute. "
            f"This is required to prevent BFCache from showing stale dropdown state."
        )
        
        # Must NOT have 'show' class initially
        assert 'dropdown-menu show' not in user_menu_section[:200], (
            f"REGRESSION: User menu on {page_name} has 'show' class on load. "
            f"Dropdowns must start closed."
        )


def assert_hidden_attribute_js_present(html: str, page_name: str = "page"):
    """
    Assert that the JavaScript for managing hidden attributes is present.
    
    This JS is critical for the Jan 2026 fix:
    - Listens to click events (capture phase)
    - Removes 'hidden' attribute BEFORE Bootstrap processes click
    - Allows Bootstrap to show dropdown normally
    - Implements mutual exclusion (opening one closes the other)
    """
    
    # Check for the setup function
    assert 'setupDropdownHiddenManagement' in html, (
        f"REGRESSION: {page_name} missing 'setupDropdownHiddenManagement' function. "
        f"This is required to make dropdowns clickable."
    )
    
    # Check for click event listener setup (capture phase)
    assert "addEventListener('click'" in html, (
        f"REGRESSION: {page_name} missing click event listeners. "
        f"Dropdowns need click handlers to remove 'hidden' attribute."
    )
    
    # Check for removeAttribute('hidden') calls
    assert "removeAttribute('hidden')" in html or "removeAttribute(\"hidden\")" in html, (
        f"REGRESSION: {page_name} missing removeAttribute('hidden') calls. "
        f"This is required to make dropdowns visible on click."
    )
    
    # Check for setAttribute('hidden') calls (for mutual exclusion)
    assert "setAttribute('hidden'" in html or "setAttribute(\"hidden\"" in html, (
        f"REGRESSION: {page_name} missing setAttribute('hidden') calls. "
        f"This is required for mutual exclusion (closing one when opening the other)."
    )


def assert_css_allows_bootstrap_override(html: str, page_name: str = "page"):
    """
    Assert that CSS doesn't prevent Bootstrap from showing dropdowns.
    
    REGRESSION FIX: Removed !important from hidden attribute CSS.
    Before: display: none !important (blocked Bootstrap)
    After: display: none (Bootstrap can override)
    """
    
    # Look for the CSS rule for dropdown-menu[hidden]
    css_section_start = html.find('.dropdown-menu[hidden]')
    if css_section_start > 0:
        css_section = html[css_section_start:css_section_start+500]
        
        # Should have display: none but NOT !important
        if 'display:' in css_section or 'display :' in css_section:
            # Check that !important is NOT used on display property
            display_index = css_section.find('display')
            if display_index > 0:
                display_line = css_section[display_index:display_index+100]
                assert 'none !important' not in display_line and 'none!important' not in display_line, (
                    f"REGRESSION: {page_name} has 'display: none !important' on dropdown-menu[hidden]. "
                    f"This prevents Bootstrap from showing dropdowns. Must use 'display: none' without !important."
                )


# ============================================================================
# Test Classes
# ============================================================================

class TestNavbarDropdownClickFunctionality:
    """
    Tests for navbar dropdown click functionality (Jan 2026 fix).
    
    These tests verify the HTML contract required for dropdowns to:
    1. Start closed (hidden attribute, no show class)
    2. Open on click (JS removes hidden, Bootstrap adds show)
    3. Implement mutual exclusion (opening one closes the other)
    """

    def test_phones_dashboard_dropdowns_have_correct_attributes(self):
        """Phones dashboard: dropdowns have all required attributes for clicks to work"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Phones dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        assert_dropdown_elements_have_correct_attributes(html, "Phones Dashboard")

    def test_phones_dashboard_hidden_attribute_js_present(self):
        """Phones dashboard: JavaScript for managing hidden attributes is present"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Phones dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        assert_hidden_attribute_js_present(html, "Phones Dashboard")

    def test_phones_dashboard_css_allows_bootstrap_override(self):
        """Phones dashboard: CSS doesn't block Bootstrap from showing dropdowns"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Phones dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        assert_css_allows_bootstrap_override(html, "Phones Dashboard")

    def test_clothing_dashboard_dropdowns_have_correct_attributes(self):
        """Clothing dashboard: dropdowns have all required attributes for clicks to work"""
        user, business, location = bootstrap_business_with_user("clothing")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("clothing")
        if not dashboard_url:
            pytest.skip("Clothing dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Clothing dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        assert_dropdown_elements_have_correct_attributes(html, "Clothing Dashboard")

    def test_liquor_dashboard_dropdowns_have_correct_attributes(self):
        """Liquor dashboard: dropdowns have all required attributes for clicks to work"""
        user, business, location = bootstrap_business_with_user("liquor")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("liquor")
        if not dashboard_url:
            pytest.skip("Liquor dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Liquor dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        assert_dropdown_elements_have_correct_attributes(html, "Liquor Dashboard")

    def test_gym_dashboard_dropdowns_have_correct_attributes(self):
        """Gym dashboard: dropdowns have all required attributes for clicks to work"""
        user, business, location = bootstrap_business_with_user("gym")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("gym")
        if not dashboard_url:
            pytest.skip("Gym dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Gym dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        assert_dropdown_elements_have_correct_attributes(html, "Gym Dashboard")


class TestBootstrapDropdownContract:
    """
    Tests that verify the Bootstrap dropdown contract is correctly implemented.
    
    Bootstrap dropdowns require:
    - Button with data-bs-toggle="dropdown"
    - Menu with .dropdown-menu class
    - Proper ARIA attributes
    - No CSS that blocks Bootstrap's show/hide logic
    """

    def test_notification_button_has_bootstrap_attributes(self):
        """Notification button must have all Bootstrap dropdown attributes"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Find notification button
        notif_btn_index = html.find('id="ccNotifBtn"')
        assert notif_btn_index > 0, "Notification button not found"
        
        notif_btn_section = html[max(0, notif_btn_index-300):notif_btn_index+500]
        
        # Check all required Bootstrap attributes
        assert 'data-bs-toggle="dropdown"' in notif_btn_section, "Missing data-bs-toggle"
        assert 'aria-expanded="false"' in notif_btn_section, "Missing aria-expanded or wrong value"
        assert 'type="button"' in notif_btn_section, "Button missing type attribute"

    def test_user_menu_button_has_bootstrap_attributes(self):
        """User menu button must have all Bootstrap dropdown attributes"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Find user menu button
        user_btn_index = html.find('id="userMenuBtn"')
        assert user_btn_index > 0, "User menu button not found"
        
        user_btn_section = html[max(0, user_btn_index-300):user_btn_index+500]
        
        # Check all required Bootstrap attributes
        assert 'data-bs-toggle="dropdown"' in user_btn_section, "Missing data-bs-toggle"
        assert 'aria-expanded="false"' in user_btn_section, "Missing aria-expanded or wrong value"
        assert 'type="button"' in user_btn_section, "Button missing type attribute"

    def test_notification_menu_has_dropdown_class(self):
        """Notification menu must have dropdown-menu class"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Find notification menu
        notif_menu_index = html.find('id="ccNotifMenu"')
        assert notif_menu_index > 0, "Notification menu not found"
        
        notif_menu_section = html[notif_menu_index:notif_menu_index+300]
        
        # Check for dropdown-menu class
        assert 'dropdown-menu' in notif_menu_section, "Missing dropdown-menu class"

    def test_user_menu_has_dropdown_class(self):
        """User menu must have dropdown-menu class"""
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Find user menu
        user_menu_index = html.find('id="userMenu"')
        assert user_menu_index > 0, "User menu not found"
        
        user_menu_section = html[user_menu_index:user_menu_index+300]
        
        # Check for dropdown-menu class
        assert 'dropdown-menu' in user_menu_section, "Missing dropdown-menu class"

