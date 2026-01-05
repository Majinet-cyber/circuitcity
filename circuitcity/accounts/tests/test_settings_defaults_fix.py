# circuitcity/accounts/tests/test_settings_defaults_fix.py
"""
Tests for settings defaults fix.

Ensures:
1. New users get proper defaults (notifications ON, location Lilongwe, language English)
2. Existing users with NULL values get defaults filled in
3. User-chosen values are NEVER overwritten
4. Settings UI is clean and not crowded
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from circuitcity.accounts.models import Profile
from circuitcity.accounts.services.settings_defaults import (
    DEFAULT_CITY,
    DEFAULT_COUNTRY,
    DEFAULT_LANGUAGE,
    DEFAULT_TIMEZONE,
    ensure_all_settings_defaults,
    ensure_notification_defaults,
    ensure_user_profile_defaults,
)

User = get_user_model()


@pytest.mark.django_db
class TestProfileDefaults:
    """Test profile default values"""

    def test_new_user_gets_default_profile_values(self):
        """New users should get Malawi/Lilongwe/English defaults"""
        user = User.objects.create_user(username="newuser", password="test123")

        # Apply defaults
        ensure_user_profile_defaults(user)

        # Check profile
        profile = Profile.objects.get(user=user)
        assert profile.language == DEFAULT_LANGUAGE, f"Language should default to {DEFAULT_LANGUAGE}"
        assert profile.country == DEFAULT_COUNTRY, f"Country should default to {DEFAULT_COUNTRY}"
        assert profile.timezone == DEFAULT_TIMEZONE, f"Timezone should default to {DEFAULT_TIMEZONE}"
        assert profile.city == DEFAULT_CITY, f"City should default to {DEFAULT_CITY}"

    def test_defaults_only_fill_empty_fields(self):
        """Defaults should NOT overwrite user-chosen values"""
        user = User.objects.create_user(username="existing_user", password="test123")
        profile = Profile.objects.create(
            user=user,
            language="French",  # User chose French
            country="France",  # User chose France
            timezone="Europe/Paris",
            city="Paris",
        )

        # Apply defaults (should NOT change anything)
        changed = ensure_user_profile_defaults(user)

        # Should return False (no changes made)
        assert changed is False, "Should not change existing values"

        # Verify values unchanged
        profile.refresh_from_db()
        assert profile.language == "French"
        assert profile.country == "France"
        assert profile.timezone == "Europe/Paris"
        assert profile.city == "Paris"

    def test_defaults_fill_null_fields_only(self):
        """Defaults should fill NULL/empty fields but not touch set fields"""
        user = User.objects.create_user(username="partial_user", password="test123")
        profile = Profile.objects.create(
            user=user,
            language="",  # Empty (should be filled)
            country="South Africa",  # Set (should NOT be changed)
            timezone="",  # Empty (should be filled)
            city="",  # Empty (should be filled)
        )

        # Apply defaults
        changed = ensure_user_profile_defaults(user)

        # Should return True (changes made)
        assert changed is True

        # Verify
        profile.refresh_from_db()
        assert profile.language == DEFAULT_LANGUAGE, "Empty language should be filled"
        assert profile.country == "South Africa", "Set country should NOT be changed"
        assert profile.timezone == DEFAULT_TIMEZONE, "Empty timezone should be filled"
        assert profile.city == DEFAULT_CITY, "Empty city should be filled"


@pytest.mark.django_db
class TestNotificationDefaults:
    """Test notification preference defaults"""

    def test_new_user_gets_all_notifications_enabled(self):
        """New users should have ALL notifications enabled by default"""
        user = User.objects.create_user(username="newuser", password="test123")

        # Apply defaults
        ensure_notification_defaults(user)

        # Check preferences
        from notifications.models import NotificationPreference

        pref = NotificationPreference.objects.get(user=user)

        # All notifications should be ON (except commission emails for non-agents)
        assert pref.welcome_emails is True
        assert pref.instant_sale_email is True
        assert pref.sale_emails_enabled is True
        assert pref.daily_summary_email is True
        assert pref.important_alerts_email is True
        assert pref.high_sales_alerts is True
        assert pref.weekly_digest_enabled is True
        # Commission emails default to False (for agents only)
        assert pref.commission_emails_enabled is False

    def test_notification_defaults_never_re_enable_disabled_notifications(self):
        """
        CRITICAL: If user disabled a notification, defaults should NOT re-enable it.
        Only fill NULL values, not False values.
        """
        user = User.objects.create_user(username="existing_user", password="test123")

        # Create preferences with some explicitly disabled
        from notifications.models import NotificationPreference

        pref = NotificationPreference.objects.create(
            user=user,
            welcome_emails=False,  # User DISABLED this
            instant_sale_email=True,
            sale_emails_enabled=None,  # NULL (should be filled)
            daily_summary_email=False,  # User DISABLED this
        )

        # Apply defaults
        changed = ensure_notification_defaults(user)

        # Verify
        pref.refresh_from_db()
        assert pref.welcome_emails is False, "Should NOT re-enable disabled notification"
        assert pref.instant_sale_email is True, "Should keep enabled notification"
        assert pref.sale_emails_enabled is True, "Should fill NULL with default (True)"
        assert pref.daily_summary_email is False, "Should NOT re-enable disabled notification"


@pytest.mark.django_db
class TestCombinedDefaults:
    """Test combined profile + notification defaults"""

    def test_ensure_all_settings_defaults_applies_both(self):
        """ensure_all_settings_defaults should apply both profile and notification defaults"""
        user = User.objects.create_user(username="newuser", password="test123")

        # Apply all defaults
        result = ensure_all_settings_defaults(user)

        # Should return dict with both keys
        assert "profile_changed" in result
        assert "notifications_changed" in result

        # Both should be True for new user
        assert result["profile_changed"] is True
        assert result["notifications_changed"] is True

        # Verify profile
        profile = Profile.objects.get(user=user)
        assert profile.city == DEFAULT_CITY

        # Verify notifications
        from notifications.models import NotificationPreference

        pref = NotificationPreference.objects.get(user=user)
        assert pref.welcome_emails is True


@pytest.mark.django_db
class TestSettingsUIAccess:
    """Test settings UI is accessible and clean"""

    def test_settings_profile_page_loads(self):
        """Settings profile page should load without errors"""
        user = User.objects.create_user(username="testuser", password="test123")

        client = Client()
        client.force_login(user)

        # Access settings profile page
        url = reverse("accounts:settings_profile")
        response = client.get(url)

        assert response.status_code == 200, "Settings profile page should be accessible"

        # Check for key elements
        content = response.content.decode()
        assert "Settings" in content or "Profile" in content
        assert "Display Name" in content or "display_name" in content

    def test_settings_security_page_loads(self):
        """Settings security page should load without errors"""
        user = User.objects.create_user(username="testuser", password="test123")

        client = Client()
        client.force_login(user)

        # Access settings security page
        url = reverse("accounts:settings_security")
        response = client.get(url)

        assert response.status_code == 200, "Settings security page should be accessible"

    def test_settings_defaults_applied_on_first_visit(self):
        """
        When user visits settings for first time, defaults should be applied automatically.
        """
        user = User.objects.create_user(username="newuser", password="test123")

        # Profile should not exist yet
        assert not Profile.objects.filter(user=user).exists()

        client = Client()
        client.force_login(user)

        # Visit settings page (should trigger default application)
        url = reverse("accounts:settings_profile")
        response = client.get(url)

        assert response.status_code == 200

        # Profile should now exist with defaults
        profile = Profile.objects.get(user=user)
        assert profile.city == DEFAULT_CITY
        assert profile.language == DEFAULT_LANGUAGE


@pytest.mark.django_db
class TestDefaultValues:
    """Test the actual default values are correct"""

    def test_default_values_are_correct(self):
        """Verify default values match requirements"""
        assert DEFAULT_LANGUAGE == "English", "Default language must be English"
        assert DEFAULT_COUNTRY == "Malawi", "Default country must be Malawi"
        assert DEFAULT_TIMEZONE == "Africa/Blantyre", "Default timezone must be Africa/Blantyre"
        assert DEFAULT_CITY == "Lilongwe", "Default city must be Lilongwe"

    def test_profile_model_defaults_match_service_defaults(self):
        """Profile model defaults should match service defaults"""
        user = User.objects.create_user(username="testuser", password="test123")
        profile = Profile.objects.create(user=user)

        # Model defaults should match
        assert profile.country == DEFAULT_COUNTRY
        assert profile.language == DEFAULT_LANGUAGE
        assert profile.timezone == DEFAULT_TIMEZONE
        assert profile.city == DEFAULT_CITY
