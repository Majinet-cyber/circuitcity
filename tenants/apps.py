from __future__ import annotations

from django.apps import AppConfig


class TenantsConfig(AppConfig):
    """
    AppConfig for the Tenants app.

    - `name` must match the top-level Python package ("tenants").
    - `label` remains "tenants" so FK references like "tenants.Business" stay stable.
    - On app ready, we import signals (if present) without crashing in environments
      where the inventory app/models might not be loaded yet.
    """
    default_auto_field = "django.db.models.BigAutoField"

    # Top-level package (NOT inside circuitcity)
    name = "tenants"
    label = "tenants"
    verbose_name = "Tenants"

    def ready(self) -> None:  # type: ignore[override]
        # Import signals if present, but don't crash if missing.
        try:
            from . import signals  # noqa: F401
        except Exception:
            # Keep startup resilient if signals have optional deps
            pass
