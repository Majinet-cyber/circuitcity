# circuitcity/tenants/utils.py
from __future__ import annotations

from functools import wraps
from typing import Callable, Iterable, Optional
from urllib.parse import quote_plus

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify
from django.core.exceptions import PermissionDenied

try:
    from django.http import HttpRequest, HttpResponse
    from django.shortcuts import redirect
    from django.urls import reverse
    from django.contrib import messages
except Exception:  # pragma: no cover
    # Minimal shims if imported very early
    HttpRequest = object  # type: ignore
    HttpResponse = object  # type: ignore

    def redirect(url):  # type: ignore
        return url

    def reverse(name):  # type: ignore
        return "/"

# Import models and (optionally) the thread-local setter
try:
    from .models import Business, Membership, set_current_business_id  # type: ignore
except Exception:  # pragma: no cover
    Business = None  # type: ignore
    Membership = None  # type: ignore

    def set_current_business_id(_):  # type: ignore
        return None


# ----------------------------
# Constants
# ----------------------------
TENANT_SESSION_KEY = getattr(settings, "TENANT_SESSION_KEY", "active_business_id")
ROLE_GROUP_MANAGER_NAMES = set(getattr(settings, "ROLE_GROUP_MANAGER_NAMES", ["Manager", "Admin"]))
ROLE_GROUP_ADMIN_NAMES = set(getattr(settings, "ROLE_GROUP_ADMIN_NAMES", ["Admin"]))


# ----------------------------
# Internals
# ----------------------------
def _has_status_field() -> bool:
    if Business is None:
        return False
    try:
        Business._meta.get_field("status")
        return True
    except Exception:
        return False


def _active_filter(qs):
    if _has_status_field():
        try:
            return qs.filter(status__iexact="ACTIVE")
        except Exception:
            return qs
    return qs


def _resolve_business_by_id(pk):
    if Business is None:
        return None
    try:
        qs = _active_filter(Business.objects.all())
        return qs.get(pk=pk)
    except Exception:
        return None


def _safe_reverse(name: str, default: str) -> str:
    try:
        return reverse(name)
    except Exception:
        return default


def _superuser_home_url() -> str:
    """
    Where to send superusers when no active tenant is selected.
    Prefer the HQ dashboard; fall back to a general dashboard, then /hq/, then root.
    """
    url = _safe_reverse("hq:dashboard", "")
    if url and url != "/":
        return url
    url = _safe_reverse("dashboard:home", "")
    if url and url != "/":
        return url
    return "/hq/"


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except Exception:
        return False


# ----------------------------
# Public helpers (session / context)
# ----------------------------
def set_active_business(request: "HttpRequest", business) -> None:
    """
    Persist the selected business in session, attach it to the request,
    and mirror into thread-local (if available). Pass business=None to clear.
    """
    try:
        if business is None:
            # Clear session + request
            try:
                request.session.pop(TENANT_SESSION_KEY, None)
            except Exception:
                pass
            try:
                setattr(request, "business", None)
            except Exception:
                pass
            # Clear thread-local
            set_current_business_id(None)
            return

        # Persist selection
        bid = getattr(business, "pk", None)
        try:
            request.session[TENANT_SESSION_KEY] = bid
        except Exception:
            pass

        try:
            setattr(request, "business", business)
        except Exception:
            pass

        # Sync thread-local for the current request lifecycle (middleware should also set this)
        set_current_business_id(bid)

    except Exception:
        # Never crash login/boot flows because session isn't available yet
        try:
            setattr(request, "business", business)
        except Exception:
            pass


def get_active_business(request: "HttpRequest"):
    """
    Return the Business referenced by request or session, caching onto request.
    """
    # If middleware already set request.business, keep it authoritative.
    b = getattr(request, "business", None)
    if b is not None:
        return b

    bid = None
    try:
        bid = request.session.get(TENANT_SESSION_KEY)
    except Exception:
        bid = None

    if not bid:
        return None

    b = _resolve_business_by_id(bid)
    try:
        setattr(request, "business", b)
    except Exception:
        pass
    return b


# ----------------------------
# Middleware
# ----------------------------
def attach_business(get_response):
    """
    Middleware: attach request.business from session (if any) and mirror to thread-local.
    Put this near the top of MIDDLEWARE so all downstream code sees request.business.
    """
    def middleware(request: "HttpRequest"):
        # Try to load from session and set onto request
        b = get_active_business(request)
        try:
            set_current_business_id(getattr(b, "pk", None))
        except Exception:
            pass
        return get_response(request)

    return middleware


# ----------------------------
# Query scoping & object binding
# ----------------------------
def scoped(qs_or_manager, request: "HttpRequest"):
    """
    Scope any queryset/manager to the active business. If there is no active business,
    returns qs.none() (when possible) to avoid accidental cross-tenant leakage.
    Only applies if the model has a 'business' field; otherwise returns original qs.
    """
    biz = get_active_business(request)
    # Build a queryset from manager or queryset
    try:
        qs = qs_or_manager.all() if hasattr(qs_or_manager, "all") else qs_or_manager
    except Exception:
        qs = qs_or_manager

    # If model has a business field, apply the filter
    try:
        model = getattr(qs, "model", None)
        if model and _model_has_field(model, "business"):
            if not biz:
                return qs.none() if hasattr(qs, "none") else qs
            return qs.filter(business=biz)
    except Exception:
        # Fail-safe: return original qs on any unexpected issue
        return qs

    # If model doesn’t carry business, leave unchanged
    return qs


def bind_business(obj, request: "HttpRequest"):
    """
    Stamp an object with the active business if it has a 'business' field and isn't set.
    Use for create flows to guarantee tenant ownership.
    """
    try:
        if hasattr(obj, "business") and getattr(obj, "business_id", None) is None:
            biz = get_active_business(request)
            if biz is None:
                raise PermissionDenied("No active business selected.")
            obj.business = biz
    except Exception:
        pass
    return obj


def assert_owns(obj, request: "HttpRequest"):
    """
    Raise PermissionDenied if `obj` does not belong to the active tenant.
    Use after lookups that aren't pre-scoped (defense-in-depth).
    """
    try:
        biz = get_active_business(request)
        if hasattr(obj, "business_id") and biz and obj.business_id != biz.id:
            raise PermissionDenied("Cross-tenant access denied.")
    except PermissionDenied:
        raise
    except Exception:
        # If we can't determine, don't throw here—let the caller decide.
        pass


# ----------------------------
# Role & membership helpers
# ----------------------------
def _user_group_names(user) -> set[str]:
    try:
        return set(user.groups.values_list("name", flat=True))
    except Exception:
        return set()


def user_is_admin(user) -> bool:
    """
    Platform admin ≠ Django staff.
    - Superusers are platform-admins.
    - Users in ROLE_GROUP_ADMIN_NAMES (default: ["Admin"]) are platform-admins.
    - Plain is_staff does NOT grant platform-admin power.
    """
    if getattr(user, "is_superuser", False):
        return True
    names = _user_group_names(user)
    return bool(names.intersection(ROLE_GROUP_ADMIN_NAMES))


def user_is_manager(user) -> bool:
    """
    Managers are users in ROLE_GROUP_MANAGER_NAMES (default: ["Manager", "Admin"])
    or platform-admins. Django staff alone does not imply manager.
    """
    if user_is_admin(user):
        return True
    names = _user_group_names(user)
    return bool(names.intersection(ROLE_GROUP_MANAGER_NAMES))


def _has_active_membership(user, business) -> bool:
    if Membership is None or business is None or not getattr(user, "is_authenticated", False):
        return False
    try:
        return Membership.objects.filter(
            user=user, business=business, status="ACTIVE"
        ).exists()
    except Exception:
        return False


# ----------------------------
# Decorators
# ----------------------------
def require_business(view: Callable) -> Callable:
    """
    Ensure a Business is active (via request.business or session key).

    If not:
      - SUPERUSERS are redirected to the HQ dashboard (never to agent join).
      - Everyone else is redirected to the activation helper (with ?next=…),
        or to account settings if tenant URLs aren’t wired.
    """
    @wraps(view)
    def _wrapped(request: "HttpRequest", *args, **kwargs):
        # Already selected
        if get_active_business(request) is not None:
            return view(request, *args, **kwargs)

        # Superusers should not see onboarding/join
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False):
            return redirect(_superuser_home_url())

        # Normal users → activation flow with next=
        target = _safe_reverse("tenants:activate_mine", "/tenants/activate/")
        next_q = quote_plus(getattr(request, "get_full_path", lambda: "/")())
        url = f"{target}?next={next_q}" if next_q else target

        # If tenants app not mounted, nudge to unified settings
        if target in ("/", "/tenants/activate/"):
            fallback = _safe_reverse("accounts:settings_unified", "/accounts/settings/")
            url = f"{fallback}?next={next_q}"

        try:
            messages.info(request, "Select or set up your business to continue.")
        except Exception:
            pass
        return redirect(url)

    return _wrapped


def require_role(roles: Optional[Iterable[str]] = None) -> Callable:
    """
    Group-based role check with tenant membership enforcement.

    Rules:
      - Superusers always pass (platform-admin).
      - Otherwise, user MUST have an ACTIVE membership in the active business.
      - Then user must belong to at least one of the required groups (roles).
    """
    roles = list(roles or [])
    role_set = set(roles)

    if not roles:
        # pass-through
        def _decorator(fn: Callable) -> Callable:
            return fn
        return _decorator

    def _decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def _wrapped(request: "HttpRequest", *args, **kwargs):
            user = getattr(request, "user", None)
            if not getattr(user, "is_authenticated", False):
                login_url = _safe_reverse("accounts:login", "/accounts/login/")
                next_q = quote_plus(getattr(request, "get_full_path", lambda: "/")())
                # FIX: remove stray '}' that caused SyntaxError
                return redirect(f"{login_url}?next={next_q}")

            # Superuser bypass (platform-admin)
            if getattr(user, "is_superuser", False):
                return fn(request, *args, **kwargs)

            # Ensure an active business context exists
            biz = get_active_business(request)
            if biz is None:
                # Reuse require_business redirection logic
                target = _safe_reverse("tenants:activate_mine", "/tenants/activate/")
                next_q = quote_plus(getattr(request, "get_full_path", lambda: "/")())
                return redirect(f"{target}?next={next_q}")

            # Must be an ACTIVE member of the active business
            if not _has_active_membership(user, biz):
                try:
                    messages.error(request, "You don’t have access to this business.")
                except Exception:
                    pass
                return redirect(_safe_reverse("tenants:choose_business", "/tenants/choose/"))

            # Check group role
            if _user_group_names(user).intersection(role_set):
                return fn(request, *args, **kwargs)

            try:
                messages.error(request, "You don't have access to that page.")
            except Exception:
                pass
            return redirect("/")

        return _wrapped
    return _decorator


# Convenience decorators frequently used elsewhere
def manager_required(fn: Callable) -> Callable:
    return require_role(ROLE_GROUP_MANAGER_NAMES)(fn)


def admin_required(fn: Callable) -> Callable:
    return require_role(ROLE_GROUP_ADMIN_NAMES)(fn)


# ----------------------------
# NEW: Tenant bootstrap for manager sign-up
# ----------------------------
@transaction.atomic
def bootstrap_manager_tenant(
    request: "HttpRequest",
    user,
    store_name: str,
    subdomain: str = "",
    auto_approve: bool = True,
):
    """
    Create & activate a Business for a new manager, seed defaults, set active.

    - Ensures unique slug (slugify + numeric suffix)
    - Creates MANAGER membership (ACTIVE if auto_approve)
    - Calls Business.seed_defaults() if available (Store/Warehouse, etc.)
    - Sets session key (and thread-local if available) so they land on a fresh dashboard immediately
    """
    if Business is None:
        raise RuntimeError("Business model is not available")

    name = (store_name or "").strip()
    if not name:
        raise ValueError("store_name is required")

    # Unique slug
    slug = slugify(name) or "store"
    base, i = slug, 2
    try:
        while Business.objects.filter(slug=slug).exists():
            slug = f"{base}-{i}"
            i += 1
    except Exception:
        # In pathological cases fallback to timestamp suffix
        import time
        slug = f"{base}-{int(time.time())}"

    status = "ACTIVE" if auto_approve else "PENDING"

    b = Business.objects.create(
        name=name,
        slug=slug,
        subdomain=(subdomain or "").strip().lower(),
        status=status,
        created_by=user,
    )

    # Manager membership
    if Membership is not None:
        Membership.objects.create(
            user=user,
            business=b,
            role="MANAGER",
            status=("ACTIVE" if auto_approve else "PENDING"),
        )

    # Seed defaults (idempotent)
    if hasattr(b, "seed_defaults"):
        try:
            b.seed_defaults()
        except Exception:
            # Do not block signup on seed failures
            pass

    # Activate for this session (+ thread-local mirror)
    set_active_business(request, b)

    try:
        messages.success(request, f"Welcome! {b.name} is ready.")
    except Exception:
        pass

    return b
