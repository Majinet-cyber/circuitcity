"""
Date filtering utilities for HQ and dashboard views.
Ensures consistent date range handling across all dashboards.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Tuple

from django.utils import timezone


def get_month_range(year: int, month: int) -> Tuple[date, date]:
    """
    Return (start_date, end_date) for a given year/month.
    - start_date: first day of the month (inclusive)
    - end_date: first day of the NEXT month (exclusive)
    
    This ensures consistent filtering: start_date <= date < end_date
    """
    start_date = date(year, month, 1)
    # Compute the first day of the next month
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    return start_date, end_date


def get_period_from_request(request, default_to_current_month: bool = True) -> Tuple[date, date, str]:
    """
    Extract date range from request query params.
    
    Query params:
    - month (int): 1-12
    - year (int): e.g., 2025
    - range (str): "7d", "30d", "custom", or "all" (optional fallback)
    
    Returns:
    - (start_date, end_date, period_type)
    - period_type: "month", "7d", "30d", "custom", or "all"
    
    If default_to_current_month=True and no params given, returns current month range.
    """
    today = timezone.now().date()
    
    # Try month/year first (most specific)
    month_str = request.GET.get("month", "").strip()
    year_str = request.GET.get("year", "").strip()
    
    if month_str and year_str:
        try:
            month = int(month_str)
            year = int(year_str)
            if 1 <= month <= 12 and 1900 <= year <= 2100:
                start, end = get_month_range(year, month)
                return start, end, "month"
        except (ValueError, TypeError):
            pass
    
    # Fallback to range param
    rng = (request.GET.get("range") or "").lower()
    
    if rng == "7d":
        start = today - timedelta(days=7)
        return start, today, "7d"
    
    if rng == "30d":
        start = today - timedelta(days=30)
        return start, today, "30d"
    
    if rng == "custom":
        start_str = request.GET.get("start", "").strip()
        end_str = request.GET.get("end", "").strip()
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d").date()
            end = datetime.strptime(end_str, "%Y-%m-%d").date()
            if start <= end:
                return start, end, "custom"
        except (ValueError, TypeError):
            pass
    
    # Default behavior
    if default_to_current_month:
        start, end = get_month_range(today.year, today.month)
        return start, end, "month"
    else:
        # Return "all time" (no filtering)
        return None, None, "all"


def get_year_from_request(request) -> int:
    """
    Extract year from request, defaulting to current year.
    """
    year_str = request.GET.get("year", "").strip()
    if year_str:
        try:
            year = int(year_str)
            if 1900 <= year <= 2100:
                return year
        except (ValueError, TypeError):
            pass
    return timezone.now().year


def month_list_for_year(year: int) -> list[Tuple[int, str]]:
    """
    Return list of (month_num, month_name) for a given year.
    Useful for generating month selectors in templates.
    """
    import calendar
    return [(m, calendar.month_name[m]) for m in range(1, 13)]


def tz_aware_start_of_day(d: date) -> datetime:
    """
    Convert a date to timezone-aware datetime at start of day (midnight).
    """
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(d, datetime.min.time()), tz)


def tz_aware_end_of_day(d: date) -> datetime:
    """
    Convert a date to timezone-aware datetime at end of day (23:59:59.999999).
    """
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(d, datetime.max.time()), tz)

