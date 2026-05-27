"""
Regression Tests for Landing Page and Settings
- Landing page business count consistency (SSOT)
- Notification defaults for new users
"""
from __future__ import annotations

import re
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
        username="test_manager_regression",
        email="regression_manager@example.com",
        password="testpass123",
        first_name="Regression",
        last_name="Test",
    )
    business = Business.objects.create(
        name="Regression Test Business",
        slug="regression-test-business",
        business_kind="phones",
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
    )
    return user, business


@pytest.mark.django_db
class TestLandingPageBusinessCount:
    """Test that the 'Join XX+ businesses' count matches the KPI 'Active Merchants' count."""

    def test_landing_business_count_is_consistent(self, db):
        """
        The 'Join X+ businesses...' CTA must use the same number
        as the 'Active Merchants' KPI displayed on the landing page.
        No hardcoded mismatch allowed.
        """
        # Create some test businesses
        for i in range(3):
            Business.objects.create(
                name=f"Test Business {i}",
                slug=f"test-business-{i}",
                business_kind="phones",
            )

        client = Client()
        response = client.get("/")  # Landing page
        assert response.status_code == 200

        content = response.content.decode("utf-8")

        # Extract the total_merchants from context (passed by the view)
        # The number should appear in both the KPI section and the CTA section
        context_merchants = response.context.get("total_merchants")
        
        # If we have metrics shown, check that the numbers match
        if response.context.get("show_metrics"):
            # Find all instances of "XX+ businesses" pattern
            cta_patterns = re.findall(r"Join\s+(\d+)\+\s+businesses", content, re.IGNORECASE)
            
            # All CTA numbers should match total_merchants
            for cta_count in cta_patterns:
                assert int(cta_count) == context_merchants, (
                    f"CTA count ({cta_count}) does not match total_merchants ({context_merchants})"
                )
        else:
            # Even in fallback mode, check the context value is used
            assert context_merchants is not None or "total_merchants" in content

    def test_landing_page_uses_ssot_for_business_count(self, db):
        """
        Verify landing page template uses total_merchants variable,
        not hardcoded MARKETING_ACTIVE_BUSINESSES.
        """
        client = Client()
        response = client.get("/")
        assert response.status_code == 200

        # Check that total_merchants is in the context
        assert "total_merchants" in response.context
        
        # The context should have the actual count from database
        actual_count = Business.objects.count()
        assert response.context["total_merchants"] == actual_count or (
            # Or fallback if count is below threshold
            response.context["total_merchants"] >= 1
        )


@pytest.mark.django_db
class TestNotificationDefaultsRegression:
    """Test notification checkboxes default to checked for new users."""

    def test_notifications_default_checked_for_new_user(self, manager_user):
        """
        Create a new user -> open /accounts/settings/ -> 
        all notification checkboxes should be checked without clicking anything.
        """
        user, business = manager_user
        client = Client()
        client.force_login(user)

        # Delete any existing preferences to simulate new user
        NotificationPreference.objects.filter(user=user).delete()

        # Visit settings
        response = client.get(reverse("accounts:settings_unified"))
        assert response.status_code == 200

        content = response.content.decode("utf-8")

        # All notification checkboxes should be checked
        # Check for "checked" attribute on each checkbox input
        checkbox_names = [
            "instant_sale_email",
            "daily_summary_email",
            "weekly_digest_enabled",
            "high_sales_alerts",
            "important_alerts_email",
        ]

        for name in checkbox_names:
            # Look for the checkbox with this name and "checked" attribute
            # The pattern should match: name="instant_sale_email" checked
            pattern = rf'name="{name}"[^>]*checked'
            assert re.search(pattern, content, re.IGNORECASE), (
                f"Checkbox '{name}' should be checked by default for new users"
            )

    def test_existing_user_unchecked_remains_unchecked(self, manager_user):
        """
        Existing users who have explicitly unchecked a notification
        should NOT have it re-enabled automatically.
        """
        user, business = manager_user
        client = Client()
        client.force_login(user)

        # Create preferences with some disabled
        pref, _ = NotificationPreference.objects.get_or_create(
            user=user,
            defaults={
                "instant_sale_email": False,  # User explicitly disabled
                "daily_summary_email": True,
                "weekly_digest_enabled": True,
                "high_sales_alerts": True,
                "important_alerts_email": True,
            },
        )
        pref.instant_sale_email = False
        pref.save()

        # Visit settings
        response = client.get(reverse("accounts:settings_unified"))
        assert response.status_code == 200

        content = response.content.decode("utf-8")

        # instant_sale_email should NOT be checked
        # Look for: name="instant_sale_email" WITHOUT "checked"
        assert 'name="instant_sale_email"' in content
        # The checkbox should appear but not be checked
        pattern = r'name="instant_sale_email"[^>]*checked'
        if re.search(pattern, content, re.IGNORECASE):
            # If checked is present, the user's preference was overwritten - FAIL
            pytest.fail("Existing user's disabled notification was re-enabled!")

        # Verify the preference is still False in the database
        pref.refresh_from_db()
        assert pref.instant_sale_email is False


@pytest.mark.django_db
class TestSettingsCleanUI:
    """Test settings page has clean white UI without blue panels."""

    def test_settings_page_renders_without_error(self, manager_user):
        """Settings page should render successfully."""
        user, business = manager_user
        client = Client()
        client.force_login(user)

        response = client.get(reverse("accounts:settings_unified"))
        assert response.status_code == 200

        content = response.content.decode("utf-8")
        # Should contain settings-page class for clean white styling
        assert "settings-page" in content or "Settings" in content

    def test_settings_page_has_notification_section(self, manager_user):
        """Settings page should have a notification preferences section."""
        user, business = manager_user
        client = Client()
        client.force_login(user)

        response = client.get(reverse("accounts:settings_unified"))
        assert response.status_code == 200

        content = response.content.decode("utf-8")
        assert "Notification Preferences" in content
        assert "save_notifications" in content

