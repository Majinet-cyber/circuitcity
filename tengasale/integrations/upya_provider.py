from django.conf import settings

from .base import DeviceLockProvider


class UpyaProvider(DeviceLockProvider):
    provider_name = "upya"

    def __init__(self):
        self.api_key = getattr(settings, "UPYA_API_KEY", "")
        self.api_url = getattr(settings, "UPYA_API_URL", "")

    def register_device(self, device, contract):
        raise NotImplementedError("Upya integration is adapter-ready but not configured.")

    def lock_device(self, device):
        raise NotImplementedError("Upya integration is adapter-ready but not configured.")

    def unlock_device(self, device, valid_until):
        raise NotImplementedError("Upya integration is adapter-ready but not configured.")

    def get_device_status(self, device):
        raise NotImplementedError("Upya integration is adapter-ready but not configured.")
