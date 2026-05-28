"""
integrations/device_lock_provider.py

Device lock provider abstraction for TengaSale PayG financing.

Supports enrolling financed devices into a lock/PayG system so that
missed payments can restrict device access. Only legitimate financed-device
management — no illegal bypass behavior.

Providers:
    MockDeviceLockProvider  — Safe local mock (default)
    PrediktProvider         — Stub for Predikt integration
    TransUnionProvider      — Stub for TransUnion/PayG
    ParetixProvider         — Stub for Paretix

Usage:
    provider = get_lock_provider()
    result = provider.enroll_device(contract)

Configuration:
    DEVICE_LOCK_PROVIDER = 'mock' | 'predikt' | 'transunion' | 'paretix'
    MOCK_DEVICE_LOCKING = true/false
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


class BaseDeviceLockProvider:
    """Abstract base for all device lock providers."""

    name: str = "base"

    def enroll_device(self, contract) -> Dict[str, Any]:
        raise NotImplementedError

    def link_contract(self, contract) -> Dict[str, Any]:
        raise NotImplementedError

    def lock_device(self, contract) -> Dict[str, Any]:
        raise NotImplementedError

    def unlock_device(self, contract) -> Dict[str, Any]:
        raise NotImplementedError

    def get_device_status(self, contract) -> Dict[str, Any]:
        raise NotImplementedError

    def send_payment_reminder(self, contract) -> Dict[str, Any]:
        raise NotImplementedError

    def _audit(self, action: str, contract, detail: Optional[Dict] = None) -> None:
        try:
            from core.models import AuditLog
            AuditLog.objects.create(
                action=action,
                object_type="PaymentContract",
                object_id=str(contract.pk),
                detail=detail or {},
            )
        except Exception:
            pass


class MockDeviceLockProvider(BaseDeviceLockProvider):
    """
    Mock device lock provider for development and testing.
    Logs all actions without making real API calls.
    """

    name = "mock"

    def enroll_device(self, contract) -> Dict[str, Any]:
        logger.info("MOCK lock: enroll_device contract=%s imei=%s", contract.pk, getattr(contract, "imei_number", ""))
        self._audit("device_enroll", contract, {"provider": "mock", "action": "enroll"})
        return {"status": "success", "message": "Mock device enrolled.", "enrollment_id": f"MOCK-{contract.pk}"}

    def link_contract(self, contract) -> Dict[str, Any]:
        logger.info("MOCK lock: link_contract contract=%s", contract.pk)
        return {"status": "success", "message": "Mock contract linked."}

    def lock_device(self, contract) -> Dict[str, Any]:
        logger.info("MOCK lock: lock_device contract=%s", contract.pk)
        self._audit("device_lock", contract, {"provider": "mock", "action": "lock"})
        return {"status": "success", "message": "Mock device locked."}

    def unlock_device(self, contract) -> Dict[str, Any]:
        logger.info("MOCK lock: unlock_device contract=%s", contract.pk)
        self._audit("device_unlock", contract, {"provider": "mock", "action": "unlock"})
        return {"status": "success", "message": "Mock device unlocked."}

    def get_device_status(self, contract) -> Dict[str, Any]:
        return {"status": "success", "lock_status": "unlocked", "enrollment_status": "enrolled", "provider": "mock"}

    def send_payment_reminder(self, contract) -> Dict[str, Any]:
        logger.info("MOCK lock: send_payment_reminder contract=%s", contract.pk)
        return {"status": "success", "message": "Mock payment reminder sent."}


class PrediktProvider(BaseDeviceLockProvider):
    """
    Stub for Predikt device lock integration.
    Connect real API when credentials are available.
    """

    name = "predikt"

    def enroll_device(self, contract) -> Dict[str, Any]:
        logger.warning("Predikt: enroll_device called but provider not yet live.")
        return {"status": "not_implemented", "message": "Predikt integration not yet live."}

    def link_contract(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Predikt integration not yet live."}

    def lock_device(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Predikt integration not yet live."}

    def unlock_device(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Predikt integration not yet live."}

    def get_device_status(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Predikt integration not yet live."}

    def send_payment_reminder(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Predikt integration not yet live."}


class TransUnionProvider(BaseDeviceLockProvider):
    """Stub for TransUnion/PayG device lock integration."""

    name = "transunion"

    def enroll_device(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "TransUnion integration not yet live."}

    def link_contract(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "TransUnion integration not yet live."}

    def lock_device(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "TransUnion integration not yet live."}

    def unlock_device(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "TransUnion integration not yet live."}

    def get_device_status(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "TransUnion integration not yet live."}

    def send_payment_reminder(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "TransUnion integration not yet live."}


class ParetixProvider(BaseDeviceLockProvider):
    """Stub for Paretix device lock integration."""

    name = "paretix"

    def enroll_device(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Paretix integration not yet live."}

    def link_contract(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Paretix integration not yet live."}

    def lock_device(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Paretix integration not yet live."}

    def unlock_device(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Paretix integration not yet live."}

    def get_device_status(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Paretix integration not yet live."}

    def send_payment_reminder(self, contract) -> Dict[str, Any]:
        return {"status": "not_implemented", "message": "Paretix integration not yet live."}


_PROVIDERS = {
    "mock": MockDeviceLockProvider,
    "predikt": PrediktProvider,
    "transunion": TransUnionProvider,
    "paretix": ParetixProvider,
}


def get_lock_provider() -> BaseDeviceLockProvider:
    """
    Return the configured device lock provider instance.
    Falls back to MockDeviceLockProvider if MOCK_DEVICE_LOCKING=true or
    DEVICE_LOCK_PROVIDER is not set/unrecognised.
    """
    mock = getattr(settings, "MOCK_DEVICE_LOCKING", True)
    if mock:
        return MockDeviceLockProvider()

    provider_name = getattr(settings, "DEVICE_LOCK_PROVIDER", "mock").lower()
    cls = _PROVIDERS.get(provider_name, MockDeviceLockProvider)
    return cls()
