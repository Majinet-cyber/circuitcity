# circuitcity/tenants/middleware.py
from __future__ import annotations

from typing import Iterable, Optional

from django.utils.deprecation import MiddlewareMixin
from django.utils.functional import cached_property

# ── Lazy/defensive imports (never crash at startup) ─────────────────────────────
try:
    from django.conf import settings
except Exception:  # pragma: no cover

    class _S:  # minimal shim
        TENANT_SESSION_KEY = "active_business_id"

    settings = _S()  # type: ignore

# Import shared bypass prefixes for consistent middleware behavior
try:
    from cc.middleware_constants import BYPASS_PREFIXES
except Exception:  # pragma: no cover
    # Fallback if import fails
    BYPASS_PREFIXES = (
        "/sw.js",
        "/manifest.json",
        "/favicon.ico",
        "/static/",
        "/media/",
    )

try:
    from tenants.models import Business, Membership, set_current_business_id  # thread-local setter
except Exception:  # pragma: no cover
    Business = None  # type: ignore
    Membership = None  # type: ignore

    def set_current_business_id(_):  # type: ignore
        return


try:
    # Use the SAME utils your views use to store/read active biz
    from tenants.utils import get_active_business, set_active_business
except Exception:  # pragma: no cover

    def get_active_business(_request):  # type: ignore
        return None

    def set_active_business(_request, _biz):  # type: ignore
        return


# Optional: scope helpers (location resolution). All guarded.
try:
    from tenants.scope import get_active_business as scope_get_active_business  # same behavior as utils-based
    from tenants.scope import resolve_location_for_user, serialize_scope_for_ui, set_scope_in_session
except Exception:  # pragma: no cover

    def resolve_location_for_user(_request):  # type: ignore
        return None

    def serialize_scope_for_ui(_request):  # type: ignore
        return {}

    def set_scope_in_session(_request, *, business_id=None, location_id=None):  # type: ignore
        return

    scope_get_active_business = get_active_business  # type: ignore

LOCAL_HOSTS = {"127.0.0.1", "localhost"}

# Canonical session key (configurable) + legacy keys
CANONICAL_SESSION_KEY = getattr(settings, "TENANT_SESSION_KEY", "active_business_id")
LEGACY_SESSION_KEYS: Iterable[str] = (CANONICAL_SESSION_KEY, "active_business_id", "biz_id")

PRODUCT_MODE_SESSION_KEY = "product_mode"  # single source of truth for UI mode

# ── product/vertical normalization (aliases) ────────────────────────────────────
VERTICAL_ALIASES = {
    # Phones / Electronics
    "phones & electronics": "phones",
    "electronics": "phones",
    "phone": "phones",
    "phones": "phones",
    "mobile": "phones",
    "mobiles": "phones",
    # Pharmacy
    "pharmacy": "pharmacy",
    "chemist": "pharmacy",
    "medicine": "pharmacy",
    "drugstore": "pharmacy",
    # Liquor
    "liquor": "liquor",
    "bar": "liquor",
    "alcohol": "liquor",
    "pub": "liquor",
    "bottle-store": "liquor",
    "bottle store": "liquor",
    # Grocery / Supermarket / Retail
    "grocery": "grocery",
    "groceries": "grocery",
    "supermarket": "grocery",
    "supermarket & groceries": "grocery",
    "retail": "grocery",
}


def normalize_vertical(v: str | None) -> str:
    key = (v or "").strip().lower()
    return VERTICAL_ALIASES.get(key, "generic")


# ── small helpers ───────────────────────────────────────────────────────────────
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


def _mark_session_modified(request) -> None:
    try:
        request.session.modified = True
    except Exception:
        pass


def _clear_tenant_session_keys(request) -> None:
    """
    Clear canonical + legacy tenant keys from the session.
    """
    try:
        for k in LEGACY_SESSION_KEYS:
            try:
                request.session.pop(k, None)
            except Exception:
                pass
        _mark_session_modified(request)
    except Exception:
        pass


def _activate(request, business) -> None:
    """
    Set session (via project util), request.business(+_id) and thread-local tenant id.
    Never raises. If business is None, clears selection.
    """
    try:
        # Preferred: your canonical util writes both canonical & legacy keys
        set_active_business(request, business)
        _mark_session_modified(request)
    except Exception:
        # Fallback to legacy session keys
        try:
            if business is not None:
                bid = getattr(business, "pk", None)
                request.session[CANONICAL_SESSION_KEY] = bid
                request.session["active_business_id"] = bid
                request.session["biz_id"] = bid
            else:
                _clear_tenant_session_keys(request)
            _mark_session_modified(request)
        except Exception:
            pass

    request.business = business
    request.business_id = getattr(business, "pk", None) if business else None
    try:
        set_current_business_id(getattr(business, "pk", None) if business else None)
    except Exception:
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
    Choose the SINGLE ACTIVE membership's business if user has exactly one.
    Returns None if user has 0 or 2+ active memberships (preserves multi-business selection flow).
    
    CRITICAL FIX: Only auto-select when user has exactly ONE membership.
    Multi-business users should NOT have auto-selected business - they must choose.
    """
    if Membership is None or user is None:
        return None
    try:
        mem_qs = Membership.objects.filter(user=user).select_related("business").order_by("-created_at", "-id")
        
        # Filter to only ACTIVE memberships with ACTIVE businesses
        active_memberships = []
        for mem in mem_qs:
            biz = getattr(mem, "business", None)
            if not biz:
                continue
            if _has_field(Business, "status") and str(getattr(biz, "status", "")).upper() != "ACTIVE":
                continue
            if _is_active_membership(mem):
                active_memberships.append((mem, biz))
        
        # CRITICAL: Only auto-select if exactly ONE membership
        if len(active_memberships) != 1:
            return None
        
        return active_memberships[0][1]  # Return the business
    except Exception:
        return None


def _derive_product_mode_from_business(biz) -> str:
    """
    Inspect common Business attributes and their display() to derive a vertical mode.
    """
    if not biz:
        return "generic"

    for attr in ("vertical", "category", "industry", "type", "kind", "sector", "business_kind", "business_type"):
        val = getattr(biz, attr, None)
        if isinstance(val, str) and val.strip():
            return normalize_vertical(val)
        disp = getattr(biz, f"get_{attr}_display", None)
        if callable(disp):
            try:
                dv = disp()
                if isinstance(dv, str) and dv.strip():
                    return normalize_vertical(dv)
            except Exception:
                pass

    return "generic"


def _set_product_mode_on_request(request, business) -> None:
    """
    Decide and attach request.product_mode, also persist in session for templates.
    Priority:
      1) ?mode= override (dev/testing)
      2) derived from Business fields
      3) session fallback
      4) 'generic'
    """
    # 1) explicit override
    override = request.GET.get("mode")
    if override:
        mode = normalize_vertical(override)
    else:
        # 2) from business
        mode = _derive_product_mode_from_business(business)

        # 3) session fallback if still generic
        if mode == "generic":
            try:
                sess_mode = request.session.get(PRODUCT_MODE_SESSION_KEY)
                if isinstance(sess_mode, str) and sess_mode:
                    mode = normalize_vertical(sess_mode)
            except Exception:
                pass

    request.product_mode = mode or "generic"
    try:
        request.session[PRODUCT_MODE_SESSION_KEY] = request.product_mode
        _mark_session_modified(request)
    except Exception:
        pass


def _attach_location_scope(request) -> None:
    """
    Optional helper: if tenants.scope is available, compute the effective location,
    store it on the request for templates, and persist in session.
    No-ops if the helpers aren't importable.
    """
    try:
        # Resolve against the same active business we just activated
        bid = getattr(request, "business_id", None)
        if not bid:
            request.location_id = None
            request.scope = {}
            return

        lid = resolve_location_for_user(request)
        request.location_id = lid
        request.scope = serialize_scope_for_ui(request)

        # Persist chosen scope for UX continuity
        set_scope_in_session(request, business_id=bid, location_id=lid)
    except Exception:
        # Never block request flow if scope helpers fail
        request.location_id = None
        request.scope = {}


def _attach_role_to_request(request) -> None:
    """
    AUTHORITATIVE role attachment: compute role using centralized logic and store on request.
    This is the single source of truth for role determination used by views, templates, etc.

    Attaches:
        - request.cc_business: Business object
        - request.cc_role: Role string ("MANAGER", "AGENT", "OWNER", "AUDITOR", "BAR_MANAGER", "NONE")
        - request.cc_is_manager: Boolean (True for managers, owners, staff, superusers)
        - request.cc_is_agent: Boolean (True ONLY if agent and NOT manager)
        - request.cc_is_owner: Boolean (True if business owner)

    CRITICAL: This implements manager precedence - managers are NEVER agents.
    """
    try:
        from tenants.utils_roles import attach_role_to_request

        attach_role_to_request(request)
    except Exception:
        # Fallback: set safe defaults if utils_roles isn't available
        request.cc_business = getattr(request, "business", None)
        request.cc_role = "NONE"
        request.cc_is_manager = False
        request.cc_is_agent = False
        request.cc_is_owner = False


# ── Middleware ─────────────────────────────────────────────────────────────────
class TenantResolutionMiddleware(MiddlewareMixin):
    """
    Resolve request.business using (in order):

      0) initialize request.business=None and clear thread-local id
      1) canonical util: get_active_business(request)  ← matches your views
      2) superuser impersonation via ?as_business=<id> (NOT staff)
      3) session selection via any known keys (membership required unless superuser)
      4) subdomain (ignored on localhost) (for authenticated users: membership required unless superuser)
      5) ACTIVE membership business for authenticated user
      6) owned/created ACTIVE business for authenticated user

    Also sets a *single source of truth* for UI vertical:
      request.product_mode ∈ {'phones','pharmacy','liquor','grocery','generic'}
      and persists it under session['product_mode'].

    Additionally (if tenants.scope is present), attaches:
      request.location_id and request.scope (JSON) for templates/JS.
    """

    @cached_property
    def _has_business_model(self) -> bool:
        return Business is not None

    def __call__(self, request):
        # CRITICAL: Bypass critical paths at the very top to prevent redirect loops
        path = request.path_info or request.path or "/"

        # Bypass shared allowlist paths (service worker, static, etc.)
        for prefix in BYPASS_PREFIXES:
            if path.startswith(prefix):
                return self.get_response(request)

        # CRITICAL: Bypass HQ paths to prevent redirect loops
        if path.startswith("/hq/"):
            return self.get_response(request)
        # CRITICAL: Bypass public gym QR code endpoints (no tenant resolution required)
        if path.startswith("/gym/qr/"):
            return self.get_response(request)
        return super().__call__(request)

    def process_request(self, request):
        # Start clean every request
        request.business = None
        request.business_id = None
        request.product_mode = "generic"
        request.location_id = None
        request.scope = {}
        # Role flags (will be set after business resolution)
        request.cc_business = None
        request.cc_role = "NONE"
        request.cc_is_manager = False
        request.cc_is_agent = False
        request.cc_is_owner = False
        try:
            set_current_business_id(None)  # reset thread-local at request start
        except Exception:
            pass

        # CRITICAL: Bypass critical paths entirely to prevent redirect loops
        path = getattr(request, "path", "")

        # Bypass shared allowlist paths (service worker, static, etc.)
        for prefix in BYPASS_PREFIXES:
            if path.startswith(prefix):
                _set_product_mode_on_request(request, None)
                return

        # CRITICAL: Bypass HQ paths to prevent redirect loops
        if path.startswith("/hq/"):
            _set_product_mode_on_request(request, None)
            return
        # CRITICAL: Bypass public gym QR code endpoints (no tenant resolution required)
        if path.startswith("/gym/qr/"):
            _set_product_mode_on_request(request, None)
            return

        # CRITICAL: Bypass staff/superusers to prevent redirect loops
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
                _set_product_mode_on_request(request, None)
                return

        if not self._has_business_model:
            # Still allow mode override even if Business model isn't present
            _set_product_mode_on_request(request, None)
            return

        # (0) CRITICAL: Auto-select single-business users FIRST
        #     This prevents 302 redirects to /tenants/ for users with exactly one membership
        #     Must happen BEFORE any other resolution to ensure session is populated
        if getattr(user, "is_authenticated", False):
            try:
                from tenants.services.active_business import ensure_active_business
                biz = ensure_active_business(request, user, auto_select_single=True)
                if biz:
                    # SSOT auto-selected a business - activate it and return
                    _activate(request, biz)
                    _set_product_mode_on_request(request, biz)
                    _attach_location_scope(request)  # safe, optional
                    _attach_role_to_request(request)  # AUTHORITATIVE role determination
                    return
            except Exception:
                pass  # Continue with normal resolution if SSOT fails

        # (1) Canonical: use the same util as your views/templates
        #     (This will now benefit from the session set by SSOT above)
        try:
            b = get_active_business(request)
            if b:
                _activate(request, b)
                _set_product_mode_on_request(request, b)
                _attach_location_scope(request)  # safe, optional
                _attach_role_to_request(request)  # AUTHORITATIVE role determination
                return
        except Exception:
            # continue with fallbacks
            pass

        # (2) Superuser impersonation (NOT staff)
        as_bid = request.GET.get("as_business")
        if as_bid and getattr(user, "is_superuser", False):
            try:
                b = _filter_active_business(Business.objects).get(pk=as_bid)
                _activate(request, b)
                _set_product_mode_on_request(request, b)
                _attach_location_scope(request)
                _attach_role_to_request(request)  # AUTHORITATIVE role determination
                return
            except Exception:
                pass  # ignore bad ids quietly

        # (3) Session selection (validate membership for non-superusers)
        bid = None
        try:
            # Try ANY known keys (canonical + legacy)
            for k in LEGACY_SESSION_KEYS:
                bid = request.session.get(k)
                if bid:
                    break
        except Exception:
            bid = None

        if bid:
            try:
                b = _filter_active_business(Business.objects).get(pk=bid)
                # CRITICAL FIX: Also accept business creators as valid (owner == manager access)
                is_creator = getattr(b, "created_by_id", None) == getattr(user, "pk", None)
                if getattr(user, "is_superuser", False) or _user_has_active_membership(user, b) or is_creator:
                    _activate(request, b)
                    _set_product_mode_on_request(request, b)
                    _attach_location_scope(request)
                    _attach_role_to_request(request)  # AUTHORITATIVE role determination
                    return
            except Exception:
                pass  # invalid id / inactive business

            # Clear stale session value(s)
            _clear_tenant_session_keys(request)

        # (4) Subdomain resolution (production-style)
        try:
            host = _host_without_port(request.get_host())
            sub = _first_label(host)
            if sub and _has_field(Business, "subdomain"):
                b = _filter_active_business(Business.objects).filter(subdomain__iexact=sub).first()
                if b:
                    # Allow anonymous or superusers; require membership for authed users
                    if (
                        (not getattr(user, "is_authenticated", False))
                        or getattr(user, "is_superuser", False)
                        or _user_has_active_membership(user, b)
                    ):
                        _activate(request, b)
                        _set_product_mode_on_request(request, b)
                        _attach_location_scope(request)
                        _attach_role_to_request(request)  # AUTHORITATIVE role determination
                        return
        except Exception:
            # get_host() may raise in tests or odd proxies
            pass

        # (5) Active membership (most-recent)
        if getattr(user, "is_authenticated", False):
            b = _pick_active_membership_business_for_user(user)
            if b:
                _activate(request, b)
                _set_product_mode_on_request(request, b)
                _attach_location_scope(request)
                _attach_role_to_request(request)  # AUTHORITATIVE role determination
                return

        # (6) Owned/created business (fresh signups / dev localhost)
        if getattr(user, "is_authenticated", False):
            b = _pick_owned_business_for_user(user)
            if b:
                _activate(request, b)
                _set_product_mode_on_request(request, b)
                _attach_location_scope(request)
                _attach_role_to_request(request)  # AUTHORITATIVE role determination
                return

        # Unresolved business → still compute/allow mode override so UI is not blocked
        _set_product_mode_on_request(request, None)
        _attach_location_scope(request)
        _attach_role_to_request(request)  # AUTHORITATIVE role determination (will set NONE if no business)

    def process_response(self, request, response):
        # Clear thread-local after the response is built (belt & suspenders)
        try:
            set_current_business_id(None)
        except Exception:
            pass
        return response


# ── Compatibility shim ─────────────────────────────────────────────────────────
# Some settings may still refer to `tenants.middleware.ActiveBusinessMiddleware`.
# Keep this class name available and delegate to the resolver above.
class ActiveBusinessMiddleware(TenantResolutionMiddleware):
    """
    Backwards-compatible alias for setups that list `ActiveBusinessMiddleware`
    in MIDDLEWARE. Inherits full behavior from TenantResolutionMiddleware.
    """

    pass
