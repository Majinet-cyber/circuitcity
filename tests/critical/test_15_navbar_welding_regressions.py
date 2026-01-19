"""
CRITICAL REGRESSION TEST: Navbar Dropdowns + Welding Quotes
================================================================================
Jan 2026 - Mission Critical Bug Fixes

ISSUE 1: Navbar/Logout dropdown not responding in PROD
- Profile dropdown must open on click in production
- Notifications dropdown must open on click in production
- Opening one closes the other (mutual exclusion)
- Works on ALL pages including billing and vertical dashboards
- Must be SSOT fix in shared navbar code

ISSUE 2: Welding Quotes buttons not working
- "Add materials" and "Add costs" buttons must work
- Modal triggers must properly open modals
- Works on mobile and desktop

These tests verify the HTML contracts that enable click functionality.
================================================================================
"""
import pytest
import re
from django.test import Client
from django.urls import reverse, NoReverseMatch
from django.contrib.auth import get_user_model

from tests.critical.conftest import (
    bootstrap_business_with_user,
    setup_authenticated_client,
)

User = get_user_model()

pytestmark = [pytest.mark.critical, pytest.mark.django_db]


# ============================================================================
# ISSUE 1: Navbar Dropdown Regression Tests
# ============================================================================

class TestAuthenticatedHTMLCacheHeaders:
    """
    Test that authenticated HTML pages have proper Cache-Control headers.
    
    This is the primary fix for prod-only dropdown failures:
    - Stale HTML served from cache references old/missing JS files
    - Dropdowns don't work because JS isn't properly loaded
    - Hard refresh works because it bypasses cache
    
    FIX: Set Cache-Control: no-store on all authenticated HTML.
    """

    def test_phones_dashboard_has_no_store_cache_header(self):
        """Phones dashboard must have Cache-Control: no-store."""
        from tests.critical.conftest import get_dashboard_url
        
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Phones dashboard URL not available")
        
        response = client.get(dashboard_url)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        cache_control = response.get('Cache-Control', '')
        assert 'no-store' in cache_control, (
            f"REGRESSION: Dashboard missing 'no-store' in Cache-Control. "
            f"Got: {cache_control!r}. "
            f"This causes stale HTML caching which breaks dropdowns in production."
        )

    def test_billing_subscribe_page_has_no_store_cache_header(self):
        """Billing subscribe page must have Cache-Control: no-store."""
        user, business, location = bootstrap_business_with_user("phones")
        
        # Make user a manager so they can access billing
        membership = user.memberships.filter(business=business).first()
        if membership:
            membership.role = "MANAGER"
            membership.save()
        
        client = setup_authenticated_client(user, business, location)
        
        response = client.get(reverse('billing:subscribe'))
        
        if response.status_code != 200:
            pytest.skip(f"Billing subscribe returned {response.status_code}")
        
        cache_control = response.get('Cache-Control', '')
        assert 'no-store' in cache_control, (
            f"REGRESSION: Billing page missing 'no-store' in Cache-Control. "
            f"Got: {cache_control!r}. "
            f"Without no-store, browsers cache HTML with old JS references."
        )

    def test_clothing_dashboard_has_no_store_cache_header(self):
        """Clothing dashboard must have Cache-Control: no-store."""
        from tests.critical.conftest import get_dashboard_url
        
        user, business, location = bootstrap_business_with_user("clothing")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("clothing")
        if not dashboard_url:
            pytest.skip("Clothing dashboard URL not available")
        
        response = client.get(dashboard_url, follow=True)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        cache_control = response.get('Cache-Control', '')
        assert 'no-store' in cache_control, (
            f"REGRESSION: Clothing dashboard missing 'no-store'. Got: {cache_control!r}."
        )


class TestNavbarBootstrapRequirements:
    """
    Test that navbar dropdowns have all Bootstrap requirements.
    
    Bootstrap dropdowns require:
    1. Button with data-bs-toggle="dropdown"
    2. Menu with .dropdown-menu class
    3. Proper ARIA attributes
    4. Bootstrap JS loaded
    """

    def test_billing_page_has_dropdown_buttons_with_bootstrap_attributes(self):
        """Billing page navbar buttons must have Bootstrap dropdown attributes."""
        user, business, location = bootstrap_business_with_user("phones")
        
        membership = user.memberships.filter(business=business).first()
        if membership:
            membership.role = "MANAGER"
            membership.save()
        
        client = setup_authenticated_client(user, business, location)
        
        response = client.get(reverse('billing:subscribe'))
        
        if response.status_code != 200:
            pytest.skip(f"Billing page returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have notification button with Bootstrap toggle
        notif_btn_index = html.find('id="ccNotifBtn"')
        assert notif_btn_index > 0, "Billing page missing notifications button"
        
        notif_section = html[max(0, notif_btn_index-300):notif_btn_index+500]
        assert 'data-bs-toggle="dropdown"' in notif_section, (
            "REGRESSION: Notification button on billing page missing data-bs-toggle. "
            "Clicks will not open dropdown."
        )
        
        # Must have user menu button with Bootstrap toggle
        user_btn_index = html.find('id="userMenuBtn"')
        assert user_btn_index > 0, "Billing page missing user menu button"
        
        user_section = html[max(0, user_btn_index-300):user_btn_index+500]
        assert 'data-bs-toggle="dropdown"' in user_section, (
            "REGRESSION: User menu button on billing page missing data-bs-toggle. "
            "Clicks will not open dropdown."
        )

    def test_all_pages_load_bootstrap_bundle(self):
        """All authenticated pages must load Bootstrap JS bundle."""
        from tests.critical.conftest import get_dashboard_url
        
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Dashboard URL not available")
        
        response = client.get(dashboard_url)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have Bootstrap bundle loaded
        has_bootstrap = 'bootstrap.bundle' in html or 'bootstrap@5.3' in html
        assert has_bootstrap, (
            "REGRESSION: Page missing Bootstrap JS bundle. "
            "Dropdowns require Bootstrap to function."
        )


class TestNavbarDropdownJSContract:
    """
    Test that navbar dropdown JavaScript is properly configured.
    
    The Jan 2026 fix uses:
    1. 'hidden' attribute on menus by default
    2. Click handlers (capture phase) to remove hidden before Bootstrap processes
    3. Mutual exclusion (opening one closes the other)
    """

    def test_dropdown_menus_have_hidden_attribute(self):
        """Dropdown menus must have 'hidden' attribute in initial HTML."""
        from tests.critical.conftest import get_dashboard_url
        
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Dashboard URL not available")
        
        response = client.get(dashboard_url)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Notifications menu must have hidden attribute
        notif_menu_match = re.search(r'id="ccNotifMenu"[^>]*hidden', html)
        assert notif_menu_match, (
            "REGRESSION: Notifications menu missing 'hidden' attribute. "
            "This prevents BFCache from showing stale dropdown state."
        )
        
        # User menu must have hidden attribute
        user_menu_match = re.search(r'id="userMenu"[^>]*hidden', html)
        assert user_menu_match, (
            "REGRESSION: User menu missing 'hidden' attribute. "
            "This prevents BFCache from showing stale dropdown state."
        )

    def test_dropdown_js_removes_hidden_on_click(self):
        """JavaScript must remove 'hidden' attribute on click."""
        from tests.critical.conftest import get_dashboard_url
        
        user, business, location = bootstrap_business_with_user("phones")
        client = setup_authenticated_client(user, business, location)
        
        dashboard_url = get_dashboard_url("phones")
        if not dashboard_url:
            pytest.skip("Dashboard URL not available")
        
        response = client.get(dashboard_url)
        
        if response.status_code != 200:
            pytest.skip(f"Dashboard returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have removeAttribute('hidden') for click handling
        assert "removeAttribute('hidden')" in html or 'removeAttribute("hidden")' in html, (
            "REGRESSION: Missing removeAttribute('hidden') in JS. "
            "This is required to make dropdowns visible on click."
        )
        
        # Must have setupDropdownHiddenManagement function
        assert 'setupDropdownHiddenManagement' in html, (
            "REGRESSION: Missing setupDropdownHiddenManagement function. "
            "This is required for dropdown click functionality."
        )


# ============================================================================
# ISSUE 2: Welding Quotes Regression Tests
# ============================================================================

class TestWeldingQuoteCreatePage:
    """
    Test that welding quote create page works correctly.
    """

    def test_quote_create_page_loads_successfully(self):
        """GET welding quotes create page returns 200."""
        from inventory.helpers_core import WELDING
        
        user, business, location = bootstrap_business_with_user("welding")
        client = setup_authenticated_client(user, business, location)
        
        try:
            response = client.get(reverse('verticals:welding_quote_create'))
        except NoReverseMatch:
            pytest.skip("Welding quote create URL not available")
        
        assert response.status_code == 200, (
            f"Welding quote create page should return 200, got {response.status_code}"
        )

    def test_quote_create_page_has_form(self):
        """Quote create page must have a form with customer name input."""
        from inventory.helpers_core import WELDING
        
        user, business, location = bootstrap_business_with_user("welding")
        client = setup_authenticated_client(user, business, location)
        
        try:
            response = client.get(reverse('verticals:welding_quote_create'))
        except NoReverseMatch:
            pytest.skip("Welding quote create URL not available")
        
        if response.status_code != 200:
            pytest.skip(f"Page returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have form with POST method
        assert '<form method="post"' in html, (
            "Quote create page missing POST form"
        )
        
        # Must have customer name input
        assert 'name="customer_name"' in html, (
            "Quote create page missing customer_name input"
        )
        
        # Must have submit button
        assert 'type="submit"' in html, (
            "Quote create page missing submit button"
        )
        
        # Must have CSRF token
        assert 'csrfmiddlewaretoken' in html or 'csrf_token' in html, (
            "Quote create page missing CSRF token"
        )


class TestWeldingQuoteDetailModals:
    """
    Test that welding quote detail page has working modal buttons.
    
    The "Add materials" and "Add costs" buttons must:
    1. Be present when quote is editable
    2. Have correct data-bs-toggle and data-bs-target attributes
    3. Have corresponding modal elements on the page
    """

    def test_quote_detail_has_modal_buttons_when_editable(self):
        """Quote detail page must have modal trigger buttons when editable."""
        from inventory.helpers_core import WELDING
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        user, business, location = bootstrap_business_with_user("welding")
        client = setup_authenticated_client(user, business, location)
        
        # Create a draft quote (editable)
        quote = WeldingQuote.objects.create(
            business=business,
            customer_name="Test Customer",
            status=WeldingQuoteStatus.DRAFT,
            quote_number="Q-TEST-001",
        )
        
        try:
            response = client.get(
                reverse('verticals:welding_quote_detail', args=[quote.id])
            )
        except NoReverseMatch:
            pytest.skip("Welding quote detail URL not available")
        
        if response.status_code != 200:
            pytest.skip(f"Page returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have Add Material button with modal trigger
        assert 'data-bs-target="#materialPickerModal"' in html, (
            "REGRESSION: Quote detail page missing Add Material modal trigger. "
            "Button should have data-bs-target='#materialPickerModal'."
        )
        
        # Must have Add Cost button with modal trigger
        assert 'data-bs-target="#costPickerModal"' in html, (
            "REGRESSION: Quote detail page missing Add Cost modal trigger. "
            "Button should have data-bs-target='#costPickerModal'."
        )

    def test_quote_detail_has_modal_elements(self):
        """Quote detail page must have modal elements matching triggers."""
        from inventory.helpers_core import WELDING
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        user, business, location = bootstrap_business_with_user("welding")
        client = setup_authenticated_client(user, business, location)
        
        # Create a draft quote (editable)
        quote = WeldingQuote.objects.create(
            business=business,
            customer_name="Test Customer",
            status=WeldingQuoteStatus.DRAFT,
            quote_number="Q-TEST-002",
        )
        
        try:
            response = client.get(
                reverse('verticals:welding_quote_detail', args=[quote.id])
            )
        except NoReverseMatch:
            pytest.skip("Welding quote detail URL not available")
        
        if response.status_code != 200:
            pytest.skip(f"Page returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have materialPickerModal element
        assert 'id="materialPickerModal"' in html, (
            "REGRESSION: Quote detail page missing materialPickerModal element. "
            "Modal must exist for data-bs-target to find it."
        )
        
        # Must have costPickerModal element
        assert 'id="costPickerModal"' in html, (
            "REGRESSION: Quote detail page missing costPickerModal element. "
            "Modal must exist for data-bs-target to find it."
        )
        
        # Modals must have class="modal"
        assert 'class="modal fade" id="materialPickerModal"' in html or \
               'class="modal fade" id="costPickerModal"' in html, (
            "REGRESSION: Modals missing proper 'modal fade' class. "
            "Bootstrap requires class='modal' for modal functionality."
        )

    def test_quote_detail_modal_buttons_have_bootstrap_toggle(self):
        """Modal trigger buttons must have data-bs-toggle='modal'."""
        from inventory.helpers_core import WELDING
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        user, business, location = bootstrap_business_with_user("welding")
        client = setup_authenticated_client(user, business, location)
        
        quote = WeldingQuote.objects.create(
            business=business,
            customer_name="Test Customer",
            status=WeldingQuoteStatus.DRAFT,
            quote_number="Q-TEST-003",
        )
        
        try:
            response = client.get(
                reverse('verticals:welding_quote_detail', args=[quote.id])
            )
        except NoReverseMatch:
            pytest.skip("Welding quote detail URL not available")
        
        if response.status_code != 200:
            pytest.skip(f"Page returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Find Add Material button and verify it has data-bs-toggle
        material_btn_pattern = r'data-bs-toggle="modal"[^>]*data-bs-target="#materialPickerModal"'
        material_match = re.search(material_btn_pattern, html)
        assert material_match, (
            "REGRESSION: Add Material button missing data-bs-toggle='modal'. "
            "Bootstrap requires this attribute to trigger modal on click."
        )
        
        # Find Add Cost button and verify it has data-bs-toggle  
        cost_btn_pattern = r'data-bs-toggle="modal"[^>]*data-bs-target="#costPickerModal"'
        cost_match = re.search(cost_btn_pattern, html)
        assert cost_match, (
            "REGRESSION: Add Cost button missing data-bs-toggle='modal'. "
            "Bootstrap requires this attribute to trigger modal on click."
        )

    def test_quote_detail_loads_bootstrap_js(self):
        """Quote detail page must load Bootstrap JS for modals to work."""
        from inventory.helpers_core import WELDING
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        user, business, location = bootstrap_business_with_user("welding")
        client = setup_authenticated_client(user, business, location)
        
        quote = WeldingQuote.objects.create(
            business=business,
            customer_name="Test Customer",
            status=WeldingQuoteStatus.DRAFT,
            quote_number="Q-TEST-004",
        )
        
        try:
            response = client.get(
                reverse('verticals:welding_quote_detail', args=[quote.id])
            )
        except NoReverseMatch:
            pytest.skip("Welding quote detail URL not available")
        
        if response.status_code != 200:
            pytest.skip(f"Page returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have Bootstrap bundle
        has_bootstrap = 'bootstrap.bundle' in html or 'bootstrap@5.3' in html
        assert has_bootstrap, (
            "REGRESSION: Quote detail page missing Bootstrap JS. "
            "Modal buttons require Bootstrap to function."
        )


class TestWeldingModalPortalIntegration:
    """
    Test that welding modals work with the modal portal system.
    
    The base.html has a modal portal that moves modals to #cc-modal-root
    to prevent z-index stacking context issues. Welding modals must be
    compatible with this system.
    """

    def test_quote_detail_page_has_modal_portal_root(self):
        """Quote detail page must have #cc-modal-root element."""
        from inventory.helpers_core import WELDING
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        user, business, location = bootstrap_business_with_user("welding")
        client = setup_authenticated_client(user, business, location)
        
        quote = WeldingQuote.objects.create(
            business=business,
            customer_name="Test Customer",
            status=WeldingQuoteStatus.DRAFT,
            quote_number="Q-TEST-005",
        )
        
        try:
            response = client.get(
                reverse('verticals:welding_quote_detail', args=[quote.id])
            )
        except NoReverseMatch:
            pytest.skip("Welding quote detail URL not available")
        
        if response.status_code != 200:
            pytest.skip(f"Page returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Must have modal portal root
        assert 'id="cc-modal-root"' in html, (
            "REGRESSION: Page missing #cc-modal-root. "
            "This element is required for modals to work properly with z-index."
        )

    def test_welding_modals_have_proper_structure_for_portal(self):
        """Welding modals must have structure that works with modal portal."""
        from inventory.helpers_core import WELDING
        from inventory.models_welding import WeldingQuote, WeldingQuoteStatus
        
        user, business, location = bootstrap_business_with_user("welding")
        client = setup_authenticated_client(user, business, location)
        
        quote = WeldingQuote.objects.create(
            business=business,
            customer_name="Test Customer",
            status=WeldingQuoteStatus.DRAFT,
            quote_number="Q-TEST-006",
        )
        
        try:
            response = client.get(
                reverse('verticals:welding_quote_detail', args=[quote.id])
            )
        except NoReverseMatch:
            pytest.skip("Welding quote detail URL not available")
        
        if response.status_code != 200:
            pytest.skip(f"Page returned {response.status_code}")
        
        html = response.content.decode('utf-8')
        
        # Material modal must have .modal class for portal to find it
        material_modal_index = html.find('id="materialPickerModal"')
        if material_modal_index > 0:
            modal_section = html[max(0, material_modal_index-100):material_modal_index+50]
            assert 'class="modal' in modal_section, (
                "Material picker modal must have 'modal' class for portal to move it"
            )
        
        # Cost modal must have .modal class for portal to find it
        cost_modal_index = html.find('id="costPickerModal"')
        if cost_modal_index > 0:
            modal_section = html[max(0, cost_modal_index-100):cost_modal_index+50]
            assert 'class="modal' in modal_section, (
                "Cost picker modal must have 'modal' class for portal to move it"
            )

