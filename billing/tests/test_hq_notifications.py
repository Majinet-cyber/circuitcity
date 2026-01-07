# billing/tests/test_hq_notifications.py
"""
Tests for HQ notification service (idempotency, content, recipients).
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import call, patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from billing.models import BusinessSubscription, Invoice, InvoiceItem, SubscriptionPlan
from billing.services import notify_hq
from tenants.models import Business

User = get_user_model()


@pytest.mark.django_db
class TestHQNotifications(TestCase):
    """Test HQ notification service."""

    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(
            name="Test Business HQ",
            slug="test-business-hq",
            business_kind="CLOTHING",
        )
        # Use get_or_create to avoid UNIQUE constraint errors
        self.plan, _ = SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter",
                "amount": Decimal("20000.00"),
                "currency": "MWK",
                "interval": SubscriptionPlan.Interval.MONTH,
            },
        )
        now = timezone.now()
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status=BusinessSubscription.Status.ACTIVE,
            current_period_start=now - timedelta(days=10),
            current_period_end=now + timedelta(days=20),
        )

    def test_notify_new_signup_sends_email(self):
        """Test new signup notification sends email to HQ."""
        # Clear mail outbox
        mail.outbox = []

        # Notify HQ
        notify_hq.notify_new_signup(self.business)

        # Assert email sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Check recipients
        self.assertIn("info@imajinet.com", email.to)
        self.assertIn("jadepaulchris@gmail.com", email.to)

        # Check subject
        self.assertIn("[Emajinet]", email.subject)
        self.assertIn("New signup", email.subject)
        self.assertIn("Test Business HQ", email.subject)

        # Check body
        self.assertIn("Test Business HQ", email.body)
        self.assertIn("CLOTHING", email.body)

    def test_notify_new_signup_idempotent(self):
        """Test new signup notification is idempotent (only sends once)."""
        mail.outbox = []

        # First call: should send
        notify_hq.notify_new_signup(self.business)
        self.assertEqual(len(mail.outbox), 1)

        # Second call: should NOT send (already notified)
        notify_hq.notify_new_signup(self.business)
        self.assertEqual(len(mail.outbox), 1)  # Still 1 email

        # Verify hq_notified_signup_at is set
        self.business.refresh_from_db()
        self.assertIsNotNone(self.business.hq_notified_signup_at)

    def test_notify_subscription_paid_sends_email(self):
        """Test subscription paid notification sends email to HQ."""
        mail.outbox = []

        # Create invoice
        invoice = Invoice.objects.create(
            business=self.business,
            subscription=self.subscription,
            status=Invoice.Status.PAID,
            total=Decimal("20000.00"),
            currency="MWK",
            paid_at=timezone.now(),
        )

        # Notify HQ
        notify_hq.notify_subscription_paid(invoice, self.subscription)

        # Assert email sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Check subject
        self.assertIn("[Emajinet]", email.subject)
        self.assertIn("Subscription paid", email.subject)
        self.assertIn("Test Business HQ", email.subject)

        # Check body
        self.assertIn("Test Business HQ", email.body)
        self.assertIn("Starter", email.body)
        self.assertIn("MWK 20,000", email.body)

    def test_notify_subscription_paid_idempotent(self):
        """Test subscription paid notification is idempotent."""
        mail.outbox = []

        invoice = Invoice.objects.create(
            business=self.business,
            subscription=self.subscription,
            status=Invoice.Status.PAID,
            total=Decimal("20000.00"),
            currency="MWK",
            paid_at=timezone.now(),
        )

        # First call: should send
        notify_hq.notify_subscription_paid(invoice, self.subscription)
        self.assertEqual(len(mail.outbox), 1)

        # Second call: should NOT send
        notify_hq.notify_subscription_paid(invoice, self.subscription)
        self.assertEqual(len(mail.outbox), 1)

        # Verify hq_notified_paid_at is set
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.hq_notified_paid_at)

    def test_notify_cancellation_requested_sends_email(self):
        """Test cancellation request notification sends email to HQ."""
        mail.outbox = []

        # Set cancellation request
        self.subscription.cancel_at_period_end = True
        self.subscription.cancel_requested_at = timezone.now()
        self.subscription.save()

        # Notify HQ
        notify_hq.notify_cancellation_requested(self.subscription)

        # Assert email sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Check subject
        self.assertIn("[Emajinet]", email.subject)
        self.assertIn("Cancellation requested", email.subject)

        # Check body
        self.assertIn("Test Business HQ", email.body)
        self.assertIn("Starter", email.body)

    def test_notify_cancellation_requested_idempotent(self):
        """Test cancellation request notification is idempotent."""
        mail.outbox = []

        self.subscription.cancel_at_period_end = True
        self.subscription.cancel_requested_at = timezone.now()
        self.subscription.save()

        # First call: should send
        notify_hq.notify_cancellation_requested(self.subscription)
        self.assertEqual(len(mail.outbox), 1)

        # Second call: should NOT send
        notify_hq.notify_cancellation_requested(self.subscription)
        self.assertEqual(len(mail.outbox), 1)

        # Verify hq_notified_cancel_requested_at is set
        self.subscription.refresh_from_db()
        self.assertIsNotNone(self.subscription.hq_notified_cancel_requested_at)

    def test_notify_cancellation_effective_sends_email(self):
        """Test effective cancellation notification sends email to HQ."""
        mail.outbox = []

        # Set subscription as canceled
        self.subscription.status = BusinessSubscription.Status.CANCELED
        self.subscription.canceled_at = timezone.now()
        self.subscription.save()

        # Notify HQ
        notify_hq.notify_cancellation_effective(self.subscription)

        # Assert email sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Check subject
        self.assertIn("[Emajinet]", email.subject)
        self.assertIn("Subscription canceled", email.subject)

        # Check body
        self.assertIn("Test Business HQ", email.body)

    def test_notify_cancellation_effective_idempotent(self):
        """Test effective cancellation notification is idempotent."""
        mail.outbox = []

        self.subscription.status = BusinessSubscription.Status.CANCELED
        self.subscription.canceled_at = timezone.now()
        self.subscription.save()

        # First call: should send
        notify_hq.notify_cancellation_effective(self.subscription)
        self.assertEqual(len(mail.outbox), 1)

        # Second call: should NOT send
        notify_hq.notify_cancellation_effective(self.subscription)
        self.assertEqual(len(mail.outbox), 1)

        # Verify hq_notified_canceled_at is set
        self.subscription.refresh_from_db()
        self.assertIsNotNone(self.subscription.hq_notified_canceled_at)

    def test_notify_subscription_suspended_sends_email(self):
        """Test suspension notification sends email to HQ."""
        mail.outbox = []

        # Set subscription as suspended
        self.subscription.status = BusinessSubscription.Status.SUSPENDED
        self.subscription.suspended_at = timezone.now()
        self.subscription.save()

        # Notify HQ
        notify_hq.notify_subscription_suspended(self.subscription)

        # Assert email sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Check subject
        self.assertIn("[Emajinet]", email.subject)
        self.assertIn("Subscription suspended", email.subject)

        # Check body
        self.assertIn("Test Business HQ", email.body)

    def test_notify_subscription_suspended_idempotent(self):
        """Test suspension notification is idempotent."""
        mail.outbox = []

        self.subscription.status = BusinessSubscription.Status.SUSPENDED
        self.subscription.suspended_at = timezone.now()
        self.subscription.save()

        # First call: should send
        notify_hq.notify_subscription_suspended(self.subscription)
        self.assertEqual(len(mail.outbox), 1)

        # Second call: should NOT send
        notify_hq.notify_subscription_suspended(self.subscription)
        self.assertEqual(len(mail.outbox), 1)

        # Verify hq_notified_suspended_at is set
        self.subscription.refresh_from_db()
        self.assertIsNotNone(self.subscription.hq_notified_suspended_at)

    def test_hq_recipients_include_admin_email(self):
        """Test HQ recipients include admin email from settings."""
        with patch("billing.services.notify_hq._get_admin_email", return_value="admin@example.com"):
            recipients = notify_hq._get_hq_recipients()
            self.assertIn("info@imajinet.com", recipients)
            self.assertIn("jadepaulchris@gmail.com", recipients)
            self.assertIn("admin@example.com", recipients)

    def test_daily_summary_includes_all_stats(self):
        """Test daily summary includes all relevant statistics."""
        # Create some activity today
        now = timezone.now()

        # Create paid invoice
        invoice = Invoice.objects.create(
            business=self.business,
            subscription=self.subscription,
            status=Invoice.Status.PAID,
            total=Decimal("20000.00"),
            currency="MWK",
            paid_at=now,
        )

        # Get summary
        summary = notify_hq._get_today_summary()

        # Assert statistics
        self.assertGreaterEqual(summary["paid_count"], 1)
        self.assertGreaterEqual(summary["paid_total"], Decimal("20000.00"))
        self.assertIn("vertical_breakdown", summary)
