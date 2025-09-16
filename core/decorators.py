# circuitcity/core/decorators.py
"""
Reusable view decorators for role-gating and safe HTTP usage.

Exports:
- manager_required(view)          -> allow staff/managers only
- staff_or_manager_required(view) -> allow staff or managers
- agent_required(view)            -> allow authenticated agents (non-staff, non-manager)
- group_required(*names)          -> allow users in any of the named Django groups (or manager/staff)
- post_required(view)             -> 405 unless POST

Behavior:
- If unauthenticated: redirect to LOGIN_URL (HTML) or return 401 JSON for XHR/JSON.
- If forbidden: 403 HTML or 403 JSON for XHR/JSON.
- Manager detection is resilient (superuser, is_staff, group names from settings,
  and optional user.profile.is_manager if present).
"""

from __future__ import annotations

import functools
from typing import Callable, Iterable

from django.conf import settings
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import redirect
from django.urls import resolve
from urllib.parse import quote as urlquote


# ------------------------------
# Helpers
# ------------------------------
def _wants_json(request: HttpRequest) -> bool:
    accept = (request.headers.get("Accept") or "").lower()
    xrw = (request.headers.get("X-Requested-With") or "").lower()
    # Consider JSON if explicit Accept contains json OR XHR OR requesting .json URL
    return (
        "application/json" in accept
        or xrw == "xmlhttprequest"
        or (request.path or "").lower().endswith(".json")
    )


def _login_redirect(request: HttpRequest) -> HttpResponse:
    login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
    nxt = urlquote(request.get_full_path() or "/")
    return redirect(f"{login_url}?next={nxt}")


def _safe_getattr(obj, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _user_in_any_group(user, names: Iterable[str]) -> bool:
    try:
        user_groups = set(g.name for g in user.groups.all())  # type: ignore[attr-defined]
        return any(n in user_groups for n in names)
    except Exception:
        return False


def _is_manager(user) -> bool:
    """
    Broad manager detection:
    - superuser OR is_staff
    - OR in any group listed in settings.ROLE_GROUP_MANAGER_NAMES
    - OR user.profile.is_manager is True (if profile exists)
    """
    try:
        if not user or not user.is_authenticated:
            return False
        if _safe_getattr(user, "is_superuser", False):
            return True
        if _safe_getattr(user, "is_staff", False):
            return True

        group_names = getattr(settings, "ROLE_GROUP_MANAGER_NAMES", ["Manager", "Admin"])
        if _user_in_any_group(user, group_names):
            return True

        profile = _safe_getattr(user, "profile", None)
        if profile and bool(_safe_getattr(profile, "is_manager", False)):
            return True
    except Exception:
        # Be conservative if anything goes wrong
        return False
    return False


def _is_agent(user) -> bool:
    """
    Agent = authenticated user who is NOT staff and NOT manager.
    """
    try:
        return bool(user and user.is_authenticated and not _is_manager(user) and not _safe_getattr(user, "is_staff", False))
    except Exception:
        return False


def _json_unauthorized() -> JsonResponse:
    return JsonResponse({"ok": False, "error": "authentication_required"}, status=401)


def _json_forbidden() -> JsonResponse:
    return JsonResponse({"ok": False, "error": "forbidden"}, status=403)


# ------------------------------
# Decorators
# ------------------------------
def manager_required(view_func: Callable) -> Callable:
    """
    Allow only staff/managers/superusers. Agents are blocked.
    """
    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return _json_unauthorized() if _wants_json(request) else _login_redirect(request)
        if not _is_manager(user):
            return _json_forbidden() if _wants_json(request) else HttpResponseForbidden("Forbidden: managers only")
        return view_func(request, *args, **kwargs)
    return _wrapped


def staff_or_manager_required(view_func: Callable) -> Callable:
    """
    Allow staff OR managers (superusers included).
    """
    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return _json_unauthorized() if _wants_json(request) else _login_redirect(request)
        if not (_safe_getattr(user, "is_staff", False) or _is_manager(user)):
            return _json_forbidden() if _wants_json(request) else HttpResponseForbidden("Forbidden: staff/manager only")
        return view_func(request, *args, **kwargs)
    return _wrapped


def agent_required(view_func: Callable) -> Callable:
    """
    Allow authenticated agents (non-staff, non-manager) only.
    Use this for agent self-service pages (e.g., wallet views).
    """
    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return _json_unauthorized() if _wants_json(request) else _login_redirect(request)
        if not _is_agent(user):
            return _json_forbidden() if _wants_json(request) else HttpResponseForbidden("Forbidden: agents only")
        return view_func(request, *args, **kwargs)
    return _wrapped


def group_required(*group_names: str) -> Callable:
    """
    Allow access if the user belongs to ANY of the specified Django groups.
    Managers/staff/superusers are always allowed.
    Usage:
        @group_required("Finance", "Ops")
        def view(...):
            ...
    """
    names = [n for n in group_names if n]

    def _decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs):
            user = getattr(request, "user", None)
            if not (user and user.is_authenticated):
                return _json_unauthorized() if _wants_json(request) else _login_redirect(request)
            if _is_manager(user) or _safe_getattr(user, "is_staff", False):
                return view_func(request, *args, **kwargs)
            if names and _user_in_any_group(user, names):
                return view_func(request, *args, **kwargs)
            return _json_forbidden() if _wants_json(request) else HttpResponseForbidden("Forbidden: group membership required")
        return _wrapped
    return _decorator


def post_required(view_func: Callable) -> Callable:
    """
    Enforce POST-only for state-changing endpoints (returns 405 on non-POST).
    """
    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if request.method != "POST":
            if _wants_json(request):
                return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)
            return HttpResponse(status=405)
        return view_func(request, *args, **kwargs)
    return _wrapped


# ------------------------------
# Public utilities (optional export)
# ------------------------------
__all__ = [
    "manager_required",
    "staff_or_manager_required",
    "agent_required",
    "group_required",
    "post_required",
]
