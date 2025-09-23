"""
AppConfig for the onboarding app (top-level package).

If you later move the app under the project package, switch:
    name = "circuitcity.onboarding"
but keep:
    label = "onboarding"
so migrations and relations remain consistent.
"""

from __future__ import annotations

import importlib.util
import logging
from django.apps import AppConfig

log = logging.getLogger(__name__)


class OnboardingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"

    # IMPORTANT: match your actual package path.
    # You currently have a top-level 'onboarding' package.
    name = "onboarding"

    # Keep a stable short label so migrations and relations remain consistent.
    label = "onboarding"

    verbose_name = "Onboarding"

    def ready(self) -> None:  # pragma: no cover
        """
        Optionally auto-load signals.py if it exists (no error if missing).
        """
        try:
            signals_mod = f"{self.name}.signals"
            if importlib.util.find_spec(signals_mod):
                __import__(signals_mod)
                log.debug("Loaded %s", signals_mod)
        except Exception as exc:
            log.warning("Failed to load %s: %s", signals_mod, exc)
