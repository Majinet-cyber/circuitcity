# tenants/urls.py
from __future__ import annotations

from django.urls import path
from django.shortcuts import redirect
from django.views.generic import RedirectView

from . import views

# Optional helper module (don't crash if missing)
try:
    from . import views_join  # type: ignore
except Exception:  # pragma: no cover
    class _JoinFallback:
        @staticmethod
        def join(request, *args, **kwargs):
            # If the helper isn't installed, send users to the normal join page.
            return redirect("tenants:join_as_agent")
    views_join = _JoinFallback()  # type: ignore


# ---- Safe fallback helpers ---------------------------------------------------
def _fallback_redirect(to_name: str):
    def _v(request, *args, **kwargs):
        return redirect(to_name)
    return _v

def _get_or_fallback(name: str, fallback_to: str):
    fn = getattr(views, name, None)
    return fn if callable(fn) else _fallback_redirect(fallback_to)


# ---- Resolve views with graceful fallbacks (so templates never 500) ----------
# Core pages
activate_mine          = _get_or_fallback("activate_mine",          "tenants:choose_business")
activate               = _get_or_fallback("activate_mine",          "tenants:choose_business")
clear_active           = _get_or_fallback("clear_active",           "tenants:choose_business")
choose_business        = _get_or_fallback("choose_business",        "tenants:join_as_agent")
set_active             = _get_or_fallback("set_active",             "tenants:choose_business")
create_business        = _get_or_fallback("create_business_as_manager", "tenants:choose_business")
join_as_agent          = _get_or_fallback("join_as_agent",          "tenants:choose_business")

# Manager pages
# Prefer the dedicated view in views_manager.py to avoid redirect loops.
try:
    from .views_manager import manager_agents as _manager_agents_view  # type: ignore
    manager_review_agents = _manager_agents_view
except Exception:
    # Fallback to a view in views.py or (last resort) choose_business
    manager_review_agents = _get_or_fallback("manager_agents", "tenants:choose_business")

manager_locations      = _get_or_fallback("manager_locations",      "tenants:choose_business")

# Agent invite actions
create_agent_invite    = _get_or_fallback("create_agent_invite",    "tenants:manager_review_agents")
resend_agent_invite    = _get_or_fallback("resend_agent_invite",    "tenants:manager_review_agents")
revoke_agent_invite    = _get_or_fallback("revoke_agent_invite",    "tenants:manager_review_agents")
invite_accept          = _get_or_fallback("accept_invite",          "tenants:choose_business")

app_name = "tenants"

urlpatterns = [
    # Quick entry — decide/activate something sensible for this user
    path("",           activate_mine, name="activate_mine"),
    path("activate/",  activate,      name="activate"),
    path("clear/",     clear_active,  name="clear_active"),

    # Onboarding & switching
    path("choose/", choose_business, name="choose_business"),
    # Back-compat alias used by some helpers/templates
    path(
        "switcher/",
        RedirectView.as_view(pattern_name="tenants:choose_business", permanent=False),
        name="switcher",
    ),

    # Accept UUID-like string or numeric pk (slug converter allows both forms)
    path("set/<slug:biz_id>/", set_active, name="set_active"),
    # Friendly alias
    path("switch/<slug:biz_id>/", set_active, name="switch_active"),

    # Create / join
    path("create/", create_business, name="create_business"),
    path("join/",   join_as_agent,   name="join_as_agent"),

    # Self-service: managers creating their own business (optional helper)
    path("join-business/", views_join.join, name="join"),

    # Alias /tenants/signup/ → /accounts/signup/
    path(
        "signup/",
        RedirectView.as_view(pattern_name="accounts:signup", permanent=False),
        name="signup",
    ),

    # Staff approvals (supreme control)
    path(
        "staff/approve/<int:pk>/",
        _get_or_fallback("staff_approve_business", "tenants:choose_business"),
        name="staff_approve_business",
    ),

    # Manager: review agent join requests (per active business)
    path("manager/agents/", manager_review_agents, name="manager_review_agents"),

    # Manager: manage store locations (per active business)
    path("manager/locations/", manager_locations, name="manager_locations"),

    # Optional convenience alias: /tenants/manager/ → /tenants/manager/agents/
    path(
        "manager/",
        RedirectView.as_view(pattern_name="tenants:manager_review_agents", permanent=False),
        name="manager_home",
    ),

    # ----- Agent invite actions (names used in templates) -----
    # POST: create a new invite
    path("manager/agents/invite/", create_agent_invite, name="create_agent_invite"),
    # POST: resend an invite (optional)
    path("manager/agents/invite/<int:pk>/resend/", resend_agent_invite, name="resend_agent_invite"),
    # POST: revoke an invite (optional)
    path("manager/agents/invite/<int:pk>/revoke/", revoke_agent_invite, name="revoke_agent_invite"),

    # Accept invite (used in links shared with agents)
    path("invites/accept/<str:token>/", invite_accept, name="invite_accept"),
]
