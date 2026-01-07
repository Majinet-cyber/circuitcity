# inventory/utils/date_ranges.py
"""
Date range utilities for dashboard and analytics filters.
Supports presets (today, 7d, mtd, all) and custom date ranges.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from django.utils import timezone


def parse_date_range(
    preset: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse date range from preset or custom start/end dates.

    Args:
        preset: One of "today", "7d", "mtd", "all", or None
        start_date: Custom start date (YYYY-MM-DD format)
        end_date: Custom end date (YYYY-MM-DD format)

    Returns:
        Tuple of (start_datetime, end_datetime)
        - start_datetime: Start of range (inclusive), or None for "all time"
        - end_datetime: End of range (inclusive, end of day), or None for "all time"

    Examples:
        >>> parse_date_range(preset="today")
        (datetime(2024, 1, 5, 0, 0, 0), datetime(2024, 1, 5, 23, 59, 59))

        >>> parse_date_range(preset="7d")
        (datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 1, 5, 23, 59, 59))

        >>> parse_date_range(start_date="2024-01-01", end_date="2024-01-31")
        (datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 1, 31, 23, 59, 59))
    """
    now = timezone.now()
    today = now.date()

    # Handle presets first
    if preset == "today":
        start_dt = datetime.combine(today, datetime.min.time())
        end_dt = datetime.combine(today, datetime.max.time())
        return timezone.make_aware(start_dt), timezone.make_aware(end_dt)

    elif preset == "7d":
        # Last 7 days (including today)
        start_date_obj = today - timedelta(days=6)  # 6 days ago + today = 7 days
        start_dt = datetime.combine(start_date_obj, datetime.min.time())
        end_dt = datetime.combine(today, datetime.max.time())
        return timezone.make_aware(start_dt), timezone.make_aware(end_dt)

    elif preset == "mtd":
        # Month to date (first day of current month to today)
        start_date_obj = date(today.year, today.month, 1)
        start_dt = datetime.combine(start_date_obj, datetime.min.time())
        end_dt = datetime.combine(today, datetime.max.time())
        return timezone.make_aware(start_dt), timezone.make_aware(end_dt)

    elif preset == "all":
        # All time (no date filter)
        return None, None

    # Handle custom date range
    if start_date or end_date:
        try:
            if start_date:
                start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
                start_dt = datetime.combine(start_date_obj, datetime.min.time())
                start_dt = timezone.make_aware(start_dt)
            else:
                start_dt = None

            if end_date:
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                end_dt = datetime.combine(end_date_obj, datetime.max.time())
                end_dt = timezone.make_aware(end_dt)
            else:
                end_dt = timezone.make_aware(datetime.combine(today, datetime.max.time()))

            return start_dt, end_dt
        except (ValueError, TypeError):
            # Invalid date format - fall back to today
            start_dt = datetime.combine(today, datetime.min.time())
            end_dt = datetime.combine(today, datetime.max.time())
            return timezone.make_aware(start_dt), timezone.make_aware(end_dt)

    # Default: today
    start_dt = datetime.combine(today, datetime.min.time())
    end_dt = datetime.combine(today, datetime.max.time())
    return timezone.make_aware(start_dt), timezone.make_aware(end_dt)


def get_date_range_label(
    preset: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    Get human-readable label for date range.

    Args:
        preset: One of "today", "7d", "mtd", "all", or None
        start_date: Custom start date (YYYY-MM-DD format)
        end_date: Custom end date (YYYY-MM-DD format)

    Returns:
        Human-readable label (e.g., "Today", "Last 7 days", "Jan 1 - Jan 31")
    """
    if preset == "today":
        return "Today"
    elif preset == "7d":
        return "Last 7 days"
    elif preset == "mtd":
        return "Month to Date"
    elif preset == "all":
        return "All Time"
    elif start_date or end_date:
        try:
            start_obj = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
            end_obj = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

            if start_obj and end_obj:
                return f"{start_obj.strftime('%b %d')} - {end_obj.strftime('%b %d, %Y')}"
            elif start_obj:
                return f"From {start_obj.strftime('%b %d, %Y')}"
            elif end_obj:
                return f"Until {end_obj.strftime('%b %d, %Y')}"
        except (ValueError, TypeError):
            pass

    return "Today"


def get_preset_options() -> list[dict]:
    """
    Get list of preset date range options for UI.

    Returns:
        List of dicts with 'value', 'label', and 'icon' keys
    """
    return [
        {"value": "today", "label": "Today", "icon": "bi-calendar-day"},
        {"value": "7d", "label": "Last 7 days", "icon": "bi-calendar-week"},
        {"value": "mtd", "label": "Month to Date", "icon": "bi-calendar-month"},
        {"value": "all", "label": "All Time", "icon": "bi-infinity"},
    ]
