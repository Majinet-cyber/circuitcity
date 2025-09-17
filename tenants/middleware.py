# tenants/middleware.py
from __future__ import annotations

from typing import Optional
from django.utils.deprecation import MiddlewareMixin
from django.utils.functional import cached_property
from django.contrib import messages

# Lazy/defensive imports (so startup never crashes if tenants app isn’t ready)
try:
    from tenants.models import Business, Membership, set_current_business_id  # thread-local setter
except Exception:  # pragma: no cover
    Business = None  # type: ignore
    Membership = None  # type: ignore

    def set_current_business_id(_):  # type: ignore
        return


LOCAL_HOSTS = {"127.0.0.1", "localhost"}
SESSION_KEY = "active_business_id"


def _host_without_port(host: str) -> str:
    if not host:
        return ""
    return host.split(":", 1)[0].strip().lower()


def _first_label(host: str) -> str:
    host = _host_without_port(host)
    if not host or host in LOCAL_HOSTS:
        return ""
    parts = host.split(".")
    return parts[0] if len(parts) > 1 else ""


def _has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def _filter_active_business(qs):
    """Respect Business.status == ACTIVE if that field exists; else pass-through."""
    if Business is None:
        return qs
    return qs.filter(status__iexact="ACTIVE") if _has_field(Business, "status") else qs


def _is_active_membership(mem) -> bool:
    if mem is None:
        return False
    # status ACTIVE if field exists; otherwise assume active
    if _has_field(Membership, "status"):
        return str(getattr(mem, "status", "")).upper() == "ACTIVE"
    return True


def _user_has_active_membership(user, business) -> bool:
    """True iff user has ACTIVE membership in given business (if models are available)."""
    if Membership is None or business is None or not getattr(user, "is_authenticated", False):
        return False
    try:
        qs = Membership.objects.filter(user=user, business=business)
        if _has_field(Membership, "status"):
            qs = qs.filter(status__iexact="ACTIVE")
        return qs.exists()
    except Exception:
        return False


def _activate(request, business) -> None:
    """
    Set session, request.business, AND thread-local tenant id.
    Never raises. If business is None, clears selection.
    """
    try:
        if business is not None:
            request.session[SESSION_KEY] = business.pk
        else:
            request.session.pop(SESSION_KEY, None)
    except Exception:
        # Session may be readonly; proceed anyway.
        pass

    request.business = business
    try:
        set_current_business_id(business.pk if business else None)
    except Exception:
        # Thread-local helper might be unavailable in early boot.
        pass


def _pick_owned_business_for_user(user) -> Optional[object]:
    """
    Return a sensible owned/created Business for the user if model supports it.
    Tries owner then created_by, newest first (Business must be ACTIVE).
    """
    if Business is None or user is None:
        return None

    qs = _filter_active_business(Business.objects)

    if _has_field(Business, "owner"):
        owned = qs.filter(owner=user).order_by("-id").first()
        if owned:
            return owned

    if _has_field(Business, "created_by"):
        created = qs.filter(created_by=user).order_by("-id").first()
        if created:
            return created

    return None


def _pick_active_membership_business_for_user(user) -> Optional[object]:
    """
    If Membership model exists, choose the most recent ACTIVE membership's business
    where the Business itself is ACTIVE.
    """
    if Membership is None or user is None:
        return None
    try:
        mem_qs = (
            Membership.objects.filter(user=user)
            .select_related("business")
            .order_by("-created_at", "-id")
        )
        for mem in mem_qs:
            biz = getattr(mem, "business", None)
            if not biz:
                continue
            # Respect Business.status if present
            if _has_field(Business, "status") and str(getattr(biz, "status", "")).upper() != "ACTIVE":
                continue
            if _is_active_membership(mem):
                return biz
    except Exception:
        return None
    return None


class TenantResolutionMiddleware(MiddlewareMixin):
    """
    Resolve request.business using (in order):

      0) initialize request.business=None and clear thread-local id
      1) superuser impersonation via ?as_business=<id> (NOT staff)
      2) session 'active_business_id'  (membership required unless superuser)
      3) subdomain (ignored on localhost) (for authenticated users: membership required unless superuser)
      4) ACTIVE membership business for authenticated user
      5) owned/created ACTIVE business for authenticated user

    On success, also writes thread-local tenant id so auto-scoped managers work.
    """

    @cached_property
    def _has_business_model(self) -> bool:
        return Business is not None

    def process_request(self, request):
        # Start clean every request
        request.business = None
        try:
            set_current_business_id(None)  # reset thread-local at request start
        except Exception:
            pass

        if not self._has_business_model:
            return

        user = getattr(request, "user", None)

        # (1) Superuser impersonation (NOT staff)
        as_bid = request.GET.get("as_business")
        if as_bid and getattr(user, "is_superuser", False):
            try:
                b = _filter_active_business(Business.objects).get(pk=as_bid)
                _activate(request, b)
                try:
                    messages.info(request, f"Impersonating {b.name}")
                except Exception:
                    pass
                return
            except Exception:
                # Ignore bad ids quietly
                pass

        # (2) Session selection (validate membership for non-superusers)
        bid = None
        try:
            bid = request.session.get(SESSION_KEY)
        except Exception:
            bid = None

        if bid:
            try:
                b = _filter_active_business(Business.objects).get(pk=bid)
                if getattr(user, "is_superuser", False) or _user_has_active_membership(user, b):
                    _activate(request, b)
                    return
            except Exception:
                # invalid id or inactive business
                pass
            # Session points to a non-existent/inactive/unauthorized business → clear it
            try:
                request.session.pop(SESSION_KEY, None)
            except Exception:
                pass

        # (3) Subdomain resolution (production-style)
        try:
            host = _host_without_port(request.get_host())
            sub = _first_label(host)
            if sub and _has_field(Business, "subdomain"):
                b = _filter_active_business(Business.objects).filter(subdomain__iexact=sub).first()
                if b:
                    # Allow for anonymous (pre-auth) and superusers; for authenticated users require membership
                    if (not getattr(user, "is_authenticated", False)) or getattr(user, "is_superuser", False) or _user_has_active_membership(user, b):
                        _activate(request, b)
                        return
        except Exception:
            # get_host() may raise in tests or odd proxies
            pass

        # (4) Active membership (most-recent)
        if getattr(user, "is_authenticated", False):
            b = _pick_active_membership_business_for_user(user)
            if b:
                _activate(request, b)
                return

        # (5) Owned/created business (fresh signups / dev localhost)
        if getattr(user, "is_authenticated", False):
            b = _pick_owned_business_for_user(user)
            if b:
                _activate(request, b)
                return

        # Unresolved → request.business stays None; thread-local already cleared.

    def process_response(self, request, response):
        # belt & suspenders: clear thread-local after the response is built
        try:
            set_current_business_id(None)
        except Exception:
            pass
        return response
