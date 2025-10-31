# tenants/urls.py
from __future__ import annotations

from django.shortcuts import redirect
from django.urls import path
from django.views.generic import RedirectView

from . import views

# --- Optional helpers (import if present; never crash) -------------------------
try:
    from . import views_join  # type: ignore
except Exception:
    class _JoinFallback:
        @staticmethod
        def join(request, *args, **kwargs):
            # If the helper isn't installed, send users to the normal join page.
            return redirect("tenants:join_as_agent")
    views_join = _JoinFallback()  # type: ignore

# Prefer a dedicated manager views module if present
_vm = None
try:
    from . import views_manager as _vm  # type: ignore
except Exception:
    _vm = None

# Prefer dedicated invite-accept views module if present
_vinv = None
try:
    from . import views_invites as _vinv  # type: ignore
except Exception:
    _vinv = None


# --- Safe fallback helpers -----------------------------------------------------
def _fallback_redirect(to_name: str):
    def _v(request, *args, **kwargs):
        return redirect(to_name)
    return _v


def _get_or_fallback(name: str, fallback_to: str):
    fn = getattr(views, name, None)
    return fn if callable(fn) else _fallback_redirect(fallback_to)


def _is_from_module(fn, module_prefix: str) -> bool:
    """
    Guard against accidentally wiring non-view helpers/services that share names.
    We only accept callables whose __module__ starts with the expected prefix.
    """
    return callable(fn) and getattr(fn, "__module__", "").startswith(module_prefix)


def _safe_redirect_to(name: str, fallback: str):
    """
    Return a view that redirects to `name` if it exists at request time;
    otherwise redirect to `fallback`. Prevents 500s from NoReverseMatch.
    """
    from django.urls import reverse, NoReverseMatch

    def _view(_request, *args, **kwargs):
        try:
            reverse(name)
            return redirect(name)
        except NoReverseMatch:
            return redirect(fallback)
    return _view


# --- Resolve core views with graceful fallbacks (so templates never 500) -------
# Core pages
activate_mine   = _get_or_fallback("activate_mine",              "tenants:choose_business")
activate        = _get_or_fallback("activate_mine",              "tenants:choose_business")
clear_active    = _get_or_fallback("clear_active",               "tenants:choose_business")
choose_business = _get_or_fallback("choose_business",            "tenants:join_as_agent")
set_active      = _get_or_fallback("set_active",                 "tenants:choose_business")
create_business = _get_or_fallback("create_business_as_manager", "tenants:choose_business")
join_as_agent   = _get_or_fallback("join_as_agent",              "tenants:choose_business")

# Manager pages (prefer dedicated views_manager.py)
_manager_agents_view = getattr(_vm, "manager_agents", None) if _vm else None
_create_invite_candidate = getattr(_vm, "create_agent_invite", None) if _vm else None

# Use manager_agents from views_manager if available; otherwise fall back
manager_review_agents = (
    _manager_agents_view
    if _is_from_module(_manager_agents_view, "tenants.views_manager")
    else _get_or_fallback("manager_agents", "tenants:choose_business")
)

# ----- Agent invite actions ----------------------------------------------------
# We must ensure we point to a real Django view (callable(request,...)),
# NOT the zero-arg service function with the same name inside tenants.services.
create_agent_invite = None

# 1) Prefer a function defined in tenants.views_manager
if _is_from_module(_create_invite_candidate, "tenants.views_manager"):
    create_agent_invite = _create_invite_candidate

# 2) Else try a view function in tenants.views
if create_agent_invite is None:
    _views_create = getattr(views, "create_agent_invite", None)
    if _is_from_module(_views_create, "tenants.views"):
        create_agent_invite = _views_create

# 3) Final fallback: safe redirect back to the list page
if create_agent_invite is None:
    create_agent_invite = _fallback_redirect("tenants:manager_review_agents")

# These two are optional in your codebase; fall back to the list page if missing.
resend_agent_invite = _get_or_fallback("resend_agent_invite", "tenants:manager_review_agents")
revoke_agent_invite = _get_or_fallback("revoke_agent_invite", "tenants:manager_review_agents")

# Locations manager (list + create)
manager_locations = _get_or_fallback("manager_locations", "tenants:choose_business")

# Accept invite link (used in shared URLs).
# Prefer tenants.views_invites.accept_invite if present; else views.accept_invite; else fallback.
invite_accept = None
if _vinv:
    _accept_candidate = getattr(_vinv, "accept_invite", None)
    if _is_from_module(_accept_candidate, "tenants.views_invites"):
        invite_accept = _accept_candidate
if invite_accept is None:
    _views_accept = getattr(views, "accept_invite", None)
    if _is_from_module(_views_accept, "tenants.views"):
        invite_accept = _views_accept
if invite_accept is None:
    invite_accept = _fallback_redirect("tenants:choose_business")


# --- URL patterns --------------------------------------------------------------
app_name = "tenants"

urlpatterns = [
    # Quick entry — decide/activate something sensible for this user
    path("",          activate_mine, name="activate_mine"),
    path("activate/", activate,      name="activate"),
    path("clear/",    clear_active,  name="clear_active"),

    # Onboarding & switching
    path("choose/", choose_business, name="choose_business"),
    # Back-compat alias used by some helpers/templates
    path(
        "switcher/",
        RedirectView.as_view(pattern_name="tenants:choose_business", permanent=False),
        name="switcher",
    ),

    # Accept UUID-like string or numeric pk (slug converter allows both forms)
    path("set/<slug:biz_id>/",    set_active, name="set_active"),
    path("switch/<slug:biz_id>/", set_active, name="switch_active"),  # friendly alias

    # Create / join
    path("create/",        create_business,        name="create_business"),
    path("join/",          join_as_agent,          name="join_as_agent"),
    path("join-business/", views_join.join,        name="join"),  # optional helper

    # Alias /tenants/signup/ → /accounts/signup/ (fallback to accounts:login if missing)
    path("signup/", _safe_redirect_to("accounts:signup", "accounts:login"), name="signup"),

    # Staff approvals (supreme control)
    path(
        "staff/approve/<int:pk>/",
        _get_or_fallback("staff_approve_business", "tenants:choose_business"),
        name="staff_approve_business",
    ),

    # --- Manager: review agent join requests (per active business)
    path("manager/agents/", manager_review_agents, name="manager_review_agents"),

    # --- Manager: manage store locations (per active business)
    path("manager/locations/", manager_locations, name="manager_locations"),
    # Optional convenience: explicitly select a business in the URL
    path("manager/<int:business_id>/locations/", manager_locations, name="manager_locations_for_biz"),

    # Optional convenience alias: /tenants/manager/ → /tenants/manager/agents/
    path(
        "manager/",
        RedirectView.as_view(pattern_name="tenants:manager_review_agents", permanent=False),
        name="manager_home",
    ),

    # ----- Agent invite actions (names used by templates) -----
    path("manager/agents/invite/",                 create_agent_invite, name="create_agent_invite"),
    path("manager/agents/invite/<int:pk>/resend/", resend_agent_invite, name="resend_agent_invite"),
    path("manager/agents/invite/<int:pk>/revoke/", revoke_agent_invite, name="revoke_agent_invite"),

    # Accept invite (used in links shared with agents)
    # NOTE: <str:token> safely carries TimestampSigner tokens (no slashes).
    path("invites/accept/<str:token>/", invite_accept, name="invite_accept"),
]
