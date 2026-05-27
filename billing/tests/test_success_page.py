# billing/tests/test_success_page.py
"""
Tests for success page (STEP 5): Ensures redirect doesn't activate subscriptions.
"""
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from billing.models import (
    BusinessSubscription,
    Invoice,
    Payment,
    PaymentTransaction,
    SubscriptionPlan,
)
from tests.helpers.tenant_setup import make_business, make_membership, make_user


@pytest.mark.django_db
class TestSuccessPageHonesty:
    """Test that success page doesn't lie or activate subscriptions."""

    @pytest.fixture
    def setup_data(self):
        """Create test data with pending payment."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test Business", slug="test-biz")
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

        # Create PENDING transaction (user just redirected back)
        # NOTE: provider must be lowercase "paychangu" — matches production checkout behaviour
        transaction = PaymentTransaction.objects.create(
            business=business,
            provider="paychangu",
            tx_ref="test-tx-ref-123",
            amount=Decimal("10000.00"),
            currency="MWK",
            payment_method="card",
            status=PaymentTransaction.Status.PENDING,
        )

        return {
            "user": user,
            "business": business,
            "subscription": subscription,
            "transaction": transaction,
        }

    def test_return_page_shows_processing_message(self, setup_data):
        """Test that return page shows honest processing message."""
        client = Client()
        client.force_login(setup_data["user"])

        url = reverse("billing:paychangu_return")
        response = client.get(url, {"tx_ref": setup_data["transaction"].tx_ref})

        assert response.status_code == 200
        assert b"Processing" in response.content or b"processing" in response.content

    def test_status_api_does_not_activate_on_pending(self, setup_data):
        """Test that status API doesn't activate subscription while pending."""
        client = Client()
        client.force_login(setup_data["user"])

        # Get initial subscription status
        subscription = setup_data["subscription"]
        initial_status = subscription.status

        # Poll status endpoint
        url = reverse("billing:paychangu_payment_status")
        response = client.get(url, {"tx_ref": setup_data["transaction"].tx_ref})

        assert response.status_code == 200
        data = response.json()

        # Should return pending status
        assert data["status"] in ["pending", "processing"]

        # Subscription should NOT be activated by polling
        subscription.refresh_from_db()
        assert subscription.status == initial_status

    def test_status_api_does_not_activate_on_verified_success(self, setup_data):
        """
        Test that status API doesn't activate subscription even when payment
        is verified as SUCCESS by PayChangu API.

        This is the core test: webhook is source of truth, not redirect/polling.
        """
        client = Client()
        client.force_login(setup_data["user"])

        # Get initial subscription status
        subscription = setup_data["subscription"]
        initial_status = subscription.status

        # Mock the verify_payment to return SUCCESS
        # (This simulates PayChangu API confirming payment)
        from unittest.mock import patch

        with patch("billing.paychangu_service.verify_payment") as mock_verify:
            mock_verify.return_value = {
                "status": "SUCCESS",
                "amount": "10000.00",
                "currency": "MWK",
                "raw_response": {},
            }

            # Poll status endpoint
            url = reverse("billing:paychangu_payment_status")
            response = client.get(url, {"tx_ref": setup_data["transaction"].tx_ref})

            assert response.status_code == 200
            data = response.json()

            # Should return "processing" (not "success") because webhook hasn't confirmed
            assert data["status"] == "processing"

            # Message should be honest
            assert "receive" in data["message"].lower() or "email" in data["message"].lower()

        # Subscription should STILL NOT be activated (webhook hasn't run)
        subscription.refresh_from_db()
        assert subscription.status == initial_status

    def test_status_api_returns_success_after_webhook_activates(self, setup_data):
        """
        Test that status API returns success only after webhook has activated.
        """
        client = Client()
        client.force_login(setup_data["user"])

        # Simulate webhook activation
        subscription = setup_data["subscription"]
        subscription.activate_now()

        transaction = setup_data["transaction"]
        transaction.status = PaymentTransaction.Status.SUCCESS
        transaction.save()

        # Now poll status endpoint
        url = reverse("billing:paychangu_payment_status")
        response = client.get(url, {"tx_ref": transaction.tx_ref})

        assert response.status_code == 200
        data = response.json()

        # Should return success
        assert data["status"] == "success"
        assert "active" in data["message"].lower() or "confirmed" in data["message"].lower()

    def test_return_page_handles_missing_tx_ref(self, setup_data):
        """Test that return page handles missing tx_ref gracefully."""
        client = Client()
        client.force_login(setup_data["user"])

        url = reverse("billing:paychangu_return")
        response = client.get(url)  # No tx_ref

        assert response.status_code == 200
        assert b"error" in response.content.lower() or b"no payment reference" in response.content.lower()


@pytest.mark.django_db
class TestSuccessPageMessaging:
    """Test success page messaging is honest and helpful."""

    @pytest.fixture
    def setup_data(self):
        """Create test data."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test Business", slug="test-biz")
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

        return {
            "user": user,
            "business": business,
            "subscription": subscription,
        }

    def test_pending_message_mentions_email_confirmation(self, setup_data):
        """Test that pending status mentions email confirmation."""
        client = Client()
        client.force_login(setup_data["user"])

        transaction = PaymentTransaction.objects.create(
            business=setup_data["business"],
            provider="paychangu",
            tx_ref="test-pending",
            amount=Decimal("10000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )

        url = reverse("billing:paychangu_payment_status")
        response = client.get(url, {"tx_ref": transaction.tx_ref})

        assert response.status_code == 200
        data = response.json()

        # Should mention email
        assert "email" in data["message"].lower()

    def test_processing_message_is_different_from_success(self, setup_data):
        """Test that processing message is distinct from success message."""
        client = Client()
        client.force_login(setup_data["user"])

        # Create transaction
        transaction = PaymentTransaction.objects.create(
            business=setup_data["business"],
            provider="paychangu",
            tx_ref="test-processing",
            amount=Decimal("10000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )

        # Get processing message
        from unittest.mock import patch

        with patch("billing.paychangu_service.verify_payment") as mock_verify:
            mock_verify.return_value = {"status": "SUCCESS", "amount": "10000.00"}

            url = reverse("billing:paychangu_payment_status")
            response = client.get(url, {"tx_ref": transaction.tx_ref})
            processing_data = response.json()

        # Now mark as SUCCESS
        transaction.status = PaymentTransaction.Status.SUCCESS
        transaction.save()
        setup_data["subscription"].activate_now()

        response = client.get(url, {"tx_ref": transaction.tx_ref})
        success_data = response.json()

        # Messages should be different
        assert processing_data["message"] != success_data["message"]
        assert processing_data["status"] != success_data["status"]

    def test_failed_message_offers_retry(self, setup_data):
        """Test that failed status offers helpful retry message."""
        client = Client()
        client.force_login(setup_data["user"])

        transaction = PaymentTransaction.objects.create(
            business=setup_data["business"],
            provider="paychangu",
            tx_ref="test-failed",
            amount=Decimal("10000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.FAILED,
        )

        url = reverse("billing:paychangu_payment_status")
        response = client.get(url, {"tx_ref": transaction.tx_ref})

        assert response.status_code == 200
        data = response.json()

        # Should be failed status
        assert data["status"] == "failed"

        # Should offer help
        assert "try again" in data["message"].lower() or "support" in data["message"].lower()

