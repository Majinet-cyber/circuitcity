# tests/test_notifications.py
"""
Tests for the notification system.
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from notifications.models import Notification

User = get_user_model()


@pytest.mark.django_db
class NotificationTest(TestCase):
    """Test notification creation and retrieval."""
    
    def setUp(self):
        """Create test user."""
        self.user = User.objects.create_user(
            username="testuser",
            password="password123"
        )
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
    
    def test_create_notification(self):
        """Notifications can be created for users."""
        notif = Notification.objects.create(
            audience='AGENT',
            user=self.user,
            message="Test notification message",
            level='info'
        )
        
        self.assertEqual(notif.message, "Test notification message")
        self.assertFalse(notif.is_read)
    
    def test_mark_notification_as_read(self):
        """Notifications can be marked as read."""
        notif = Notification.objects.create(
            audience='AGENT',
            user=self.user,
            message="Test notification",
            level='info'
        )
        
        self.assertFalse(notif.is_read)
        
        notif.mark_read()
        notif.refresh_from_db()
        
        self.assertTrue(notif.is_read)
        self.assertIsNotNone(notif.read_at)
    
    def test_user_can_retrieve_notifications(self):
        """Users can retrieve their notifications."""
        # Create multiple notifications
        Notification.objects.create(
            audience='AGENT',
            user=self.user,
            message="Notification 1",
            level='info'
        )
        
        Notification.objects.create(
            audience='AGENT',
            user=self.user,
            message="Notification 2",
            level='success'
        )
        
        # Create notification for another user
        other_user = User.objects.create_user(username="other", password="pass")
        Notification.objects.create(
            audience='AGENT',
            user=other_user,
            message="Other user notification",
            level='info'
        )
        
        # Retrieve notifications for testuser
        user_notifs = Notification.objects.filter(user=self.user)
        
        self.assertEqual(user_notifs.count(), 2)
        messages = [n.message for n in user_notifs]
        self.assertIn("Notification 1", messages)
        self.assertIn("Notification 2", messages)
        self.assertNotIn("Other user notification", messages)

