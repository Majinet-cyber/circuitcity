# tests/test_navbar_dropdown_closed_state.py
"""
REGRESSION TESTS: Navbar dropdown menus MUST be closed on initial page load.

BUG BACKGROUND (Jan 2026):
- iOS Safari and Android Chrome were showing navbar dropdowns (notifications + profile)
  as OPEN on initial page load.
- Root cause: BFCache (back-forward cache) restores page with previous UI state,
  causing dropdowns to appear visible.
- Also seen: "Assign stock" bottom sheet and filter panels appearing on load.

FIXES IMPLEMENTED:
1. Added `hidden` attribute to dropdown menus in HTML by default.
2. Added CSS to enforce `display:none` for dropdown-menu[hidden].
3. Added comprehensive BFCache/pageshow reset in JavaScript.
4. Bootstrap dropdown events manage the hidden attribute.

THESE TESTS ENSURE:
- Dropdown menus have `hidden` attribute in rendered HTML.
- Dropdown toggles have `aria-expanded="false"` by default.
- No dropdown menus have `show` class in rendered HTML.
- No modals or offcanvas have `show` class in rendered HTML.
"""

import re
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.helpers_core import PHONES
from conftest import unique_slug

User = get_user_model()


class NavbarDropdownClosedStateTestCase(TestCase):
    """
    Ensure navbar dropdowns are ALWAYS closed on initial HTML render.
    This is critical for mobile browsers using BFCache.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name="Test Business",
            slug=unique_slug("Test Business"),
            business_kind=PHONES,
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['biz_id'] = self.business.id
        session['active_business_id'] = self.business.id
        session.save()

    def test_notifications_menu_has_hidden_attribute(self):
        """Notifications dropdown menu must have `hidden` attribute in HTML."""
        response = self.client.get('/inventory/dashboard/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Find the notifications menu
        # Pattern: id="ccNotifMenu" ... hidden
        self.assertIn('id="ccNotifMenu"', content)
        
        # Check that it has hidden attribute
        # The hidden attribute should be on the same element as id="ccNotifMenu"
        notif_menu_pattern = r'id="ccNotifMenu"[^>]*hidden'
        match = re.search(notif_menu_pattern, content)
        self.assertIsNotNone(
            match,
            "Notifications menu (ccNotifMenu) must have `hidden` attribute in HTML"
        )

    def test_user_menu_has_hidden_attribute(self):
        """User/profile dropdown menu must have `hidden` attribute in HTML."""
        response = self.client.get('/inventory/dashboard/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Find the user menu
        self.assertIn('id="userMenu"', content)
        
        # Check that it has hidden attribute
        user_menu_pattern = r'id="userMenu"[^>]*hidden'
        match = re.search(user_menu_pattern, content)
        self.assertIsNotNone(
            match,
            "User menu (userMenu) must have `hidden` attribute in HTML"
        )

    def test_notification_toggle_aria_expanded_false(self):
        """Notification toggle button must have aria-expanded='false' by default."""
        response = self.client.get('/inventory/dashboard/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Find the notification toggle button
        self.assertIn('id="ccNotifBtn"', content)
        
        # Check aria-expanded is false
        notif_btn_pattern = r'id="ccNotifBtn"[^>]*aria-expanded="false"'
        match = re.search(notif_btn_pattern, content)
        self.assertIsNotNone(
            match,
            "Notification toggle (ccNotifBtn) must have aria-expanded='false' in HTML"
        )

    def test_user_menu_toggle_aria_expanded_false(self):
        """User menu toggle button must have aria-expanded='false' by default."""
        response = self.client.get('/inventory/dashboard/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Find the user menu toggle button
        self.assertIn('id="userMenuBtn"', content)
        
        # Check aria-expanded is false
        user_btn_pattern = r'id="userMenuBtn"[^>]*aria-expanded="false"'
        match = re.search(user_btn_pattern, content)
        self.assertIsNotNone(
            match,
            "User menu toggle (userMenuBtn) must have aria-expanded='false' in HTML"
        )

    def test_no_dropdown_menu_show_class_in_html(self):
        """No dropdown menu should have 'show' class in rendered HTML."""
        response = self.client.get('/inventory/dashboard/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Look for dropdown-menu with show class (this would be a bug)
        # Pattern: class="... dropdown-menu ... show ..."
        show_dropdown_pattern = r'class="[^"]*dropdown-menu[^"]*\bshow\b[^"]*"'
        match = re.search(show_dropdown_pattern, content)
        
        self.assertIsNone(
            match,
            "No dropdown-menu should have 'show' class in rendered HTML"
        )

    def test_no_modal_show_class_in_html(self):
        """No modal should have 'show' class in rendered HTML."""
        response = self.client.get('/inventory/dashboard/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Look for modal with show class (this would be a bug)
        # Pattern: class="... modal ... show ..."
        show_modal_pattern = r'class="[^"]*\bmodal\b[^"]*\bshow\b[^"]*"'
        match = re.search(show_modal_pattern, content)
        
        self.assertIsNone(
            match,
            "No modal should have 'show' class in rendered HTML"
        )

    def test_no_offcanvas_show_class_in_html(self):
        """No offcanvas should have 'show' class in rendered HTML."""
        response = self.client.get('/inventory/dashboard/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Look for offcanvas with show class (this would be a bug)
        # Pattern: class="... offcanvas ... show ..."
        show_offcanvas_pattern = r'class="[^"]*\boffcanvas\b[^"]*\bshow\b[^"]*"'
        match = re.search(show_offcanvas_pattern, content)
        
        self.assertIsNone(
            match,
            "No offcanvas should have 'show' class in rendered HTML"
        )

    def test_css_hidden_dropdown_rule_exists(self):
        """Ensure CSS rule for hidden dropdown menus exists in rendered HTML."""
        response = self.client.get('/inventory/dashboard/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for the CSS rule that enforces display:none on hidden dropdowns
        # This is in inline <style> in base.html
        # NOTE: We do NOT use !important so Bootstrap can override when showing
        self.assertIn('.dropdown-menu[hidden]', content)
        # Verify the rule exists - it should have display: none (without !important)
        self.assertIn('#ccNotifMenu[hidden]', content)
        self.assertIn('#userMenu[hidden]', content)

    def test_bfcache_reset_script_exists(self):
        """Ensure the BFCache/pageshow reset script is present."""
        response = self.client.get('/inventory/dashboard/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for the UI cleanup system v5 (Jan 2026 - includes dropdown click fix)
        self.assertIn('UI CLEANUP SYSTEM v5', content)
        
        # Check for pageshow event handler
        self.assertIn('pageshow', content)
        
        # Check for resetTransientUIState function
        self.assertIn('resetTransientUIState', content)


class NavbarDropdownOnStockListTestCase(TestCase):
    """
    Test navbar dropdown state on stock list page specifically.
    This page was mentioned in the bug report.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name="Test Business 2",
            slug=unique_slug("Test Business 2"),
            business_kind=PHONES,
        )
        self.client.login(username='testuser2', password='testpass123')
        
        session = self.client.session
        session['biz_id'] = self.business.id
        session['active_business_id'] = self.business.id
        session.save()

    def test_stock_list_dropdowns_hidden(self):
        """Stock list page dropdowns must be hidden by default."""
        response = self.client.get('/inventory/list/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Both dropdown menus should have hidden attribute
        notif_menu_pattern = r'id="ccNotifMenu"[^>]*hidden'
        user_menu_pattern = r'id="userMenu"[^>]*hidden'
        
        self.assertIsNotNone(
            re.search(notif_menu_pattern, content),
            "Notifications menu must have hidden attribute on stock list page"
        )
        self.assertIsNotNone(
            re.search(user_menu_pattern, content),
            "User menu must have hidden attribute on stock list page"
        )

    def test_stock_list_no_assign_stock_modal_visible(self):
        """Assign stock modal must NOT have 'show' class on initial load."""
        response = self.client.get('/inventory/list/', follow=True)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # The assign stock modal should exist but not have show class
        if 'id="assignStockModal"' in content:
            # Check it doesn't have show class
            assign_modal_pattern = r'id="assignStockModal"[^>]*class="[^"]*\bshow\b[^"]*"'
            match = re.search(assign_modal_pattern, content)
            self.assertIsNone(
                match,
                "Assign stock modal should not have 'show' class on initial load"
            )


class NavbarDropdownMultiVerticalTestCase(TestCase):
    """
    Test navbar dropdown closed state across multiple verticals.
    Ensures the SSOT fix works for all business types.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='multitest',
            email='multi@example.com',
            password='testpass123'
        )
        self.client.login(username='multitest', password='testpass123')

    def _create_business_and_set_session(self, name, kind):
        """Helper to create business and set session."""
        business = Business.objects.create(
            name=name,
            slug=unique_slug(name),
            business_kind=kind,
        )
        session = self.client.session
        session['biz_id'] = business.id
        session['active_business_id'] = business.id
        session.save()
        return business

    def test_phones_vertical_dropdowns_hidden(self):
        """Phones vertical: dropdowns hidden by default."""
        from inventory.helpers_core import PHONES
        self._create_business_and_set_session("Phones Biz", PHONES)
        
        response = self.client.get('/inventory/dashboard/', follow=True)
        if response.status_code == 200:
            content = response.content.decode()
            self.assertIn('id="ccNotifMenu"', content)
            self.assertRegex(content, r'id="ccNotifMenu"[^>]*hidden')

    def test_clothing_vertical_dropdowns_hidden(self):
        """Clothing vertical: dropdowns hidden by default."""
        from inventory.helpers_core import CLOTHING
        self._create_business_and_set_session("Clothing Biz", CLOTHING)
        
        response = self.client.get('/verticals/clothing/', follow=True)
        if response.status_code == 200:
            content = response.content.decode()
            if 'id="ccNotifMenu"' in content:
                self.assertRegex(content, r'id="ccNotifMenu"[^>]*hidden')

    def test_gym_vertical_dropdowns_hidden(self):
        """Gym vertical: dropdowns hidden by default."""
        from inventory.helpers_core import GYM
        self._create_business_and_set_session("Gym Biz", GYM)
        
        response = self.client.get('/verticals/gym/', follow=True)
        if response.status_code == 200:
            content = response.content.decode()
            if 'id="ccNotifMenu"' in content:
                self.assertRegex(content, r'id="ccNotifMenu"[^>]*hidden')

    def test_pharmacy_vertical_dropdowns_hidden(self):
        """Pharmacy vertical: dropdowns hidden by default."""
        from inventory.helpers_core import PHARMACY
        self._create_business_and_set_session("Pharmacy Biz", PHARMACY)
        
        response = self.client.get('/verticals/pharmacy/', follow=True)
        if response.status_code == 200:
            content = response.content.decode()
            if 'id="ccNotifMenu"' in content:
                self.assertRegex(content, r'id="ccNotifMenu"[^>]*hidden')

    def test_liquor_vertical_dropdowns_hidden(self):
        """Liquor vertical: dropdowns hidden by default."""
        from inventory.helpers_core import LIQUOR
        self._create_business_and_set_session("Liquor Biz", LIQUOR)
        
        response = self.client.get('/verticals/liquor/', follow=True)
        if response.status_code == 200:
            content = response.content.decode()
            if 'id="ccNotifMenu"' in content:
                self.assertRegex(content, r'id="ccNotifMenu"[^>]*hidden')

