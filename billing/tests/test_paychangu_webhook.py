# billing/tests/test_paychangu_webhook.py
"""
Tests for PayChangu webhook signature verification and transaction processing.
"""
import json
import hmac
import hashlib
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from tests.helpers.tenant_setup import (
    make_user,
    make_business,
    make_location,
    make_membership,
)
from billing.models import PaymentTransaction, WebhookEvent
from billing import paychangu_service


@pytest.mark.django_db
class TestPayChanguWebhookSignature:
    """Test PayChangu webhook signature verification."""
    
    @pytest.fixture
    def setup_data(self):
        """Create test user, business, and location."""
        user = make_user(email="manager@test.com", password="pass1234")
        business = make_business(created_by=user, name="Test Biz", slug="test-biz")
        location = make_location(business=business, name="Main Store")
        make_membership(business=business, user=user, role="MANAGER")
        
        return {
            "user": user,
            "business": business,
            "location": location,
        }
    
    @pytest.fixture
    def transaction(self, setup_data):
        """Create a pending PaymentTransaction."""
        return PaymentTransaction.objects.create(
            business=setup_data["business"],
            location=setup_data["location"],
            created_by=setup_data["user"],
            provider="paychangu",
            tx_ref="pc-test-12345",
            amount=Decimal("5000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )
    
    def compute_signature(self, payload: bytes, secret: str) -> str:
        """Compute HMAC-SHA256 signature for webhook payload."""
        return hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256
        ).hexdigest()
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret-12345")
    def test_webhook_rejects_invalid_signature(self, transaction):
        """Test that webhook rejects requests with invalid signature."""
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "tx_ref": transaction.tx_ref,
            "amount": "5000.00",
            "currency": "MWK",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        # Send with invalid signature
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE="invalid-signature-xyz"
        )
        
        assert response.status_code == 401
        assert b"Invalid signature" in response.content
        
        # Transaction should still be pending
        transaction.refresh_from_db()
        assert transaction.status == PaymentTransaction.Status.PENDING
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret-12345")
    def test_webhook_rejects_missing_signature(self, transaction):
        """Test that webhook rejects requests without signature header."""
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "tx_ref": transaction.tx_ref,
            "amount": "5000.00",
            "currency": "MWK",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        # Send without signature header
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
        )
        
        assert response.status_code == 401
        assert b"Missing signature" in response.content
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret-12345")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_accepts_valid_signature_and_updates_transaction(
        self, mock_verify, transaction
    ):
        """Test that webhook accepts valid signature and updates transaction."""
        # Mock verify_payment to return success
        mock_verify.return_value = {
            "status": "SUCCESS",
            "amount": "5000.00",
            "currency": "MWK",
            "tx_ref": transaction.tx_ref,
            "raw_response": {
                "data": {
                    "status": "successful",
                    "amount": "5000.00",
                    "tx_ref": transaction.tx_ref,
                }
            },
            "message": "Payment successful",
        }
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "tx_ref": transaction.tx_ref,
            "amount": "5000.00",
            "currency": "MWK",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        # Compute valid signature
        signature = self.compute_signature(
            payload_bytes,
            "test-webhook-secret-12345"
        )
        
        # Send with valid signature
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        
        assert response.status_code == 200
        assert response.content == b"OK"
        
        # Verify that verify_payment was called
        mock_verify.assert_called_once_with(transaction.tx_ref)
        
        # Transaction should be marked as SUCCESS
        transaction.refresh_from_db()
        assert transaction.status == PaymentTransaction.Status.SUCCESS
        assert transaction.raw_webhook_payload["tx_ref"] == transaction.tx_ref
        assert transaction.raw_verify_payload["data"]["status"] == "successful"
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret-12345")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_accepts_signature_header_via_request_headers(self, mock_verify, transaction):
        """Test that webhook accepts 'Signature' header via request.headers.get()."""
        mock_verify.return_value = {
            "status": "SUCCESS",
            "amount": "5000.00",
            "currency": "MWK",
            "tx_ref": transaction.tx_ref,
            "raw_response": {"data": {"status": "successful"}},
            "message": "Payment successful",
        }
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "tx_ref": transaction.tx_ref,
            "amount": "5000.00",
            "currency": "MWK",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        # Compute valid signature
        signature = self.compute_signature(
            payload_bytes,
            "test-webhook-secret-12345"
        )
        
        # Send with HTTP_SIGNATURE (which Django maps to request.headers.get("Signature"))
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        
        assert response.status_code == 200
        mock_verify.assert_called_once_with(transaction.tx_ref)
        
        transaction.refresh_from_db()
        assert transaction.status == PaymentTransaction.Status.SUCCESS
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret-12345")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_accepts_x_signature_header(self, mock_verify, transaction):
        """Test that webhook accepts X-Signature header (alternative format)."""
        mock_verify.return_value = {
            "status": "SUCCESS",
            "amount": "5000.00",
            "currency": "MWK",
            "tx_ref": transaction.tx_ref,
            "raw_response": {"data": {"status": "successful"}},
            "message": "Payment successful",
        }
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "tx_ref": transaction.tx_ref,
            "amount": "5000.00",
            "currency": "MWK",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        # Compute valid signature
        signature = self.compute_signature(
            payload_bytes,
            "test-webhook-secret-12345"
        )
        
        # Send with X-Signature header instead of Signature
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SIGNATURE=signature
        )
        
        assert response.status_code == 200
        mock_verify.assert_called_once_with(transaction.tx_ref)
        
        transaction.refresh_from_db()
        assert transaction.status == PaymentTransaction.Status.SUCCESS
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret-12345")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_idempotency_already_success(self, mock_verify, transaction):
        """Test that webhook skips processing if transaction already SUCCESS."""
        # Mark transaction as SUCCESS first
        transaction.status = PaymentTransaction.Status.SUCCESS
        transaction.save()
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "tx_ref": transaction.tx_ref,
            "amount": "5000.00",
            "currency": "MWK",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        signature = self.compute_signature(
            payload_bytes,
            "test-webhook-secret-12345"
        )
        
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        
        assert response.status_code == 200
        
        # Verify that verify_payment was NOT called (idempotency)
        mock_verify.assert_not_called()
        
        # Transaction should still be SUCCESS
        transaction.refresh_from_db()
        assert transaction.status == PaymentTransaction.Status.SUCCESS
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret-12345")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_handles_failed_payment(self, mock_verify, transaction):
        """Test that webhook marks transaction as FAILED when verification fails."""
        mock_verify.return_value = {
            "status": "FAILED",
            "amount": "5000.00",
            "currency": "MWK",
            "tx_ref": transaction.tx_ref,
            "raw_response": {"data": {"status": "failed"}},
            "message": "Payment failed",
        }
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.failed",
            "tx_ref": transaction.tx_ref,
            "amount": "5000.00",
            "currency": "MWK",
            "status": "failed",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        signature = self.compute_signature(
            payload_bytes,
            "test-webhook-secret-12345"
        )
        
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        
        assert response.status_code == 200
        mock_verify.assert_called_once_with(transaction.tx_ref)
        
        transaction.refresh_from_db()
        assert transaction.status == PaymentTransaction.Status.FAILED
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret-12345")
    def test_webhook_handles_unknown_transaction(self):
        """Test that webhook returns 200 for unknown tx_ref (avoid retries)."""
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        payload = {
            "event": "payment.success",
            "tx_ref": "unknown-tx-ref-xyz",
            "amount": "5000.00",
            "currency": "MWK",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        signature = self.compute_signature(
            payload_bytes,
            "test-webhook-secret-12345"
        )
        
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        
        # Should return 200 to avoid retries
        assert response.status_code == 200
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="test-webhook-secret-12345")
    @patch('billing.paychangu_service.verify_payment')
    def test_webhook_no_cross_tenant_leakage(self, mock_verify, setup_data, transaction):
        """Test that webhook only updates transactions for correct business."""
        # Create another business and transaction
        other_user = make_user(email="other@test.com", password="pass1234")
        other_business = make_business(
            created_by=other_user,
            name="Other Biz",
            slug="other-biz"
        )
        other_location = make_location(business=other_business, name="Other Store")
        
        other_tx = PaymentTransaction.objects.create(
            business=other_business,
            location=other_location,
            created_by=other_user,
            provider="paychangu",
            tx_ref="pc-other-99999",
            amount=Decimal("3000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )
        
        mock_verify.return_value = {
            "status": "SUCCESS",
            "amount": "5000.00",
            "currency": "MWK",
            "tx_ref": transaction.tx_ref,
            "raw_response": {"data": {"status": "successful"}},
            "message": "Payment successful",
        }
        
        client = Client()
        url = reverse("billing:paychangu_webhook")
        
        # Send webhook for first transaction
        payload = {
            "event": "payment.success",
            "tx_ref": transaction.tx_ref,
            "amount": "5000.00",
            "currency": "MWK",
            "status": "successful",
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        
        signature = self.compute_signature(
            payload_bytes,
            "test-webhook-secret-12345"
        )
        
        response = client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_SIGNATURE=signature
        )
        
        assert response.status_code == 200
        
        # First transaction should be SUCCESS
        transaction.refresh_from_db()
        assert transaction.status == PaymentTransaction.Status.SUCCESS
        
        # Other transaction should still be PENDING (no cross-tenant leakage)
        other_tx.refresh_from_db()
        assert other_tx.status == PaymentTransaction.Status.PENDING


@pytest.mark.django_db
class TestPayChanguSignatureVerification:
    """Test signature verification helper function."""
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="my-secret-key")
    def test_verify_webhook_signature_valid(self):
        """Test signature verification with valid signature."""
        payload = b'{"tx_ref":"test-123","amount":"1000"}'
        
        expected_sig = hmac.new(
            b"my-secret-key",
            payload,
            hashlib.sha256
        ).hexdigest()
        
        is_valid = paychangu_service.verify_webhook_signature(payload, expected_sig)
        assert is_valid is True
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="my-secret-key")
    def test_verify_webhook_signature_invalid(self):
        """Test signature verification with invalid signature."""
        payload = b'{"tx_ref":"test-123","amount":"1000"}'
        
        is_valid = paychangu_service.verify_webhook_signature(payload, "wrong-sig")
        assert is_valid is False
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="my-secret-key")
    def test_verify_webhook_signature_empty(self):
        """Test signature verification with empty signature."""
        payload = b'{"tx_ref":"test-123","amount":"1000"}'
        
        is_valid = paychangu_service.verify_webhook_signature(payload, "")
        assert is_valid is False
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET='  "my-secret-key"  \n')
    def test_verify_webhook_signature_secret_with_whitespace_and_quotes(self):
        """Test signature verification when secret has whitespace/quotes/newlines."""
        payload = b'{"tx_ref":"test-123","amount":"1000"}'
        
        # Compute signature with CLEAN secret (after strip)
        expected_sig = hmac.new(
            b"my-secret-key",
            payload,
            hashlib.sha256
        ).hexdigest()
        
        # Should still verify correctly (service cleans the secret)
        is_valid = paychangu_service.verify_webhook_signature(payload, expected_sig)
        assert is_valid is True
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="  my-secret-key\n")
    def test_verify_webhook_signature_secret_with_trailing_newline(self):
        """Test signature verification when secret has trailing newline."""
        payload = b'{"tx_ref":"test-123","amount":"1000"}'
        
        # Compute signature with clean secret
        expected_sig = hmac.new(
            b"my-secret-key",
            payload,
            hashlib.sha256
        ).hexdigest()
        
        # Should verify correctly after cleaning
        is_valid = paychangu_service.verify_webhook_signature(payload, expected_sig)
        assert is_valid is True
    
    @override_settings(PAYCHANGU_WEBHOOK_SECRET="my-secret-key")
    def test_verify_webhook_signature_handles_signature_with_whitespace(self):
        """Test that signature with whitespace is cleaned before verification."""
        payload = b'{"tx_ref":"test-123","amount":"1000"}'
        
        expected_sig = hmac.new(
            b"my-secret-key",
            payload,
            hashlib.sha256
        ).hexdigest()
        
        # Add whitespace to signature
        signature_with_whitespace = f"  {expected_sig}  \n"
        
        # Should still verify correctly (service cleans the signature)
        is_valid = paychangu_service.verify_webhook_signature(payload, signature_with_whitespace)
        assert is_valid is True

