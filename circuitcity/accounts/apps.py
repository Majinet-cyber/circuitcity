# accounts/apps.py
from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """
    App config for the Accounts app.
    - Ensures modern BigAutoField primary keys.
    - Imports signal handlers on startup (profile creation, login security, OTP pruning, etc.).
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "User Accounts"

    def ready(self) -> None:
        """
        Import side-effect modules (signals) so their receivers are registered.
        Keep this import inside ready() to avoid issues during migrations.
        """
        try:
            # Registers:
            # - ensure_user_related_rows (Profile & LoginSecurity auto-creation)
            # - reset_login_security_on_password_change
            # - prune_expired_reset_codes
            from . import signals  # noqa: F401
        except Exception:
            # Fail silently in production to avoid boot-time crashes
            # if, for example, models aren’t ready during certain commands.
            # (Django will still log the original exception.)
            pass
