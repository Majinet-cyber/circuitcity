# notifications/daily_summary/registry.py
"""
Maps a Business's ``business_kind`` to the appropriate DailySummaryProvider.

Retail kinds are all non-gym, non-car-hire verticals.
"""
from __future__ import annotations

from typing import Any

from inventory.business_kinds import BusinessKind
from notifications.daily_summary.base import DailySummaryProvider


# Lazy imports inside function to avoid circular imports at module load time.

_RETAIL_KINDS = {
    BusinessKind.PHONES,
    BusinessKind.GROCERY,
    BusinessKind.PHARMACY,
    BusinessKind.CLOTHING,
    BusinessKind.LIQUOR,
    BusinessKind.HARDWARE,
    BusinessKind.CEMENT,
    BusinessKind.WELDING,
    BusinessKind.FARM,
}


def get_provider(business: Any) -> DailySummaryProvider:
    """
    Return the correct DailySummaryProvider for ``business``.

    Falls back to RetailDailySummaryProvider for unknown or null verticals
    so that new verticals added later still get a useful email.
    """
    kind = getattr(business, "business_kind", None) or ""

    if kind == BusinessKind.GYM:
        from notifications.daily_summary.gym import GymDailySummaryProvider
        return GymDailySummaryProvider()

    if kind == BusinessKind.CAR_HIRE:
        from notifications.daily_summary.car_hire import CarHireDailySummaryProvider
        return CarHireDailySummaryProvider()

    # Default: all retail-like verticals + unknown/null kinds
    from notifications.daily_summary.retail import RetailDailySummaryProvider
    return RetailDailySummaryProvider()
