# tenants/resolution.py
"""
CANONICAL WORKSPACE RESOLVER — Single Source of Truth
======================================================
All code that needs to determine the active Business for a request
MUST use these helpers.  Do NOT duplicate resolution logic elsewhere.

Public API
----------
resolve_active_business(request)  → Business | None
require_active_business(request, *, for_api)  → Business  (raises/redirects on None)
get_membership_for_business(user, business)  → Membership | None
require_membership(request, business)  → Membership  (raises/redirects on missing)

Security guarantees
-------------------
- Session business_id is always validated against user membership.
- Multi-workspace users with no session selection → None (caller decides).
- Single-membership users → auto-resolved from DB.
- Invalid/stale session ids → cleared automatically.
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from django.conf import settings
from django.http import JsonResponse

if TYPE_CHECKING:
    from django.http import HttpRequest
    from tenants.models import Business, Membership

log = logging.getLogger(__name__)

TENANT_SESSION_KEY: str = getattr(settings, "TENANT_SESSION_KEY", "active_business_id")
_LEGACY_KEYS = (TENANT_SESSION_KEY, "active_business_id", "biz_id")

# URL constants (avoids reverse() failures during import)
_CHOOSE_URL = "/tenants/choose/"
_CREATE_URL = "/tenants/create/"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_active_business(request: "HttpRequest") -> Optional["Business"]:
    """
    Determine the active Business for *request*.

    Resolution order:
      1. request.business (set by TenantResolutionMiddleware) — fast path.
      2. Session key(s) → validate membership → return or clear + fall through.
      3. Single ACTIVE membership → auto-set session and return.
      4. Multiple memberships with no session selection → return None.
      5. Zero memberships → return None.

    Never raises. Returns None when workspace cannot be unambiguously resolved.
    """
    # Fast path: middleware already resolved it
    biz = getattr(request, "business", None)
    if biz is not None:
        return biz

    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None

    # Try session
    bid = _read_session_bid(request)
    if bid:
        biz = _resolve_biz(bid)
        if biz is not None:
            # Validate user membership (superusers bypass)
            if getattr(user, "is_superuser", False) or _has_membership(user, biz):
                _cache_on_request(request, biz)
                return biz
        # Stale / invalid → clear and fall through
        _clear_session(request)

    # Auto-resolve for single-membership users
    single = _single_membership_business(user)
    if single is not None:
        _persist_session(request, single)
        _cache_on_request(request, single)
        return single

    return None


def require_active_business(
    request: "HttpRequest",
    *,
    for_api: bool = False,
) -> "Business":
    """
    Return the active Business or raise/redirect.

    Args:
        request:  HttpRequest.
        for_api:  If True, raises an HttpResponse-subclass (JsonResponse 409) instead
                  of redirecting.  If False, returns an HttpResponse redirect.

    Returns:
        Business  — guaranteed non-None.

    Raises (for_api=True):
        _NoActiveWorkspace — callers should catch and return it as a response.

    Returns (for_api=False):
        An HttpResponseRedirect  — callers should detect this and return it.
    """
    biz = resolve_active_business(request)
    if biz is not None:
        return biz

    # Determine destination
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        has_any = _user_has_any_membership(user)
        dest = _CHOOSE_URL if has_any else _CREATE_URL
    else:
        dest = _CHOOSE_URL

    if for_api:
        raise _NoActiveWorkspace(choose_url=dest)

    from django.shortcuts import redirect
    return redirect(dest)


def get_membership_for_business(
    user, business: "Business"
) -> Optional["Membership"]:
    """
    Return the user's active Membership in *business*, or None.
    Never raises.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    if business is None:
        return None
    try:
        from tenants.models import Membership
        qs = Membership.objects.filter(user=user, business=business)
        if _membership_has_status():
            qs = qs.filter(status__iexact="ACTIVE")
        return qs.select_related("business").first()
    except Exception:
        return None


def require_membership(request: "HttpRequest", business: "Business") -> "Membership":
    """
    Return the user's membership in *business* or raise PermissionDenied.
    Callers in API views should catch PermissionDenied and return 403.
    """
    user = getattr(request, "user", None)
    mem = get_membership_for_business(user, business)
    if mem is None:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Not a member of this workspace.")
    return mem


# ---------------------------------------------------------------------------
# Internal exception used by require_active_business(for_api=True)
# ---------------------------------------------------------------------------

class _NoActiveWorkspace(Exception):
    """Raised by require_active_business when for_api=True and no workspace set."""

    def __init__(self, choose_url: str = _CHOOSE_URL):
        self.choose_url = choose_url
        super().__init__("No active workspace selected.")

    def as_response(self) -> JsonResponse:
        return JsonResponse(
            {
                "detail": "No active workspace selected",
                "action": "choose_workspace",
                "choose_url": self.choose_url,
            },
            status=409,
        )


# Make this importable as a first-class exception for API views
NoActiveWorkspaceError = _NoActiveWorkspace


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_session_bid(request) -> Optional[int]:
    try:
        for k in _LEGACY_KEYS:
            v = request.session.get(k)
            if v:
                return int(v)
    except Exception:
        pass
    return None


def _resolve_biz(pk: int) -> Optional["Business"]:
    try:
        from tenants.models import Business
        return Business.objects.filter(pk=pk, status="ACTIVE").first()
    except Exception:
        return None


def _has_membership(user, business) -> bool:
    try:
        from tenants.models import Membership
        qs = Membership.objects.filter(user=user, business=business)
        if _membership_has_status():
            qs = qs.filter(status__iexact="ACTIVE")
        return qs.exists()
    except Exception:
        return False


def _user_has_any_membership(user) -> bool:
    try:
        from tenants.models import Membership
        return Membership.objects.filter(user=user).exists()
    except Exception:
        return False


def _single_membership_business(user) -> Optional["Business"]:
    """Return the business if user has exactly one ACTIVE membership; else None."""
    try:
        from tenants.models import Membership
        qs = Membership.objects.filter(user=user).select_related("business")
        if _membership_has_status():
            qs = qs.filter(status__iexact="ACTIVE")
        # Also require business to be ACTIVE
        try:
            qs = qs.filter(business__status="ACTIVE")
        except Exception:
            pass
        count = qs.count()
        if count != 1:
            return None
        mem = qs.first()
        return getattr(mem, "business", None) if mem else None
    except Exception:
        return None


def _membership_has_status() -> bool:
    try:
        from tenants.models import Membership
        Membership._meta.get_field("status")
        return True
    except Exception:
        return False


def _persist_session(request, business) -> None:
    try:
        bid = getattr(business, "pk", None)
        for k in _LEGACY_KEYS:
            request.session[k] = bid
        request.session.modified = True
    except Exception:
        pass


def _clear_session(request) -> None:
    try:
        for k in _LEGACY_KEYS:
            request.session.pop(k, None)
        request.session.modified = True
    except Exception:
        pass


def _cache_on_request(request, business) -> None:
    try:
        request.business = business
        request.business_id = getattr(business, "pk", None)
    except Exception:
        pass
