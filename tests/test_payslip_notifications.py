# tests/test_payslip_notifications.py
"""
Tests for payslip notification alerts.
"""
import pytest
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from freezegun import freeze_time

from tenants.models import Business, Membership, Location
from notifications.models import Notification
from notifications.management.commands.create_payslip_alerts import create_monthly_payslip_alerts

User = get_user_model()


@pytest.mark.django_db
class TestPayslipNotifications(TestCase):
    """Test payslip reminder notification creation."""
    
    def setUp(self):
        """Create test data."""
        # Create business and location
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business"
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store"
        )
        
        # Create two active agents
        self.agent1 = User.objects.create_user(
            username="agent1",
            email="agent1@test.com",
            password="testpass123"
        )
        Membership.objects.create(
            user=self.agent1,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        self.agent2 = User.objects.create_user(
            username="agent2",
            email="agent2@test.com",
            password="testpass123"
        )
        Membership.objects.create(
            user=self.agent2,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
    
    def test_no_alert_created_on_non_27th(self):
        """No alerts should be created on days other than the 27th."""
        with freeze_time("2024-01-15"):
            today = date(2024, 1, 15)
            create_monthly_payslip_alerts(today=today)
            
            # Should not create any notifications
            count = Notification.objects.filter(
                category='payslip_reminder'
            ).count()
            self.assertEqual(count, 0)
    
    def test_alert_created_on_27th_for_each_membership(self):
        """Alerts should be created on the 27th for all active agents."""
        with freeze_time("2024-01-27"):
            today = date(2024, 1, 27)
            create_monthly_payslip_alerts(today=today)
            
            # Should create notifications for both agents
            notifications = Notification.objects.filter(
                category='payslip_reminder',
                business=self.business
            )
            self.assertEqual(notifications.count(), 2)
            
            # Verify both agents got notifications
            agent1_notif = notifications.filter(user=self.agent1).first()
            self.assertIsNotNone(agent1_notif)
            self.assertIn("payslip", agent1_notif.message.lower())
            
            agent2_notif = notifications.filter(user=self.agent2).first()
            self.assertIsNotNone(agent2_notif)
            self.assertIn("payslip", agent2_notif.message.lower())
    
    def test_alert_not_duplicated_when_called_twice_same_month(self):
        """Running the command twice in the same month should not duplicate alerts."""
        with freeze_time("2024-01-27"):
            today = date(2024, 1, 27)
            
            # Run command first time
            create_monthly_payslip_alerts(today=today)
            first_count = Notification.objects.filter(
                category='payslip_reminder',
                business=self.business
            ).count()
            self.assertEqual(first_count, 2)
            
            # Run command second time (same day)
            create_monthly_payslip_alerts(today=today)
            second_count = Notification.objects.filter(
                category='payslip_reminder',
                business=self.business
            ).count()
            
            # Should still be 2 (not 4)
            self.assertEqual(second_count, 2)
    
    def test_alert_created_in_different_months(self):
        """Alerts should be created separately for each month."""
        # January 27
        with freeze_time("2024-01-27"):
            create_monthly_payslip_alerts(today=date(2024, 1, 27))
            jan_count = Notification.objects.filter(
                category='payslip_reminder',
                business=self.business
            ).count()
            self.assertEqual(jan_count, 2)
        
        # February 27
        with freeze_time("2024-02-27"):
            create_monthly_payslip_alerts(today=date(2024, 2, 27))
            total_count = Notification.objects.filter(
                category='payslip_reminder',
                business=self.business
            ).count()
            # Should now have 4 total (2 from Jan + 2 from Feb)
            self.assertEqual(total_count, 4)

