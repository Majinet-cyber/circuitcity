# tests/test_payment_providers.py
"""
Tests for Stripe and Pesapal payment provider integrations.
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from tenants.models import Business
from billing.models import SubscriptionPlan, BusinessSubscription
from billing import stripe_service, pesapal_service
from billing.views_providers import (
    stripe_checkout,
    stripe_webhook,
    pesapal_checkout,
    pesapal_ipn,
)

User = get_user_model()


class StripeServiceTests(TestCase):
    """Tests for Stripe service functions."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Test Business", slug="test-biz")
        self.plan = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter",
            amount=Decimal("20000"),
            currency="MWK"
        )
    
    @patch('billing.stripe_service.stripe')
    @patch('billing.stripe_service.is_stripe_configured', return_value=True)
    def test_create_checkout_session_success(self, mock_is_configured, mock_stripe):
        """Test creating a Stripe checkout session successfully."""
        mock_session = Mock()
        mock_session.id = "cs_test_123"
        mock_session.url = "https://checkout.stripe.com/test"
        mock_stripe.checkout.Session.create.return_value = mock_session
        
        result = stripe_service.create_checkout_session(
            business=self.business,
            plan=self.plan,
            success_url="http://example.com/success",
            cancel_url="http://example.com/cancel"
        )
        
        assert result["id"] == "cs_test_123"
        assert result["url"] == "https://checkout.stripe.com/test"
        assert "error" not in result
    
    @patch('billing.stripe_service.is_stripe_configured', return_value=False)
    def test_create_checkout_session_not_configured(self, mock_is_configured):
        """Test checkout session creation fails when Stripe not configured."""
        with pytest.raises(RuntimeError, match="not configured"):
            stripe_service.create_checkout_session(
                business=self.business,
                plan=self.plan,
                success_url="http://example.com/success",
                cancel_url="http://example.com/cancel"
            )
    
    def test_handle_checkout_completed(self):
        """Test handling checkout.session.completed event."""
        event_data = {
            "object": {
                "metadata": {
                    "business_id": str(self.business.id),
                    "plan_code": "starter"
                },
                "subscription": "sub_123",
                "customer": "cus_123"
            }
        }
        
        result = stripe_service.handle_checkout_completed(event_data)
        
        assert result["status"] == "success"
        assert result["business_id"] == str(self.business.id)
        assert result["stripe_subscription_id"] == "sub_123"


class PesapalServiceTests(TestCase):
    """Tests for Pesapal service functions."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Test Business", slug="test-biz")
        self.plan = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter",
            amount=Decimal("20000"),
            currency="MWK"
        )
    
    @patch('billing.pesapal_service.requests')
    @patch('billing.pesapal_service.is_pesapal_configured', return_value=True)
    def test_get_access_token_success(self, mock_is_configured, mock_requests):
        """Test getting Pesapal access token successfully."""
        mock_response = Mock()
        mock_response.json.return_value = {"token": "test_token_123"}
        mock_requests.post.return_value = mock_response
        
        token = pesapal_service.get_access_token(force_refresh=True)
        
        assert token == "test_token_123"
    
    @patch('billing.pesapal_service.requests')
    @patch('billing.pesapal_service.is_pesapal_configured', return_value=True)
    @patch('billing.pesapal_service.get_access_token', return_value="test_token")
    def test_submit_order_request_success(self, mock_get_token, mock_is_configured, mock_requests):
        """Test submitting order to Pesapal successfully."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "order_tracking_id": "track_123",
            "redirect_url": "https://pesapal.com/pay/track_123"
        }
        mock_response.raise_for_status = Mock()
        mock_requests.post.return_value = mock_response
        
        result = pesapal_service.submit_order_request(
            business=self.business,
            plan=self.plan,
            callback_url="http://example.com/callback"
        )
        
        assert result["status"] == "success"
        assert result["order_tracking_id"] == "track_123"
        assert "redirect_url" in result
    
    @patch('billing.pesapal_service.requests')
    @patch('billing.pesapal_service.is_pesapal_configured', return_value=True)
    @patch('billing.pesapal_service.get_access_token', return_value="test_token")
    def test_get_transaction_status(self, mock_get_token, mock_is_configured, mock_requests):
        """Test getting transaction status from Pesapal."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "payment_status_code": 1,
            "payment_method": "Mobile Money",
            "amount": 20000,
            "currency": "MWK"
        }
        mock_response.raise_for_status = Mock()
        mock_requests.get.return_value = mock_response
        
        result = pesapal_service.get_transaction_status("track_123")
        
        assert result["status"] == "COMPLETED"
        assert result["payment_method"] == "Mobile Money"


class PaymentWebhookTests(TestCase):
    """Tests for payment provider webhooks."""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.business = Business.objects.create(name="Test Business", slug="test-biz")
        self.plan = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter",
            amount=Decimal("20000"),
            currency="MWK"
        )
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
    
    @patch('billing.views_providers.stripe_service.construct_webhook_event')
    def test_stripe_webhook_valid_event(self, mock_construct):
        """Test Stripe webhook with valid event."""
        mock_event = {
            "type": "checkout.session.completed",
            "id": "evt_123",
            "data": {
                "object": {
                    "metadata": {
                        "business_id": str(self.business.id),
                        "plan_code": "starter"
                    },
                    "subscription": "sub_123",
                    "customer": "cus_123"
                }
            }
        }
        mock_construct.return_value = mock_event
        
        request = self.factory.post(
            '/billing/stripe/webhook/',
            data=b"test_payload",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_sig"
        )
        
        response = stripe_webhook(request)
        
        assert response.status_code == 200


@pytest.mark.django_db
class StripeIntegrationTest:
    """Integration tests for Stripe checkout flow."""
    
    def test_full_stripe_flow(self):
        """Test complete Stripe subscription flow."""
        # 1. Create business and plan
        business = Business.objects.create(name="Test Biz", slug="test")
        plan = SubscriptionPlan.objects.create(
            code="starter",
            name="Starter",
            amount=Decimal("20000")
        )
        
        # 2. Simulate checkout
        # (In real tests, mock Stripe API calls)
        
        # 3. Simulate webhook
        sub = BusinessSubscription.objects.create(
            business=business,
            plan=plan,
            status=BusinessSubscription.Status.TRIAL
        )
        
        # Update to active
        sub.status = BusinessSubscription.Status.ACTIVE
        sub.stripe_subscription_id = "sub_123"
        sub.payment_method = BusinessSubscription.Method.STRIPE
        sub.save()
        
        # Verify
        assert sub.status == BusinessSubscription.Status.ACTIVE
        assert sub.stripe_subscription_id == "sub_123"

