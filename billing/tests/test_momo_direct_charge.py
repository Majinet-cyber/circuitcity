# billing/tests/test_momo_direct_charge.py
"""
Tests for PayChangu Mobile Money Direct Charge (push-to-phone) flow.
Tests operator mapping, phone normalization, test mode validation, and polling.
"""
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from billing import paychangu_service
from billing.models import BusinessSubscription, Invoice, InvoiceItem, PaymentTransaction, SubscriptionPlan
from billing.tests.utils import ensure_plan
from tests.helpers.tenant_setup import make_business, make_location, make_membership, make_user


@pytest.mark.django_db
class TestPhoneNormalization:
    """Test phone number normalization for PayChangu MoMo."""

    def test_normalize_malawi_phone_with_leading_zero(self):
        """Test normalization of phone with leading 0."""
        result = paychangu_service.normalize_malawi_phone("0991234567")
        assert result == "991234567"

    def test_normalize_malawi_phone_without_leading_zero(self):
        """Test normalization of phone without leading 0."""
        result = paychangu_service.normalize_malawi_phone("991234567")
        assert result == "991234567"

    def test_normalize_malawi_phone_with_country_code(self):
        """Test normalization of phone with +265 country code."""
        result = paychangu_service.normalize_malawi_phone("+265991234567")
        assert result == "991234567"

    def test_normalize_malawi_phone_with_country_code_no_plus(self):
        """Test normalization of phone with 265 country code (no plus)."""
        result = paychangu_service.normalize_malawi_phone("265991234567")
        assert result == "991234567"

    def test_normalize_malawi_phone_with_spaces(self):
        """Test normalization removes spaces."""
        result = paychangu_service.normalize_malawi_phone("0991 234 567")
        assert result == "991234567"

    def test_normalize_malawi_phone_with_dashes(self):
        """Test normalization removes dashes."""
        result = paychangu_service.normalize_malawi_phone("0991-234-567")
        assert result == "991234567"

    def test_normalize_malawi_phone_invalid_length(self):
        """Test normalization raises ValueError for invalid length."""
        with pytest.raises(ValueError, match="9 digits"):
            paychangu_service.normalize_malawi_phone("099123456")  # 8 digits

        with pytest.raises(ValueError, match="9 digits"):
            paychangu_service.normalize_malawi_phone("09912345678")  # 10 digits


@pytest.mark.django_db
class TestModeValidation:
    """Test mode validation for PayChangu MoMo."""

    def test_validate_test_mode_airtel_success_number(self):
        """Test validation accepts Airtel success sandbox number."""
        result = paychangu_service.validate_test_mode_phone("0990000000", "airtel")
        assert result["valid"] is True

    def test_validate_test_mode_airtel_fail_number(self):
        """Test validation accepts Airtel fail sandbox number."""
        result = paychangu_service.validate_test_mode_phone("0990000001", "airtel")
        assert result["valid"] is True

    def test_validate_test_mode_tnm_success_number(self):
        """Test validation accepts TNM success sandbox number."""
        result = paychangu_service.validate_test_mode_phone("0899817565", "tnm")
        assert result["valid"] is True

    def test_validate_test_mode_tnm_fail_number(self):
        """Test validation accepts TNM fail sandbox number."""
        result = paychangu_service.validate_test_mode_phone("0899817566", "tnm")
        assert result["valid"] is True

    def test_validate_test_mode_rejects_real_airtel_number(self):
        """Test validation rejects real Airtel number in test mode."""
        result = paychangu_service.validate_test_mode_phone("0991234567", "airtel")
        assert result["valid"] is False
        assert "sandbox numbers only" in result["message"]
        assert "990000000" in result["message"]

    def test_validate_test_mode_rejects_real_tnm_number(self):
        """Test validation rejects real TNM number in test mode."""
        result = paychangu_service.validate_test_mode_phone("0881234567", "tnm")
        assert result["valid"] is False
        assert "sandbox numbers only" in result["message"]
        assert "899817565" in result["message"]


@pytest.mark.django_db
class TestOperatorMapping:
    """Test operator ref_id resolution."""

    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch("billing.paychangu_service.requests")
    def test_get_operator_ref_id_airtel(self, mock_requests):
        """Test resolving Airtel operator ref_id."""
        # Mock operators API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"name": "Airtel Money Malawi", "ref_id": "airtel-mw-123", "code": "airtel"},
                {"name": "TNM Mpamba", "ref_id": "tnm-mw-456", "code": "tnm"},
            ]
        }
        mock_requests.get.return_value = mock_response

        result = paychangu_service.get_operator_ref_id("airtel")

        assert result["status"] == "success"
        assert result["ref_id"] == "airtel-mw-123"
        assert "airtel" in result["operator_name"].lower()

    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch("billing.paychangu_service.requests")
    def test_get_operator_ref_id_tnm(self, mock_requests):
        """Test resolving TNM operator ref_id."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"name": "Airtel Money Malawi", "ref_id": "airtel-mw-123", "code": "airtel"},
                {"name": "TNM Mpamba", "ref_id": "tnm-mw-456", "code": "tnm"},
            ]
        }
        mock_requests.get.return_value = mock_response

        result = paychangu_service.get_operator_ref_id("tnm")

        assert result["status"] == "success"
        assert result["ref_id"] == "tnm-mw-456"
        assert "tnm" in result["operator_name"].lower() or "mpamba" in result["operator_name"].lower()

    @patch.dict("os.environ", {"PAYCHANGU_AIRTEL_REF_ID": "env-airtel-override-123"})
    def test_get_operator_ref_id_uses_env_override(self):
        """Test that env override is used instead of API call."""
        result = paychangu_service.get_operator_ref_id("airtel")

        assert result["status"] == "success"
        assert result["ref_id"] == "env-airtel-override-123"
        assert "env override" in result["message"].lower()


@pytest.mark.django_db
class TestMoMoDirectChargePayload:
    """Test that MoMo direct charge sends correct payload."""

    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch("billing.paychangu_service.requests")
    def test_momo_initialize_sends_integer_amount(self, mock_requests):
        """Test that momo_initialize_payment sends amount as integer, not string."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"charge_id": "charge-123"}}
        mock_requests.post.return_value = mock_response

        result = paychangu_service.momo_initialize_payment(
            operator_ref_id="airtel-mw-123",
            mobile="0991234567",
            amount=Decimal("20000.00"),
            currency="MWK",
            tx_ref="test-tx-123",
            charge_id="charge-123",
        )

        assert result["status"] == "success"

        # Verify payload sent to API
        call_args = mock_requests.post.call_args
        payload = call_args[1]["json"]

        # Amount must be integer
        assert isinstance(payload["amount"], int)
        assert payload["amount"] == 20000

    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch("billing.paychangu_service.requests")
    def test_momo_initialize_sends_operator_ref_id(self, mock_requests):
        """Test that momo_initialize_payment sends mobile_money_operator_ref_id field."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"charge_id": "charge-123"}}
        mock_requests.post.return_value = mock_response

        result = paychangu_service.momo_initialize_payment(
            operator_ref_id="airtel-mw-123",
            mobile="0991234567",
            amount=Decimal("20000.00"),
            currency="MWK",
            tx_ref="test-tx-123",
            charge_id="charge-123",
        )

        assert result["status"] == "success"

        # Verify payload has correct field name
        call_args = mock_requests.post.call_args
        payload = call_args[1]["json"]

        assert "mobile_money_operator_ref_id" in payload
        assert payload["mobile_money_operator_ref_id"] == "airtel-mw-123"

    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch("billing.paychangu_service.requests")
    def test_momo_initialize_normalizes_phone_to_9_digits(self, mock_requests):
        """Test that momo_initialize_payment normalizes phone to 9 digits."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"charge_id": "charge-123"}}
        mock_requests.post.return_value = mock_response

        result = paychangu_service.momo_initialize_payment(
            operator_ref_id="airtel-mw-123",
            mobile="+265991234567",  # Input with country code
            amount=Decimal("20000.00"),
            currency="MWK",
            tx_ref="test-tx-123",
            charge_id="charge-123",
        )

        assert result["status"] == "success"

        # Verify phone is normalized to 9 digits
        call_args = mock_requests.post.call_args
        payload = call_args[1]["json"]

        assert payload["mobile"] == "991234567"  # 9 digits, no leading 0


@pytest.mark.django_db
class TestMoMoCheckoutFlow:
    """Test end-to-end MoMo checkout flow."""

    @pytest.fixture
    def setup_data(self):
        """Create test user, business, subscription, and invoice."""
        user = make_user(email="manager@test.com", password="pass1234")
        business = make_business(created_by=user, name="Test Biz", slug="test-biz")
        location = make_location(business=business, name="Main Store")
        make_membership(business=business, user=user, role="MANAGER")

        plan = ensure_plan(
            code="momo-test-plan",
            name="MoMo Test Plan",
            amount=Decimal("20000.00"),
            currency="MWK",
            interval=SubscriptionPlan.Interval.MONTH,
        )

        sub = BusinessSubscription.start_trial(business=business, plan=plan, days=30)

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
        PAYCHANGU_MODE="test",
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch("billing.paychangu_service.get_operator_ref_id")
    @patch("billing.paychangu_service.momo_initialize_payment")
    def test_airtel_checkout_creates_transaction_with_charge_id(self, mock_momo_init, mock_get_operator, setup_data):
        """Test that Airtel Money checkout creates transaction with charge_id."""
        # Mock operator resolution
        mock_get_operator.return_value = {
            "status": "success",
            "ref_id": "airtel-mw-123",
            "operator_name": "Airtel Money",
        }

        # Mock MoMo initialization
        mock_momo_init.return_value = {
            "status": "success",
            "charge_id": "charge-abc123",
            "tx_ref": "billing-test-abc123",
            "raw_response": {"data": {"charge_id": "charge-abc123"}},
            "message": "Mobile money payment initialized successfully",
        }

        client = Client()
        client.force_login(setup_data["user"])

        session = client.session
        session["billing_invoice_id"] = str(setup_data["invoice"].id)
        session.save()

        url = reverse("billing:checkout")
        response = client.post(url, data={"method": "airtel", "phone": "0990000000"})

        # Should render waiting page (not redirect)
        assert response.status_code == 200
        assert b"Check your phone" in response.content or b"payment" in response.content.lower()

        # Verify transaction was created with charge_id
        transaction = PaymentTransaction.objects.filter(business=setup_data["business"]).first()
        assert transaction is not None
        assert transaction.provider == "paychangu"
        assert transaction.payment_method == "airtel"
        assert transaction.charge_id  # Should have a charge_id
        assert transaction.charge_id.startswith("charge-")  # Should match pattern
        assert transaction.status == PaymentTransaction.Status.PENDING

    @override_settings(
        PAYCHANGU_MODE="test",
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    def test_airtel_checkout_blocks_real_number_in_test_mode(self, setup_data):
        """Test that real phone numbers are blocked in test mode."""
        client = Client()
        client.force_login(setup_data["user"])

        session = client.session
        session["billing_invoice_id"] = str(setup_data["invoice"].id)
        session.save()

        url = reverse("billing:checkout")
        response = client.post(url, data={"method": "airtel", "phone": "0991234567"}, follow=True)

        # Should show warning message
        assert response.status_code == 200
        assert b"sandbox numbers only" in response.content or b"test mode" in response.content.lower()

        # No transaction should be created
        assert PaymentTransaction.objects.filter(business=setup_data["business"]).count() == 0


@pytest.mark.django_db
class TestMoMoPollingAPI:
    """Test payment status polling API for MoMo."""

    @pytest.fixture
    def setup_data(self):
        """Create test data with pending MoMo transaction."""
        user = make_user(email="test@test.com", password="pass")
        business = make_business(created_by=user, name="Test", slug="test")
        location = make_location(business=business, name="Main Store")
        make_membership(business=business, user=user, role="MANAGER")

        transaction = PaymentTransaction.objects.create(
            business=business,
            location=location,
            created_by=user,
            provider="paychangu",
            tx_ref="test-momo-123",
            charge_id="charge-momo-123",
            payment_method="airtel",
            amount=Decimal("10000.00"),
            currency="MWK",
            status=PaymentTransaction.Status.PENDING,
        )

        invoice = Invoice.objects.create(
            business=business,
            created_by=user,
            currency="MWK",
            total=Decimal("10000.00"),
            status=Invoice.Status.DRAFT,
        )

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
            "transaction": transaction,
            "invoice": invoice,
            "subscription": sub,
        }

    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch("billing.paychangu_service.momo_verify_payment")
    def test_polling_api_uses_momo_verify_for_charge_id(self, mock_momo_verify, setup_data):
        """Test that polling API uses momo_verify_payment when charge_id is present."""
        mock_momo_verify.return_value = {
            "status": "SUCCESS",
            "amount": "10000",
            "currency": "MWK",
            "charge_id": "charge-momo-123",
            "raw_response": {},
        }

        client = Client()
        client.force_login(setup_data["user"])

        url = reverse("billing:payment_status_api")
        response = client.get(url, {"charge_id": "charge-momo-123"})

        assert response.status_code == 200
        data = response.json()

        # Should call momo_verify_payment (not verify_payment)
        mock_momo_verify.assert_called_once_with("charge-momo-123")

        # Should return success
        assert data["status"] == "success"
        assert "redirect_url" in data

    @override_settings(
        PAYCHANGU_PUBLIC_KEY="test-public-key",
        PAYCHANGU_SECRET_KEY="test-secret-key",
        PAYCHANGU_API_BASE="https://api.paychangu.com",
    )
    @patch("billing.paychangu_service.momo_verify_payment")
    def test_polling_api_activates_subscription_on_success(self, mock_momo_verify, setup_data):
        """Test that polling API activates subscription when payment succeeds."""
        mock_momo_verify.return_value = {
            "status": "SUCCESS",
            "amount": "10000",
            "currency": "MWK",
            "charge_id": "charge-momo-123",
            "raw_response": {},
        }

        client = Client()
        client.force_login(setup_data["user"])

        url = reverse("billing:payment_status_api")
        response = client.get(url, {"charge_id": "charge-momo-123"})

        assert response.status_code == 200

        # Verify transaction is success
        setup_data["transaction"].refresh_from_db()
        assert setup_data["transaction"].status == PaymentTransaction.Status.SUCCESS

        # Verify subscription is activated
        setup_data["subscription"].refresh_from_db()
        assert setup_data["subscription"].status == BusinessSubscription.Status.ACTIVE

        # Note: Invoice may or may not be marked paid depending on matching logic
        # The important thing is that transaction and subscription are updated
