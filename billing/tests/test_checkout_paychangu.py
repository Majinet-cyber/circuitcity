# billing/tests/test_checkout_paychangu.py
"""
Tests for billing checkout flow using PayChangu as the payment provider.
Ensures all payment methods (Airtel, Bank, Card) use PayChangu.
"""
import json
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from tests.helpers.tenant_setup import (
    make_user,
    make_business,
    make_location,
    make_membership,
)
from billing.models import (
    SubscriptionPlan,
    BusinessSubscription,
    Invoice,
    InvoiceItem,
    PaymentTransaction,
)


@pytest.mark.django_db
class TestCheckoutPayChangu:
    """Test that checkout uses PayChangu for all payment methods."""
    
    @pytest.fixture
    def setup_data(self):
        """Create test user, business, subscription, and invoice."""
        user = make_user(email="manager@test.com", password="pass1234")
        business = make_business(created_by=user, name="Test Biz", slug="test-biz")
        location = make_location(business=business, name="Main Store")
        make_membership(business=business, user=user, role="MANAGER")
        
        # Create subscription plan
        plan = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter Plan",
            amount=Decimal("20000.00"),
            currency="MWK",
            interval=SubscriptionPlan.Interval.MONTH,
        )
        
        # Create subscription
        sub = BusinessSubscription.start_trial(
            business=business,
            plan=plan,
            days=30,
        )
        
        # Create draft invoice
        invoice = Invoice.objects.create(
            business=business,
            created_by=user,
            to_name=business.name,
            to_email=user.email,
            currency="MWK",
            status=Invoice.Status.DRAFT,
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            description="Starter Plan - Monthly",
            qty=Decimal("1"),
            unit="mo",
            unit_price=Decimal("20000.00"),
        )
        invoice.recalc_totals(save=True)
        
        return {
            "user": user,
            "business": business,
            "location": location,
            "plan": plan,
            "subscription": sub,
            "invoice": invoice,
        }
    
    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch('billing.paychangu_service.create_checkout')
    def test_checkout_airtel_creates_paychangu_transaction(
        self, mock_create_checkout, setup_data
    ):
        """Test that Airtel Money checkout creates PaymentTransaction with PAYCHANGU provider."""
        mock_create_checkout.return_value = {
            "status": "success",
            "checkout_url": "https://checkout.paychangu.test/pay/abc123",
            "tx_ref": "billing-test-abc123",
            "raw_response": {"data": {"checkout_url": "https://checkout.paychangu.test/pay/abc123"}},
            "message": "Checkout created successfully",
        }
        
        client = Client()
        client.force_login(setup_data["user"])
        
        # Store invoice ID in session
        session = client.session
        session["billing_invoice_id"] = str(setup_data["invoice"].id)
        session.save()
        
        # Submit Airtel Money payment
        url = reverse("billing:checkout")
        response = client.post(
            url,
            data={
                "method": "airtel",
                "airtel-msisdn": "0991123456",
            },
        )
        
        # Should redirect to PayChangu checkout
        assert response.status_code == 302
        assert "https://checkout.paychangu.test/pay/abc123" in response.url
        
        # Verify PaymentTransaction was created with PAYCHANGU provider
        transaction = PaymentTransaction.objects.filter(
            business=setup_data["business"]
        ).first()
        assert transaction is not None
        assert transaction.provider == "PAYCHANGU"
        assert transaction.status == PaymentTransaction.Status.PENDING
        assert transaction.amount == setup_data["invoice"].total
        assert transaction.currency == "MWK"
        assert transaction.checkout_url == "https://checkout.paychangu.test/pay/abc123"
        
        # Verify create_checkout was called
        mock_create_checkout.assert_called_once()
        call_kwargs = mock_create_checkout.call_args[1]
        assert call_kwargs["business"] == setup_data["business"]
        assert call_kwargs["amount"] == setup_data["invoice"].total
        assert call_kwargs["currency"] == "MWK"
    
    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch('billing.paychangu_service.create_checkout')
    def test_checkout_bank_creates_paychangu_transaction(
        self, mock_create_checkout, setup_data
    ):
        """Test that Standard Bank checkout creates PaymentTransaction with PAYCHANGU provider."""
        mock_create_checkout.return_value = {
            "status": "success",
            "checkout_url": "https://checkout.paychangu.test/pay/bank456",
            "tx_ref": "billing-test-bank456",
            "raw_response": {"data": {"checkout_url": "https://checkout.paychangu.test/pay/bank456"}},
            "message": "Checkout created successfully",
        }
        
        client = Client()
        client.force_login(setup_data["user"])
        
        session = client.session
        session["billing_invoice_id"] = str(setup_data["invoice"].id)
        session.save()
        
        url = reverse("billing:checkout")
        response = client.post(
            url,
            data={
                "method": "standard_bank",
                "bank-reference": "REF-BANK-12345",
            },
        )
        
        assert response.status_code == 302
        assert "https://checkout.paychangu.test/pay/bank456" in response.url
        
        transaction = PaymentTransaction.objects.filter(
            business=setup_data["business"]
        ).first()
        assert transaction is not None
        assert transaction.provider == "PAYCHANGU"
        assert transaction.status == PaymentTransaction.Status.PENDING
        
        mock_create_checkout.assert_called_once()
    
    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch('billing.paychangu_service.create_checkout')
    def test_checkout_card_creates_paychangu_transaction(
        self, mock_create_checkout, setup_data
    ):
        """Test that Card checkout creates PaymentTransaction with PAYCHANGU provider."""
        mock_create_checkout.return_value = {
            "status": "success",
            "checkout_url": "https://checkout.paychangu.test/pay/card789",
            "tx_ref": "billing-test-card789",
            "raw_response": {"data": {"checkout_url": "https://checkout.paychangu.test/pay/card789"}},
            "message": "Checkout created successfully",
        }
        
        client = Client()
        client.force_login(setup_data["user"])
        
        session = client.session
        session["billing_invoice_id"] = str(setup_data["invoice"].id)
        session.save()
        
        url = reverse("billing:checkout")
        response = client.post(
            url,
            data={
                "method": "card",
                "card-number": "4242424242424242",
                "card-exp_month": "12",
                "card-exp_year": "2028",
                "card-cvv": "123",
            },
        )
        
        assert response.status_code == 302
        assert "https://checkout.paychangu.test/pay/card789" in response.url
        
        transaction = PaymentTransaction.objects.filter(
            business=setup_data["business"]
        ).first()
        assert transaction is not None
        assert transaction.provider == "PAYCHANGU"
        assert transaction.status == PaymentTransaction.Status.PENDING
        
        mock_create_checkout.assert_called_once()
    
    @override_settings(
        PAYCHANGU_PUBLIC_KEY="",  # Not configured
        PAYCHANGU_SECRET_KEY="",
        PAYCHANGU_WEBHOOK_SECRET="",
        PAYCHANGU_API_BASE="",
    )
    def test_checkout_fails_when_paychangu_not_configured(self, setup_data):
        """Test that checkout shows error when PayChangu is not configured."""
        client = Client()
        client.force_login(setup_data["user"])
        
        session = client.session
        session["billing_invoice_id"] = str(setup_data["invoice"].id)
        session.save()
        
        url = reverse("billing:checkout")
        response = client.post(
            url,
            data={
                "method": "airtel",
                "airtel-msisdn": "0991123456",
            },
            follow=True,
        )
        
        assert response.status_code == 200
        assert b"Payment system is not configured" in response.content
        
        # No transaction should be created
        assert PaymentTransaction.objects.filter(
            business=setup_data["business"]
        ).count() == 0
    
    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch('billing.paychangu_service.create_checkout')
    def test_checkout_handles_paychangu_api_failure(
        self, mock_create_checkout, setup_data
    ):
        """Test that checkout handles PayChangu API failures gracefully."""
        mock_create_checkout.return_value = {
            "status": "error",
            "message": "API authentication failed",
            "raw_response": {},
        }
        
        client = Client()
        client.force_login(setup_data["user"])
        
        session = client.session
        session["billing_invoice_id"] = str(setup_data["invoice"].id)
        session.save()
        
        url = reverse("billing:checkout")
        response = client.post(
            url,
            data={
                "method": "airtel",
                "airtel-msisdn": "0991123456",
            },
            follow=True,
        )
        
        assert response.status_code == 200
        assert b"Payment initiation failed" in response.content
        
        # Transaction should be created but marked as FAILED
        transaction = PaymentTransaction.objects.filter(
            business=setup_data["business"]
        ).first()
        assert transaction is not None
        assert transaction.status == PaymentTransaction.Status.FAILED


@pytest.mark.django_db
class TestWebhookActivatesSubscription:
    """Test that PayChangu webhook activates subscription on successful payment."""
    
    @pytest.fixture
    def setup_data(self):
        """Create test data for webhook testing."""
        user = make_user(email="manager@test.com", password="pass1234")
        business = make_business(created_by=user, name="Test Biz", slug="test-biz")
        location = make_location(business=business, name="Main Store")
        make_membership(business=business, user=user, role="MANAGER")
        
        # Create subscription plan
        plan = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter Plan",
            amount=Decimal("20000.00"),
            currency="MWK",
            interval=SubscriptionPlan.Interval.MONTH,
        )
        
        # Create subscription in TRIAL status
        sub = BusinessSubscription.start_trial(
            business=business,
            plan=plan,
            days=30,
        )
        
        # Create invoice
        invoice = Invoice.objects.create(
            business=business,
            created_by=user,
            to_name=business.name,
            to_email=user.email,
            currency="MWK",
            status=Invoice.Status.DRAFT,
            total=Decimal("20000.00"),
        )
        
        # Create pending transaction
        transaction = PaymentTransaction.objects.create(
            business=business,
            location=location,
            created_by=user,
            provider="PAYCHANGU",
            tx_ref="billing-test-webhook123",
            amount=Decimal("20000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )
        
        return {
            "user": user,
            "business": business,
            "location": location,
            "plan": plan,
            "subscription": sub,
            "invoice": invoice,
            "transaction": transaction,
        }
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_success_activates_subscription(
        self, mock_verify, setup_data
    ):
        """Test that successful webhook activates subscription and marks invoice paid."""
        import hmac
        import hashlib
        
        mock_verify.return_value = {
            "status": "SUCCESS",
            "amount": "20000.00",
            "currency": "MWK",
            "tx_ref": setup_data["transaction"].tx_ref,
            "raw_response": {"data": {"status": "successful"}},
            "message": "Payment successful",
        }
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "tx_ref": setup_data["transaction"].tx_ref,
            "amount": "20000.00",
            "currency": "MWK",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        signature = hmac.new(
            b"test-webhook-secret",
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        
        assert response.status_code == 200
        
        # Verify transaction is marked SUCCESS
        setup_data["transaction"].refresh_from_db()
        assert setup_data["transaction"].status == PaymentTransaction.Status.SUCCESS
        
        # Verify invoice is marked PAID
        setup_data["invoice"].refresh_from_db()
        assert setup_data["invoice"].status == Invoice.Status.PAID
        
        # Verify subscription is ACTIVE
        setup_data["subscription"].refresh_from_db()
        assert setup_data["subscription"].status == BusinessSubscription.Status.ACTIVE
        assert setup_data["subscription"].last_payment_at is not None
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_idempotency_no_double_activation(
        self, mock_verify, setup_data
    ):
        """Test that webhook doesn't double-activate subscription on repeated calls."""
        import hmac
        import hashlib
        
        mock_verify.return_value = {
            "status": "SUCCESS",
            "amount": "20000.00",
            "currency": "MWK",
            "tx_ref": setup_data["transaction"].tx_ref,
            "raw_response": {"data": {"status": "successful"}},
            "message": "Payment successful",
        }
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "tx_ref": setup_data["transaction"].tx_ref,
            "amount": "20000.00",
            "currency": "MWK",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        signature = hmac.new(
            b"test-webhook-secret",
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        
        # First webhook call
        response1 = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        assert response1.status_code == 200
        
        setup_data["subscription"].refresh_from_db()
        first_period_end = setup_data["subscription"].current_period_end
        
        # Second webhook call (duplicate)
        response2 = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        assert response2.status_code == 200
        
        # Verify subscription period didn't change (idempotent)
        setup_data["subscription"].refresh_from_db()
        assert setup_data["subscription"].current_period_end == first_period_end
        
        # verify_payment should only be called once (second call skips due to idempotency)
        assert mock_verify.call_count == 1


@pytest.mark.django_db
class TestPayChanguCorrectEndpoint:
    """Test that PayChangu service calls the correct API endpoint."""
    
    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch('billing.paychangu_service.requests')
    def test_create_checkout_calls_correct_endpoint(self, mock_requests):
        """Test that create_checkout POSTs to /payment (not /v1/payments)."""
        from billing import paychangu_service
        
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test", slug="test")
        location = make_location(business=business, name="Main Store")
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "checkout_url": "https://checkout.paychangu.com/pay/test123"
            }
        }
        mock_requests.post.return_value = mock_response
        
        # Call create_checkout
        result = paychangu_service.create_checkout(
            business=business,
            location=location,
            amount=Decimal("10000.00"),
            currency="MWK",
            tx_ref="test-ref-123",
            return_url="https://example.com/return",
            callback_url="https://example.com/callback",
            user_email="test@example.com",
            description="Test payment",
        )
        
        # Verify correct endpoint was called
        assert mock_requests.post.called
        call_args = mock_requests.post.call_args
        
        # Should be https://api.paychangu.com/payment (not /v1/payments)
        assert call_args[0][0] == "https://api.paychangu.com/payment"
        
        # Verify headers
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-secret-key"
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"
        
        # Verify result
        assert result["status"] == "success"
        assert result["checkout_url"] == "https://checkout.paychangu.com/pay/test123"
    
    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch('billing.paychangu_service.requests')
    def test_create_checkout_handles_405_error(self, mock_requests):
        """Test that create_checkout handles HTTP 405 error gracefully."""
        from billing import paychangu_service
        import requests
        
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test", slug="test")
        location = make_location(business=business, name="Main Store")
        
        # Mock 405 error response
        mock_response = MagicMock()
        mock_response.status_code = 405
        mock_response.text = "POST not supported for route v1/payments"
        mock_response.json.side_effect = ValueError("No JSON")
        
        # Create HTTPError with response
        http_error = requests.exceptions.HTTPError()
        http_error.response = mock_response
        mock_requests.post.side_effect = http_error
        
        # Call create_checkout
        result = paychangu_service.create_checkout(
            business=business,
            location=location,
            amount=Decimal("10000.00"),
            currency="MWK",
            tx_ref="test-ref-456",
            return_url="https://example.com/return",
            callback_url="https://example.com/callback",
            user_email="test@example.com",
            description="Test payment",
        )
        
        # Verify error is returned with status code
        assert result["status"] == "error"
        assert "405" in result["message"]
        assert "POST not supported" in result["message"]


@pytest.mark.django_db
class TestPayChanguReturnAndPolling:
    """Test PayChangu return page and payment status polling."""
    
    @pytest.fixture
    def setup_data(self):
        """Create test data."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test", slug="test")
        location = make_location(business=business, name="Main Store")
        make_membership(business=business, user=user, role="MANAGER")
        
        # Create transaction
        transaction = PaymentTransaction.objects.create(
            business=business,
            location=location,
            created_by=user,
            provider="PAYCHANGU",
            tx_ref="test-ref-return-123",
            amount=Decimal("10000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )
        
        # Create invoice
        invoice = Invoice.objects.create(
            business=business,
            created_by=user,
            currency="MWK",
            total=Decimal("10000.00"),
            status=Invoice.Status.DRAFT,
        )
        
        # Create subscription
        from billing.models import SubscriptionPlan, BusinessSubscription
        plan = SubscriptionPlan.objects.create(
            code="test-plan",
            name="Test Plan",
            amount=Decimal("10000.00"),
            currency="MWK",
        )
        sub = BusinessSubscription.start_trial(business=business, plan=plan, days=7)
        
        return {
            "user": user,
            "business": business,
            "location": location,
            "transaction": transaction,
            "invoice": invoice,
            "subscription": sub,
        }
    
    def test_return_page_renders_with_tx_ref(self, setup_data):
        """Test that return page renders and accepts tx_ref parameter."""
        client = Client()
        client.force_login(setup_data["user"])
        
        url = reverse("billing:paychangu_return")
        response = client.get(url, {"tx_ref": "test-ref-return-123"})
        
        assert response.status_code == 200
        assert b"test-ref-return-123" in response.content
        assert b"Processing Payment" in response.content
    
    def test_return_page_accepts_alternate_tx_ref_names(self, setup_data):
        """Test that return page accepts various tx_ref field names."""
        client = Client()
        client.force_login(setup_data["user"])
        
        url = reverse("billing:paychangu_return")
        
        # Test with 'reference'
        response = client.get(url, {"reference": "test-ref-return-123"})
        assert response.status_code == 200
        assert b"test-ref-return-123" in response.content
        
        # Test with 'transaction_id'
        response = client.get(url, {"transaction_id": "test-ref-return-123"})
        assert response.status_code == 200
        assert b"test-ref-return-123" in response.content
    
    def test_payment_status_api_pending(self, setup_data):
        """Test payment status API returns pending for pending transaction."""
        client = Client()
        client.force_login(setup_data["user"])
        
        url = reverse("billing:paychangu_payment_status")
        response = client.get(url, {"tx_ref": "test-ref-return-123"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["pending", "success"]  # May verify immediately
        assert data["transaction_status"] in ["pending", "success"]
    
    def test_payment_status_api_success(self, setup_data):
        """Test payment status API returns success for successful transaction."""
        # Mark transaction as successful
        setup_data["transaction"].mark_success({})
        setup_data["invoice"].mark_paid()
        setup_data["subscription"].activate_now()
        
        client = Client()
        client.force_login(setup_data["user"])
        
        url = reverse("billing:paychangu_payment_status")
        response = client.get(url, {"tx_ref": "test-ref-return-123"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["transaction_status"] == "success"
        assert "next_url" in data
        assert data["subscription_status"] == "active"
    
    def test_payment_status_api_scoped_to_business(self, setup_data):
        """Test that payment status API is scoped to current business."""
        # Create another business with same tx_ref (should not be found)
        other_user = make_user(email="other@test.com", password="pass")
        other_business = make_business(created_by=other_user, name="Other", slug="other")
        make_membership(business=other_business, user=other_user, role="MANAGER")
        
        client = Client()
        client.force_login(other_user)
        
        # Try to access transaction from first business
        url = reverse("billing:paychangu_payment_status")
        response = client.get(url, {"tx_ref": "test-ref-return-123"})
        
        # Should not find it (different business)
        assert response.status_code == 404
    
    def test_payment_status_api_missing_tx_ref(self, setup_data):
        """Test that payment status API returns error for missing tx_ref."""
        client = Client()
        client.force_login(setup_data["user"])
        
        url = reverse("billing:paychangu_payment_status")
        response = client.get(url)
        
        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"


@pytest.mark.django_db
class TestPayChanguWebhookHardening:
    """Test webhook robustness with various payload formats."""
    
    @pytest.fixture
    def setup_data(self):
        """Create test data."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test", slug="test")
        location = make_location(business=business, name="Main Store")
        
        transaction = PaymentTransaction.objects.create(
            business=business,
            location=location,
            created_by=user,
            provider="PAYCHANGU",
            tx_ref="webhook-test-456",
            amount=Decimal("5000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )
        
        return {
            "user": user,
            "business": business,
            "transaction": transaction,
        }
    
    def compute_signature(self, payload: bytes, secret: str) -> str:
        """Compute HMAC-SHA256 signature."""
        import hmac
        import hashlib
        return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-secret")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_accepts_reference_field(self, mock_verify, setup_data):
        """Test webhook accepts 'reference' field instead of 'tx_ref'."""
        mock_verify.return_value = {
            "status": "SUCCESS",
            "tx_ref": "webhook-test-456",
            "raw_response": {},
        }
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "reference": "webhook-test-456",  # Using 'reference' not 'tx_ref'
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self.compute_signature(payload_bytes, "test-secret")
        
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        
        assert response.status_code == 200
        mock_verify.assert_called_once_with("webhook-test-456")
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-secret")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_accepts_payment_reference_field(self, mock_verify, setup_data):
        """Test webhook accepts 'payment_reference' field."""
        mock_verify.return_value = {
            "status": "SUCCESS",
            "tx_ref": "webhook-test-456",
            "raw_response": {},
        }
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "payment_reference": "webhook-test-456",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self.compute_signature(payload_bytes, "test-secret")
        
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        
        assert response.status_code == 200
        mock_verify.assert_called_once_with("webhook-test-456")
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-secret")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_idempotent_on_repeated_calls(self, mock_verify, setup_data):
        """Test webhook is idempotent - doesn't re-process already successful transactions."""
        # First call
        mock_verify.return_value = {
            "status": "SUCCESS",
            "tx_ref": "webhook-test-456",
            "raw_response": {},
        }
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "tx_ref": "webhook-test-456",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self.compute_signature(payload_bytes, "test-secret")
        
        # First webhook call
        response1 = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        assert response1.status_code == 200
        assert mock_verify.call_count == 1
        
        # Verify transaction is now SUCCESS
        setup_data["transaction"].refresh_from_db()
        assert setup_data["transaction"].status == PaymentTransaction.Status.SUCCESS
        
        # Second webhook call (duplicate)
        response2 = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        assert response2.status_code == 200
        
        # verify_payment should NOT be called again (idempotent)
        assert mock_verify.call_count == 1


@pytest.mark.django_db
class TestInvoiceTaxTotal:
    """Test that Invoice.tax_total property works correctly in templates."""
    
    def test_invoice_tax_total_property_exists(self):
        """Test that Invoice model has tax_total property."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test", slug="test")
        
        invoice = Invoice.objects.create(
            business=business,
            created_by=user,
            currency="MWK",
            tax_amount=Decimal("1000.00"),
        )
        
        # Should not raise AttributeError
        assert invoice.tax_total == Decimal("1000.00")
        assert invoice.tax_total == invoice.tax_amount

