# tenants/apps.py
from __future__ import annotations
from django.apps import AppConfig

class TenantsConfig(AppConfig):
    """
    AppConfig for the Tenants app.

    - `name` must match the Python import path for your models (`tenants.models`)
      since this app lives at top-level alongside `circuitcity/`.
    - `label` stays "tenants" so FKs like "tenants.Business" remain stable.
    """
    default_auto_field = "django.db.models.BigAutoField"

    # Top-level package (NOT inside circuitcity)
    name = "tenants"

    label = "tenants"
    verbose_name = "Tenants"

    def ready(self) -> None:  # type: ignore[override]
        # Import signals if present, but donâ€™t crash if missing.
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass


