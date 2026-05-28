from django.conf import settings

from .base import PaymentProvider


class PlaceholderPaymentProvider(PaymentProvider):
    provider_name = "placeholder"

    def __init__(self):
        self.api_key = getattr(settings, "PAYMENT_PROVIDER_API_KEY", "")
        self.api_url = getattr(settings, "PAYMENT_PROVIDER_API_URL", "")

    def verify_payment(self, reference, amount):
        return {
            "success": False,
            "message": "Payment API integration pending. Use manual verification for now.",
            "data": {"reference": reference, "amount": str(amount)},
        }

    def get_transaction_status(self, reference):
        return {
            "success": False,
            "message": "Payment API integration pending.",
            "data": {"reference": reference},
        }
