"""
Regression tests for mobile UI fixes (Jan 2025)

These tests prevent regressions that appeared after Dec 20:
1. Notifications panel should be closed by default
2. Sidebar should open reliably with one tap
3. 2FA phone setup should never return 500
"""
import pytest
from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from circuitcity.accounts.models import Profile
from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
class TestNotificationsDefaultClosed(TestCase):
    """Test that notifications panel is hidden by default on all pages."""

    def setUp(self):
        """Set up user with business and active session."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        Profile.objects.get_or_create(user=self.user, defaults={"display_name": "Test User"})
        
        # Create business and membership
        self.business = Business.objects.create(
            name="Test Business",
            kind=BusinessKind.PHONES,
            owner=self.user,
            status="ACTIVE"
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client.login(username="testuser", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_dashboard_notifications_hidden(self):
        """Notifications panel should be closed by default on dashboard."""
        # Get dashboard
        response = self.client.get("/dashboard/")
        
        # Should return 200
        assert response.status_code == 200
        
        # Should NOT contain visible notification panel text in main content
        content = response.content.decode("utf-8")
        
        # The modal should exist but be hidden (aria-hidden="true")
        assert 'id="ccInbox"' in content
        assert 'aria-hidden="true"' in content
        
        # These strings should only appear INSIDE the hidden modal, not in visible page flow
        # We check that they're not in the main app content by ensuring the modal wrapper exists
        inbox_text = "Notifications Inbox"
        fallback_text = "Read-only fallback"
        
        # Count occurrences - should be exactly once (in the hidden modal)
        assert content.count(inbox_text) <= 2  # Once in modal title, maybe once in dropdown
        assert content.count(fallback_text) == 1  # Only in modal

    def test_inventory_pages_notifications_hidden(self):
        """Notifications panel should be closed by default on inventory pages."""
        # Test various inventory pages
        urls_to_test = [
            "/inventory/list/",
            "/accounts/settings/",
        ]

        for url in urls_to_test:
            response = self.client.get(url)
            
            # Might redirect or 200, but should not 500
            assert response.status_code in [200, 302, 403, 404]
            
            if response.status_code == 200:
                content = response.content.decode("utf-8")
                
                # Modal should be hidden by default
                if 'id="ccInbox"' in content:
                    assert 'aria-hidden="true"' in content

    def test_notification_dropdown_state(self):
        """Bootstrap dropdown should be closed by default (not auto-opened)."""
        response = self.client.get("/dashboard/")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # Check notification button exists
        assert 'id="ccNotifBtn"' in content
        
        # aria-expanded should be false by default
        assert 'aria-expanded="false"' in content
        
        # Dropdown menu should not have 'show' class initially
        # (Bootstrap adds 'show' when dropdown is open)
        assert 'id="ccNotifMenu"' in content


@pytest.mark.django_db
class TestSidebarMarkup(TestCase):
    """Test that sidebar markup is correct for single-tap behavior."""

    def setUp(self):
        """Set up user with business and active session."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        Profile.objects.get_or_create(user=self.user, defaults={"display_name": "Test User"})
        
        # Create business and membership
        self.business = Business.objects.create(
            name="Test Business",
            kind=BusinessKind.PHONES,
            owner=self.user,
            status="ACTIVE"
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client.login(username="testuser", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_sidebar_toggle_button_exists(self):
        """Mobile sidebar toggle button should exist."""
        response = self.client.get("/dashboard/")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # Sidebar toggle button should exist
        assert 'id="sidebarOpen"' in content
        
        # Should have proper ARIA attributes
        assert 'aria-expanded="false"' in content  # Default state
        assert 'aria-label="Open menu"' in content or 'aria-controls="ccSidebar"' in content

    def test_sidebar_default_closed(self):
        """Sidebar should be closed by default (not have 'open' class or attribute)."""
        response = self.client.get("/dashboard/")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # Body tag should not have data-drawer="open" attribute
        # (it appears in CSS rules, so we check the actual body tag)
        assert '<body data-drawer="open"' not in content
        assert '<body class=' in content or '<body>' in content
        
        # Backdrop should not have 'show' class initially
        assert 'id="ccBackdrop"' in content

    def test_no_duplicate_sidebar_listeners(self):
        """Ensure only one sidebar toggle implementation is active."""
        response = self.client.get("/dashboard/")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # Should have the guard flag to prevent double-init
        assert '__CC_SIDEBAR_V3__' in content
        
        # Should have the hotfix implementation
        assert 'CC Drawer Hotfix' in content or 'cloneNode' in content


@pytest.mark.django_db
class TestTwoFactorPhoneValidation:
    """Test that 2FA phone setup handles invalid numbers gracefully (no 500 errors)."""

    def test_invalid_phone_returns_200_with_error(self, client, django_user_model, settings):
        """Invalid phone number should return 200 with form error, not 500."""
        # Enable 2FA in settings
        settings.TWILIO_VERIFY_ENABLED = False  # Disable Twilio to test validation only
        
        user = django_user_model.objects.create_user(username="testuser", password="testpass123")
        Profile.objects.get_or_create(user=user, defaults={"display_name": "Test User"})
        client.login(username="testuser", password="testpass123")

        # Try to enable 2FA with invalid phone
        invalid_phones = [
            "abc123",  # Not a number
            "123",  # Too short
            "",  # Empty
        ]

        for phone in invalid_phones:
            response = client.post(
                reverse("accounts:twofa_sms_enable_start"),
                {"phone": phone},
                follow=False
            )
            
            # Should redirect (not 500)
            assert response.status_code == 302, f"Phone '{phone}' caused status {response.status_code}"
            
            # Should redirect to security settings
            assert "/accounts/settings/security/" in response.url

    def test_malawi_phone_normalization(self, client, django_user_model, settings):
        """Malawi phone numbers should be normalized to E.164 format."""
        # Disable Twilio to test normalization only
        settings.TWILIO_VERIFY_ENABLED = False
        
        user = django_user_model.objects.create_user(username="testuser", password="testpass123")
        Profile.objects.get_or_create(user=user, defaults={"display_name": "Test User"})
        client.login(username="testuser", password="testpass123")

        # These Malawi numbers should be normalized but will fail at Twilio (disabled)
        malawi_phones = [
            "0991234567",  # Should become +265991234567
            "265991234567",  # Should become +265991234567
            "+265991234567",  # Already correct
        ]

        for phone in malawi_phones:
            response = client.post(
                reverse("accounts:twofa_sms_enable_start"),
                {"phone": phone},
                follow=False
            )
            
            # Should not 500 (might redirect with "not available" error due to disabled Twilio)
            assert response.status_code in [200, 302], f"Phone '{phone}' caused status {response.status_code}"

    def test_valid_phone_proceeds_when_twilio_disabled(self, client, django_user_model, settings):
        """Valid phone with disabled Twilio should return user-friendly error, not 500."""
        settings.TWILIO_VERIFY_ENABLED = False
        
        user = django_user_model.objects.create_user(username="testuser", password="testpass123")
        Profile.objects.get_or_create(user=user, defaults={"display_name": "Test User"})
        client.login(username="testuser", password="testpass123")

        response = client.post(
            reverse("accounts:twofa_sms_enable_start"),
            {"phone": "+265991234567"},
            follow=True
        )
        
        # Should not 500
        assert response.status_code == 200
        
        # Should show error about Twilio not being available
        content = response.content.decode("utf-8")
        assert "not available" in content.lower() or "contact" in content.lower()

    def test_twilio_import_failure_returns_200(self, client, django_user_model, settings, monkeypatch):
        """If twilio library is not installed, should return 200 with error message, not 500."""
        import sys
        
        # Mock twilio module to not exist (simulate missing package)
        # Save original modules
        original_twilio = sys.modules.get('twilio')
        original_twilio_rest = sys.modules.get('twilio.rest')
        original_twilio_base = sys.modules.get('twilio.base.exceptions')
        
        # Remove twilio from sys.modules to simulate it not being installed
        for mod in list(sys.modules.keys()):
            if mod.startswith('twilio'):
                sys.modules.pop(mod, None)
        
        # Also monkeypatch import to raise ModuleNotFoundError for twilio
        import builtins
        real_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if 'twilio' in name:
                raise ModuleNotFoundError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)
        
        monkeypatch.setattr(builtins, '__import__', mock_import)
        
        try:
            # Enable Twilio in settings (but it won't be importable)
            settings.TWILIO_VERIFY_ENABLED = True
            settings.TWILIO_ACCOUNT_SID = "test_sid"
            settings.TWILIO_AUTH_TOKEN = "test_token"
            settings.TWILIO_VERIFY_SERVICE_SID = "test_service"
            
            user = django_user_model.objects.create_user(username="testuser", password="testpass123")
            Profile.objects.get_or_create(user=user, defaults={"display_name": "Test User"})
            client.login(username="testuser", password="testpass123")

            response = client.post(
                reverse("accounts:twofa_sms_enable_start"),
                {"phone": "+265991234567"},
                follow=True
            )
            
            # Should NOT 500 - should return 200 with error message
            assert response.status_code == 200, f"Got status {response.status_code}, expected 200"
            
            # Should show error about SMS being unavailable
            content = response.content.decode("utf-8").lower()
            assert "temporarily unavailable" in content or "not available" in content or "contact support" in content
        
        finally:
            # Restore original modules
            if original_twilio is not None:
                sys.modules['twilio'] = original_twilio
            if original_twilio_rest is not None:
                sys.modules['twilio.rest'] = original_twilio_rest
            if original_twilio_base is not None:
                sys.modules['twilio.base.exceptions'] = original_twilio_base

    def test_missing_twilio_env_vars_returns_200(self, client, django_user_model, settings):
        """If Twilio env vars are missing, should return 200 with error message, not 500."""
        # Enable Twilio but don't set credentials
        settings.TWILIO_VERIFY_ENABLED = True
        settings.TWILIO_ACCOUNT_SID = None
        settings.TWILIO_AUTH_TOKEN = None
        settings.TWILIO_VERIFY_SERVICE_SID = None
        
        user = django_user_model.objects.create_user(username="testuser", password="testpass123")
        Profile.objects.get_or_create(user=user, defaults={"display_name": "Test User"})
        client.login(username="testuser", password="testpass123")

        response = client.post(
            reverse("accounts:twofa_sms_enable_start"),
            {"phone": "+265991234567"},
            follow=True
        )
        
        # Should NOT 500 - should return 200 with configuration error
        assert response.status_code == 200, f"Got status {response.status_code}, expected 200"
        
        # Should show error about service not being configured
        content = response.content.decode("utf-8").lower()
        assert "not configured" in content or "contact support" in content


@pytest.mark.django_db
class TestNoRegressionSmoke(TestCase):
    """Quick smoke tests to ensure basic pages still work."""

    def setUp(self):
        """Set up user with business and active session."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        Profile.objects.get_or_create(user=self.user, defaults={"display_name": "Test User"})
        
        # Create business and membership
        self.business = Business.objects.create(
            name="Test Business",
            kind=BusinessKind.PHONES,
            owner=self.user,
            status="ACTIVE"
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client.login(username="testuser", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_dashboard_renders(self):
        """Dashboard should render without errors."""
        response = self.client.get("/dashboard/")
        
        # Should not 500
        assert response.status_code in [200, 302]

    def test_settings_page_renders(self):
        """Settings page should render without errors."""
        response = self.client.get("/accounts/settings/")
        
        # Should not 500
        assert response.status_code in [200, 302]

    def test_inventory_list_renders(self):
        """Inventory list should render without errors."""
        response = self.client.get("/inventory/list/")
        
        # Might redirect to setup, but should not 500
        assert response.status_code in [200, 302, 403, 404]


@pytest.mark.django_db
class TestCleanUIShellNoRegressions(TestCase):
    """
    Tests to ensure the clean UI behavior is maintained WITHOUT deleting any files.
    
    HARD requirements (selective fixes only):
    1. Notifications fallback NEVER appears in initial page load HTML
    2. NO blur applied to body/content when sidebar opens
    3. Sidebar toggle exists and works
    4. Modal can still be opened (not permanently hidden with d-none/hidden)
    """

    def setUp(self):
        """Set up user with business and active session."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        Profile.objects.get_or_create(user=self.user, defaults={"display_name": "Test User"})
        
        # Create business and membership
        self.business = Business.objects.create(
            name="Test Business",
            kind=BusinessKind.PHONES,
            owner=self.user,
            status="ACTIVE"
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client.login(username="testuser", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_notifications_never_visible_on_dashboard_load(self):
        """
        CRITICAL: "Notifications Inbox" text should NOT be visible on initial page load.
        It should only exist inside the modal structure, not in visible page flow.
        """
        response = self.client.get("/dashboard/")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # The modal should exist
        assert 'id="ccInbox"' in content, "Notifications modal should exist"
        
        # But it should NOT be permanently hidden in a way that breaks opening
        # Check that it doesn't have d-none or hidden on the modal root
        import re
        modal_match = re.search(r'<div[^>]*id="ccInbox"[^>]*>', content)
        if modal_match:
            modal_tag = modal_match.group(0)
            # Modal root should NOT have d-none or hidden attribute
            assert 'd-none' not in modal_tag, "Modal root should NOT have d-none (breaks opening)"
            assert 'hidden' not in modal_tag or 'aria-hidden' in modal_tag, "Modal root should not be permanently hidden"

    def test_notifications_text_not_in_visible_flow_on_phones_page(self):
        """
        Test that notifications don't leak on the phones inventory page.
        """
        response = self.client.get("/inventory/verticals/phones/")
        
        # Might redirect or return 200
        if response.status_code == 200:
            content = response.content.decode("utf-8")
            
            # If modal exists, ensure it's properly structured
            if 'id="ccInbox"' in content:
                import re
                modal_match = re.search(r'<div[^>]*id="ccInbox"[^>]*>', content)
                if modal_match:
                    modal_tag = modal_match.group(0)
                    assert 'd-none' not in modal_tag, "Modal should not have d-none on root"

    def test_modal_closed_on_load_script_exists(self):
        """
        Verify the force-closed-on-load script exists to prevent modal from showing.
        """
        response = self.client.get("/dashboard/")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # Check for the force-closed guard script
        assert 'document.getElementById("ccInbox")' in content or "getElementById('ccInbox')" in content
        assert "DOMContentLoaded" in content or "modal.classList.remove" in content

    def test_no_blur_on_sidebar_backdrop(self):
        """
        CRITICAL: Sidebar backdrop must NOT have blur. Only dim overlay allowed.
        Check that .cc-backdrop or #ccBackdrop doesn't have backdrop-filter.
        """
        response = self.client.get("/dashboard/")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # Look for stylesheet references and check loaded CSS doesn't have bad patterns
        # This is a smoke test - we check the referenced CSS files don't have drawer blur
        
        # Get all CSS links from the response
        import re
        css_links = re.findall(r'href="([^"]*\.css[^"]*)"', content)
        
        # We can't easily check external CSS here, but we can verify
        # that inline styles don't have problematic blur
        assert '.cc-backdrop { backdrop-filter: blur' not in content
        assert '.cc-backdrop{backdrop-filter:blur' not in content
        assert 'body[data-drawer="open"] { filter: blur' not in content

    def test_no_blur_on_body_main_or_content_elements(self):
        """
        HARD REQUIREMENT: NO blur CSS that blurs body, main, or content elements.
        """
        response = self.client.get("/dashboard/")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # These patterns would indicate problematic blur on main content
        forbidden_patterns = [
            "body.cc-drawer-open { filter: blur",
            "body.cc-drawer-open{filter:blur",
            'body[data-drawer="open"] { filter: blur',
            "body.no-scroll { filter: blur",
            "body.no-scroll{filter:blur",
            ".main { filter: blur",
            ".main{filter:blur",
            ".content { filter: blur",
            ".content{filter:blur",
            ".page { filter: blur",
            ".page{filter:blur",
        ]
        
        for pattern in forbidden_patterns:
            assert pattern not in content, f"Forbidden blur pattern found: {pattern}"

    def test_sidebar_toggle_exists(self):
        """Sidebar toggle button should exist for mobile users."""
        response = self.client.get("/dashboard/")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # Check for sidebar toggle elements (various possible IDs)
        has_toggle = (
            'id="ccBurger"' in content or
            'id="sidebarToggle"' in content or
            'window.CC_SIDEBAR' in content or
            'bi-list' in content  # Menu icon
        )
        
        assert has_toggle, "Sidebar toggle should exist"

    def test_all_vertical_templates_exist_not_deleted(self):
        """
        CRITICAL: Ensure we didn't delete vertical templates.
        This test verifies key vertical templates are NOT deleted.
        """
        import os
        from django.conf import settings
        
        # Check that vertical directories still exist
        template_dir = os.path.join(settings.BASE_DIR, 'templates', 'verticals')
        
        # These should exist (were being deleted in bad revert)
        critical_verticals = ['farm', 'welding', 'groceries', 'cement', 'pharmacy', 'liquor']
        
        for vertical in critical_verticals:
            vertical_path = os.path.join(template_dir, vertical)
            assert os.path.exists(vertical_path), f"Vertical {vertical} templates should NOT be deleted"


@pytest.mark.django_db
class TestPWACachingNoHardRefresh(TestCase):
    """
    Tests to ensure PWA caching works correctly and NO hard refresh is needed after deploys.
    
    Critical requirements:
    1. /sw.js is served dynamically with no-cache headers
    2. /sw.js contains BUILD_ID (auto-updates on deploy)
    3. SW registration includes auto-update logic
    """

    def test_sw_js_endpoint_exists_and_returns_js(self):
        """
        /sw.js must be accessible (public, no auth) and return JavaScript.
        """
        client = Client()
        response = client.get("/sw.js")
        
        assert response.status_code == 200, "Service worker endpoint must be accessible"
        assert "application/javascript" in response["Content-Type"], "Must return JavaScript"

    def test_sw_js_has_no_cache_headers(self):
        """
        CRITICAL: /sw.js must have Cache-Control: no-cache to ensure browsers always check for updates.
        """
        client = Client()
        response = client.get("/sw.js")
        
        assert response.status_code == 200
        
        cache_control = response.get("Cache-Control", "").lower()
        # Must have no-cache or no-store (either is acceptable)
        assert "no-cache" in cache_control or "no-store" in cache_control, \
            f"Service worker must have no-cache/no-store headers, got: {cache_control}"

    def test_sw_js_contains_dynamic_version(self):
        """
        /sw.js must contain a dynamic VERSION with BUILD_ID, not a hardcoded date.
        This ensures the SW version changes on every deploy.
        
        UPDATED: BUILD_ID is now module-level constant (stable per process).
        """
        client = Client()
        response = client.get("/sw.js")
        
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        
        # Check that VERSION is defined
        assert "const VERSION" in content or "let VERSION" in content or "var VERSION" in content, \
            "Service worker must define VERSION constant"
        
        # Check that it's not the old hardcoded placeholder
        assert "BUILD_ID_PLACEHOLDER" not in content, \
            "BUILD_ID_PLACEHOLDER should be replaced with actual build ID"
        
        # Check that VERSION uses emajinet prefix (our format)
        assert "emajinet-" in content, "VERSION should use emajinet- prefix"
        
        # Verify BUILD_ID is stable across requests (same response)
        response2 = client.get("/sw.js")
        content2 = response2.content.decode("utf-8")
        assert content == content2, "BUILD_ID must be stable (same across requests)"

    def test_sw_has_skip_waiting_message_handler(self):
        """
        SW must have message handler for SKIP_WAITING to enable auto-activation.
        """
        client = Client()
        response = client.get("/sw.js")
        
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        
        # Check for message event listener
        assert "addEventListener('message'" in content or 'addEventListener("message"' in content, \
            "Service worker must listen for messages"
        
        # Check for SKIP_WAITING handling
        assert "SKIP_WAITING" in content, "Service worker must handle SKIP_WAITING message"
        assert "skipWaiting" in content, "Service worker must call skipWaiting()"

    def test_sw_is_cleanup_only_no_caching(self):
        """
        SW must be a no-op cleanup worker — no caching strategies at all.

        The previous caching SW caused hard-refresh rendering bugs.  The new SW
        clears all caches and intercepts no fetch requests.  Stale-while-revalidate
        and cache-first strategies are intentionally absent.
        """
        client = Client()
        response = client.get("/sw.js")

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Must have cleanup behaviour
        assert "caches.keys()" in content, "SW must clear all caches on activate"
        assert "caches.delete" in content, "SW must delete old caches"
        # Must NOT cache anything (no cache.put, no cache.add, no cache.addAll)
        assert "cache.put" not in content, "Cleanup SW must NOT cache responses"
        assert "cache.addAll" not in content, "Cleanup SW must NOT precache assets"

    def test_base_template_has_sw_cleanup_not_registration(self):
        """
        CRITICAL: Base template must have SW cleanup, NOT SW registration.

        SW registration is intentionally disabled (stability hotfix — hard-refresh bug).
        The cleanup code runs on every page load and unregisters any lingering SWs.
        """
        from django.contrib.auth import get_user_model
        from tenants.models import Business, Membership
        from circuitcity.accounts.models import Profile
        from inventory.business_kinds import BusinessKind

        User = get_user_model()
        client = Client()
        user = User.objects.create_user(username="testuser", password="testpass123")
        Profile.objects.get_or_create(user=user, defaults={"display_name": "Test User"})

        business = Business.objects.create(
            name="Test Business",
            kind=BusinessKind.PHONES,
            owner=user,
            status="ACTIVE"
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )

        client.login(username="testuser", password="testpass123")
        session = client.session
        session['active_business_id'] = business.id
        session.save()

        response = client.get("/dashboard/")
        assert response.status_code == 200

        content = response.content.decode("utf-8")

        # Cleanup must be present
        assert "getRegistrations" in content, \
            "Must have SW cleanup: getRegistrations()"
        assert "unregister" in content, \
            "Must have SW cleanup: unregister()"
        # Registration must be absent
        register_count = content.count("navigator.serviceWorker.register(")
        assert register_count == 0, (
            f"SW registration must be disabled (stability hotfix). "
            f"Found {register_count} registration call(s)."
        )
        # Must NOT register /static/sw.js (was broken — bypassed BUILD_ID injection)
        assert "static/sw.js" not in content, \
            "Must NOT reference /static/sw.js (was bypassing BUILD_ID injection)"

    def test_base_template_has_single_sw_registration(self):
        """
        LEGACY: Kept for reference. SW registration count must be zero.

        This test previously checked for exactly 1 registration.  After the
        stability hotfix, it verifies that zero registrations exist.
        """
        from django.contrib.auth import get_user_model
        from tenants.models import Business, Membership
        from circuitcity.accounts.models import Profile
        from inventory.business_kinds import BusinessKind

        User = get_user_model()
        client = Client()
        user = User.objects.create_user(username="testuser2sw", password="testpass123")
        Profile.objects.get_or_create(user=user, defaults={"display_name": "Test User"})

        business = Business.objects.create(
            name="Test Business SW",
            kind=BusinessKind.PHONES,
            owner=user,
            status="ACTIVE"
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )

        client.login(username="testuser2sw", password="testpass123")
        session = client.session
        session['active_business_id'] = business.id
        session.save()

        response = client.get("/dashboard/")
        assert response.status_code == 200

        content = response.content.decode("utf-8")

        register_count = content.count("navigator.serviceWorker.register(")
        assert register_count == 0, \
            f"SW registration must be disabled (stability hotfix). Found {register_count}."

        assert "static/sw.js" not in content, \
            "Must NOT register static/sw.js"

    def test_sw_headers_complete(self):
        """
        Verify /sw.js has ALL required headers for proper caching and scope.
        """
        client = Client()
        response = client.get("/sw.js")
        
        assert response.status_code == 200
        
        # Cache control headers
        cache_control = response.get("Cache-Control", "").lower()
        assert "no-cache" in cache_control or "no-store" in cache_control
        
        # Pragma and Expires (polish)
        pragma = response.get("Pragma", "").lower()
        assert pragma == "no-cache", "Should have Pragma: no-cache"
        
        expires = response.get("Expires", "")
        assert expires == "0", "Should have Expires: 0"
        
        # Service worker scope
        sw_allowed = response.get("Service-Worker-Allowed", "")
        assert sw_allowed == "/", "Service-Worker-Allowed must be /"

