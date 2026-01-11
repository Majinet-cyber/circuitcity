# billing/tests/test_subscription_cancellation_simple.py
"""
Simplified tests for subscription cancellation and dunning functionality.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from billing.models import BillingAttempt, BusinessSubscription, Invoice, SubscriptionPlan
from tenants.models import Business

User = get_user_model()


@pytest.mark.django_db
class TestSubscriptionModel(TestCase):
    """Test subscription model fields and methods."""

    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(name="Test Model Business", slug="test-model-business")
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
            current_period_start=now - timedelta(days=20),
            current_period_end=now + timedelta(days=10),
        )

    def test_billing_phone_field_exists(self):
        """Test billing_phone field exists and can be set."""
        self.subscription.billing_phone = "+265991234567"
        self.subscription.save()
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.billing_phone, "+265991234567")

    def test_grace_until_field_exists(self):
        """Test grace_until field exists."""
        now = timezone.now()
        self.subscription.grace_until = now + timedelta(days=2)
        self.subscription.save()
        self.subscription.refresh_from_db()
        self.assertIsNotNone(self.subscription.grace_until)

    def test_past_due_since_field_exists(self):
        """Test past_due_since field exists."""
        now = timezone.now()
        self.subscription.past_due_since = now
        self.subscription.save()
        self.subscription.refresh_from_db()
        self.assertIsNotNone(self.subscription.past_due_since)

    def test_suspended_at_field_exists(self):
        """Test suspended_at field exists."""
        now = timezone.now()
        self.subscription.suspended_at = now
        self.subscription.save()
        self.subscription.refresh_from_db()
        self.assertIsNotNone(self.subscription.suspended_at)

    def test_cancel_at_period_end_flag(self):
        """Test cancel_at_period_end flag works."""
        self.assertFalse(self.subscription.cancel_at_period_end)
        self.subscription.cancel_at_period_end = True
        self.subscription.save()
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.cancel_at_period_end)


@pytest.mark.django_db
class TestInvoiceModel(TestCase):
    """Test invoice model dunning fields."""

    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(name="Test Invoice Business", slug="test-invoice-business")
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
        self.invoice = Invoice.objects.create(
            business=self.business,
            subscription=self.subscription,
            total=Decimal("20000.00"),
            currency="MWK",
        )

    def test_next_attempt_at_field_exists(self):
        """Test next_attempt_at field exists."""
        now = timezone.now()
        self.invoice.next_attempt_at = now + timedelta(hours=8)
        self.invoice.save()
        self.invoice.refresh_from_db()
        self.assertIsNotNone(self.invoice.next_attempt_at)

    def test_attempt_count_field_exists(self):
        """Test attempt_count field exists and defaults to 0."""
        self.assertEqual(self.invoice.attempt_count, 0)
        self.invoice.attempt_count = 3
        self.invoice.save()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.attempt_count, 3)

    def test_locked_for_dunning_field_exists(self):
        """Test locked_for_dunning field exists."""
        self.assertFalse(self.invoice.locked_for_dunning)
        self.invoice.locked_for_dunning = True
        self.invoice.save()
        self.invoice.refresh_from_db()
        self.assertTrue(self.invoice.locked_for_dunning)


@pytest.mark.django_db
class TestBillingAttemptModel(TestCase):
    """Test BillingAttempt model."""

    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(name="Test Billing Attempt Business", slug="test-billing-attempt")
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
        self.invoice = Invoice.objects.create(
            business=self.business,
            subscription=self.subscription,
            total=Decimal("20000.00"),
            currency="MWK",
        )

    def test_create_billing_attempt(self):
        """Test creating a BillingAttempt record."""
        attempt = BillingAttempt.objects.create(
            invoice=self.invoice,
            subscription=self.subscription,
            attempt_no=1,
            status=BillingAttempt.Status.INITIATED,
        )
        self.assertIsNotNone(attempt.id)
        self.assertEqual(attempt.attempt_no, 1)
        self.assertEqual(attempt.status, BillingAttempt.Status.INITIATED)

    def test_mark_succeeded(self):
        """Test mark_succeeded method."""
        attempt = BillingAttempt.objects.create(
            invoice=self.invoice,
            subscription=self.subscription,
            attempt_no=1,
            status=BillingAttempt.Status.INITIATED,
        )
        attempt.mark_succeeded(provider_ref="test_ref_123")
        self.assertEqual(attempt.status, BillingAttempt.Status.SUCCEEDED)
        self.assertEqual(attempt.provider_ref, "test_ref_123")

    def test_mark_failed(self):
        """Test mark_failed method."""
        attempt = BillingAttempt.objects.create(
            invoice=self.invoice,
            subscription=self.subscription,
            attempt_no=1,
            status=BillingAttempt.Status.INITIATED,
        )
        attempt.mark_failed(error_message="Payment declined")
        self.assertEqual(attempt.status, BillingAttempt.Status.FAILED)
        self.assertEqual(attempt.error_message, "Payment declined")


@pytest.mark.django_db
class TestMiddlewareAccessRules(TestCase):
    """Test subscription middleware access rules."""

    def setUp(self):
        """Set up test data."""
        from billing.middleware import SubscriptionGateMiddleware

        self.business = Business.objects.create(name="Test Middleware Business", slug="test-middleware")
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
            current_period_end=timezone.now() + timedelta(days=10),
        )
        self.middleware = SubscriptionGateMiddleware(lambda r: None)

    def test_active_subscription_allows_access(self):
        """Test active subscription allows access."""
        self.subscription.status = BusinessSubscription.Status.ACTIVE
        self.subscription.save()
        self.assertTrue(self.middleware._subscription_allows_access(self.subscription))

    def test_past_due_with_grace_allows_access(self):
        """Test past_due within grace period allows access."""
        now = timezone.now()
        self.subscription.status = BusinessSubscription.Status.PAST_DUE
        self.subscription.grace_until = now + timedelta(days=1)
        self.subscription.save()
        self.assertTrue(self.middleware._subscription_allows_access(self.subscription))

    def test_past_due_after_grace_blocks_access(self):
        """Test past_due after grace period blocks access."""
        now = timezone.now()
        self.subscription.status = BusinessSubscription.Status.PAST_DUE
        self.subscription.grace_until = now - timedelta(days=1)
        self.subscription.save()
        self.assertFalse(self.middleware._subscription_allows_access(self.subscription))

    def test_canceled_at_period_end_allows_access_before_end(self):
        """Test cancel_at_period_end allows access before period end."""
        now = timezone.now()
        self.subscription.status = BusinessSubscription.Status.ACTIVE
        self.subscription.cancel_at_period_end = True
        self.subscription.current_period_end = now + timedelta(days=5)
        self.subscription.save()
        self.assertTrue(self.middleware._subscription_allows_access(self.subscription))

    def test_canceled_after_period_end_blocks_access(self):
        """Test canceled subscription after period end blocks access."""
        now = timezone.now()
        self.subscription.status = BusinessSubscription.Status.CANCELED
        self.subscription.current_period_end = now - timedelta(days=1)
        self.subscription.save()
        self.assertFalse(self.middleware._subscription_allows_access(self.subscription))

    def test_suspended_subscription_blocks_access(self):
        """Test suspended subscription blocks access."""
        self.subscription.status = BusinessSubscription.Status.SUSPENDED
        self.subscription.suspended_at = timezone.now()
        self.subscription.save()
        self.assertFalse(self.middleware._subscription_allows_access(self.subscription))
