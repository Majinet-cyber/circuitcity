from django.conf import settings

from .base import NotificationProvider


class PlaceholderNotificationProvider(NotificationProvider):
    provider_name = "placeholder"

    def __init__(self):
        self.api_key = getattr(settings, "SMS_PROVIDER_API_KEY", "")
        self.api_url = getattr(settings, "SMS_PROVIDER_API_URL", "")

    def send_sms(self, phone_number, message):
        return {
            "success": False,
            "message": "SMS integration pending.",
            "data": {"phone_number": phone_number, "message": message},
        }
