# inventory/apps.py
import importlib
import logging
import os
from django.apps import AppConfig, apps
from django.conf import settings

logger = logging.getLogger(__name__)


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventory"
    verbose_name = "Inventory"

    # guard to avoid accidental double-wiring if ready() is called twice
    _signals_loaded = False

    def ready(self):
        """
        Wire up signal handlers if enabled.

        - Respects AUDIT_LOG_SETTINGS.ENABLED (defaults True).
        - Skips if the 'sales' app isn't installed (signals import depends on it).
        - Supports env kill-switch INVENTORY_DISABLE_SIGNALS=1.
        - Never blocks app startup; logs details instead.
        """
        if self.__class__._signals_loaded:
            return

        # Env kill-switch for ops
        if os.environ.get("INVENTORY_DISABLE_SIGNALS") == "1":
            logger.info("Inventory signals disabled via INVENTORY_DISABLE_SIGNALS=1.")
            return

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

        # Optional: verify the Sale model is available (post-migrate ready)
        try:
            apps.get_model("sales", "Sale")
        except Exception:
            logger.warning("sales.Sale model not ready; deferring inventory signal wiring.")
            return

        # Import signals (idempotent)
        try:
            importlib.import_module("inventory.signals")
            logger.debug("inventory.signals loaded successfully.")
            self.__class__._signals_loaded = True
        except ModuleNotFoundError:
            # OK in early dev; don't crash
            if getattr(settings, "DEBUG", False):
                logger.info("inventory.signals not found; skipping signal wiring.")
        except Exception:
            # Log full traceback but never crash startup
            logger.exception("Error loading inventory.signals")
