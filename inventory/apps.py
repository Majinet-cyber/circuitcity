# inventory/apps.py
from __future__ import annotations

import importlib
import logging
import os
from typing import Any, Callable, Optional

from django.apps import AppConfig, apps as djapps
from django.conf import settings
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventory"
    verbose_name = "Inventory"

    # guards to avoid accidental double work if ready() is called twice
    _signals_loaded = False
    _tenant_wired = False
    _auto_loc_wired = False  # default location signal hook
    _post_migrate_wired = False

    # -----------------------------
    # Django entrypoint
    # -----------------------------
    def ready(self):
        """
        Runs once when the app is ready:

        1) Wires multi-tenant managers + auto-fill of `business_id` (if FEATURE MULTI_TENANT on).
        2) Loads inventory signals (audit hooks), honoring env/feature flags.
        3) Registers a post_save hook to auto-create a default Location for new stores.
        4) Registers a post_migrate fallback to re-run wiring once DB models are fully ready in prod.
        """
        self._wire_tenant_scope()
        self._wire_signals()
        self._wire_default_location_hook()
        self._wire_post_migrate_fallback()

    # -----------------------------
    # 1) Multi-tenant wiring
    # -----------------------------
    def _wire_tenant_scope(self):
        if self.__class__._tenant_wired:
            return

        features = getattr(settings, "FEATURES", {})
        if not features.get("MULTI_TENANT", True):
            logger.info("MULTI_TENANT disabled; skipping tenant wiring for inventory models.")
            return

        # Import tenant helpers; if tenants app isn't ready, skip gracefully.
        try:
            from tenants.models import (
                TenantManager,
                UnscopedManager,
                get_current_business_id,
            )
        except Exception:
            logger.info("tenants.models not ready; skipping tenant wiring.")
            return

        def has_business_field(model) -> bool:
            try:
                model._meta.get_field("business")
                return True
            except Exception:
                return False

        def tenantize(model):
            if not has_business_field(model):
                return

            # Attach scoped manager (safe if already set to an equivalent)
            try:
                model.add_to_class("objects", TenantManager())
            except Exception:
                pass  # don't explode if already assigned

            # Attach global escape hatch for admin/scripts if absent
            if not hasattr(model, "all_objects"):
                try:
                    model.add_to_class("all_objects", UnscopedManager())
                except Exception:
                    pass

            # Wrap save() once to auto-fill business_id from thread-local
            if getattr(model.save, "_tenant_wrapped", False):
                return

            original_save = model.save

            def _tenant_save(self, *args, **kwargs):
                # Only fill if truly empty/None (avoid clobbering explicit values)
                if getattr(self, "business_id", None) in (None, 0):
                    try:
                        bid = get_current_business_id()
                    except Exception:
                        bid = None
                    if bid:
                        setattr(self, "business_id", bid)
                return original_save(self, *args, **kwargs)

            _tenant_save._tenant_wrapped = True  # mark as wrapped
            model.save = _tenant_save  # type: ignore[attr-defined]

        # Apply to every model in this app that has a `business` FK
        try:
            for m in djapps.get_app_config("inventory").get_models():
                tenantize(m)
        except Exception:
            logger.exception("Error tenantizing inventory models")
            return

        self.__class__._tenant_wired = True
        logger.debug("Inventory tenant wiring complete.")

    # -----------------------------
    # 2) Signals wiring (unchanged behavior, with safety)
    # -----------------------------
    def _wire_signals(self):
        if self.__class__._signals_loaded:
            return

        if os.environ.get("INVENTORY_DISABLE_SIGNALS") == "1":
            logger.info("Inventory signals disabled via INVENTORY_DISABLE_SIGNALS=1.")
            return

        try:
            audit_enabled = bool(getattr(settings, "AUDIT_LOG_SETTINGS", {}).get("ENABLED", True))
        except Exception:
            audit_enabled = True

        if not audit_enabled:
            logger.info("Inventory audit disabled via AUDIT_LOG_SETTINGS.ENABLED.")
            return

        # Require 'sales' app for Sale-related hooks
        if not djapps.is_installed("sales"):
            logger.warning("'sales' app not installed; skipping inventory signal wiring.")
            return

        # Optional: verify the Sale model is available (post-migrate ready)
        try:
            djapps.get_model("sales", "Sale")
        except Exception:
            logger.warning("sales.Sale model not ready; deferring inventory signal wiring.")
            return

        # Import signals (idempotent)
        try:
            importlib.import_module("inventory.signals")
            logger.debug("inventory.signals loaded successfully.")
            self.__class__._signals_loaded = True
        except ModuleNotFoundError:
            if getattr(settings, "DEBUG", False):
                logger.info("inventory.signals not found; skipping signal wiring.")
        except Exception:
            logger.exception("Error loading inventory.signals")

    # -----------------------------
    # 3) Auto-create default Location for new stores
    # -----------------------------
    def _wire_default_location_hook(self):
        """
        Registers inventory.auto_location.register() to auto-create a Location
        when a new Business/Store is created.

        Toggle off with:
          - env: INVENTORY_DISABLE_AUTO_LOCATION=1
          - settings.FEATURES['AUTO_DEFAULT_LOCATION'] = False
        """
        if self.__class__._auto_loc_wired:
            return

        # Opt-out controls
        if os.environ.get("INVENTORY_DISABLE_AUTO_LOCATION") == "1":
            logger.info("Auto default location disabled via INVENTORY_DISABLE_AUTO_LOCATION=1.")
            return
        features = getattr(settings, "FEATURES", {})
        if features.get("AUTO_DEFAULT_LOCATION", True) is False:
            logger.info("Auto default location disabled via FEATURES['AUTO_DEFAULT_LOCATION']=False.")
            return

        # Only proceed if tenants app is installed (we need Business model)
        if not djapps.is_installed("tenants"):
            logger.info("tenants app not installed; skipping auto default location wiring.")
            return

        try:
            # This module should expose a register() that hooks a post_save signal
            mod = importlib.import_module("inventory.auto_location")
            if hasattr(mod, "register"):
                mod.register()
                self.__class__._auto_loc_wired = True
                logger.debug("Auto default location hook registered.")
            else:
                logger.info("inventory.auto_location.register() not found; skipping.")
        except ModuleNotFoundError:
            if getattr(settings, "DEBUG", False):
                logger.info("inventory.auto_location module not found; skipping default location wiring.")
        except Exception:
            logger.exception("Error wiring auto default location hook")

    # -----------------------------
    # 4) Post-migrate fallback (prod safety net)
    # -----------------------------
    def _wire_post_migrate_fallback(self):
        """
        Re-run wiring after migrations so that, in environments where apps
        load before models are fully ready (e.g., first boot on Render),
        we still attach signals and auto-location hooks once DB state is final.
        """
        if self.__class__._post_migrate_wired:
            return

        def _after_migrate(sender, **kwargs):
            try:
                if not self.__class__._tenant_wired:
                    self._wire_tenant_scope()
                if not self.__class__._signals_loaded:
                    self._wire_signals()
                if not self.__class__._auto_loc_wired:
                    self._wire_default_location_hook()
            except Exception:
                logger.exception("inventory post_migrate fallback wiring failed")

        # Connect once
        post_migrate.connect(
            _after_migrate,
            dispatch_uid="inventory.post_migrate_fallback_once",
        )
        self.__class__._post_migrate_wired = True
        logger.debug("Inventory post_migrate fallback connected.")
