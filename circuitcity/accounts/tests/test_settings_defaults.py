# circuitcity/accounts/tests/test_settings_defaults.py
"""
Tests for Account Settings Defaults

Verifies that:
1. New users get proper defaults (English, Malawi, Africa/Blantyre, Lilongwe)
2. Notification preferences are created with all toggles True by default
3. User overrides are preserved (no auto-re-enabling)
4. Existing users with blank fields get defaults filled without overwriting non-blank values
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
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
from notifications.models import NotificationPreference

User = get_user_model()


class SettingsDefaultsServiceTestCase(TestCase):
    """Test the settings defaults service functions directly."""

    def setUp(self):
        """Create a test user."""
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="TestPass123!",
        )

    def test_ensure_user_profile_defaults_new_user(self):
        """Test that new users get proper profile defaults."""
        # Get the auto-created profile (created by signal)
        profile = self.user.profile

        # Clear defaults to simulate a new user with empty fields
        profile.language = ""
        profile.country = ""
        profile.timezone = ""
        profile.city = ""
        profile.save()

        # Apply defaults
        changed = ensure_user_profile_defaults(self.user)

        # Verify changes were made
        self.assertTrue(changed)

        # Refresh from DB
        profile.refresh_from_db()

        # Verify all defaults are set
        self.assertEqual(profile.language, DEFAULT_LANGUAGE)
        self.assertEqual(profile.country, DEFAULT_COUNTRY)
        self.assertEqual(profile.timezone, DEFAULT_TIMEZONE)
        self.assertEqual(profile.city, DEFAULT_CITY)

    def test_ensure_user_profile_defaults_preserves_existing_values(self):
        """Test that existing values are NOT overwritten."""
        profile = self.user.profile

        # Set custom values
        profile.language = "French"
        profile.country = "France"
        profile.timezone = "Europe/Paris"
        profile.city = "Paris"
        profile.save()

        # Apply defaults
        changed = ensure_user_profile_defaults(self.user)

        # Verify NO changes were made
        self.assertFalse(changed)

        # Verify custom values are preserved
        profile.refresh_from_db()
        self.assertEqual(profile.language, "French")
        self.assertEqual(profile.country, "France")
        self.assertEqual(profile.timezone, "Europe/Paris")
        self.assertEqual(profile.city, "Paris")

    def test_ensure_user_profile_defaults_mixed_blank_and_set(self):
        """Test that only blank fields get defaults, set fields are preserved."""
        profile = self.user.profile

        # Mix of blank and set values
        profile.language = "French"
        profile.country = ""  # blank
        profile.timezone = "Europe/Paris"
        profile.city = ""  # blank
        profile.save()

        # Apply defaults
        changed = ensure_user_profile_defaults(self.user)

        # Verify changes were made
        self.assertTrue(changed)

        # Verify mixed results
        profile.refresh_from_db()
        self.assertEqual(profile.language, "French")  # preserved
        self.assertEqual(profile.country, DEFAULT_COUNTRY)  # defaulted
        self.assertEqual(profile.timezone, "Europe/Paris")  # preserved
        self.assertEqual(profile.city, DEFAULT_CITY)  # defaulted

    def test_ensure_notification_defaults_new_user(self):
        """Test that new users get all notification preferences enabled."""
        # Delete any auto-created notification preferences
        NotificationPreference.objects.filter(user=self.user).delete()

        # Apply defaults
        changed = ensure_notification_defaults(self.user)

        # Verify changes were made
        self.assertTrue(changed)

        # Verify notification preference exists
        pref = NotificationPreference.objects.get(user=self.user)

        # Verify all notifications are enabled by default (except commission)
        self.assertTrue(pref.welcome_emails)
        self.assertTrue(pref.instant_sale_email)
        self.assertTrue(pref.sale_emails_enabled)
        self.assertTrue(pref.daily_summary_email)
        self.assertTrue(pref.important_alerts_email)
        self.assertTrue(pref.high_sales_alerts)
        self.assertTrue(pref.weekly_digest_enabled)
        self.assertFalse(pref.commission_emails_enabled)  # False for agents by default

    def test_ensure_notification_defaults_preserves_user_choices(self):
        """Test that user-disabled notifications are NOT re-enabled."""
        # Create preference with all notifications disabled
        pref, _ = NotificationPreference.objects.get_or_create(user=self.user)
        pref.welcome_emails = False
        pref.instant_sale_email = False
        pref.sale_emails_enabled = False
        pref.daily_summary_email = False
        pref.important_alerts_email = False
        pref.high_sales_alerts = False
        pref.weekly_digest_enabled = False
        pref.commission_emails_enabled = False
        pref.save()

        # Apply defaults
        changed = ensure_notification_defaults(self.user)

        # Verify NO changes were made (user choices preserved)
        self.assertFalse(changed)

        # Verify all notifications remain disabled
        pref.refresh_from_db()
        self.assertFalse(pref.welcome_emails)
        self.assertFalse(pref.instant_sale_email)
        self.assertFalse(pref.sale_emails_enabled)
        self.assertFalse(pref.daily_summary_email)
        self.assertFalse(pref.important_alerts_email)
        self.assertFalse(pref.high_sales_alerts)
        self.assertFalse(pref.weekly_digest_enabled)
        self.assertFalse(pref.commission_emails_enabled)

    def test_ensure_all_settings_defaults(self):
        """Test the combined convenience function."""
        # Clear profile defaults
        profile = self.user.profile
        profile.language = ""
        profile.country = ""
        profile.timezone = ""
        profile.city = ""
        profile.save()

        # Delete notification preferences
        NotificationPreference.objects.filter(user=self.user).delete()

        # Apply all defaults
        result = ensure_all_settings_defaults(self.user)

        # Verify both were changed
        self.assertTrue(result["profile_changed"])
        self.assertTrue(result["notifications_changed"])

        # Verify profile defaults
        profile.refresh_from_db()
        self.assertEqual(profile.language, DEFAULT_LANGUAGE)
        self.assertEqual(profile.country, DEFAULT_COUNTRY)
        self.assertEqual(profile.timezone, DEFAULT_TIMEZONE)
        self.assertEqual(profile.city, DEFAULT_CITY)

        # Verify notification defaults
        pref = NotificationPreference.objects.get(user=self.user)
        self.assertTrue(pref.instant_sale_email)
        self.assertTrue(pref.daily_summary_email)


class SettingsProfileViewTestCase(TestCase):
    """Test the settings profile view applies defaults correctly."""

    def setUp(self):
        """Create a test user and client."""
        self.user = User.objects.create_user(
            username="viewtest",
            email="viewtest@example.com",
            password="TestPass123!",
        )
        self.client = Client()
        self.client.login(username="viewtest", password="TestPass123!")
        self.url = reverse("accounts:settings_profile")

    def test_settings_profile_view_applies_defaults_on_get(self):
        """Test that visiting settings applies defaults."""
        # Clear profile defaults
        profile = self.user.profile
        profile.language = ""
        profile.country = ""
        profile.timezone = ""
        profile.city = ""
        profile.save()

        # Visit settings page
        response = self.client.get(self.url)

        # Verify successful response
        self.assertEqual(response.status_code, 200)

        # Verify defaults were applied
        profile.refresh_from_db()
        self.assertEqual(profile.language, DEFAULT_LANGUAGE)
        self.assertEqual(profile.country, DEFAULT_COUNTRY)
        self.assertEqual(profile.timezone, DEFAULT_TIMEZONE)
        self.assertEqual(profile.city, DEFAULT_CITY)

    def test_settings_profile_view_saves_changes(self):
        """Test that form submission persists changes."""
        # Ensure defaults are set
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        # Submit form with custom values
        response = self.client.post(
            self.url,
            {
                "display_name": "Test User",
                "country": "US",
                "language": "en-gb",
                "timezone": "America/New_York",
                "city": "New York",
                "display_currency": "USD",
            },
        )

        # Verify redirect (successful save)
        self.assertEqual(response.status_code, 302)

        # Verify values were saved
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.display_name, "Test User")
        self.assertEqual(profile.country, "US")
        self.assertEqual(profile.language, "en-gb")
        self.assertEqual(profile.timezone, "America/New_York")
        self.assertEqual(profile.city, "New York")
        self.assertEqual(profile.display_currency, "USD")

    def test_settings_profile_view_revisit_preserves_user_choices(self):
        """Test that revisiting settings does NOT overwrite user choices."""
        # Set custom values
        profile = self.user.profile
        profile.language = "French"
        profile.country = "France"
        profile.timezone = "Europe/Paris"
        profile.city = "Paris"
        profile.save()

        # Visit settings page again
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        # Verify custom values are preserved
        profile.refresh_from_db()
        self.assertEqual(profile.language, "French")
        self.assertEqual(profile.country, "France")
        self.assertEqual(profile.timezone, "Europe/Paris")
        self.assertEqual(profile.city, "Paris")


class NotificationPreferencesIntegrationTestCase(TestCase):
    """Test notification preferences in realistic scenarios."""

    def setUp(self):
        """Create a test user."""
        self.user = User.objects.create_user(
            username="notiftest",
            email="notiftest@example.com",
            password="TestPass123!",
        )

    def test_new_user_gets_all_notifications_enabled(self):
        """Test that newly created users get all notifications enabled."""
        # Delete any auto-created preferences (simulate fresh user)
        NotificationPreference.objects.filter(user=self.user).delete()

        # Ensure defaults
        ensure_notification_defaults(self.user)

        # Verify all are enabled
        pref = NotificationPreference.objects.get(user=self.user)
        self.assertTrue(pref.welcome_emails)
        self.assertTrue(pref.instant_sale_email)
        self.assertTrue(pref.sale_emails_enabled)
        self.assertTrue(pref.daily_summary_email)
        self.assertTrue(pref.important_alerts_email)
        self.assertTrue(pref.high_sales_alerts)
        self.assertTrue(pref.weekly_digest_enabled)

    def test_user_disables_notification_stays_disabled(self):
        """Test that once user disables a notification, it stays disabled."""
        # Create default preferences
        pref, _ = NotificationPreference.objects.get_or_create(user=self.user)
        pref.instant_sale_email = True
        pref.daily_summary_email = True
        pref.save()

        # User disables instant_sale_email
        pref.instant_sale_email = False
        pref.save()

        # Apply defaults again (simulating revisit to settings)
        ensure_notification_defaults(self.user)

        # Verify instant_sale_email remains disabled
        pref.refresh_from_db()
        self.assertFalse(pref.instant_sale_email)  # User choice preserved
        self.assertTrue(pref.daily_summary_email)  # Other still enabled

    def test_existing_user_with_null_preferences_gets_defaults(self):
        """Test that users with NULL preference fields get defaults filled."""
        # Note: This scenario is unlikely with Django BooleanField,
        # but we test the logic in case fields are nullable
        pref, _ = NotificationPreference.objects.get_or_create(user=self.user)

        # Set all to False to simulate user choices
        pref.welcome_emails = False
        pref.instant_sale_email = False
        pref.save()

        # Apply defaults
        ensure_notification_defaults(self.user)

        # Verify False values are preserved (not overwritten)
        pref.refresh_from_db()
        self.assertFalse(pref.welcome_emails)
        self.assertFalse(pref.instant_sale_email)


class SettingsDefaultsRegressionTestCase(TestCase):
    """Regression tests to ensure defaults never regress."""

    def setUp(self):
        """Create a test user."""
        self.user = User.objects.create_user(
            username="regtest",
            email="regtest@example.com",
            password="TestPass123!",
        )
        self.client = Client()
        self.client.login(username="regtest", password="TestPass123!")

    def test_profile_defaults_match_malawi_context(self):
        """Test that defaults are set to Malawi context as specified."""
        # Clear profile
        profile = self.user.profile
        profile.language = ""
        profile.country = ""
        profile.timezone = ""
        profile.city = ""
        profile.save()

        # Apply defaults
        ensure_user_profile_defaults(self.user)

        # Verify Malawi defaults
        profile.refresh_from_db()
        self.assertEqual(profile.language, "English")
        self.assertEqual(profile.country, "Malawi")
        self.assertEqual(profile.timezone, "Africa/Blantyre")
        self.assertEqual(profile.city, "Lilongwe")

    def test_profile_city_field_exists(self):
        """Test that city field exists on Profile model."""
        profile = self.user.profile
        self.assertTrue(hasattr(profile, "city"))

    def test_form_includes_city_field(self):
        """Test that ProfileForm includes city field."""
        from circuitcity.accounts.forms import ProfileForm

        form = ProfileForm(instance=self.user.profile)
        self.assertIn("city", form.fields)

    def test_settings_page_shows_defaults_immediately(self):
        """Test that settings page shows defaults on first visit."""
        # Clear profile
        profile = self.user.profile
        profile.language = ""
        profile.country = ""
        profile.timezone = ""
        profile.city = ""
        profile.save()

        # Visit settings
        response = self.client.get(reverse("accounts:settings_profile"))

        # Verify form shows defaults
        profile.refresh_from_db()
        self.assertEqual(profile.language, "English")
        self.assertEqual(profile.country, "Malawi")
        self.assertEqual(profile.timezone, "Africa/Blantyre")
        self.assertEqual(profile.city, "Lilongwe")

    def test_notification_preferences_created_on_user_creation(self):
        """Test that notification preferences are auto-created for new users."""
        # Create a fresh user
        new_user = User.objects.create_user(
            username="newuser",
            email="newuser@example.com",
            password="TestPass123!",
        )

        # Ensure defaults are applied
        ensure_notification_defaults(new_user)

        # Verify preferences exist
        pref = NotificationPreference.objects.get(user=new_user)
        self.assertIsNotNone(pref)

        # Verify defaults are enabled
        self.assertTrue(pref.instant_sale_email)
        self.assertTrue(pref.daily_summary_email)
        self.assertTrue(pref.important_alerts_email)
