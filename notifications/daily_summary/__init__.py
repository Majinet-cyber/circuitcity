# notifications/daily_summary/__init__.py
"""
Vertical-aware Daily Summary email providers.

Usage:
    from notifications.daily_summary.registry import get_provider
    provider = get_provider(business)
    metrics = provider.get_metrics(business, report_date)
    html, text = provider.render_email(business, metrics, report_date)
"""
from notifications.daily_summary.registry import get_provider  # noqa: F401

__all__ = ["get_provider"]
