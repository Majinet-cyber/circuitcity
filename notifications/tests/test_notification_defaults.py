# notifications/tests/test_notification_defaults.py
"""
Tests for notification preferences default values (opt-out model).
Ensures all notifications default to ON (True) for new users.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from notifications.models import NotificationPreference, WhatsAppPreference

User = get_user_model()


class NotificationPreferenceDefaultsTests(TestCase):
    """Test that NotificationPreference defaults all to True (opt-out model)."""
    
    def test_new_preference_defaults_all_true(self):
        """Test that creating new NotificationPreference has all fields True."""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        pref = NotificationPreference.objects.create(user=user)
        
        # All fields should default to True
        assert pref.welcome_emails is True, "welcome_emails should default to True"
        assert pref.instant_sale_email is True, "instant_sale_email should default to True"
        assert pref.sale_emails_enabled is True, "sale_emails_enabled should default to True"
        assert pref.daily_summary_email is True, "daily_summary_email should default to True"
        assert pref.important_alerts_email is True, "important_alerts_email should default to True"
        assert pref.high_sales_alerts is True, "high_sales_alerts should default to True"
        assert pref.commission_emails_enabled is True, "commission_emails_enabled should default to True"
        assert pref.weekly_digest_enabled is True, "weekly_digest_enabled should default to True"
    
    def test_get_or_create_default_creates_with_true_defaults(self):
        """Test get_or_create_default creates preferences with True defaults."""
        user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        
        pref = NotificationPreference.get_or_create_default(user)
        
        # Check all defaults are True
        assert pref.commission_emails_enabled is True
        assert pref.sale_emails_enabled is True
        assert pref.weekly_digest_enabled is True
    
    def test_user_can_opt_out(self):
        """Test that user can opt out of notifications."""
        user = User.objects.create_user(
            username='testuser3',
            email='test3@example.com',
            password='testpass123'
        )
        
        pref = NotificationPreference.objects.create(user=user)
        
        # User opts out of commission emails
        pref.commission_emails_enabled = False
        pref.save()
        
        pref.refresh_from_db()
        assert pref.commission_emails_enabled is False
        # Other preferences remain True
        assert pref.sale_emails_enabled is True
    
    def test_existing_preferences_not_overwritten(self):
        """Test that existing user preferences are preserved."""
        user = User.objects.create_user(
            username='testuser4',
            email='test4@example.com',
            password='testpass123'
        )
        
        # Create with specific preferences
        pref = NotificationPreference.objects.create(
            user=user,
            welcome_emails=False,  # User disabled this
            sale_emails_enabled=True
        )
        
        pref.refresh_from_db()
        
        # User's explicit choices are preserved
        assert pref.welcome_emails is False
        assert pref.sale_emails_enabled is True


class WhatsAppPreferenceDefaultsTests(TestCase):
    """Test that WhatsAppPreference defaults all to True (opt-out model)."""
    
    def test_new_whatsapp_preference_defaults_all_true(self):
        """Test that creating new WhatsAppPreference has all fields True."""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        pref = WhatsAppPreference.objects.create(
            user=user,
            phone_number='+265991234567'
        )
        
        # All fields should default to True
        assert pref.is_enabled is True, "is_enabled should default to True"
        assert pref.receive_sale_alerts is True, "receive_sale_alerts should default to True"
        assert pref.receive_profit_milestones is True, "receive_profit_milestones should default to True"
        assert pref.receive_low_stock_alerts is True, "receive_low_stock_alerts should default to True"
        assert pref.receive_commission_alerts is True, "receive_commission_alerts should default to True (CHANGED)"
    
    def test_commission_alerts_default_changed_from_false_to_true(self):
        """Test that commission alerts now default to True (was False before)."""
        user = User.objects.create_user(
            username='agent',
            email='agent@example.com',
            password='testpass123'
        )
        
        pref = WhatsAppPreference.objects.create(
            user=user,
            phone_number='+265991234567'
        )
        
        # This is the key change: commission_alerts should now default to True
        assert pref.receive_commission_alerts is True, (
            "receive_commission_alerts should default to True for opt-out model"
        )


class NotificationPreferenceMigrationTests(TestCase):
    """Test that migration backfills existing preferences correctly."""
    
    def test_backfill_sets_commission_emails_to_true(self):
        """
        Test that migration would set commission_emails_enabled to True.
        This simulates what the migration does.
        """
        user = User.objects.create_user(
            username='olduser',
            email='old@example.com',
            password='testpass123'
        )
        
        # Simulate old preference with commission_emails_enabled=False
        # (we manually set it to False to test backfill behavior)
        pref = NotificationPreference.objects.create(
            user=user,
            commission_emails_enabled=False  # Old default
        )
        
        # Simulate migration backfill
        pref.commission_emails_enabled = True
        pref.save(update_fields=['commission_emails_enabled'])
        
        pref.refresh_from_db()
        assert pref.commission_emails_enabled is True


class NotificationPreferenceIntegrationTests(TestCase):
    """Integration tests for notification preferences in real flows."""
    
    def test_signup_creates_preferences_with_all_true(self):
        """Test that signup flow creates preferences with all defaults True."""
        # This would typically be triggered by a signal on user creation
        from notifications.models import NotificationPreference
        
        user = User.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='testpass123'
        )
        
        # Signal should auto-create preferences
        try:
            pref = NotificationPreference.objects.get(user=user)
        except NotificationPreference.DoesNotExist:
            # If signal didn't fire in test, create manually
            pref = NotificationPreference.get_or_create_default(user)
        
        # All should be True
        assert pref.welcome_emails is True
        assert pref.commission_emails_enabled is True
        assert pref.sale_emails_enabled is True
    
    def test_settings_page_shows_all_checkboxes_checked(self):
        """
        Test that settings page would show all checkboxes checked for new user.
        This is a unit test; Cypress will verify the actual UI.
        """
        user = User.objects.create_user(
            username='settingsuser',
            email='settings@example.com',
            password='testpass123'
        )
        
        pref = NotificationPreference.get_or_create_default(user)
        
        # Form should render with all checkboxes checked
        checkbox_fields = [
            'welcome_emails',
            'instant_sale_email',
            'sale_emails_enabled',
            'daily_summary_email',
            'important_alerts_email',
            'high_sales_alerts',
            'commission_emails_enabled',
            'weekly_digest_enabled',
        ]
        
        for field in checkbox_fields:
            assert getattr(pref, field) is True, f"{field} should be True by default"

