# layby/apps.py
from django.apps import AppConfig


class LaybyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "layby"
    verbose_name = "Layby"

    def ready(self):
        # Import signals here if/when you add them.
        # Do NOT import models at module top-level to avoid AppRegistryNotReady.
        try:
            import layby.signals  # noqa: F401
        except Exception:
            pass
