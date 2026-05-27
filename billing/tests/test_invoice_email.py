# billing/tests/test_invoice_email.py
"""
Tests for invoice email notifications (STEP 6).
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core import mail

from billing.models import BusinessSubscription, Invoice, InvoiceItem, SubscriptionPlan
from billing import tasks
from tests.helpers.tenant_setup import make_business, make_membership, make_user


@pytest.mark.django_db
class TestInvoiceEmailTask:
    """Test invoice email Celery task."""

    @pytest.fixture
    def setup_data(self):
        """Create test invoice."""
        user = make_user(email="manager@test.com", password="pass")
        business = make_business(created_by=user, name="Test Business", slug="test-biz")
        # Note: Business model may not have email field, will fallback to manager
        make_membership(business=business, user=user, role="MANAGER")

        plan = SubscriptionPlan.objects.create(
            code="test-plan",
            name="Test Plan",
            amount=Decimal("10000.00"),
            currency="MWK",
        )

        subscription = BusinessSubscription.start_trial(
            business=business,
            plan=plan,
            days=30,
        )

        invoice = Invoice.objects.create(
            business=business,
            subscription=subscription,
            created_by=user,
            currency="MWK",
            status=Invoice.Status.PAID,
            provider_reference="pc-tx-12345",
        )

        InvoiceItem.objects.create(
            invoice=invoice,
            description="Test Plan — Monthly",
            qty=Decimal("1"),
            unit="mo",
            unit_price=Decimal("10000.00"),
        )

        invoice.recalc_totals(save=True)

        return {
            "user": user,
            "business": business,
            "subscription": subscription,
            "invoice": invoice,
        }

    def test_send_invoice_paid_email_sends_email(self, setup_data):
        """Test that task sends email successfully."""
        invoice = setup_data["invoice"]

        # Clear mail outbox before test
        mail.outbox.clear()

        # Call task directly (not async in tests)
        tasks.send_invoice_paid_email(invoice.id)

        # Check that email was sent
        assert len(mail.outbox) == 1

        # Check email properties
        email = mail.outbox[0]
        assert "Payment Confirmed" in email.subject
        assert invoice.number in email.subject
        assert "manager@test.com" in email.to  # Falls back to manager email

        # Check email body
        assert invoice.number in email.body  # Plain text
        assert "10,000" in email.body or "10000" in email.body

    def test_send_invoice_paid_email_contains_invoice_details(self, setup_data):
        """Test that email contains all invoice details."""
        invoice = setup_data["invoice"]

        tasks.send_invoice_paid_email(invoice.id)

        email = mail.outbox[0]

        # Check HTML alternative
        html_content = email.alternatives[0][0]
        assert invoice.number in html_content
        assert "Test Business" in html_content
        assert "pc-tx-12345" in html_content  # Provider reference

    def test_send_invoice_paid_email_fallback_to_user_email(self, setup_data):
        """Test email fallback when business has no email."""
        invoice = setup_data["invoice"]

        # Clear mail outbox
        mail.outbox.clear()

        tasks.send_invoice_paid_email(invoice.id)

        # Should use manager/user email (business has no email field)
        assert len(mail.outbox) == 1
        assert "manager@test.com" in mail.outbox[0].to

    def test_send_invoice_paid_email_skips_if_not_paid(self, setup_data):
        """Test that email is not sent if invoice not PAID."""
        invoice = setup_data["invoice"]

        # Mark invoice as DRAFT
        invoice.status = Invoice.Status.DRAFT
        invoice.save()

        tasks.send_invoice_paid_email(invoice.id)

        # No email should be sent
        assert len(mail.outbox) == 0

    def test_send_invoice_paid_email_handles_missing_invoice(self):
        """Test that task handles missing invoice gracefully."""
        # Call with non-existent ID
        tasks.send_invoice_paid_email("00000000-0000-0000-0000-000000000000")

        # Should not crash, no email sent
        assert len(mail.outbox) == 0

    # NOTE: PDF attachment tests are skipped because mocking FileField
    # causes Django query issues. PDF attachment is tested manually.


@pytest.mark.django_db
class TestInvoicePaidEmailIntegration:
    """Test invoice paid email is triggered by domain service."""

    @pytest.fixture
    def setup_data(self):
        """Create test data."""
        user = make_user(email="manager@test.com", password="pass")
        business = make_business(created_by=user, name="Test Business", slug="test-biz")
        # Business email will fallback to manager
        make_membership(business=business, user=user, role="MANAGER")

        plan = SubscriptionPlan.objects.create(
            code="test-plan",
            name="Test Plan",
            amount=Decimal("10000.00"),
            currency="MWK",
        )

        subscription = BusinessSubscription.start_trial(
            business=business,
            plan=plan,
            days=30,
        )

        invoice = Invoice.objects.create(
            business=business,
            subscription=subscription,
            created_by=user,
            currency="MWK",
            status=Invoice.Status.ISSUED,  # Not paid yet
        )

        InvoiceItem.objects.create(
            invoice=invoice,
            description="Test Plan",
            qty=Decimal("1"),
            unit_price=Decimal("10000.00"),
        )

        invoice.recalc_totals(save=True)

        return {
            "user": user,
            "business": business,
            "subscription": subscription,
            "invoice": invoice,
        }

    @patch("billing.tasks.send_invoice_paid_email.delay")
    def test_email_task_queued_when_invoice_marked_paid(self, mock_email_task, setup_data):
        """Test that email task is queued when invoice marked paid via domain service."""
        from billing import domain
        from billing.models import PaymentTransaction

        invoice = setup_data["invoice"]

        # Create payment transaction
        transaction = PaymentTransaction.objects.create(
            business=setup_data["business"],
            provider="PAYCHANGU",
            tx_ref="test-tx-ref",
            amount=Decimal("10000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.SUCCESS,
        )

        # Mark invoice paid via domain service
        domain.apply_payment_to_invoice(invoice, transaction)

        # Email task should be queued
        mock_email_task.assert_called_once_with(invoice.id)

    def test_email_template_renders_correctly(self, setup_data):
        """Test that email templates render without errors."""
        from django.template.loader import render_to_string

        invoice = setup_data["invoice"]
        invoice.status = Invoice.Status.PAID
        invoice.save()

        context = {
            "invoice": invoice,
            "business": setup_data["business"],
            "subscription": setup_data["subscription"],
            "next_billing_date": setup_data["subscription"].current_period_end,
            "payment_method": "Mobile Money",
            "provider_reference": "pc-tx-12345",
            "download_url": "https://test.com/download/",
            "dashboard_url": "https://test.com/",
            "support_url": "mailto:support@test.com",
        }

        # Render HTML template
        html_content = render_to_string("billing/emails/invoice_paid.html", context)
        assert invoice.number in html_content
        assert "Test Business" in html_content
        assert "Payment Confirmed" in html_content

        # Render text template
        text_content = render_to_string("billing/emails/invoice_paid.txt", context)
        assert invoice.number in text_content
        assert "Test Business" in text_content
        assert "PAYMENT CONFIRMED" in text_content.upper()

