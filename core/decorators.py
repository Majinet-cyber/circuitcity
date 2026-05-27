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
    return "application/json" in accept or xrw == "xmlhttprequest" or (request.path or "").lower().endswith(".json")


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


def _is_manager(user, request=None) -> bool:
    """
    Check if user is a manager.

    CRITICAL: Now uses AUTHORITATIVE role flags from middleware if available.
    This ensures consistent role detection with manager precedence.

    Priority:
    1. If request.cc_is_manager is set (from middleware), use it (PREFERRED)
    2. Fallback: check staff, superuser, groups, profile, business creator (for backward compatibility)

    Args:
        user: User instance
        request: Optional HttpRequest (preferred, to use middleware flags)

    Returns:
        bool: True if user is a manager
    """
    try:
        if not user or not user.is_authenticated:
            return False

        # PREFERRED: Use authoritative flag from middleware if available
        if request and hasattr(request, "cc_is_manager"):
            return bool(getattr(request, "cc_is_manager", False))

        # Fallback: legacy detection logic
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
        
        # CRITICAL FIX: Check if user is the business creator/owner
        # This handles cases where business was created but membership wasn't set up
        if request:
            business = getattr(request, "business", None)
            if business and getattr(business, "created_by_id", None) == user.pk:
                return True
    except Exception:
        # Be conservative if anything goes wrong
        return False
    return False


def _is_agent(user, request=None) -> bool:
    """
    Check if user is an agent (and NOT a manager).

    CRITICAL: Now uses AUTHORITATIVE role flags from middleware if available.
    This ensures managers are NEVER classified as agents.

    Priority:
    1. If request.cc_is_agent is set (from middleware), use it (PREFERRED)
    2. Fallback: authenticated user who is NOT manager (for backward compatibility)

    Args:
        user: User instance
        request: Optional HttpRequest (preferred, to use middleware flags)

    Returns:
        bool: True if user is an agent and NOT a manager
    """
    try:
        if not user or not user.is_authenticated:
            return False

        # PREFERRED: Use authoritative flag from middleware if available
        if request and hasattr(request, "cc_is_agent"):
            return bool(getattr(request, "cc_is_agent", False))

        # Fallback: agent = authenticated but not manager
        return not _is_manager(user, request) and not _safe_getattr(user, "is_staff", False)
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
    CRITICAL: Uses authoritative role flags from middleware.
    """

    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return _json_unauthorized() if _wants_json(request) else _login_redirect(request)
        if not _is_manager(user, request):  # Pass request to use middleware flags
            return _json_forbidden() if _wants_json(request) else HttpResponseForbidden("Forbidden: managers only")
        return view_func(request, *args, **kwargs)

    return _wrapped


def staff_or_manager_required(view_func: Callable) -> Callable:
    """
    Allow staff OR managers (superusers included).
    CRITICAL: Uses authoritative role flags from middleware.
    """

    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return _json_unauthorized() if _wants_json(request) else _login_redirect(request)
        if not (_safe_getattr(user, "is_staff", False) or _is_manager(user, request)):  # Pass request
            return _json_forbidden() if _wants_json(request) else HttpResponseForbidden("Forbidden: staff/manager only")
        return view_func(request, *args, **kwargs)

    return _wrapped


def agent_required(view_func: Callable) -> Callable:
    """
    Allow authenticated agents (non-staff, non-manager) only.
    Use this for agent self-service pages (e.g., wallet views).
    CRITICAL: Uses authoritative role flags from middleware (managers are NEVER agents).
    """

    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return _json_unauthorized() if _wants_json(request) else _login_redirect(request)
        if not _is_agent(user, request):  # Pass request to use middleware flags
            return _json_forbidden() if _wants_json(request) else HttpResponseForbidden("Forbidden: agents only")
        return view_func(request, *args, **kwargs)

    return _wrapped


def group_required(*group_names: str) -> Callable:
    """
    Allow access if the user belongs to ANY of the specified Django groups.
    Managers/staff/superusers are always allowed.
    CRITICAL: Uses authoritative role flags from middleware.
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
            if _is_manager(user, request) or _safe_getattr(user, "is_staff", False):  # Pass request
                return view_func(request, *args, **kwargs)
            if names and _user_in_any_group(user, names):
                return view_func(request, *args, **kwargs)
            return (
                _json_forbidden()
                if _wants_json(request)
                else HttpResponseForbidden("Forbidden: group membership required")
            )

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


def _is_bar_manager(user) -> bool:
    """
    Check if user has BAR_MANAGER role for the active business.
    Bar managers are liquor-specific supervisors/team leads.
    """
    try:
        if not user or not user.is_authenticated:
            return False

        # Get active business from request context (if available)
        # We check if user has a group matching biz:{business_id}:BAR_MANAGER
        user_groups = set(g.name for g in user.groups.all())

        # Check if any group matches BAR_MANAGER pattern
        for group_name in user_groups:
            if ":BAR_MANAGER" in group_name.upper():
                return True

        return False
    except Exception:
        return False


def liquor_operations_required(view_func: Callable) -> Callable:
    """
    Allow managers and bar managers to access liquor operational pages.

    Bar managers are liquor-specific team leads who can:
    - View/manage liquor agents
    - Access liquor dashboards/analytics
    - Manage liquor stock and sales

    But they cannot:
    - Access subscription/billing (manager-only)
    - Access HQ admin features
    """

    @functools.wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return _json_unauthorized() if _wants_json(request) else _login_redirect(request)

        # Allow managers, staff, or bar managers
        if _is_manager(user) or _safe_getattr(user, "is_staff", False) or _is_bar_manager(user):
            return view_func(request, *args, **kwargs)

        return (
            _json_forbidden()
            if _wants_json(request)
            else HttpResponseForbidden("Forbidden: liquor operations access required")
        )

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
    "liquor_operations_required",  # NEW: For liquor-specific bar manager + manager access
]
