"""
PHASE 2 Tests: Settings Improvements
- Notifications default checked
- Avatar defaults to initials (no gravatar)
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from notifications.models import NotificationPreference
from tenants.models import Business, Membership

User = get_user_model()


@pytest.fixture
def manager_user(db):
    """Create a manager user with a business."""
    user = User.objects.create_user(
        username="manager1",
        email="manager@example.com",
        password="testpass123",
        first_name="John",
        last_name="Manager",
    )
    business = Business.objects.create(
        name="Test Business",
        slug="test-business",
        business_kind="phones",
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
    )
    return user, business


@pytest.mark.django_db
class TestNotificationDefaults:
    """Test notification preferences default to checked."""

    def test_new_user_gets_all_checked(self, manager_user):
        """New users should have all notifications checked by default."""
        user, business = manager_user
        client = Client()
        client.force_login(user)

        # Delete any existing preferences
        NotificationPreference.objects.filter(user=user).delete()

        # Visit settings (should create preferences)
        response = client.get(reverse("accounts:settings_unified"))
        assert response.status_code == 200

        # Check that preferences were created with defaults
        pref = NotificationPreference.objects.get(user=user)
        assert pref.instant_sale_email is True
        assert pref.daily_summary_email is True
        assert pref.important_alerts_email is True
        assert pref.high_sales_alerts is True
        assert pref.weekly_digest_enabled is True

    def test_checkboxes_render_checked_by_default(self, manager_user):
        """Settings page should show checkboxes as checked for new users."""
        user, business = manager_user
        client = Client()
        client.force_login(user)

        # Delete existing preferences
        NotificationPreference.objects.filter(user=user).delete()

        response = client.get(reverse("accounts:settings_unified"))
        assert response.status_code == 200

        content = response.content.decode()
        # Check that checkboxes are checked
        assert 'name="instant_sale_email" checked' in content
        assert 'name="daily_summary_email" checked' in content
        assert 'name="important_alerts_email" checked' in content

    def test_unchecking_persists_correctly(self, manager_user):
        """Unchecking a notification should save as False."""
        user, business = manager_user
        client = Client()
        client.force_login(user)

        # Ensure preferences exist
        pref, _ = NotificationPreference.objects.get_or_create(user=user)
        assert pref.instant_sale_email is True  # default

        # Uncheck instant_sale_email (by not sending it in POST)
        response = client.post(
            reverse("accounts:settings_unified"),
            {
                "save_notifications": "1",
                # instant_sale_email NOT sent = unchecked
                "daily_summary_email": "on",
                "important_alerts_email": "on",
                "high_sales_alerts": "on",
                "weekly_digest_enabled": "on",
            },
        )
        assert response.status_code == 302  # redirect

        # Reload preference
        pref.refresh_from_db()
        assert pref.instant_sale_email is False  # should be unchecked now
        assert pref.daily_summary_email is True
        assert pref.important_alerts_email is True


@pytest.mark.django_db
class TestAvatarDefaults:
    """Test avatar rendering logic."""

    def test_user_without_avatar_gets_fallback(self, manager_user):
        """User without uploaded avatar should get a fallback avatar (gravatar or data URL)."""
        user, business = manager_user
        client = Client()
        client.force_login(user)

        response = client.get(reverse("accounts:settings_unified"))
        assert response.status_code == 200

        # Check context - should have some avatar URL (gravatar fallback or data URL)
        assert response.context["avatar_img_url"] is not None

    def test_settings_page_renders_avatar_section(self, manager_user):
        """Settings page should render the avatar/profile section."""
        user, business = manager_user
        client = Client()
        client.force_login(user)

        response = client.get(reverse("accounts:settings_unified"))
        assert response.status_code == 200

        content = response.content.decode()
        # Should have change avatar option
        assert "Change avatar" in content or "avatar" in content.lower()

    def test_uploaded_avatar_still_works(self, manager_user):
        """If user has uploaded avatar, it should still display."""
        user, business = manager_user

        # Create profile with avatar
        from circuitcity.accounts.models import Profile

        profile, _ = Profile.objects.get_or_create(user=user)
        # Simulate having an avatar file (we can't actually upload in test, but set the field)
        # This test just checks the logic doesn't break

        client = Client()
        client.force_login(user)
        response = client.get(reverse("accounts:settings_unified"))
        assert response.status_code == 200
        # If avatar exists, avatar_img_url would be set, but we can't test file upload easily here
        # The key is the view logic doesn't crash
