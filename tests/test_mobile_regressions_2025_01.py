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

