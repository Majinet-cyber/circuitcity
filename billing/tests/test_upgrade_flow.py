"""
Test subscription upgrade flow (pay the difference).

Tests:
- Upgrade amount calculation (difference between plans)
- Upgrade intent creation with idempotency
- Webhook applies upgrade after payment confirmed
- Invoice created for upgrade top-up
- current_period_end unchanged (upgrade for remainder of cycle)
- Idempotency: duplicate webhooks don't create duplicate invoices or apply twice
"""
import uuid
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from billing.domain import process_payment_webhook
from billing.models import (
    BusinessSubscription,
    Invoice,
    PaymentTransaction,
    SubscriptionChangeIntent,
    SubscriptionPlan,
)
from tenants.models import Business

User = get_user_model()


class UpgradeFlowTest(TestCase):
    """Test subscription upgrade flow."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username="testowner",
            email="owner@test.com",
            password="testpass123",
        )
        self.business = Business.objects.create(
            name="Test Business",
            subdomain="testbiz",
        )
        self.business.owner = self.user
        self.business.save()

        # Create plans
        self.starter, _ = SubscriptionPlan.objects.get_or_create(
            code="starter",
            defaults={
                "name": "Starter",
                "amount": Decimal("20000.00"),
                "currency": "MWK",
                "interval": SubscriptionPlan.Interval.MONTH,
                "max_stores": 1,
                "max_agents": 3,
                "is_active": True,
            },
        )
        self.growth, _ = SubscriptionPlan.objects.get_or_create(
            code="growth",
            defaults={
                "name": "Growth",
                "amount": Decimal("60000.00"),
                "currency": "MWK",
                "interval": SubscriptionPlan.Interval.MONTH,
                "max_stores": 5,
                "max_agents": 15,
                "is_active": True,
            },
        )
        self.pro, _ = SubscriptionPlan.objects.get_or_create(
            code="pro",
            defaults={
                "name": "Pro",
                "amount": Decimal("120000.00"),
                "currency": "MWK",
                "interval": SubscriptionPlan.Interval.MONTH,
                "max_stores": -1,
                "max_agents": -1,
                "is_active": True,
            },
        )

        # Create active subscription on Starter plan
        self.subscription = BusinessSubscription.objects.create(
            business=self.business,
            plan=self.starter,
            status=BusinessSubscription.Status.ACTIVE,
            started_at=timezone.now(),
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
            next_billing_date=timezone.now() + timezone.timedelta(days=30),
        )

        self.client = Client()
        self.client.force_login(self.user)

    def test_upgrade_amount_difference_simple(self):
        """Test upgrade amount calculation: starter(20k) → growth(60k) = 40k due."""
        amount_due = self.growth.amount - self.starter.amount
        self.assertEqual(amount_due, Decimal("40000.00"))

    def test_upgrade_amount_difference_growth_to_pro(self):
        """Test upgrade amount: growth(60k) → pro(120k) = 60k due."""
        amount_due = self.pro.amount - self.growth.amount
        self.assertEqual(amount_due, Decimal("60000.00"))

    @patch("billing.views.paychangu_service.create_checkout")
    def test_upgrade_start_creates_intent(self, mock_create_checkout):
        """Test that upgrade_start creates SubscriptionChangeIntent."""
        # Mock PayChangu response
        mock_create_checkout.return_value = {
            "status": "success",
            "checkout_url": "https://paychangu.com/checkout/test123",
            "checkout_id": "checkout_test123",
            "raw_response": {},
        }

        response = self.client.post(reverse("billing:upgrade_start", args=["growth"]))

        # Should redirect to PayChangu
        self.assertEqual(response.status_code, 302)
        self.assertIn("paychangu.com", response.url)

        # Check intent was created
        intent = SubscriptionChangeIntent.objects.filter(
            business=self.business,
            from_plan_code="starter",
            to_plan_code="growth",
        ).first()

        self.assertIsNotNone(intent)
        self.assertEqual(intent.amount_due, Decimal("40000.00"))
        self.assertEqual(intent.status, SubscriptionChangeIntent.Status.PENDING)
        self.assertEqual(intent.currency, "MWK")

    @patch("billing.views.paychangu_service.create_checkout")
    def test_upgrade_start_idempotency(self, mock_create_checkout):
        """Test that duplicate upgrade requests don't create duplicate intents."""
        # Mock PayChangu response
        mock_create_checkout.return_value = {
            "status": "success",
            "checkout_url": "https://paychangu.com/checkout/test123",
            "checkout_id": "checkout_test123",
            "raw_response": {},
        }

        # First request
        response1 = self.client.post(reverse("billing:upgrade_start", args=["growth"]))
        self.assertEqual(response1.status_code, 302)

        # Count intents
        intent_count_1 = SubscriptionChangeIntent.objects.filter(
            business=self.business,
            from_plan_code="starter",
            to_plan_code="growth",
        ).count()

        # Second request (should not create duplicate)
        response2 = self.client.post(reverse("billing:upgrade_start", args=["growth"]))

        # Count intents again
        intent_count_2 = SubscriptionChangeIntent.objects.filter(
            business=self.business,
            from_plan_code="starter",
            to_plan_code="growth",
        ).count()

        # Should be same count (idempotent)
        self.assertEqual(intent_count_1, intent_count_2)

    def test_upgrade_prevents_downgrade(self):
        """Test that downgrade attempts are rejected."""
        # Try to "upgrade" from starter to a lower-priced plan (not possible in current setup)
        # But test the validation logic by trying same-tier
        response = self.client.post(reverse("billing:upgrade_start", args=["starter"]))

        # Should redirect back to manage with error
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("billing:manage"))

        # No intent should be created
        intent_count = SubscriptionChangeIntent.objects.filter(
            business=self.business,
        ).count()
        self.assertEqual(intent_count, 0)

    def test_webhook_applies_upgrade_and_creates_invoice(self):
        """Test webhook applies upgrade after payment confirmed."""
        # Create upgrade intent
        intent = SubscriptionChangeIntent.objects.create(
            business=self.business,
            subscription=self.subscription,
            from_plan_code="starter",
            to_plan_code="growth",
            from_plan_amount=Decimal("20000.00"),
            to_plan_amount=Decimal("60000.00"),
            amount_due=Decimal("40000.00"),
            currency="MWK",
            status=SubscriptionChangeIntent.Status.PENDING,
            idempotency_key=f"{self.business.id}:starter:growth:123456",
            tx_ref="upgrade-test-123",
        )

        # Create payment transaction
        tx_ref = "upgrade-test-123"
        payment_txn = PaymentTransaction.objects.create(
            business=self.business,
            provider="paychangu",
            tx_ref=tx_ref,
            amount=Decimal("40000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )

        # Store original period_end
        original_period_end = self.subscription.current_period_end

        # Process webhook (payment success)
        result = process_payment_webhook(
            provider="paychangu",
            tx_ref=tx_ref,
            event_type="payment.success",
            amount=Decimal("40000.00"),
            currency="MWK",
            payload={"tx_ref": tx_ref, "status": "success"},
            signature_valid=True,
            event_id="evt_test_123",
        )

        # Check result
        self.assertEqual(result["status"], "processed")
        self.assertIn("upgrade_intent", result)

        # Refresh from DB
        intent.refresh_from_db()
        self.subscription.refresh_from_db()
        payment_txn.refresh_from_db()

        # Check intent marked APPLIED
        self.assertEqual(intent.status, SubscriptionChangeIntent.Status.APPLIED)
        self.assertIsNotNone(intent.paid_at)
        self.assertIsNotNone(intent.applied_at)

        # Check subscription plan upgraded
        self.assertEqual(self.subscription.plan.code, "growth")
        self.assertEqual(self.subscription.plan.amount, Decimal("60000.00"))

        # Check period_end UNCHANGED (upgrade for remainder of cycle)
        self.assertEqual(self.subscription.current_period_end, original_period_end)

        # Check payment transaction marked SUCCESS
        self.assertEqual(payment_txn.status, PaymentTransaction.Status.SUCCESS)

        # Check invoice created
        invoice = Invoice.objects.filter(
            business=self.business,
            provider_reference=tx_ref,
        ).first()

        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(invoice.total, Decimal("40000.00"))
        self.assertIn("Upgrade top-up", invoice.notes)

    def test_webhook_upgrade_idempotent(self):
        """Test duplicate webhook doesn't create duplicate invoice or apply twice."""
        # Create upgrade intent
        intent = SubscriptionChangeIntent.objects.create(
            business=self.business,
            subscription=self.subscription,
            from_plan_code="starter",
            to_plan_code="growth",
            from_plan_amount=Decimal("20000.00"),
            to_plan_amount=Decimal("60000.00"),
            amount_due=Decimal("40000.00"),
            currency="MWK",
            status=SubscriptionChangeIntent.Status.PENDING,
            idempotency_key=f"{self.business.id}:starter:growth:123456",
            tx_ref="upgrade-test-456",
        )

        # Create payment transaction
        tx_ref = "upgrade-test-456"
        payment_txn = PaymentTransaction.objects.create(
            business=self.business,
            provider="paychangu",
            tx_ref=tx_ref,
            amount=Decimal("40000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )

        # Process webhook FIRST time
        result1 = process_payment_webhook(
            provider="paychangu",
            tx_ref=tx_ref,
            event_type="payment.success",
            amount=Decimal("40000.00"),
            currency="MWK",
            payload={"tx_ref": tx_ref, "status": "success"},
            signature_valid=True,
            event_id="evt_test_456",
        )

        self.assertEqual(result1["status"], "processed")

        # Count invoices
        invoice_count_1 = Invoice.objects.filter(
            business=self.business,
            provider_reference=tx_ref,
        ).count()
        self.assertEqual(invoice_count_1, 1)

        # Process webhook SECOND time (duplicate)
        result2 = process_payment_webhook(
            provider="paychangu",
            tx_ref=tx_ref,
            event_type="payment.success",
            amount=Decimal("40000.00"),
            currency="MWK",
            payload={"tx_ref": tx_ref, "status": "success"},
            signature_valid=True,
            event_id="evt_test_456",  # Same event_id
        )

        # Should be ignored (idempotent)
        self.assertEqual(result2["status"], "ignored")

        # Count invoices again (should be same)
        invoice_count_2 = Invoice.objects.filter(
            business=self.business,
            provider_reference=tx_ref,
        ).count()
        self.assertEqual(invoice_count_2, 1)

        # Intent should still be APPLIED (not duplicated)
        intent.refresh_from_db()
        self.assertEqual(intent.status, SubscriptionChangeIntent.Status.APPLIED)

    def test_upgrade_intent_idempotency_key_format(self):
        """Test idempotency key format prevents duplicate intents."""
        period_start_ts = int(self.subscription.current_period_start.timestamp())
        expected_key = f"{self.business.id}:starter:growth:{period_start_ts}"

        intent = SubscriptionChangeIntent.objects.create(
            business=self.business,
            subscription=self.subscription,
            from_plan_code="starter",
            to_plan_code="growth",
            from_plan_amount=Decimal("20000.00"),
            to_plan_amount=Decimal("60000.00"),
            amount_due=Decimal("40000.00"),
            currency="MWK",
            status=SubscriptionChangeIntent.Status.PENDING,
            idempotency_key=expected_key,
            tx_ref="upgrade-test-789",
        )

        self.assertEqual(intent.idempotency_key, expected_key)

        # Try to create duplicate (should fail on unique constraint)
        with self.assertRaises(Exception):
            SubscriptionChangeIntent.objects.create(
                business=self.business,
                subscription=self.subscription,
                from_plan_code="starter",
                to_plan_code="growth",
                from_plan_amount=Decimal("20000.00"),
                to_plan_amount=Decimal("60000.00"),
                amount_due=Decimal("40000.00"),
                currency="MWK",
                status=SubscriptionChangeIntent.Status.PENDING,
                idempotency_key=expected_key,  # Same key
                tx_ref="upgrade-test-999",
            )

