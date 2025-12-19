"""
Unified Date Filter Parser for Emajinet
Standardizes date range handling across all verticals, dashboards, and analytics.

Query Param Standard:
    - range: today|yesterday|7d|30d|month|custom
    - start: YYYY-MM-DD (required for custom)
    - end: YYYY-MM-DD (required for custom)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Any, Optional, Tuple
from django.utils import timezone


def parse_date_filter(
    request,
    default_range: str = "month"
) -> Dict[str, Any]:
    """
    Parse unified date filter from request.
    
    Args:
        request: Django HttpRequest object
        default_range: Default range if no params provided (default: "month")
    
    Returns:
        Dictionary with:
            - range_key: str (today|yesterday|7d|30d|month|custom)
            - start_date: date object (inclusive)
            - end_date: date object (inclusive)
            - range_label: str (human-readable label)
    
    Example:
        >>> data = parse_date_filter(request)
        >>> queryset.filter(created_at__date__gte=data['start_date'],
        ...                 created_at__date__lte=data['end_date'])
    """
    range_key = request.GET.get('range', default_range).lower()
    today = timezone.now().date()
    
    # Today
    if range_key == 'today':
        start_date = today
        end_date = today
        range_label = 'Today'
    
    # Yesterday
    elif range_key == 'yesterday':
        start_date = today - timedelta(days=1)
        end_date = start_date
        range_label = 'Yesterday'
    
    # Last 7 days
    elif range_key == '7d':
        start_date = today - timedelta(days=6)  # Last 7 days including today
        end_date = today
        range_label = 'Last 7 days'
    
    # Last 30 days
    elif range_key == '30d':
        start_date = today - timedelta(days=29)  # Last 30 days including today
        end_date = today
        range_label = 'Last 30 days'
    
    # This month (MTD)
    elif range_key == 'month' or range_key == 'mtd':
        start_date = today.replace(day=1)
        end_date = today
        range_label = 'This month'
    
    # Custom range
    elif range_key == 'custom':
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        
        try:
            start_date = date.fromisoformat(start_str)
        except (ValueError, TypeError):
            # Fallback to month start if invalid
            start_date = today.replace(day=1)
        
        try:
            end_date = date.fromisoformat(end_str)
        except (ValueError, TypeError):
            # Fallback to today if invalid
            end_date = today
        
        # Ensure start <= end
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        
        range_label = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    
    # Default fallback (shouldn't reach here)
    else:
        start_date = today.replace(day=1)
        end_date = today
        range_label = 'This month'
        range_key = 'month'
    
    return {
        'range_key': range_key,
        'start_date': start_date,
        'end_date': end_date,
        'range_label': range_label,
    }


def get_date_range_for_queries(
    request,
    default_range: str = "month"
) -> Tuple[date, date]:
    """
    Get (start_date, end_date) tuple for database queries.
    Both dates are inclusive.
    
    Args:
        request: Django HttpRequest object
        default_range: Default range if no params provided
    
    Returns:
        Tuple of (start_date, end_date) where both are inclusive
    
    Example:
        >>> start, end = get_date_range_for_queries(request)
        >>> queryset.filter(date__gte=start, date__lte=end)
    """
    data = parse_date_filter(request, default_range)
    return data['start_date'], data['end_date']


def get_date_range_context(
    request,
    default_range: str = "month"
) -> Dict[str, Any]:
    """
    Get complete date filter context for templates.
    
    Args:
        request: Django HttpRequest object
        default_range: Default range if no params provided
    
    Returns:
        Dictionary with all filter data ready for template context
    
    Example:
        >>> context = get_date_range_context(request)
        >>> return render(request, 'template.html', context)
    """
    return parse_date_filter(request, default_range)


# Backward compatibility helpers
def parse_date_range_from_request(request) -> Dict[str, Any]:
    """
    Legacy helper for backward compatibility.
    Maps old return format to new unified format.
    """
    data = parse_date_filter(request)
    return {
        'active_range': data['range_key'],
        'start_date': data['start_date'],
        'end_date': data['end_date'],
        'range_label': data['range_label'],
    }

