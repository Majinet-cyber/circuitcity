# circuitcity/accounts/signals.py
from __future__ import annotations

from typing import Optional

from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out

# Defensive imports so auth never explodes if tenants app shifts around
try:
    from tenants.models import Business, Membership, set_current_business_id  # type: ignore
except Exception:  # pragma: no cover
    Business = None  # type: ignore
    Membership = None  # type: ignore

    def set_current_business_id(_):  # type: ignore
        return

try:
    # Canonical helpers that also write legacy session keys in this project
    from tenants.utils import set_active_business, get_active_business  # type: ignore
except Exception:  # pragma: no cover
    def set_active_business(_request, _biz):  # type: ignore
        return

    def get_active_business(_request):  # type: ignore
        return None


# -------------------------------------------------------------------
# Small helpers (safe if fields/models are missing)
# -------------------------------------------------------------------

def _has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def _filter_active_memberships(qs):
    """If Membership.status exists, keep only ACTIVE rows; else pass-through."""
    if Membership is None:
        return qs
    if _has_field(Membership, "status"):
        return qs.filter(status__iexact="ACTIVE")
    return qs


def _business_is_active(biz) -> bool:
    """If Business.status exists, require ACTIVE; else treat as active."""
    if biz is None:
        return False
    if Business is None:
        return True
    if _has_field(Business, "status"):
        return str(getattr(biz, "status", "")).upper() == "ACTIVE"
    return True


def _pick_business_from_memberships(user) -> Optional[object]:
    """
    Most recent ACTIVE membership’s business where Business is ACTIVE (if such fields exist).
    """
    if Membership is None or Business is None or user is None:
        return None
    try:
        qs = Membership.objects.filter(user=user).select_related("business")
        qs = _filter_active_memberships(qs).order_by("-created_at", "-id")
        for mem in qs:
            biz = getattr(mem, "business", None)
            if not biz:
                continue
            if _business_is_active(biz):
                return biz
    except Exception:
        return None
    return None


def _pick_owned_or_created_business(user) -> Optional[object]:
    """
    Fallback to a Business owned/created by user (prefer newest), restricted to ACTIVE if that field exists.
    """
    if Business is None or user is None:
        return None
    try:
        qs = Business.objects.all()
        if _has_field(Business, "status"):
            qs = qs.filter(status__iexact="ACTIVE")
        # Prefer owner
        if _has_field(Business, "owner"):
            owned = qs.filter(owner=user).order_by("-id").first()
            if owned:
                return owned
        # Else created_by
        if _has_field(Business, "created_by"):
            created = qs.filter(created_by=user).order_by("-id").first()
            if created:
                return created
    except Exception:
        return None
    return None


def _clear_tenant_session(request) -> None:
    """
    Remove all known/legacy tenant session keys and clear thread-local.
    Never raises (auth flow must not break).
    """
    try:
        # Canonical + legacy keys
        for k in ("active_business_id", "biz_id"):
            try:
                request.session.pop(k, None)
            except Exception:
                pass
        try:
            # Canonical key may be customized in settings
            from django.conf import settings
            key = getattr(settings, "TENANT_SESSION_KEY", "active_business_id")
            try:
                request.session.pop(key, None)
            except Exception:
                pass
        except Exception:
            pass

        # Mirror to thread-local and request attributes
        try:
            set_current_business_id(None)
        except Exception:
            pass
        try:
            request.business = None  # type: ignore[attr-defined]
            request.business_id = None  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception:
        pass


def _activate_on_request(request, business) -> None:
    """
    Use canonical util; fall back to writing session keys; set thread-local id.
    Never raises (auth flow must not break).
    """
    try:
        set_active_business(request, business)
    except Exception:
        try:
            if business is not None:
                bid = getattr(business, "pk", None)
                request.session["active_business_id"] = bid
                request.session["biz_id"] = bid
            else:
                request.session.pop("active_business_id", None)
                request.session.pop("biz_id", None)
        except Exception:
            pass

    try:
        request.business = business  # type: ignore[attr-defined]
        request.business_id = getattr(business, "pk", None) if business else None  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        set_current_business_id(getattr(business, "pk", None) if business else None)
    except Exception:
        pass


# -------------------------------------------------------------------
# Auth signal handlers (privacy-first; defense-in-depth)
# -------------------------------------------------------------------

@receiver(user_logged_in)
def _set_default_business(sender, request, user, **kwargs):
    """
    After login (privacy-first):
      0) Cycle the session key to prevent session fixation.
      1) If a business is already active for this request/session, keep it.
      2) Else pick the most recent ACTIVE membership’s business (and Business must be ACTIVE, if that field exists).
      3) Else pick an ACTIVE business the user owns/created.
      4) Else clear any stale tenant context.

    This avoids ever dropping a manager/owner into the agent-join path by accident,
    and prevents cross-tenant bleed from a previous session.
    """
    # 0) Session fixation defense
    try:
        if hasattr(request, "session") and request.session is not None:
            request.session.cycle_key()
    except Exception:
        pass

    # 1) Respect any previously chosen business for this session
    try:
        existing = get_active_business(request)
        if existing and _business_is_active(existing):
            _activate_on_request(request, existing)
            return
    except Exception:
        pass

    # 2) Active membership business
    biz = _pick_business_from_memberships(user)
    if not biz:
        # 3) Owned/created fallback
        biz = _pick_owned_or_created_business(user)

    if biz:
        _activate_on_request(request, biz)
    else:
        # 4) No safe default → clear any stale context
        _clear_tenant_session(request)


@receiver(user_logged_out)
def _purge_tenant_on_logout(sender, request, user, **kwargs):
    """
    On logout: clear active business markers (session + threadlocal) to avoid
    cross-tenant bleed when the next user logs in on a shared device.
    """
    _clear_tenant_session(request)
