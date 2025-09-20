# circuitcity/accounts/apps.py
from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """
    AppConfig for the Accounts app.

    - `name` points to the real dotted path (circuitcity.accounts).
    - `label` is kept as "accounts" so AUTH_USER_MODEL = "accounts.User" works.
    """

    default_auto_field = "django.db.models.BigAutoField"

    # Full dotted path to the app package
    name = "circuitcity.accounts"

    # Stable label regardless of package path
    label = "accounts"
    verbose_name = "User Accounts"

    def ready(self) -> None:  # type: ignore[override]
        """Import signals on startup if available, but don’t crash if missing."""
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
