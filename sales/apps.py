# sales/apps.py
from django.apps import AppConfig


class SalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sales"
    verbose_name = "Sales"

    def ready(self):
        # Import signals here if you add any later, e.g.:
        # from . import signals  # noqa: F401
        pass


