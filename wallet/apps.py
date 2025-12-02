# wallet/apps.py
from django.apps import AppConfig

class WalletConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wallet"
    verbose_name = "Wallet"

    def ready(self):
        """Import signals when the app is ready."""
        try:
            from . import signals  # noqa: F401
        except ImportError:
            pass

