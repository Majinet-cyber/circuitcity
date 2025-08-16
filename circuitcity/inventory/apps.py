# inventory/apps.py
import importlib
import logging
from django.apps import AppConfig, apps
from django.conf import settings

logger = logging.getLogger(__name__)


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventory"
    verbose_name = "Inventory"

    def ready(self):
        """
        Wire up signal handlers if enabled.

        - Respects AUDIT_LOG_SETTINGS.ENABLED (defaults True).
        - Skips if the 'sales' app isn't installed (signals import depends on it).
        - Never blocks app startup; logs details instead.
        """
        # Feature flag
        try:
            audit_enabled = bool(getattr(settings, "AUDIT_LOG_SETTINGS", {}).get("ENABLED", True))
        except Exception:
            audit_enabled = True

        if not audit_enabled:
            logger.info("Inventory audit disabled via AUDIT_LOG_SETTINGS.ENABLED.")
            return

        # Require 'sales' app for Sale-related hooks
        if not apps.is_installed("sales"):
            logger.warning("'sales' app not installed; skipping inventory signal wiring.")
            return

        # Import signals (idempotent)
        try:
            importlib.import_module("inventory.signals")
            logger.debug("inventory.signals loaded successfully.")
        except ModuleNotFoundError:
            # OK in early dev; don't crash
            if getattr(settings, "DEBUG", False):
                logger.info("inventory.signals not found; skipping signal wiring.")
        except Exception:
            # Log full traceback but never crash startup
            logger.exception("Error loading inventory.signals")
