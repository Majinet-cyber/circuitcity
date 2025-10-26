# billing/apps.py
from __future__ import annotations

import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"
    verbose_name = "Billing & Subscriptions"

    def ready(self) -> None:
        """
        Wire up signal handlers (plan seeding, invoice/payment notifications,
        subscription trial defaults, etc.). Any import errors are swallowed so
        migrations/startup arenâ€™t blocked by ordering issues.
        """
        try:
            # Ensure signal receivers are registered
            import billing.signals  # noqa: F401
            # Optional: uncomment to see this once in logs
            # logger.debug("billing.signals registered")
        except Exception as exc:
            # Fail silently in case of migration-time or import-order issues
            # Optional: log at DEBUG to avoid noisy prod logs
            logger.debug("billing.signals registration skipped due to import error: %s", exc)
            pass


