"""
integrations/device_check.py

Provider abstraction for device authenticity, warranty, and lock-eligibility checks.
Real providers can be added later — for now a MockDeviceCheckProvider is used.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class BaseDeviceCheckProvider:
    """Abstract base for device check providers."""

    name: str = "base"

    def check_imei(self, imei: str) -> Dict[str, Any]:
        """
        Check a device by IMEI.

        Must return a dict with at minimum:
            status: 'passed' | 'failed' | 'skipped'
            warranty_status: 'valid' | 'expired' | 'unknown'
            lock_eligible: bool
            response_summary: str
        """
        raise NotImplementedError


class MockDeviceCheckProvider(BaseDeviceCheckProvider):
    """
    Mock provider for development/testing.
    Returns placeholder responses for all IMEI checks.
    """

    name = "mock"

    def check_imei(self, imei: str) -> Dict[str, Any]:
        logger.info("MockDeviceCheckProvider: check_imei(%s)", imei)
        if not imei or len(imei.strip()) < 8:
            return {
                "status": "failed",
                "warranty_status": "unknown",
                "lock_eligible": False,
                "response_summary": "IMEI too short or missing.",
            }
        return {
            "status": "passed",
            "warranty_status": "unknown",
            "lock_eligible": True,
            "response_summary": f"Mock check passed for IMEI {imei}. Warranty and lock status require live provider.",
        }


def get_device_check_provider() -> BaseDeviceCheckProvider:
    """
    Return the configured device check provider.
    Defaults to MockDeviceCheckProvider until a live provider is configured.
    """
    from django.conf import settings

    provider_name = getattr(settings, "DEVICE_CHECK_PROVIDER", "mock")
    if provider_name == "mock":
        return MockDeviceCheckProvider()
    logger.warning("DeviceCheck: unknown provider '%s', falling back to mock.", provider_name)
    return MockDeviceCheckProvider()


def run_device_check(imei: str, application=None, contract=None) -> "risk.models.DeviceCheck":
    """
    Run a device check and persist the result as a DeviceCheck record.
    Returns the DeviceCheck instance.
    """
    from risk.models import DeviceCheck

    provider = get_device_check_provider()
    result = provider.check_imei(imei)

    check = DeviceCheck(
        imei=imei,
        provider=provider.name,
        status=result.get("status", DeviceCheck.STATUS_SKIPPED),
        warranty_status=result.get("warranty_status", DeviceCheck.WARRANTY_UNKNOWN),
        lock_eligible=result.get("lock_eligible", False),
        response_summary=result.get("response_summary", ""),
    )
    if application is not None:
        check.application = application
    if contract is not None:
        check.contract = contract
    check.save()
    return check
