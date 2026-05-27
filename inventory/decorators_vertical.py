# inventory/decorators_vertical.py
"""
Vertical guard decorator to prevent vertical leakage.
Redirects users to the correct vertical-specific URL if they access a wrong vertical's route.
"""
from __future__ import annotations

from functools import wraps
from typing import Callable, Optional
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch

from inventory.helpers import business_vertical, get_active_business
from inventory.helpers_core import PHONES, CLOTHING, LIQUOR, PHARMACY, GYM
from inventory.views_router import (
    _get_vertical_dashboard_url,
    _get_vertical_scan_url,
    _get_vertical_sell_url,
    _get_vertical_stock_url,
)


def vertical_guard(allowed_verticals: Optional[list[str]] = None, redirect_to: Optional[str] = None):
    """
    Decorator that ensures a view is only accessible for specific verticals.

    Args:
        allowed_verticals: List of vertical keys (e.g., [PHONES, CLOTHING]). If None, allows all.
        redirect_to: URL name to redirect to if vertical doesn't match. If None, uses dashboard.

    Usage:
        @vertical_guard(allowed_verticals=[PHONES])
        def phones_only_view(request):
            ...
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            business = get_active_business(request)
            if not business:
                # No business, let the view handle it (or require_business decorator will catch it)
                return view_func(request, *args, **kwargs)

            current_vertical = business_vertical(request)

            # If no restrictions, allow access
            if allowed_verticals is None:
                return view_func(request, *args, **kwargs)

            # Check if current vertical is allowed
            if current_vertical in allowed_verticals:
                return view_func(request, *args, **kwargs)

            # Vertical mismatch - redirect to correct vertical
            if redirect_to:
                try:
                    url = reverse(redirect_to)
                    return redirect(url)
                except NoReverseMatch:
                    pass

            # Default: redirect to current vertical's dashboard
            url = _get_vertical_dashboard_url(current_vertical)
            return redirect(url)

        return wrapper

    return decorator


def prevent_vertical_leakage(view_func: Callable) -> Callable:
    """
    Decorator that redirects old vertical-specific URLs to the business-aware router.

    This prevents users with old bookmarks (e.g., /verticals/phones/stock/) from
    accessing the wrong vertical's pages.

    Usage:
        @prevent_vertical_leakage
        def old_phones_stock_view(request):
            # This will redirect to /app/stock/ which routes correctly
            ...
    """

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        business = get_active_business(request)
        if not business:
            return view_func(request, *args, **kwargs)

        current_vertical = business_vertical(request)

        # Determine which router endpoint to use based on the view name or URL
        # This is a best-effort approach - views should use the router endpoints directly
        url_path = request.path.lower()

        if "/stock" in url_path or "/list" in url_path:
            url = _get_vertical_stock_url(current_vertical)
        elif "/scan" in url_path and "/sell" not in url_path:
            url = _get_vertical_scan_url(current_vertical)
        elif "/sell" in url_path or "/scan-sold" in url_path:
            url = _get_vertical_sell_url(current_vertical)
        else:
            url = _get_vertical_dashboard_url(current_vertical)

        return redirect(url)

    return wrapper
