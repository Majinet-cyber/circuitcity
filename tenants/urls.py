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

# ---- Safe fallbacks so URLs never explode if views are missing ----
_manager_agents_view = getattr(views, "manager_review_agents", None)
if _manager_agents_view is None:
    def _manager_agents_view(request, *args, **kwargs):  # type: ignore
        return redirect("tenants:choose_business")

_manager_locations_view = getattr(views, "manager_locations", None)
if _manager_locations_view is None:
    def _manager_locations_view(request, *args, **kwargs):  # type: ignore
        # Graceful fallback until you implement the page
        return redirect("tenants:choose_business")

app_name = "tenants"

urlpatterns = [
    # Quick entry — decide/activate something sensible for this user
    path("", views.activate_mine, name="activate_mine"),
    path("activate/", views.activate_mine, name="activate"),
    path("clear/", views.clear_active, name="clear_active"),

    # Onboarding & switching
    path("choose/", views.choose_business, name="choose_business"),
    # Back-compat alias used by some helpers/templates
    path(
        "switcher/",
        RedirectView.as_view(pattern_name="tenants:choose_business", permanent=False),
        name="switcher",
    ),

    # Accept UUID-like string or numeric pk (slug converter allows both forms)
    path("set/<slug:biz_id>/", views.set_active, name="set_active"),
    # Friendly alias
    path("switch/<slug:biz_id>/", views.set_active, name="switch_active"),

    path("create/", views.create_business_as_manager, name="create_business"),
    path("join/", views.join_as_agent, name="join_as_agent"),

    # Self-service: managers creating their own business (optional helper)
    path("join-business/", views_join.join, name="join"),

    # Alias /tenants/signup/ → /accounts/signup/
    path(
        "signup/",
        RedirectView.as_view(pattern_name="accounts:signup", permanent=False),
        name="signup",
    ),

    # Staff approvals (supreme control)
    path("staff/approve/<int:pk>/", views.staff_approve_business, name="staff_approve_business"),

    # Manager: review agent join requests (per active business)
    path("manager/agents/", _manager_agents_view, name="manager_review_agents"),

    # Manager: manage store locations (per active business)
    path("manager/locations/", _manager_locations_view, name="manager_locations"),

    # Optional convenience alias: /tenants/manager/ → /tenants/manager/agents/
    path(
       "manager/",
       RedirectView.as_view(pattern_name="tenants:manager_review_agents", permanent=False),
       name="manager_home",
    ),
]
