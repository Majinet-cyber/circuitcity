# inventory/analytics/common.py
"""
Core helpers for analytics: date range parsing, filters, grouping, caching.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from functools import lru_cache

from django.core.cache import cache
from django.db.models import QuerySet, Q
from django.utils import timezone


def parse_date_range(
    range_preset: Optional[str] = None,
    start_str: Optional[str] = None,
    end_str: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse date range from request parameters.

    Args:
        range_preset: One of 'today', 'yesterday', 'this_month', 'last_month', 'custom'
        start_str: Start date string (YYYY-MM-DD) for custom range
        end_str: End date string (YYYY-MM-DD) for custom range

    Returns:
        Dict with 'start_date', 'end_date', 'range_label', 'active_range'
    """
    today = timezone.now().date()

    if range_preset == "today":
        start_date = today
        end_date = today
        range_label = "Today"
        active_range = "today"
    elif range_preset == "yesterday":
        start_date = today - timedelta(days=1)
        end_date = start_date
        range_label = "Yesterday"
        active_range = "yesterday"
    elif range_preset == "this_month":
        start_date = today.replace(day=1)
        end_date = today
        range_label = "This Month"
        active_range = "this_month"
    elif range_preset == "last_month":
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        start_date = last_day_last_month.replace(day=1)
        end_date = last_day_last_month
        range_label = "Last Month"
        active_range = "last_month"
    elif range_preset == "custom" or start_str or end_str:
        # Custom range
        if start_str:
            try:
                start_date = date.fromisoformat(start_str)
            except (ValueError, TypeError):
                start_date = today - timedelta(days=30)
        else:
            start_date = today - timedelta(days=30)

        if end_str:
            try:
                end_date = date.fromisoformat(end_str)
            except (ValueError, TypeError):
                end_date = today
        else:
            end_date = today

        range_label = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
        active_range = "custom"
    else:
        # Default: last 30 days
        start_date = today - timedelta(days=30)
        end_date = today
        range_label = "Last 30 Days"
        active_range = None

    return {
        "start_date": start_date,
        "end_date": end_date,
        "range_label": range_label,
        "active_range": active_range,
    }


def apply_business_scope(qs: QuerySet, business) -> QuerySet:
    """
    Apply business scoping to a queryset.
    Tries multiple common field patterns.
    """
    if not business:
        return qs.none()

    model = qs.model

    # Direct business FK
    if hasattr(model, "business_id"):
        return qs.filter(business=business)

    # Via location
    if hasattr(model, "location_id"):
        try:
            return qs.filter(location__business=business)
        except Exception:
            pass

    # Via shift (for liquor)
    if hasattr(model, "shift_id"):
        try:
            return qs.filter(shift__location__business=business)
        except Exception:
            pass

    # Via member (for gym)
    if hasattr(model, "member_id"):
        try:
            return qs.filter(member__business=business)
        except Exception:
            pass

    # If we can't scope, return empty queryset for safety
    return qs.none()


def apply_location_filter(qs: QuerySet, location) -> QuerySet:
    """Apply location filter to queryset."""
    if not location:
        return qs

    model = qs.model

    # Direct location FK
    if hasattr(model, "location_id"):
        return qs.filter(location=location)

    # Via shift
    if hasattr(model, "shift_id"):
        try:
            return qs.filter(shift__location=location)
        except Exception:
            pass

    return qs


def apply_payment_method_filter(qs: QuerySet, payment_method: Optional[str]) -> QuerySet:
    """Apply payment method filter."""
    if not payment_method or payment_method == "ALL":
        return qs

    model = qs.model

    # Common field names
    for field_name in ["payment_method", "payment_mode", "payment_type"]:
        if hasattr(model, field_name):
            try:
                return qs.filter(**{field_name: payment_method})
            except Exception:
                continue

    return qs


def apply_search_filter(qs: QuerySet, search_query: str, search_fields: list[str]) -> QuerySet:
    """Apply search filter across multiple fields."""
    if not search_query or not search_fields:
        return qs

    model = qs.model
    q_objects = Q()

    for field in search_fields:
        if hasattr(model, field) or "__" in field:
            try:
                q_objects |= Q(**{f"{field}__icontains": search_query})
            except Exception:
                continue

    if q_objects.children:
        return qs.filter(q_objects)

    return qs


def get_cache_key(prefix: str, business_id: int, **filters) -> str:
    """
    Generate cache key for analytics data.
    Includes all filter parameters to ensure correct cache hits.
    """
    filter_str = "_".join(f"{k}:{v}" for k, v in sorted(filters.items()) if v)
    return f"analytics:v2:{prefix}:biz:{business_id}:{filter_str}"


def cache_analytics_data(key: str, data: Any, timeout: int = 300) -> None:
    """
    Cache analytics data with default 5 minute timeout.
    Increase timeout for expensive aggregates.

    Args:
        key: Cache key
        data: Data to cache
        timeout: Cache timeout in seconds (default 300 = 5 minutes)
    """
    cache.set(key, data, timeout)


def get_cached_analytics_data(key: str) -> Optional[Any]:
    """Get cached analytics data. Returns None if not cached or expired."""
    return cache.get(key)


def cache_or_compute(key: str, compute_fn, timeout: int = 300) -> Any:
    """
    Cache-or-compute pattern helper.
    Checks cache first, computes and caches if miss.

    Args:
        key: Cache key
        compute_fn: Callable that computes the value
        timeout: Cache timeout in seconds

    Returns:
        Cached or computed value
    """
    cached = get_cached_analytics_data(key)
    if cached is not None:
        return cached

    # Compute
    result = compute_fn()

    # Cache for next time
    cache_analytics_data(key, result, timeout)

    return result
