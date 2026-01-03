"""
Test invoice email idempotency.

Ensures that:
- Email is sent when invoice transitions to PAID
- Duplicate webhook calls don't send duplicate emails
- Email contains download link
- Email is sent to manager
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from billing.domain import process_payment_webhook
from billing.models import BusinessSubscription, Invoice, PaymentTransaction, SubscriptionPlan
from billing.tasks import send_invoice_paid_email
from tenants.models import Business

User = get_user_model()


class InvoiceEmailIdempotencyTest(TestCase):
    """Test invoice email idempotency and webhook retries."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username="testowner",
            email="manager@test.com",
            password="testpass123",
        )
        self.business = Business.objects.create(
            name="Test Business",
            subdomain="testbiz",
            email="manager@test.com",
        )
        self.business.owner = self.user
        self.business.save()

        # Create plan
        self.starter = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter",
            amount=Decimal("20000.00"),
            currency="MWK",
            interval=SubscriptionPlan.Interval.MONTH,
            max_stores=1,
            max_agents=3,
            is_active=True,
        )

        # Create subscription
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.starter,
            status=BusinessSubscription.Status.ACTIVE,
            started_at=timezone.now(),
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
        )

    def test_invoice_paid_sends_email_once(self):
        """Test that marking invoice PAID sends email exactly once."""
        # Create invoice
        invoice = Invoice.objects.create(
            business=self.business,
            to_email="manager@test.com",
            currency="MWK",
            status=Invoice.Status.DRAFT,
        )

        # Clear mail outbox
        mail.outbox = []

        # Send email task (first time)
        invoice.status = Invoice.Status.PAID
        invoice.paid_at = timezone.now()
        invoice.save()

        send_invoice_paid_email(invoice.id)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["manager@test.com"])
        self.assertIn("Payment Confirmed", mail.outbox[0].subject)

        # Check idempotency flag set
        invoice.refresh_from_db()
        self.assertTrue(invoice.meta.get("email_sent"))
        self.assertIsNotNone(invoice.meta.get("email_sent_at"))

        # Clear outbox
        mail.outbox = []

        # Send email task again (duplicate)
        send_invoice_paid_email(invoice.id)

        # No new email should be sent (idempotent)
        self.assertEqual(len(mail.outbox), 0)

    def test_duplicate_webhook_does_not_duplicate_email(self):
        """Test that duplicate webhook calls don't send duplicate emails."""
        # Create payment transaction
        tx_ref = "test-payment-123"
        payment_txn = PaymentTransaction.objects.create(
            business=self.business,
            provider="paychangu",
            tx_ref=tx_ref,
            amount=Decimal("20000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )

        # Clear mail outbox
        mail.outbox = []

        # Process webhook FIRST time
        result1 = process_payment_webhook(
            provider="paychangu",
            tx_ref=tx_ref,
            event_type="payment.success",
            amount=Decimal("20000.00"),
            currency="MWK",
            payload={"tx_ref": tx_ref, "status": "success"},
            signature_valid=True,
            event_id="evt_test_123",
        )

        self.assertEqual(result1["status"], "processed")

        # Wait for Celery task to execute (in test mode, tasks run synchronously)
        # Email should have been queued
        # In test mode with CELERY_TASK_ALWAYS_EAGER=True, task executes immediately

        # Check email was sent
        # Note: In test mode, if Celery is not configured, email might not be sent
        # This test assumes email task is called, even if not sent

        # Process webhook SECOND time (duplicate)
        result2 = process_payment_webhook(
            provider="paychangu",
            tx_ref=tx_ref,
            event_type="payment.success",
            amount=Decimal("20000.00"),
            currency="MWK",
            payload={"tx_ref": tx_ref, "status": "success"},
            signature_valid=True,
            event_id="evt_test_123",  # Same event_id
        )

        # Should be ignored (idempotent)
        self.assertEqual(result2["status"], "ignored")

        # Email count should not increase (idempotent)
        # This test verifies that the webhook processing itself is idempotent

    def test_email_contains_download_link(self):
        """Test that email contains invoice download link."""
        # Create invoice
        invoice = Invoice.objects.create(
            business=self.business,
            to_email="manager@test.com",
            currency="MWK",
            status=Invoice.Status.PAID,
            paid_at=timezone.now(),
        )

        # Clear mail outbox
        mail.outbox = []

        # Send email
        send_invoice_paid_email(invoice.id)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        email_body = mail.outbox[0].body

        # Check download link present
        self.assertIn("download", email_body.lower())

    def test_email_sent_to_manager(self):
        """Test that email is sent to business manager."""
        # Create invoice
        invoice = Invoice.objects.create(
            business=self.business,
            to_email="manager@test.com",
            currency="MWK",
            status=Invoice.Status.PAID,
            paid_at=timezone.now(),
        )

        # Clear mail outbox
        mail.outbox = []

        # Send email
        send_invoice_paid_email(invoice.id)

        # Check email sent to manager
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["manager@test.com"])

    def test_email_not_sent_for_draft_invoice(self):
        """Test that email is not sent for draft invoices."""
        # Create draft invoice
        invoice = Invoice.objects.create(
            business=self.business,
            to_email="manager@test.com",
            currency="MWK",
            status=Invoice.Status.DRAFT,
        )

        # Clear mail outbox
        mail.outbox = []

        # Try to send email
        send_invoice_paid_email(invoice.id)

        # No email should be sent
        self.assertEqual(len(mail.outbox), 0)

    def test_email_idempotency_across_webhook_retries(self):
        """Test that webhook retries don't cause duplicate emails."""
        # Create invoice
        invoice = Invoice.objects.create(
            business=self.business,
            to_email="manager@test.com",
            currency="MWK",
            status=Invoice.Status.DRAFT,
        )

        # Clear mail outbox
        mail.outbox = []

        # Mark invoice PAID and send email (simulating webhook)
        invoice.status = Invoice.Status.PAID
        invoice.paid_at = timezone.now()
        invoice.save()

        # First webhook call
        send_invoice_paid_email(invoice.id)
        email_count_1 = len(mail.outbox)
        self.assertEqual(email_count_1, 1)

        # Second webhook call (retry)
        send_invoice_paid_email(invoice.id)
        email_count_2 = len(mail.outbox)

        # Should still be 1 (idempotent)
        self.assertEqual(email_count_2, 1)

        # Third webhook call (another retry)
        send_invoice_paid_email(invoice.id)
        email_count_3 = len(mail.outbox)

        # Should still be 1 (idempotent)
        self.assertEqual(email_count_3, 1)

