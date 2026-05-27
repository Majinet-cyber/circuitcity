"""
TengaSale Payment Provider Abstraction Layer.

Providers:
  - MockPaymentProvider  — always succeeds, used when MOCK_PAYMENTS=true
  - PayChanguProvider    — PayChangu integration (placeholder)
  - AirtelMoneyProvider  — Airtel Money integration (placeholder)
  - TNMMpambaProvider    — TNM Mpamba integration (placeholder)
  - PayTriggerProvider   — PayTrigger integration (placeholder)

Usage:
  provider = get_payment_provider()
  result = provider.create_payment_intent(amount=1500, phone="0881234567", reference="TS-PAY-ABC12345")
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import datetime

from django.conf import settings


class PaymentIntentResult:
    """Returned by create_payment_intent."""
    def __init__(self, success: bool, provider_reference: str = "", redirect_url: str = "",
                 message: str = "", raw: dict = None):
        self.success = success
        self.provider_reference = provider_reference
        self.redirect_url = redirect_url
        self.message = message
        self.raw = raw or {}


class PaymentVerifyResult:
    """Returned by verify_payment."""
    def __init__(self, paid: bool, provider_reference: str = "", amount: Decimal = Decimal("0"),
                 message: str = "", raw: dict = None):
        self.paid = paid
        self.provider_reference = provider_reference
        self.amount = amount
        self.message = message
        self.raw = raw or {}


class PaymentProvider(ABC):
    """Abstract base for all payment providers."""

    @abstractmethod
    def create_payment_intent(
        self, amount: Decimal, phone: str, reference: str, description: str = ""
    ) -> PaymentIntentResult:
        """Initiate a payment request. Returns redirect URL or confirmation."""

    @abstractmethod
    def verify_payment(self, provider_reference: str) -> PaymentVerifyResult:
        """Check whether a payment has been completed."""

    @abstractmethod
    def handle_webhook(self, payload: dict) -> dict:
        """Process an incoming webhook from the provider."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def mode(self) -> str:
        return "sandbox"


# ---------------------------------------------------------------------------
# Mock Provider
# ---------------------------------------------------------------------------

class MockPaymentProvider(PaymentProvider):
    """
    Sandbox mock provider. Always returns success.
    Used when MOCK_PAYMENTS=true or when no real keys are configured.
    """

    def create_payment_intent(self, amount, phone, reference, description="") -> PaymentIntentResult:
        mock_ref = f"MOCK-{reference}"
        return PaymentIntentResult(
            success=True,
            provider_reference=mock_ref,
            message=f"[MOCK] Payment of MWK {amount} initiated for {phone}",
            raw={"mock": True, "reference": mock_ref, "amount": str(amount), "phone": phone},
        )

    def verify_payment(self, provider_reference) -> PaymentVerifyResult:
        return PaymentVerifyResult(
            paid=True,
            provider_reference=provider_reference,
            amount=Decimal("0"),
            message="[MOCK] Payment verified (sandbox mode)",
            raw={"mock": True, "status": "paid"},
        )

    def handle_webhook(self, payload) -> dict:
        return {"ok": True, "mock": True, "payload": payload}

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def mode(self) -> str:
        return "mock"


# ---------------------------------------------------------------------------
# PayChangu Provider (placeholder)
# ---------------------------------------------------------------------------

class PayChanguProvider(PaymentProvider):
    """
    PayChangu payment integration.

    Environment variables required:
      PAYCHANGU_PUBLIC_KEY
      PAYCHANGU_SECRET_KEY
      PAYCHANGU_WEBHOOK_SECRET

    Docs: https://paychangu.com/docs
    """

    def __init__(self):
        self.public_key = getattr(settings, "PAYCHANGU_PUBLIC_KEY", "")
        self.secret_key = getattr(settings, "PAYCHANGU_SECRET_KEY", "")
        self.webhook_secret = getattr(settings, "PAYCHANGU_WEBHOOK_SECRET", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.public_key and self.secret_key)

    @property
    def mode(self) -> str:
        return "live" if self.is_configured else "not_configured"

    def create_payment_intent(self, amount, phone, reference, description="") -> PaymentIntentResult:
        if not self.is_configured:
            return PaymentIntentResult(
                success=False,
                message="PayChangu is not configured. Set PAYCHANGU_PUBLIC_KEY and PAYCHANGU_SECRET_KEY.",
            )
        # TODO: Implement PayChangu API call
        # POST https://api.paychangu.com/payment with Bearer auth
        return PaymentIntentResult(
            success=False,
            message="PayChangu integration not yet implemented. Contact TengaSale support.",
        )

    def verify_payment(self, provider_reference) -> PaymentVerifyResult:
        if not self.is_configured:
            return PaymentVerifyResult(paid=False, message="PayChangu not configured.")
        # TODO: GET https://api.paychangu.com/verify/{reference}
        return PaymentVerifyResult(paid=False, message="PayChangu verification not yet implemented.")

    def handle_webhook(self, payload) -> dict:
        # TODO: Verify HMAC signature using webhook_secret
        return {"ok": False, "message": "PayChangu webhook handler not yet implemented."}


# ---------------------------------------------------------------------------
# Airtel Money Provider (placeholder)
# ---------------------------------------------------------------------------

class AirtelMoneyProvider(PaymentProvider):
    """
    Airtel Money Malawi integration.

    Environment variables required:
      AIRTEL_MONEY_CLIENT_ID
      AIRTEL_MONEY_CLIENT_SECRET

    Docs: https://developers.airtel.africa/
    """

    def __init__(self):
        self.client_id = getattr(settings, "AIRTEL_MONEY_CLIENT_ID", "")
        self.client_secret = getattr(settings, "AIRTEL_MONEY_CLIENT_SECRET", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def mode(self) -> str:
        return "live" if self.is_configured else "not_configured"

    def create_payment_intent(self, amount, phone, reference, description="") -> PaymentIntentResult:
        if not self.is_configured:
            return PaymentIntentResult(
                success=False,
                message="Airtel Money is not configured. Set AIRTEL_MONEY_CLIENT_ID and AIRTEL_MONEY_CLIENT_SECRET.",
            )
        # TODO: POST /merchant/v2/payments/ (Airtel Africa APIs)
        return PaymentIntentResult(success=False, message="Airtel Money integration not yet implemented.")

    def verify_payment(self, provider_reference) -> PaymentVerifyResult:
        return PaymentVerifyResult(paid=False, message="Airtel Money verification not yet implemented.")

    def handle_webhook(self, payload) -> dict:
        return {"ok": False, "message": "Airtel Money webhook handler not yet implemented."}


# ---------------------------------------------------------------------------
# TNM Mpamba Provider (placeholder)
# ---------------------------------------------------------------------------

class TNMMpambaProvider(PaymentProvider):
    """
    TNM Mpamba integration.

    Environment variables required:
      TNM_MPAMBA_API_KEY

    Docs: Contact TNM Business Solutions team.
    """

    def __init__(self):
        self.api_key = getattr(settings, "TNM_MPAMBA_API_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def mode(self) -> str:
        return "live" if self.is_configured else "not_configured"

    def create_payment_intent(self, amount, phone, reference, description="") -> PaymentIntentResult:
        if not self.is_configured:
            return PaymentIntentResult(
                success=False,
                message="TNM Mpamba is not configured. Set TNM_MPAMBA_API_KEY.",
            )
        return PaymentIntentResult(success=False, message="TNM Mpamba integration not yet implemented.")

    def verify_payment(self, provider_reference) -> PaymentVerifyResult:
        return PaymentVerifyResult(paid=False, message="TNM Mpamba verification not yet implemented.")

    def handle_webhook(self, payload) -> dict:
        return {"ok": False, "message": "TNM Mpamba webhook handler not yet implemented."}


# ---------------------------------------------------------------------------
# PayTrigger Provider (placeholder)
# ---------------------------------------------------------------------------

class PayTriggerProvider(PaymentProvider):
    """
    PayTrigger integration.

    Environment variables required:
      PAYTRIGGER_API_KEY
    """

    def __init__(self):
        self.api_key = getattr(settings, "PAYTRIGGER_API_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def mode(self) -> str:
        return "live" if self.is_configured else "not_configured"

    def create_payment_intent(self, amount, phone, reference, description="") -> PaymentIntentResult:
        if not self.is_configured:
            return PaymentIntentResult(
                success=False,
                message="PayTrigger is not configured. Set PAYTRIGGER_API_KEY.",
            )
        return PaymentIntentResult(success=False, message="PayTrigger integration not yet implemented.")

    def verify_payment(self, provider_reference) -> PaymentVerifyResult:
        return PaymentVerifyResult(paid=False, message="PayTrigger verification not yet implemented.")

    def handle_webhook(self, payload) -> dict:
        return {"ok": False, "message": "PayTrigger webhook handler not yet implemented."}


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def get_payment_provider(provider_name: str = None) -> PaymentProvider:
    """
    Return the appropriate payment provider.

    If MOCK_PAYMENTS=true (default), always returns MockPaymentProvider.
    Otherwise, selects based on provider_name or defaults to PayChangu.
    """
    if getattr(settings, "MOCK_PAYMENTS", True):
        return MockPaymentProvider()

    providers = {
        "paychangu": PayChanguProvider,
        "airtel_money": AirtelMoneyProvider,
        "tnm_mpamba": TNMMpambaProvider,
        "paytrigger": PayTriggerProvider,
    }

    if provider_name and provider_name in providers:
        provider = providers[provider_name]()
        if provider.is_configured:
            return provider

    # Try PayChangu first, then fall back to mock
    paychangu = PayChanguProvider()
    if paychangu.is_configured:
        return paychangu

    return MockPaymentProvider()


def get_integration_status() -> list[dict]:
    """
    Return integration status for all providers.
    Used in admin/dev surfaces to show what's configured.
    """
    return [
        {
            "name": "Mock Payment",
            "provider": "mock",
            "status": "active" if getattr(settings, "MOCK_PAYMENTS", True) else "inactive",
            "mode": "mock",
        },
        {
            "name": "PayChangu",
            "provider": "paychangu",
            "status": "configured" if PayChanguProvider().is_configured else "not_configured",
            "mode": PayChanguProvider().mode,
        },
        {
            "name": "Airtel Money",
            "provider": "airtel_money",
            "status": "configured" if AirtelMoneyProvider().is_configured else "not_configured",
            "mode": AirtelMoneyProvider().mode,
        },
        {
            "name": "TNM Mpamba",
            "provider": "tnm_mpamba",
            "status": "configured" if TNMMpambaProvider().is_configured else "not_configured",
            "mode": TNMMpambaProvider().mode,
        },
        {
            "name": "PayTrigger",
            "provider": "paytrigger",
            "status": "configured" if PayTriggerProvider().is_configured else "not_configured",
            "mode": PayTriggerProvider().mode,
        },
    ]
