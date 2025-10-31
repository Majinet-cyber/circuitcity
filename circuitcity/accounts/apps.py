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
        """
        Import signals on startup if available, and (defensively) connect
        login/logout hardening hooks so we never leak tenant context across users.

        - On login: cycle the session key (prevents session fixation) and try to
          select a sensible default business (owners/managers first). If none,
          ensure any stale tenant session keys are cleared.

        - On logout: clear active business (session + threadlocal) to avoid
          cross-tenant bleed when the next user logs in on a shared device.
        """
        # Optional user-defined signals (harmless if missing)
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass

        # Built-in hardening hooks
        try:
            from django.contrib.auth.signals import user_logged_in, user_logged_out
        except Exception:
            return  # cannot wire hooks; do nothing

        # We import inside ready() to avoid app registry issues
        def _clear_tenant_session(request) -> None:
            """
            Remove all known/legacy tenant session keys and clear thread-local.
            Never crash if session is unavailable (e.g., non-cookie auth).
            """
            try:
                for k in ("active_business_id", "biz_id"):
                    try:
                        request.session.pop(k, None)
                    except Exception:
                        pass
                # Canonical key (settings.TENANT_SESSION_KEY) may differ
                try:
                    from django.conf import settings
                    key = getattr(settings, "TENANT_SESSION_KEY", "active_business_id")
                    try:
                        request.session.pop(key, None)
                    except Exception:
                        pass
                except Exception:
                    pass
                # Mirror to thread-local (if available)
                try:
                    from circuitcity.tenants.models import set_current_business_id  # type: ignore
                    set_current_business_id(None)
                except Exception:
                    pass
                try:
                    request.business = None  # type: ignore[attr-defined]
                except Exception:
                    pass
            except Exception:
                # Never let session plumbing break auth flow
                pass

        def _set_default_business(request, user) -> None:
            """
            Resolve and set a safe default business for this user.
            Prefers OWNER/MANAGER/ADMIN and ACTIVE memberships.
            Falls back to clearing tenant keys if none found.
            """
            try:
                from circuitcity.tenants.utils import (  # type: ignore
                    resolve_default_business_for_user,
                    set_active_business,
                    user_has_membership,
                )
            except Exception:
                # utils not importable; at least clear potentially stale context
                _clear_tenant_session(request)
                return

            try:
                biz = resolve_default_business_for_user(user)
            except Exception:
                biz = None

            if biz is not None:
                # Defense in depth: confirm user truly belongs to that business
                try:
                    if user_has_membership(user, getattr(biz, "id", None)):
                        set_active_business(request, biz)
                        return
                except Exception:
                    # If membership check failed, do not set anything
                    pass

            # If we cannot determine a safe biz, clear any stale tenant context
            _clear_tenant_session(request)

        # --- Signal handlers -------------------------------------------------

        def _on_user_logged_in(sender, user, request, **kwargs):
            # 1) Cycle session id to prevent session fixation
            try:
                if hasattr(request, "session") and request.session is not None:
                    request.session.cycle_key()
            except Exception:
                pass

            # 2) Set a safe default business (or clear stale keys)
            try:
                _set_default_business(request, user)
            except Exception:
                # Final safety: never crash login
                pass

        def _on_user_logged_out(sender, user, request, **kwargs):
            # Clear any active business markers (session + threadlocal)
            try:
                _clear_tenant_session(request)
            except Exception:
                pass

        # Connect the hooks once
        try:
            user_logged_in.disconnect(receiver=_on_user_logged_in)  # idempotency
        except Exception:
            pass
        try:
            user_logged_out.disconnect(receiver=_on_user_logged_out)  # idempotency
        except Exception:
            pass

        try:
            user_logged_in.connect(_on_user_logged_in, dispatch_uid="accounts_user_logged_in_harden")
        except Exception:
            pass
        try:
            user_logged_out.connect(_on_user_logged_out, dispatch_uid="accounts_user_logged_out_harden")
        except Exception:
            pass
