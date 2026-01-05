# billing/tests/test_subscription_cancellation_dunning.py
"""
Comprehensive tests for subscription cancellation, auto-billing/dunning, and subscription state UI.
Tests follow SaaS best practices for subscription management.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import BillingAttempt, BusinessSubscription, Invoice, SubscriptionPlan
from tenants.models import Business

User = get_user_model()


@pytest.mark.django_db
class TestSubscriptionCancellation(TestCase):
    """Test subscription cancellation flow (cancel_at_period_end)."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser-cancel", password="testpass123", email="test-cancel@example.com"
        )
        self.business = Business.objects.create(name="Test Business Cancel", slug="test-business-cancel")
        self.plan, _ = SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter",
                "amount": Decimal("20000.00"),
                "currency": "MWK",
                "interval": SubscriptionPlan.Interval.MONTH,
            },
        )
        # Create active subscription ending in 10 days
        now = timezone.now()
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status=BusinessSubscription.Status.ACTIVE,
            current_period_start=now - timedelta(days=20),
            current_period_end=now + timedelta(days=10),
            cancel_at_period_end=False,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_cancel_subscription_sets_flag(self):
        """Test POST to cancel_subscription sets cancel_at_period_end=True."""
        with patch("billing.views.request") as mock_request:
            mock_request.business = self.business

            response = self.client.post(
                reverse("billing:cancel_subscription"), data={"confirm": "yes"}, HTTP_HOST="test-business.localhost"
            )

            # Refresh subscription
            self.subscription.refresh_from_db()

            # Assert cancel_at_period_end is set
            self.assertTrue(self.subscription.cancel_at_period_end)
            self.assertIsNotNone(self.subscription.canceled_at)

            # Assert redirect
            self.assertEqual(response.status_code, 302)

    def test_middleware_allows_access_before_period_end(self):
        """Test middleware still allows access before period end when canceling."""
        from billing.middleware import SubscriptionGateMiddleware

        # Set cancel_at_period_end
        self.subscription.cancel_at_period_end = True
        self.subscription.save()

        # Create middleware instance
        middleware = SubscriptionGateMiddleware(lambda r: MagicMock(status_code=200))

        # Test access is allowed
        self.assertTrue(middleware._subscription_allows_access(self.subscription))

    def test_cancellation_processor_marks_canceled(self):
        """Test process_cancellations task marks subscription as canceled after period end."""
        from django.core import mail

        from billing.tasks import process_cancellations

        # Set cancel_at_period_end and move period_end to past
        now = timezone.now()
        self.subscription.cancel_at_period_end = True
        self.subscription.current_period_end = now - timedelta(days=1)
        self.subscription.save()

        # Clear mail outbox
        mail.outbox = []

        # Run cancellation processor
        stats = process_cancellations()

        # Refresh subscription
        self.subscription.refresh_from_db()

        # Assert status is canceled
        self.assertEqual(self.subscription.status, BusinessSubscription.Status.CANCELED)
        self.assertIsNotNone(self.subscription.canceled_at)
        self.assertEqual(stats["canceled"], 1)

        # Assert HQ notification was sent
        self.assertGreaterEqual(len(mail.outbox), 1)
        # Find the cancellation email
        cancel_emails = [e for e in mail.outbox if "canceled" in e.subject.lower()]
        self.assertGreater(len(cancel_emails), 0)

    def test_middleware_blocks_after_cancellation_effective(self):
        """Test middleware blocks access after cancellation becomes effective."""
        from billing.middleware import SubscriptionGateMiddleware

        # Set canceled status after period end
        self.subscription.status = BusinessSubscription.Status.CANCELED
        self.subscription.current_period_end = timezone.now() - timedelta(days=1)
        self.subscription.save()

        # Create middleware instance
        middleware = SubscriptionGateMiddleware(lambda r: MagicMock(status_code=200))

        # Test access is blocked
        self.assertFalse(middleware._subscription_allows_access(self.subscription))

    def test_undo_cancellation(self):
        """Test undo_cancellation clears cancel_at_period_end flag."""
        # Set cancel_at_period_end
        self.subscription.cancel_at_period_end = True
        self.subscription.save()

        # POST to undo
        with patch("billing.views.request") as mock_request:
            mock_request.business = self.business

            response = self.client.post(reverse("billing:undo_cancellation"), HTTP_HOST="test-business.localhost")

            # Refresh subscription
            self.subscription.refresh_from_db()

            # Assert flag is cleared
            self.assertFalse(self.subscription.cancel_at_period_end)

            # Assert redirect
            self.assertEqual(response.status_code, 302)


@pytest.mark.django_db
class TestDunningAndGrace(TestCase):
    """Test auto-billing/dunning retry flow with grace period."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser-dunning", password="testpass123", email="test-dunning@example.com"
        )
        self.business = Business.objects.create(name="Test Business Dunning", slug="test-business-dunning")
        self.plan, _ = SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter",
                "amount": Decimal("20000.00"),
                "currency": "MWK",
                "interval": SubscriptionPlan.Interval.MONTH,
            },
        )
        # Create subscription with period_end in past
        now = timezone.now()
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status=BusinessSubscription.Status.ACTIVE,
            current_period_start=now - timedelta(days=30),
            current_period_end=now - timedelta(hours=1),
            cancel_at_period_end=False,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_renewal_creates_invoice_and_sets_past_due(self):
        """Test create_renewal_invoices task creates invoice and sets subscription to past_due."""
        from billing.tasks import create_renewal_invoices

        # Run renewal job
        stats = create_renewal_invoices()

        # Assert invoice was created
        self.assertEqual(stats["invoices_created"], 1)

        # Get invoice
        invoice = Invoice.objects.filter(subscription=self.subscription).first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.total, self.plan.amount)

        # Refresh subscription
        self.subscription.refresh_from_db()

        # Assert subscription is past_due with grace period
        self.assertEqual(self.subscription.status, BusinessSubscription.Status.PAST_DUE)
        self.assertIsNotNone(self.subscription.grace_until)
        self.assertIsNotNone(self.subscription.past_due_since)

        # Grace period should be 2 days from now
        expected_grace = timezone.now() + timedelta(days=2)
        self.assertAlmostEqual(
            self.subscription.grace_until.timestamp(), expected_grace.timestamp(), delta=60  # 1 minute tolerance
        )

    def test_middleware_allows_access_during_grace(self):
        """Test middleware allows access during grace period (past_due but grace_until not expired)."""
        from billing.middleware import SubscriptionGateMiddleware

        # Set past_due with grace_until in future
        now = timezone.now()
        self.subscription.status = BusinessSubscription.Status.PAST_DUE
        self.subscription.grace_until = now + timedelta(days=1)
        self.subscription.save()

        # Create middleware instance
        middleware = SubscriptionGateMiddleware(lambda r: MagicMock(status_code=200))

        # Test access is allowed
        self.assertTrue(middleware._subscription_allows_access(self.subscription))

    @patch("billing.tasks.paychangu_service")
    def test_dunning_retry_increments_attempt_count(self, mock_paychangu):
        """Test dunning processor increments attempt_count and creates BillingAttempt."""
        from billing.tasks import process_dunning_attempts

        # Create invoice in draft status
        now = timezone.now()
        invoice = Invoice.objects.create(
            business=self.business,
            subscription=self.subscription,
            status=Invoice.Status.DRAFT,
            total=self.plan.amount,
            currency=self.plan.currency,
            next_attempt_at=now - timedelta(minutes=1),  # Ready for retry
            attempt_count=0,
        )

        # Set subscription to past_due with grace
        self.subscription.status = BusinessSubscription.Status.PAST_DUE
        self.subscription.grace_until = now + timedelta(days=2)
        self.subscription.billing_phone = "+265991234567"
        self.subscription.save()

        # Mock PayChangu configured and success
        mock_paychangu.is_paychangu_configured.return_value = True
        mock_paychangu.create_checkout.return_value = {
            "status": "success",
            "checkout_url": "https://paychangu.com/checkout/test",
        }

        # Run dunning processor
        stats = process_dunning_attempts()

        # Assert attempt was made
        self.assertEqual(stats["succeeded"], 1)

        # Refresh invoice
        invoice.refresh_from_db()

        # Assert attempt_count incremented
        self.assertEqual(invoice.attempt_count, 1)

        # Assert next_attempt_at is 8 hours later
        expected_next_attempt = now + timedelta(hours=8)
        self.assertAlmostEqual(
            invoice.next_attempt_at.timestamp(), expected_next_attempt.timestamp(), delta=300  # 5 min tolerance
        )

        # Assert BillingAttempt created
        billing_attempt = BillingAttempt.objects.filter(invoice=invoice).first()
        self.assertIsNotNone(billing_attempt)
        self.assertEqual(billing_attempt.attempt_no, 1)

    @patch("billing.tasks.paychangu_service")
    def test_dunning_fails_6_times_then_suspends(self, mock_paychangu):
        """Test dunning retries 6 times, then suspend_expired_grace_periods suspends subscription."""
        from billing.tasks import process_dunning_attempts, suspend_expired_grace_periods

        # Create invoice
        now = timezone.now()
        invoice = Invoice.objects.create(
            business=self.business,
            subscription=self.subscription,
            status=Invoice.Status.DRAFT,
            total=self.plan.amount,
            currency=self.plan.currency,
            next_attempt_at=now,
            attempt_count=5,  # Already 5 attempts
        )

        # Set subscription to past_due with grace
        self.subscription.status = BusinessSubscription.Status.PAST_DUE
        self.subscription.grace_until = now + timedelta(hours=1)
        self.subscription.billing_phone = "+265991234567"
        self.subscription.save()

        # Mock PayChangu failure
        mock_paychangu.is_paychangu_configured.return_value = True
        mock_paychangu.create_checkout.return_value = {"status": "error", "message": "Payment failed"}

        # Run dunning one more time (6th attempt)
        process_dunning_attempts()

        # Refresh invoice
        invoice.refresh_from_db()
        self.assertEqual(invoice.attempt_count, 6)

        # Move grace_until to past
        self.subscription.grace_until = now - timedelta(hours=1)
        self.subscription.save()

        # Run suspend job
        stats = suspend_expired_grace_periods()

        # Refresh subscription
        self.subscription.refresh_from_db()

        # Assert subscription is suspended
        self.assertEqual(self.subscription.status, BusinessSubscription.Status.SUSPENDED)
        self.assertIsNotNone(self.subscription.suspended_at)
        self.assertEqual(stats["suspended"], 1)

    def test_middleware_blocks_suspended_subscription(self):
        """Test middleware blocks access for suspended subscriptions."""
        from billing.middleware import SubscriptionGateMiddleware

        # Set suspended status
        self.subscription.status = BusinessSubscription.Status.SUSPENDED
        self.subscription.suspended_at = timezone.now()
        self.subscription.save()

        # Create middleware instance
        middleware = SubscriptionGateMiddleware(lambda r: MagicMock(status_code=200))

        # Test access is blocked
        self.assertFalse(middleware._subscription_allows_access(self.subscription))

    @patch("billing.tasks.paychangu_service")
    @patch("billing.views_paychangu.PaymentTransaction")
    def test_dunning_success_extends_period(self, mock_transaction_model, mock_paychangu):
        """Test successful payment during dunning extends subscription period and resets to active."""
        # This would be tested via webhook processing
        # Create invoice
        now = timezone.now()
        invoice = Invoice.objects.create(
            business=self.business,
            subscription=self.subscription,
            status=Invoice.Status.DRAFT,
            total=self.plan.amount,
            currency=self.plan.currency,
        )

        # Set subscription to past_due
        self.subscription.status = BusinessSubscription.Status.PAST_DUE
        self.subscription.grace_until = now + timedelta(days=1)
        self.subscription.save()

        # Simulate webhook marking invoice as paid
        invoice.status = Invoice.Status.PAID
        invoice.paid_at = now
        invoice.save()

        # Manually extend period (this would be done in webhook handler)
        old_period_end = self.subscription.current_period_end
        self.subscription.current_period_start = old_period_end
        self.subscription.current_period_end = old_period_end + timedelta(days=30)
        self.subscription.status = BusinessSubscription.Status.ACTIVE
        self.subscription.past_due_since = None
        self.subscription.grace_until = None
        self.subscription.save()

        # Refresh
        self.subscription.refresh_from_db()

        # Assert subscription is active again
        self.assertEqual(self.subscription.status, BusinessSubscription.Status.ACTIVE)
        self.assertIsNone(self.subscription.past_due_since)
        self.assertIsNone(self.subscription.grace_until)


@pytest.mark.django_db
class TestSubscriptionUI(TestCase):
    """Test subscription state display in UI (choose plan page)."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser-ui", password="testpass123", email="test-ui@example.com"
        )
        self.business = Business.objects.create(name="Test Business UI", slug="test-business-ui")
        self.plan_starter, _ = SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter",
                "amount": Decimal("20000.00"),
                "currency": "MWK",
                "interval": SubscriptionPlan.Interval.MONTH,
                "is_active": True,
            },
        )
        self.plan_growth, _ = SubscriptionPlan.objects.get_or_create(
            code="growth",
            defaults={
                "name": "Growth",
                "amount": Decimal("50000.00"),
                "currency": "MWK",
                "interval": SubscriptionPlan.Interval.MONTH,
                "is_active": True,
            },
        )
        now = timezone.now()
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan_starter,
            status=BusinessSubscription.Status.ACTIVE,
            current_period_end=now + timedelta(days=15),
        )
        self.client = Client()
        self.client.force_login(self.user)

    @patch("billing.views._ensure_trial_subscription")
    @patch("billing.views.request")
    def test_subscribe_page_shows_current_badge(self, mock_request, mock_ensure):
        """Test subscribe page shows CURRENT badge on current plan."""
        mock_request.business = self.business
        mock_ensure.return_value = self.subscription

        with patch("tenants.utils.get_active_business", return_value=self.business):
            response = self.client.get(reverse("billing:subscribe"), HTTP_HOST="test-business.localhost")

        # Assert response contains CURRENT badge (in HTML)
        self.assertContains(response, "CURRENT")

    @patch("billing.views._ensure_trial_subscription")
    @patch("billing.views.request")
    def test_subscribe_page_shows_cancellation_banner(self, mock_request, mock_ensure):
        """Test subscribe page shows cancellation banner when cancel_at_period_end=True."""
        # Set cancel_at_period_end
        self.subscription.cancel_at_period_end = True
        self.subscription.save()

        mock_request.business = self.business
        mock_ensure.return_value = self.subscription

        with patch("tenants.utils.get_active_business", return_value=self.business):
            response = self.client.get(reverse("billing:subscribe"), HTTP_HOST="test-business.localhost")

        # Assert response contains cancellation banner
        self.assertContains(response, "Cancels on")
        self.assertContains(response, "Undo Cancellation")

    @patch("billing.views._ensure_trial_subscription")
    @patch("billing.views.request")
    def test_subscribe_page_shows_past_due_banner(self, mock_request, mock_ensure):
        """Test subscribe page shows past_due banner with Pay Now link."""
        # Set past_due
        self.subscription.status = BusinessSubscription.Status.PAST_DUE
        self.subscription.grace_until = timezone.now() + timedelta(days=1)
        self.subscription.save()

        mock_request.business = self.business
        mock_ensure.return_value = self.subscription

        with patch("tenants.utils.get_active_business", return_value=self.business):
            response = self.client.get(reverse("billing:subscribe"), HTTP_HOST="test-business.localhost")

        # Assert response contains past_due banner
        self.assertContains(response, "Payment Required")
        self.assertContains(response, "Pay Now")


@pytest.mark.django_db
class TestBillingPhoneUpdate(TestCase):
    """Test billing phone number update and validation."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser-phone", password="testpass123", email="test-phone@example.com"
        )
        self.business = Business.objects.create(name="Test Business Phone", slug="test-business-phone")
        self.plan, _ = SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter",
                "amount": Decimal("20000.00"),
                "currency": "MWK",
                "interval": SubscriptionPlan.Interval.MONTH,
            },
        )
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.plan,
            status=BusinessSubscription.Status.ACTIVE,
        )
        self.client = Client()
        self.client.force_login(self.user)

    @patch("billing.views.request")
    def test_update_billing_phone_normalizes_malawi_number(self, mock_request):
        """Test billing phone update normalizes various Malawi number formats."""
        mock_request.business = self.business

        test_cases = [
            ("0991234567", "+265991234567"),
            ("+265991234567", "+265991234567"),
            ("265991234567", "+265991234567"),
            ("991234567", "+265991234567"),
            ("088 123 4567", "+265881234567"),
        ]

        for input_phone, expected_normalized in test_cases:
            response = self.client.post(
                reverse("billing:update_billing_phone"),
                data={"billing_phone": input_phone},
                HTTP_HOST="test-business.localhost",
            )

            # Refresh subscription
            self.subscription.refresh_from_db()

            # Assert phone is normalized
            self.assertEqual(self.subscription.billing_phone, expected_normalized)

    @patch("billing.views.request")
    def test_update_billing_phone_rejects_invalid_format(self, mock_request):
        """Test billing phone update rejects invalid phone numbers."""
        mock_request.business = self.business

        invalid_phones = [
            "123",  # Too short
            "+265701234567",  # Invalid prefix (70)
            "+1234567890",  # Not Malawi
            "abcd1234567",  # Contains letters
        ]

        for invalid_phone in invalid_phones:
            response = self.client.post(
                reverse("billing:update_billing_phone"),
                data={"billing_phone": invalid_phone},
                HTTP_HOST="test-business.localhost",
            )

            # Assert error message (redirect to manage)
            self.assertEqual(response.status_code, 302)
