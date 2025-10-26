# layby/apps.py
from django.apps import AppConfig

class LaybyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    # IMPORTANT: use top-level package name
    name = "layby"
    label = "layby"
    verbose_name = "Layby"

    def ready(self):
        try:
            import layby.signals  # noqa: F401
        except Exception:
            pass


