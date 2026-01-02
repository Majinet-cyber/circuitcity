# core/decorators_bar_manager.py
"""
Decorators for Bar Manager role permissions.

Bar Managers have manager-level access EXCEPT they cannot:
- Delete products/stock items
- Archive stock
- Delete sales
"""
from __future__ import annotations

from functools import wraps
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect

from tenants.utils_roles import get_role, is_manager


def bar_manager_can_edit(view_func):
    """
    Decorator that allows Bar Managers to edit (but not delete/archive).

    Use this on views that allow editing prices, stock quantities, etc.
    but should block delete/archive operations.
    """

    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        user = getattr(request, "user", None)
        business = getattr(request, "business", None) or getattr(request, "active_business", None)

        if not user or not user.is_authenticated:
            messages.error(request, "Authentication required")
            return redirect("accounts:login")

        # Check if user is bar manager
        role = get_role(user, business)
        is_bar_manager = role == "BAR_MANAGER"

        # Bar managers can edit, but full managers can too
        if is_bar_manager or is_manager(user, business):
            return view_func(request, *args, **kwargs)

        # Not authorized
        messages.error(request, "You don't have permission to perform this action")
        return redirect("dashboard:home")

    return _wrapped_view


def manager_only_no_bar_manager(view_func):
    """
    Decorator that requires full Manager role (not Bar Manager).

    Use this on destructive operations like delete/archive that Bar Managers
    should not be able to perform.
    """

    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        user = getattr(request, "user", None)
        business = getattr(request, "business", None) or getattr(request, "active_business", None)

        if not user or not user.is_authenticated:
            messages.error(request, "Authentication required")
            return redirect("accounts:login")

        # Check role
        role = get_role(user, business)

        # Block Bar Managers from destructive operations
        if role == "BAR_MANAGER":
            messages.error(request, "Bar Managers cannot perform this action. Please contact a full Manager.")
            return redirect(request.META.get("HTTP_REFERER", "dashboard:home"))

        # Full managers can proceed
        if is_manager(user, business) and role != "BAR_MANAGER":
            return view_func(request, *args, **kwargs)

        # Not authorized
        messages.error(request, "You don't have permission to perform this action")
        return redirect("dashboard:home")

    return _wrapped_view


def is_bar_manager(user, business=None) -> bool:
    """
    Check if user is a Bar Manager (not a full manager).

    Args:
        user: User instance
        business: Business instance (optional)

    Returns:
        bool: True if user is BAR_MANAGER role
    """
    if not user or not user.is_authenticated:
        return False

    role = get_role(user, business)
    return role == "BAR_MANAGER"
