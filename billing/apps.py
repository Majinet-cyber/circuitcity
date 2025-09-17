# billing/apps.py
from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"
    verbose_name = "Billing & Subscriptions"

    def ready(self):
        # Import signals so trial seeding, payments, etc. hook in
        try:
            import billing.signals  # noqa: F401
        except Exception:
            # Fail silently in case of migration time / import order issues
            pass
