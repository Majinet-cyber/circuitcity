# inventory/tests/test_gym_email_tasks.py
"""
Tests for gym email notification tasks.
Requires celery to be installed. Skipped automatically when celery is missing.
"""
import pytest

try:
    import celery  # noqa: F401
    HAS_CELERY = True
except ImportError:
    HAS_CELERY = False

if not HAS_CELERY:
    pytest.skip("celery not installed — skipping gym email task tests", allow_module_level=True)

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from inventory.models_verticals import GymCheckIn, GymMember, GymMemberStatus, GymPayment, GymTrainer, PaymentMethod

User = get_user_model()
from inventory.tasks_gym_emails import (
    notify_gym_payment_to_managers,
    send_gym_inactivity_reminders,
    send_gym_weekly_manager_summary,
)
from tenants.models import Business, Membership


class GymEmailTasksTestCase(TestCase):
    """Test gym email notification tasks"""

    def setUp(self):
        """Set up test data"""
        # Create business
        self.business = Business.objects.create(
            name="Test Gym",
            vertical="gym",
        )

        # Create users
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

        self.manager = User.objects.create_user(username="manager", email="manager@example.com", password="testpass123")

        # Create manager membership
        self.manager_membership = Membership.objects.create(
            business=self.business,
            user=self.manager,
            role="MANAGER",
            is_active=True,
        )

        # Set up dates
        self.today = timezone.now().date()
        self.two_days_ago = self.today - timedelta(days=2)

    def test_inactivity_reminder_eligibility(self):
        """Test that inactivity reminders are sent to eligible members"""
        # Create member who hasn't checked in for 3 days (eligible)
        member = GymMember.objects.create(
            business=self.business,
            name="Inactive Member",
            phone="0999111111",
            email="inactive@example.com",
            membership_start=self.today - timedelta(days=10),
            membership_end=self.today + timedelta(days=20),
            status=GymMemberStatus.ACTIVE,
        )

        # Last check-in was 3 days ago
        three_days_ago_dt = timezone.now() - timedelta(days=3)
        GymCheckIn.objects.create(
            business=self.business,
            member=member,
            timestamp=three_days_ago_dt,
            checked_in_by=self.user,
        )

        # Run task
        result = send_gym_inactivity_reminders()

        # Should send 1 email
        self.assertEqual(result["sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(member.email, mail.outbox[0].to)
        self.assertIn("missed you", mail.outbox[0].subject.lower())

    def test_inactivity_reminder_skips_no_email(self):
        """Test that members without email are skipped"""
        member = GymMember.objects.create(
            business=self.business,
            name="No Email Member",
            phone="0999111111",
            email="",  # No email
            membership_start=self.today - timedelta(days=10),
            membership_end=self.today + timedelta(days=20),
            status=GymMemberStatus.ACTIVE,
        )

        # Run task
        result = send_gym_inactivity_reminders()

        # Should skip
        self.assertEqual(result["sent"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactivity_reminder_skips_expired_membership(self):
        """Test that expired members don't get reminders"""
        member = GymMember.objects.create(
            business=self.business,
            name="Expired Member",
            phone="0999111111",
            email="expired@example.com",
            membership_start=self.today - timedelta(days=40),
            membership_end=self.today - timedelta(days=10),  # Expired
            status=GymMemberStatus.EXPIRED,
        )

        # Run task
        result = send_gym_inactivity_reminders()

        # Should skip expired members
        self.assertEqual(result["sent"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactivity_reminder_skips_recent_checkin(self):
        """Test that members who checked in recently are skipped"""
        member = GymMember.objects.create(
            business=self.business,
            name="Active Member",
            phone="0999111111",
            email="active@example.com",
            membership_start=self.today - timedelta(days=10),
            membership_end=self.today + timedelta(days=20),
            status=GymMemberStatus.ACTIVE,
        )

        # Checked in yesterday (within 2 days)
        yesterday_dt = timezone.now() - timedelta(days=1)
        GymCheckIn.objects.create(
            business=self.business,
            member=member,
            timestamp=yesterday_dt,
            checked_in_by=self.user,
        )

        # Run task
        result = send_gym_inactivity_reminders()

        # Should skip (checked in within 2 days)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_weekly_manager_summary_sends_to_managers(self):
        """Test that weekly summary is sent to managers"""
        # Create some test data
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0999111111",
            email="member@example.com",
            membership_start=self.today - timedelta(days=5),
            membership_end=self.today + timedelta(days=25),
            status=GymMemberStatus.ACTIVE,
        )

        # Create check-in this week
        today_dt = timezone.now()
        GymCheckIn.objects.create(
            business=self.business,
            member=member,
            timestamp=today_dt,
            checked_in_by=self.user,
        )

        # Create payment this week
        GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("50000.00"),
            amount=Decimal("50000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
            paid_by=self.user,
            paid_at=today_dt,
        )

        # Run task
        result = send_gym_weekly_manager_summary()

        # Should send 1 email to manager
        self.assertEqual(result["sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.manager.email, mail.outbox[0].to)
        self.assertIn("Weekly", mail.outbox[0].subject)
        self.assertIn(self.business.name, mail.outbox[0].subject)

    def test_weekly_manager_summary_skips_no_managers(self):
        """Test that businesses without managers are skipped"""
        # Create business without managers
        other_business = Business.objects.create(
            name="No Manager Gym",
            vertical="gym",
        )

        member = GymMember.objects.create(
            business=other_business,
            name="Test Member",
            phone="0999111111",
            membership_start=self.today,
            membership_end=self.today + timedelta(days=30),
            status=GymMemberStatus.ACTIVE,
        )

        # Run task
        result = send_gym_weekly_manager_summary()

        # Should skip businesses without managers
        self.assertEqual(len(mail.outbox), 0)

    def test_payment_notification_sends_immediately(self):
        """Test that payment notification is sent immediately"""
        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0999111111",
            email="member@example.com",
            membership_start=self.today,
            membership_end=self.today + timedelta(days=30),
            status=GymMemberStatus.ACTIVE,
            member_number="GYM-000001",
        )

        payment = GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("50000.00"),
            trainer_fee=Decimal("20000.00"),
            amount=Decimal("70000.00"),
            payment_method=PaymentMethod.CASH,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
            paid_by=self.user,
        )

        # Run task
        result = notify_gym_payment_to_managers(payment.id)

        # Should send email to manager
        self.assertEqual(result["sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.manager.email, mail.outbox[0].to)
        self.assertIn("Payment", mail.outbox[0].subject)
        self.assertIn(member.name, mail.outbox[0].subject)

    def test_payment_notification_includes_details(self):
        """Test that payment notification includes all required details"""
        trainer = GymTrainer.objects.create(
            business=self.business,
            name="Test Trainer",
            phone="0999123456",
        )

        member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0999111111",
            email="member@example.com",
            membership_start=self.today,
            membership_end=self.today + timedelta(days=30),
            status=GymMemberStatus.ACTIVE,
            member_number="GYM-000001",
            trainer=trainer,
        )

        payment = GymPayment.objects.create(
            member=member,
            membership_amount=Decimal("50000.00"),
            trainer=trainer,
            trainer_fee=Decimal("20000.00"),
            amount=Decimal("70000.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            start_date=self.today,
            end_date=self.today + timedelta(days=30),
            paid_by=self.user,
        )

        # Run task
        result = notify_gym_payment_to_managers(payment.id)

        # Check email content
        email = mail.outbox[0]
        email_body = email.body

        # Should include member details
        self.assertIn(member.name, email_body)
        self.assertIn(member.member_number, email_body)

        # Should include payment details
        self.assertIn("70000.00", email_body)  # Total amount
        self.assertIn("50000.00", email_body)  # Membership amount
        self.assertIn("20000.00", email_body)  # Trainer fee

        # Should include trainer name
        self.assertIn(trainer.name, email_body)

    def test_tenant_isolation_in_emails(self):
        """Test that emails are properly scoped to business"""
        # Create another business
        other_business = Business.objects.create(
            name="Other Gym",
            vertical="gym",
        )

        # Create manager for other business
        other_manager = User.objects.create_user(
            username="othermanager", email="othermanager@example.com", password="testpass123"
        )

        Membership.objects.create(
            business=other_business,
            user=other_manager,
            role="MANAGER",
            is_active=True,
        )

        # Create member in our business
        member = GymMember.objects.create(
            business=self.business,
            name="Our Member",
            phone="0999111111",
            email="our@example.com",
            membership_start=self.today - timedelta(days=10),
            membership_end=self.today + timedelta(days=20),
            status=GymMemberStatus.ACTIVE,
        )

        # Last check-in was 3 days ago
        three_days_ago_dt = timezone.now() - timedelta(days=3)
        GymCheckIn.objects.create(
            business=self.business,
            member=member,
            timestamp=three_days_ago_dt,
            checked_in_by=self.user,
        )

        # Run inactivity reminders
        send_gym_inactivity_reminders()

        # Should only send to our member, not other business
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(member.email, mail.outbox[0].to)
        self.assertNotIn(other_manager.email, mail.outbox[0].to)
