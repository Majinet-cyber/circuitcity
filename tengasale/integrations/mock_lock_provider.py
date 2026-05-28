from financing.models import Device, DeviceStatusLog
from .base import DeviceLockProvider


class MockLockProvider(DeviceLockProvider):
    """
    Mock lock provider for financing.Device objects (HQ/financing app).
    Uses DeviceStatusLog for state tracking.
    """
    provider_name = "mock"

    def _complete_command(self, device, action, status_after, notes, valid_until=None):
        contract = device.financing_contract
        before = device.status
        device.status = status_after
        device.save(update_fields=["status"])
        DeviceStatusLog.objects.create(
            device=device,
            contract=contract,
            action=action,
            status_before=before,
            status_after=device.status,
            notes=notes,
        )
        return {
            "success": True,
            "integration": "mock",
            "message": notes,
            "valid_until": str(valid_until) if valid_until else "",
        }

    # Legacy method name — preserved for backward compatibility
    def register_device(self, device, contract=None):
        if contract is None and hasattr(device, "financing_contract"):
            contract = device.financing_contract
        DeviceStatusLog.objects.create(
            device=device,
            contract=contract,
            action=DeviceStatusLog.ACTION_REGISTERED,
            status_before=device.status,
            status_after=device.status,
            notes="Mock provider registered device. Real MDM registration pending.",
        )
        return {"success": True, "message": "Device registered in mock provider."}

    # DeviceLockProvider ABC compliance
    def enroll_device(self, contract) -> dict:
        return {"success": True, "message": "[MOCK] Device enrollment recorded.", "provider": "mock"}

    def link_contract(self, contract) -> dict:
        return {"success": True, "message": "[MOCK] Contract linked to device.", "provider": "mock"}

    def lock_device(self, device_or_contract) -> dict:
        if hasattr(device_or_contract, "financing_contract"):
            device = device_or_contract
            result = self._complete_command(
                device,
                DeviceStatusLog.ACTION_LOCKED,
                Device.STATUS_LOCKED,
                "Mock provider marked device as locked. Physical lock integration pending.",
            )
            return {"success": True, "message": "Mock lock request completed.", "data": result}
        return {"success": True, "message": "[MOCK] Lock command sent.", "provider": "mock"}

    def unlock_device(self, device_or_contract, valid_until=None) -> dict:
        if hasattr(device_or_contract, "financing_contract"):
            device = device_or_contract
            result = self._complete_command(
                device,
                DeviceStatusLog.ACTION_UNLOCKED,
                Device.STATUS_UNLOCKED,
                "Unlock authorized in mock provider. Physical unlock integration pending.",
                valid_until=valid_until,
            )
            return {"success": True, "message": "Mock unlock request completed.", "data": result}
        return {"success": True, "message": "[MOCK] Unlock command sent.", "provider": "mock"}

    def get_device_status(self, device_or_contract) -> dict:
        if hasattr(device_or_contract, "financing_contract"):
            device = device_or_contract
            return {
                "success": True,
                "message": "Mock status returned from internal database.",
                "data": {
                    "device_id": device.id,
                    "status": device.status,
                    "imei": device.masked_imei,
                },
            }
        return {"success": True, "message": "[MOCK] Status query completed.", "provider": "mock"}

    def send_payment_reminder(self, contract) -> dict:
        return {"success": True, "message": "[MOCK] Payment reminder sent.", "provider": "mock"}
