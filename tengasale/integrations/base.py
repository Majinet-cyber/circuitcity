from abc import ABC, abstractmethod


class DeviceLockProvider(ABC):
    """
    Provider interface for MDM / device locking integrations.

    Supported providers: Mock, Samsung Knox, NuovoPay, Upya.

    All methods accept a `contract` argument that can be either
    a `portal.PaymentContract` or a `financing.FinancingContract`
    — adapters normalise the fields internally.

    All methods return a dict with at minimum:
      success (bool)
      message (str)
      data    (dict, optional)
    """

    provider_name = "base"

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def mode(self) -> str:
        return "mock"

    # -- Core lifecycle --

    @abstractmethod
    def enroll_device(self, contract) -> dict:
        """Register a device with the MDM provider for the first time."""
        raise NotImplementedError

    @abstractmethod
    def link_contract(self, contract) -> dict:
        """Associate an existing MDM device record with this contract."""
        raise NotImplementedError

    @abstractmethod
    def lock_device(self, contract) -> dict:
        """Send a lock command to the device (e.g. on missed payment)."""
        raise NotImplementedError

    @abstractmethod
    def unlock_device(self, contract) -> dict:
        """Send an unlock command after a successful payment."""
        raise NotImplementedError

    @abstractmethod
    def get_device_status(self, contract) -> dict:
        """Query current lock/unlock status from provider."""
        raise NotImplementedError

    @abstractmethod
    def send_payment_reminder(self, contract) -> dict:
        """Push a payment reminder notification to the device."""
        raise NotImplementedError


class PaymentProvider(ABC):
    """Provider interface for future Airtel Money, TNM Mpamba, bank, or aggregator APIs."""

    provider_name = "base"

    @abstractmethod
    def verify_payment(self, reference, amount):
        raise NotImplementedError

    @abstractmethod
    def get_transaction_status(self, reference):
        raise NotImplementedError


class NotificationProvider(ABC):
    """Provider interface for future SMS and WhatsApp messaging APIs."""

    provider_name = "base"

    @abstractmethod
    def send_sms(self, phone_number, message):
        raise NotImplementedError

    def send_whatsapp(self, phone_number, message):
        return {"success": False, "message": "WhatsApp provider not configured."}
