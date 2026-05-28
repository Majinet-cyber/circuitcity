"""
TengaSale Portal Device Lock Provider Abstraction.

Provides a clean interface for MDM / device locking operations on
portal.PaymentContract objects (the customer-facing contracts).

Providers:
  MockPortalDeviceLockProvider  — always succeeds, no real API calls
  KnoxProvider                  — Samsung Knox placeholder
  NuovoPayProvider              — NuovoPay MDM placeholder
  UpyaProvider                  — Upya MDM placeholder

Usage:
    from integrations.portal_device_lock import get_portal_lock_provider
    provider = get_portal_lock_provider(contract)
    result = provider.lock_device(contract)

All providers return:
  {
      "success": bool,
      "message": str,
      "provider": str,
      "data": dict (optional),
  }

Legitimate MDM/device-financing lock flows only.
No bypass, no illegal remote wipe, no privacy violation.
"""

import logging
from django.conf import settings
from django.utils import timezone

from .base import DeviceLockProvider

logger = logging.getLogger(__name__)


class DeviceLockResult:
    """Standardised result from any lock provider operation."""

    def __init__(self, success: bool, message: str, provider: str = "", data: dict = None):
        self.success = success
        self.message = message
        self.provider = provider
        self.data = data or {}

    def as_dict(self):
        return {
            "success": self.success,
            "message": self.message,
            "provider": self.provider,
            "data": self.data,
        }


# ---------------------------------------------------------------------------
# Mock Provider
# ---------------------------------------------------------------------------

class MockPortalDeviceLockProvider(DeviceLockProvider):
    """
    Sandbox mock provider. Always returns success.
    Used when MOCK_DEVICE_LOCKING=true (default) or provider not configured.
    """

    provider_name = "mock"

    @property
    def mode(self) -> str:
        return "mock"

    def _mock_result(self, action: str, contract) -> dict:
        result = DeviceLockResult(
            success=True,
            message=f"[MOCK] {action} — no real MDM call made.",
            provider=self.provider_name,
            data={"contract_number": str(getattr(contract, "contract_number", ""))},
        )
        self._sync_contract_timestamp(contract)
        return result.as_dict()

    def _sync_contract_timestamp(self, contract):
        """Update last_lock_sync_at if the contract supports it."""
        try:
            contract.last_lock_sync_at = timezone.now()
            contract.save(update_fields=["last_lock_sync_at"])
        except Exception:
            pass

    def enroll_device(self, contract) -> dict:
        return self._mock_result("Device enrollment", contract)

    def link_contract(self, contract) -> dict:
        return self._mock_result("Contract linked to device", contract)

    def lock_device(self, contract) -> dict:
        try:
            contract.device_lock_status = "locked"
            contract.last_lock_sync_at = timezone.now()
            contract.last_lock_error = ""
            contract.save(update_fields=["device_lock_status", "last_lock_sync_at", "last_lock_error"])
        except Exception:
            pass
        return DeviceLockResult(
            success=True,
            message="[MOCK] Device lock command sent.",
            provider=self.provider_name,
            data={"lock_status": "locked"},
        ).as_dict()

    def unlock_device(self, contract) -> dict:
        try:
            contract.device_lock_status = "unlocked"
            contract.last_lock_sync_at = timezone.now()
            contract.last_lock_error = ""
            contract.save(update_fields=["device_lock_status", "last_lock_sync_at", "last_lock_error"])
        except Exception:
            pass
        return DeviceLockResult(
            success=True,
            message="[MOCK] Device unlock command sent.",
            provider=self.provider_name,
            data={"lock_status": "unlocked"},
        ).as_dict()

    def get_device_status(self, contract) -> dict:
        status = getattr(contract, "device_lock_status", "unknown")
        return DeviceLockResult(
            success=True,
            message=f"[MOCK] Device status: {status}",
            provider=self.provider_name,
            data={"lock_status": status},
        ).as_dict()

    def send_payment_reminder(self, contract) -> dict:
        return self._mock_result("Payment reminder sent", contract)


# ---------------------------------------------------------------------------
# Knox Provider (placeholder)
# ---------------------------------------------------------------------------

class KnoxProvider(DeviceLockProvider):
    """
    Samsung Knox device management integration.

    Environment variables required:
      KNOX_API_KEY
      KNOX_API_URL

    Docs: https://docs.samsungknox.com/
    """

    provider_name = "knox"

    def __init__(self):
        self.api_key = getattr(settings, "KNOX_API_KEY", "")
        self.api_url = getattr(settings, "KNOX_API_URL", "https://api.samsungknox.com")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def mode(self) -> str:
        return "live" if self.is_configured else "not_configured"

    def _not_configured(self) -> dict:
        return DeviceLockResult(
            success=False,
            message="Samsung Knox is not configured. Set KNOX_API_KEY.",
            provider=self.provider_name,
        ).as_dict()

    def enroll_device(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        # TODO: POST /knox/v2/devices/enroll
        return DeviceLockResult(
            success=False,
            message="Knox enrollment not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def link_contract(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False,
            message="Knox contract linking not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def lock_device(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        # TODO: POST /knox/v2/devices/{id}/lock
        return DeviceLockResult(
            success=False,
            message="Knox device lock not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def unlock_device(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        # TODO: POST /knox/v2/devices/{id}/unlock
        return DeviceLockResult(
            success=False,
            message="Knox device unlock not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def get_device_status(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        # TODO: GET /knox/v2/devices/{id}/status
        return DeviceLockResult(
            success=False,
            message="Knox status query not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def send_payment_reminder(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        # TODO: POST /knox/v2/devices/{id}/notification
        return DeviceLockResult(
            success=False,
            message="Knox payment reminder not yet implemented.",
            provider=self.provider_name,
        ).as_dict()


# ---------------------------------------------------------------------------
# NuovoPay Provider (placeholder)
# ---------------------------------------------------------------------------

class NuovoPayProvider(DeviceLockProvider):
    """
    NuovoPay MDM device financing integration.

    Environment variables required:
      NUOVOPAY_API_KEY
      NUOVOPAY_API_URL

    Docs: https://www.nuovopay.com/docs/
    """

    provider_name = "nuovopay"

    def __init__(self):
        self.api_key = getattr(settings, "NUOVOPAY_API_KEY", "")
        self.api_url = getattr(settings, "NUOVOPAY_API_URL", "https://api.nuovopay.com")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def mode(self) -> str:
        return "live" if self.is_configured else "not_configured"

    def _not_configured(self) -> dict:
        return DeviceLockResult(
            success=False,
            message="NuovoPay is not configured. Set NUOVOPAY_API_KEY.",
            provider=self.provider_name,
        ).as_dict()

    def enroll_device(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="NuovoPay enrollment not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def link_contract(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="NuovoPay contract linking not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def lock_device(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="NuovoPay device lock not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def unlock_device(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="NuovoPay device unlock not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def get_device_status(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="NuovoPay status query not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def send_payment_reminder(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="NuovoPay payment reminder not yet implemented.",
            provider=self.provider_name,
        ).as_dict()


# ---------------------------------------------------------------------------
# Upya Provider (placeholder)
# ---------------------------------------------------------------------------

class UpyaPortalProvider(DeviceLockProvider):
    """
    Upya PAYG device management integration.

    Environment variables required:
      UPYA_API_KEY
      UPYA_API_URL

    Docs: Contact Upya for API documentation.
    """

    provider_name = "upya"

    def __init__(self):
        self.api_key = getattr(settings, "UPYA_API_KEY", "")
        self.api_url = getattr(settings, "UPYA_API_URL", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def mode(self) -> str:
        return "live" if self.is_configured else "not_configured"

    def _not_configured(self) -> dict:
        return DeviceLockResult(
            success=False,
            message="Upya is not configured. Set UPYA_API_KEY.",
            provider=self.provider_name,
        ).as_dict()

    def enroll_device(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="Upya enrollment not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def link_contract(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="Upya contract linking not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def lock_device(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="Upya device lock not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def unlock_device(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="Upya device unlock not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def get_device_status(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="Upya status query not yet implemented.",
            provider=self.provider_name,
        ).as_dict()

    def send_payment_reminder(self, contract) -> dict:
        if not self.is_configured:
            return self._not_configured()
        return DeviceLockResult(
            success=False, message="Upya payment reminder not yet implemented.",
            provider=self.provider_name,
        ).as_dict()


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def get_portal_lock_provider(contract=None) -> DeviceLockProvider:
    """
    Return the appropriate device lock provider for a portal contract.

    If MOCK_DEVICE_LOCKING=true (default), always returns mock provider.
    Otherwise selects based on contract.device_lock_provider or settings.
    """
    if getattr(settings, "MOCK_DEVICE_LOCKING", True):
        return MockPortalDeviceLockProvider()

    if contract and hasattr(contract, "device_lock_provider"):
        provider_name = contract.device_lock_provider
        if provider_name == "knox" and getattr(settings, "ENABLE_KNOX", False):
            return KnoxProvider()
        if provider_name == "nuovopay" and getattr(settings, "ENABLE_NUOVOPAY", False):
            return NuovoPayProvider()
        if provider_name == "upya" and getattr(settings, "ENABLE_UPYA", False):
            return UpyaPortalProvider()

    return MockPortalDeviceLockProvider()


def get_lock_integration_status() -> list[dict]:
    """
    Return status of all lock providers.
    Used in admin/dev surfaces.
    """
    return [
        {
            "name": "Mock Device Lock",
            "provider": "mock",
            "status": "active" if getattr(settings, "MOCK_DEVICE_LOCKING", True) else "inactive",
            "mode": "mock",
        },
        {
            "name": "Samsung Knox",
            "provider": "knox",
            "status": "configured" if KnoxProvider().is_configured else "not_configured",
            "mode": KnoxProvider().mode,
        },
        {
            "name": "NuovoPay",
            "provider": "nuovopay",
            "status": "configured" if NuovoPayProvider().is_configured else "not_configured",
            "mode": NuovoPayProvider().mode,
        },
        {
            "name": "Upya",
            "provider": "upya",
            "status": "configured" if UpyaPortalProvider().is_configured else "not_configured",
            "mode": UpyaPortalProvider().mode,
        },
    ]
