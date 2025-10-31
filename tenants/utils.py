# tenants/utils.py
from __future__ import annotations

from functools import wraps
from typing import Callable, Iterable, Optional
from urllib.parse import quote_plus

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify
from django.core.exceptions import PermissionDenied
from django.db.models import Q

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
# Accept both canonical and legacy session keys when reading:
TENANT_SESSION_KEYS_READ_ORDER = (
    TENANT_SESSION_KEY,         # usually "active_business_id"
    "active_business_id",       # explicit
    "biz_id",                   # legacy
)

ROLE_GROUP_MANAGER_NAMES = set(getattr(settings, "ROLE_GROUP_MANAGER_NAMES", ["Manager", "Admin"]))
ROLE_GROUP_ADMIN_NAMES = set(getattr(settings, "ROLE_GROUP_ADMIN_NAMES", ["Admin"]))
# Agent-role names (templates expect tenants.utils.is_agent)
ROLE_GROUP_AGENT_NAMES = set(getattr(settings, "ROLE_GROUP_AGENT_NAMES", ["Agent"]))

# Normalize role priority (case-insensitive match)
_ROLE_PRIORITY = ["OWNER", "MANAGER", "ADMIN", "AGENT"]


# ----------------------------
# Internals
# ----------------------------
def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _business_has_status_field() -> bool:
    if Business is None:
        return False
    return _model_has_field(Business, "status")


def _membership_has_status_field() -> bool:
    if Membership is None:
        return False
    return _model_has_field(Membership, "status")


def _active_filter_business(qs):
    if _business_has_status_field():
        try:
            return qs.filter(status__iexact="ACTIVE")
        except Exception:
            return qs
    return qs


def _resolve_business_by_id(pk):
    if Business is None:
        return None
    try:
        qs = _active_filter_business(Business.objects.all())
        return qs.get(pk=pk)
    except Exception:
        return None


def _safe_reverse(name: str, default: str) -> str:
    """
    Reverse a URL by name, falling back to the provided default string
    if reversing fails or the URL is "/".
    """
    try:
        url = reverse(name)
        return url or default
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


def _user_group_names(user) -> set[str]:
    try:
        return set(user.groups.values_list("name", flat=True))
    except Exception:
        return set()


def _same_path(request, url_path: str) -> bool:
    """True if the target path equals the current request path (normalized)."""
    try:
        cur = getattr(request, "path", "") or "/"
        return cur.rstrip("/") == (url_path or "/").rstrip("/")
    except Exception:
        return False


def _read_session_business_id(request: "HttpRequest"):
    """
    Read a business id from session using tolerant key order (new + legacy).
    """
    try:
        session = request.session
    except Exception:
        return None
    for k in TENANT_SESSION_KEYS_READ_ORDER:
        try:
            bid = session.get(k)
            if bid:
                return bid
        except Exception:
            continue
    return None


def _read_request_business_id(request: "HttpRequest"):
    """
    Read a business id directly from the request (query/header/body-lite).
    Priority:
      1) ?business_id= on GET
      2) X-Business-ID header
      3) business_id in POST form (if present)
    """
    try:
        bid = request.GET.get("business_id")
        if bid:
            return bid
    except Exception:
        pass
    try:
        bid = request.headers.get("X-Business-ID")
        if bid:
            return bid
    except Exception:
        pass
    try:
        # only cheap access; do not parse JSON here to avoid side effects
        bid = request.POST.get("business_id")
        if bid:
            return bid
    except Exception:
        pass
    return None


def _single_membership_business(user):
    """
    If the user has exactly one membership, return its business.
    Prefer ACTIVE membership if the field exists.
    """
    if Membership is None or not getattr(user, "is_authenticated", False):
        return None
    try:
        qs = Membership.objects.filter(user=user).select_related("business")
        # Prefer ACTIVE if 'status' exists
        if _membership_has_status_field():
            active_qs = qs.filter(status__iexact="ACTIVE")
            if active_qs.count() == 1:
                return active_qs.first().business
        # Fallback: exactly one membership overall
        if qs.count() == 1:
            return qs.first().business
    except Exception:
        return None
    return None


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
            # Clear session + request (canonical + legacy) and mark modified
            try:
                request.session.pop(TENANT_SESSION_KEY, None)
                request.session.pop("active_business_id", None)  # explicit
                request.session.pop("biz_id", None)             # legacy
                request.session.modified = True
            except Exception:
                pass
            try:
                setattr(request, "business", None)
            except Exception:
                pass
            # Clear thread-local
            set_current_business_id(None)
            return

        # Persist selection (write both canonical and legacy keys to be safe)
        bid = getattr(business, "pk", None)
        try:
            request.session[TENANT_SESSION_KEY] = bid
            request.session["active_business_id"] = bid
            request.session["biz_id"] = bid  # legacy compatibility
            request.session.modified = True
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
    Tries request.business first, then tolerant session keys.
    """
    # If middleware already set request.business, keep it authoritative.
    b = getattr(request, "business", None)
    if b is not None:
        return b

    bid = _read_session_business_id(request)
    if not bid:
        return None

    b = _resolve_business_by_id(bid)
    try:
        setattr(request, "business", b)
    except Exception:
        pass
    return b


def get_active_business_id(request: "HttpRequest"):
    """
    Convenience: return the active business id (or None).
    """
    b = get_active_business(request)
    return getattr(b, "id", None) if b else None


def ensure_active_business_id(
    request: "HttpRequest",
    *,
    auto_select_single: bool = True,
) -> Optional[int]:
    """
    Robustly determine the active business id for API/views.

    Resolution order:
      1) business_id from request (GET/POST/header)
      2) session (tolerant keys)
      3) if user has EXACTLY ONE membership (pref ACTIVE), set it and return (when auto_select_single=True)

    If a concrete Business cannot be resolved for the id discovered in (1) or (2),
    this returns None (and does NOT mutate session) unless auto_select_single can resolve one.
    """
    # 1) Request-provided id
    bid = _read_request_business_id(request)
    if bid:
        b = _resolve_business_by_id(bid)
        if b is not None:
            # Persist as the active business for the session/thread
            set_active_business(request, b)
            return int(getattr(b, "id", bid))

    # 2) Session
    bid = _read_session_business_id(request)
    if bid:
        b = _resolve_business_by_id(bid)
        if b is not None:
            # Cache onto request and mirror thread-local (idempotent)
            try:
                setattr(request, "business", b)
            except Exception:
                pass
            try:
                set_current_business_id(getattr(b, "pk", None))
            except Exception:
                pass
            return int(getattr(b, "id", bid))

    # 3) Single membership auto-pick
    if auto_select_single:
        auto_biz = _single_membership_business(getattr(request, "user", None))
        if auto_biz is not None:
            set_active_business(request, auto_biz)
            return int(getattr(auto_biz, "id", None) or 0) or None

    return None


# ----------------------------
# NEW: membership/role helpers (additive)
# ----------------------------
def resolve_default_business_for_user(user) -> Optional["Business"]:
    """
    Preferred default for a user:
      1) First ACTIVE membership with role OWNER/MANAGER/ADMIN (in that order)
      2) Any ACTIVE membership
      3) Any membership
    """
    if Membership is None or not getattr(user, "is_authenticated", False):
        return None

    qs = Membership.objects.filter(user=user).select_related("business")

    # Filter ACTIVE where applicable
    if _membership_has_status_field():
        qs_active = qs.filter(status__iexact="ACTIVE")
    else:
        qs_active = qs

    # 1) Prefer higher roles
    role_field = "role" if _model_has_field(Membership, "role") else None
    if role_field:
        for pref in _ROLE_PRIORITY:
            m = qs_active.filter(**{f"{role_field}__iexact": pref}).first()
            if m:
                return m.business

    # 2) Any ACTIVE membership
    m = qs_active.first()
    if m:
        return m.business

    # 3) Any membership
    m = qs.first()
    return m.business if m else None


def user_has_membership(user, business_id: int) -> bool:
    """
    True if the user has membership in the business (ACTIVE preferred when field exists).
    """
    if Membership is None or not getattr(user, "is_authenticated", False) or not business_id:
        return False
    try:
        base = Membership.objects.filter(user=user, business_id=business_id)
        if _membership_has_status_field():
            return base.filter(status__iexact="ACTIVE").exists()
        return base.exists()
    except Exception:
        return False


def user_highest_role(user) -> Optional[str]:
    """
    Return the user's highest role across memberships by priority OWNER>MANAGER>ADMIN>AGENT.
    If no roles are stored, returns None.
    """
    if Membership is None or not getattr(user, "is_authenticated", False):
        return None
    if not _model_has_field(Membership, "role"):
        return None
    try:
        roles = list(
            Membership.objects.filter(user=user)
            .values_list("role", flat=True)
        )
        roles_upper = {(r or "").upper() for r in roles}
        for pref in _ROLE_PRIORITY:
            if pref in roles_upper:
                return pref
        return next(iter(roles_upper), None)
    except Exception:
        return None


# ----------------------------
# Default Location helpers (lazy import to avoid cycles)
# ----------------------------
def default_location_for(business_or_id):
    """
    Return the default Location for the given business (or business id).
    This lazily imports Location to avoid circular imports.
    """
    try:
        # Import inside the function to avoid import-time circular deps
        from circuitcity.inventory.models import Location  # your project path
    except Exception:
        try:
            from inventory.models import Location  # fallback if app path differs
        except Exception:
            return None

    try:
        return Location.default_for(business_or_id)
    except Exception:
        return None


def default_location_for_request(request: "HttpRequest"):
    """
    Shortcut: default location for the current request's active business.
    """
    return default_location_for(get_active_business_id(request))


def get_default_location_for(request: "HttpRequest"):
    """
    Preferred location for forms:
      1) AgentProfile.primary_location (if present and belongs to active business)
      2) Business default location (Location.default_for)
      3) First Location for the active business
    Returns a Location instance or None.
    """
    biz = get_active_business(request)
    biz_id = getattr(biz, "id", None)
    if not biz_id:
        return None

    # Lazy imports to avoid cycles
    AgentProfile = None
    Location = None
    try:
        from circuitcity.accounts.models import AgentProfile as _AP  # type: ignore
        AgentProfile = _AP
    except Exception:
        try:
            from accounts.models import AgentProfile as _AP  # type: ignore
            AgentProfile = _AP
        except Exception:
            AgentProfile = None

    try:
        from circuitcity.inventory.models import Location as _Loc  # type: ignore
        Location = _Loc
    except Exception:
        try:
            from inventory.models import Location as _Loc  # type: ignore
            Location = _Loc
        except Exception:
            Location = None

    # 1) Agent's primary location
    try:
        user = getattr(request, "user", None)
        if AgentProfile and user and getattr(user, "is_authenticated", False):
            ap = AgentProfile.objects.filter(user=user).select_related("primary_location").first()
            loc = getattr(ap, "primary_location", None)
            if loc and getattr(loc, "business_id", None) == biz_id:
                return loc
    except Exception:
        pass

    # 2) Business default location
    try:
        loc = default_location_for(biz_id)
        if loc:
            return loc
    except Exception:
        pass

    # 3) Fallback: first location of business
    try:
        if Location:
            return Location.objects.filter(business_id=biz_id).first()
    except Exception:
        pass

    return None


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
# Role helpers
# ----------------------------
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


def user_is_agent(user) -> bool:
    """
    Agents are users in ROLE_GROUP_AGENT_NAMES (default: ["Agent"]).
    By definition here, superusers/admins/managers are not considered agents.
    """
    if user_is_admin(user) or user_is_manager(user):
        return False
    names = _user_group_names(user)
    return bool(names.intersection(ROLE_GROUP_AGENT_NAMES))


# —— Aliases expected by template tags / other modules ——
is_manager = user_is_manager
is_admin = user_is_admin
is_agent = user_is_agent


def _has_active_membership(user, business) -> bool:
    if Membership is None or business is None or not getattr(user, "is_authenticated", False):
        return False
    try:
        if _membership_has_status_field():
            return Membership.objects.filter(
                user=user, business=business, status__iexact="ACTIVE"
            ).exists()
        return Membership.objects.filter(user=user, business=business).exists()
    except Exception:
        return False


# ----------------------------
# Query scoping & object binding
# ----------------------------
def _tenant_fence(qs, business):
    """
    Apply tenant filter if the model carries either 'business' or 'location__business'.
    """
    try:
        model = getattr(qs, "model", None)
        if not model or business is None:
            return qs.none() if business is None and hasattr(qs, "none") else qs

        # Prefer direct business fence
        if _model_has_field(model, "business"):
            return qs.filter(business=business)

        # Otherwise try via location
        return qs.filter(location__business=business)
    except Exception:
        return qs


def _agent_visibility_q(user, model):
    """
    Build a best-effort Q() that limits visibility to rows the agent 'owns'.
    We try multiple common patterns but never crash if a field is missing.
    """
    q = Q()
    # direct ownership fields commonly seen
    for fname in ("assigned_to", "owner", "agent", "user"):
        try:
            if _model_has_field(model, fname):
                q |= Q(**{fname: user})
        except Exception:
            pass

    # via location membership
    try:
        # If model has FK to Location
        if _model_has_field(model, "location"):
            # Location has memberships.user (if you modeled it)
            q |= Q(location__memberships__user=user)
    except Exception:
        pass

    # If nothing matched, q will be empty; caller will handle fallback
    return q


def scoped(qs_or_manager, request: "HttpRequest", *, role_aware: bool = True):
    """
    Scope any queryset/manager to the active business and (optionally) role.
    - Managers/Admins: see all rows within their active business.
    - Agents: see ONLY their own/assigned/location rows.
    If a model does not carry a tenant field, the queryset is returned unchanged.
    """
    biz = get_active_business(request)

    # Normalize to queryset
    try:
        qs = qs_or_manager.all() if hasattr(qs_or_manager, "all") else qs_or_manager
    except Exception:
        qs = qs_or_manager

    # If the model doesn't expose anything we can fence by, leave as-is or none()
    model = getattr(qs, "model", None)
    if model is None:
        return qs

    # 1) Tenant fence
    qs = _tenant_fence(qs, biz)

    # If role-aware scoping is disabled or user is manager/admin, we're done
    user = getattr(request, "user", None)
    if not role_aware or is_manager(user):
        return qs

    # 2) Agent narrowing (best effort)
    try:
        q_agent = _agent_visibility_q(user, model)
        if q_agent.children:
            return qs.filter(q_agent)
        # If we can't determine ownership fields, safest is to return none for agents
        return qs.none() if hasattr(qs, "none") else qs
    except Exception:
        # Never leak cross-agent data on errors
        return qs.none() if hasattr(qs, "none") else qs


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
# Decorators
# ----------------------------
def require_business(_fn: Optional[Callable] = None) -> Callable:
    """
    Ensure a Business is active (via request.business or session key).

    Flexible usage (to avoid misuse bugs):
        @require_business
        def view(...): ...

        @require_business()   # also OK
        def view(...): ...

        path("...", require_business(view_func), ...)

    If not active:
      - Try to auto-select if the user has exactly ONE membership (prefers ACTIVE).
      - SUPERUSERS: send to HQ/dashboard unless that would loop, then run the view.
      - Everyone else: redirect to activation/settings with ?next=…, avoiding loops.
    """
    def _decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def _wrapped(request: "HttpRequest", *args, **kwargs):
            # Already selected
            biz = get_active_business(request)
            if biz is not None:
                return view_func(request, *args, **kwargs)

            user = getattr(request, "user", None)

            # Auto-pick if they have exactly one membership
            auto_biz = _single_membership_business(user)
            if auto_biz is not None:
                set_active_business(request, auto_biz)
                return view_func(request, *args, **kwargs)

            # Superusers should not be forced into tenant onboarding.
            if getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False):
                target = _superuser_home_url()

                # If the target resolves to the current path, DO NOT redirect: run the view.
                if _same_path(request, target):
                    return view_func(request, *args, **kwargs)

                # If the target is empty/root or equals current route, just render.
                if not target or target == "/" or _same_path(request, "/"):
                    return view_func(request, *args, **kwargs)

                return redirect(target)

            # Normal users → activation flow with next=
            target = _safe_reverse("tenants:activate_mine", "/tenants/activate/")
            next_q = quote_plus(getattr(request, "get_full_path", lambda: "/")())

            # If tenants app not mounted, nudge to unified settings
            if target in ("/", "/tenants/activate/"):
                target = _safe_reverse("accounts:settings_unified", "/accounts/settings/")

            # Avoid redirect loop: if we're already on the target, let the page render.
            if _same_path(request, target):
                try:
                    messages.info(request, "Select or set up your business to continue.")
                except Exception:
                    pass
                return view_func(request, *args, **kwargs)

            try:
                messages.info(request, "Select or set up your business to continue.")
            except Exception:
                pass
            return redirect(f"{target}?next={next_q}" if next_q else target)
        return _wrapped

    # Support bare and called usage
    if _fn is None:
        return _decorator
    return _decorator(_fn)


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
# Tenant bootstrap for manager sign-up
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


__all__ = [
    # session/context
    "set_active_business", "get_active_business", "get_active_business_id",
    # NEW helper (for APIs/views)
    "ensure_active_business_id",
    # NEW helpers
    "resolve_default_business_for_user", "user_has_membership", "user_highest_role",
    # default location helpers
    "default_location_for", "default_location_for_request", "get_default_location_for",
    # role checks (export both canonical and aliases)
    "user_is_manager", "user_is_admin", "user_is_agent",
    "is_manager", "is_admin", "is_agent",
    # scoping/binding/assert
    "scoped", "bind_business", "assert_owns",
    # decorators
    "require_business", "require_role", "manager_required", "admin_required",
    # bootstrap
    "bootstrap_manager_tenant",
]
