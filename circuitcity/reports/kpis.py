import calendar
from datetime import datetime, timedelta, date
from django.utils import timezone
from django.db.models import Sum


def _prev_month_same_day(d: date) -> date:
    """Return the same day in the previous month (clamped to last day)."""
    y, m = d.year, d.month - 1
    if m == 0:
        y, m = y - 1, 12
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def _sum_amount(qs, amount_field: str = "price") -> float:
    """Sum a numeric field (default 'price'). Returns 0.0 if no rows."""
    agg = qs.aggregate(total=Sum(amount_field))
    return float(agg["total"] or 0)


def _percent_change(curr: float, prev: float):
    """
    Return {'percent': x.x, 'direction': 'up'|'down'|'flat'} or None if prev==0.
    """
    if prev == 0:
        return None
    pct = round(((curr - prev) / prev) * 100, 1)
    return {
        "percent": pct,
        "direction": "up" if pct > 0 else ("down" if pct < 0 else "flat"),
    }


def _start_of_day(d: date, tz):
    """Timezone-aware start-of-day for a given date."""
    return datetime.combine(d, datetime.min.time(), tzinfo=tz)


def compute_sales_kpis(qs, dt_field: str = "sold_at", amount_field: str = "price"):
    """
    Compute Today / MTD / All-time totals + trends.

    Uses timezone-aware datetime boundaries (no __date lookups), so it works
    whether the model field is DateField or DateTimeField.

    Args:
        qs: pre-scoped queryset (e.g., all sales for admin; user's sales for agent)
        dt_field: name of the datetime/date field to filter by (default: 'sold_at')
        amount_field: numeric field to sum (default: 'price')
    """
    now = timezone.localtime()
    tz = now.tzinfo
    today = now.date()

    # --- Today vs Yesterday (using [sta]()


