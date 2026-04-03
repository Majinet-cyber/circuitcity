# staticpages/story_metrics.py
"""
Story Metrics Resolver — vertical-aware live proof data for landing page stories.

Architecture
------------
Each story maps to a vertical key (e.g. "gym", "pharmacy").  A resolver function
is registered for every vertical key.  The resolver queries live DB data and
returns a list of KPI dicts.  All resolvers degrade gracefully — they never raise
and always return a valid (possibly fallback) list.

Adding a new vertical story:
    1. Write a `_resolve_<vertical>()` function.
    2. Register it in STORY_RESOLVERS at the bottom of this file.
    3. Add a matching entry in STORY_META if you want labels/accents.

Data sourcing strategy
----------------------
We use AGGREGATE data across all active businesses of a given vertical.
This gives honest, always-live numbers without tying a story to a single
named business (which creates brittleness if that business churns).

Optional override: set STORY_FEATURED_BUSINESS_IDS in Django settings to
pin specific businesses:
    STORY_FEATURED_BUSINESS_IDS = {
        'gym': 42,           # Use only this gym's data
        'pharmacy': None,    # Aggregate all pharmacies
    }
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
MetricList = List[Dict[str, Any]]
"""
Each metric dict has:
    label: str          — short KPI label e.g. "Members tracked"
    value: str|int      — formatted value e.g. 128 or "MWK 4.2M"
    sublabel: str       — optional context e.g. "this month"
    status: str         — optional "positive" | "warning" | "neutral"
"""


# ---------------------------------------------------------------------------
# Story metadata (accent colours, display names)
# ---------------------------------------------------------------------------
STORY_META: Dict[str, Dict[str, str]] = {
    "gym": {
        "label": "Fitness & Gym",
        "accent": "#8b5cf6",          # purple
        "accent_light": "#ede9fe",
        "icon": "🏋️",
    },
    "pharmacy": {
        "label": "Pharmacy & Retail",
        "accent": "#10b981",          # green-teal
        "accent_light": "#d1fae5",
        "icon": "💊",
    },
}


# ---------------------------------------------------------------------------
# Currency formatter
# ---------------------------------------------------------------------------
def _fmt_mwk(value) -> str:
    """Format a Decimal/int as a human-readable MWK string."""
    try:
        v = float(value)
        if v >= 1_000_000:
            return f"MWK {v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"MWK {v / 1_000:.0f}K"
        return f"MWK {v:,.0f}"
    except (TypeError, ValueError):
        return "MWK —"


# ---------------------------------------------------------------------------
# Optional: get the pinned "featured" business id from settings
# ---------------------------------------------------------------------------
def _featured_biz_id(vertical: str) -> Optional[int]:
    from django.conf import settings

    mapping = getattr(settings, "STORY_FEATURED_BUSINESS_IDS", {})
    return mapping.get(vertical)


# ---------------------------------------------------------------------------
# Gym resolver
# ---------------------------------------------------------------------------
def _resolve_gym() -> MetricList:
    """Return live gym KPIs aggregated across all gym businesses (or pinned one)."""
    try:
        from inventory.models_verticals import GymMember, GymPayment
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        from django.utils import timezone
        from django.db.models import Q

        today = timezone.localdate()

        # Base queryset — all gym businesses (or pinned one)
        biz_qs = Business.objects.filter(business_kind=BusinessKind.GYM)
        featured_id = _featured_biz_id("gym")
        if featured_id:
            biz_qs = biz_qs.filter(pk=featured_id)

        # Total active members
        total_members = GymMember.objects.filter(
            business__in=biz_qs,
            is_active=True,
            is_archived=False,
        ).count()

        if total_members == 0:
            # No data — return honest fallback
            return _fallback_gym()

        # Active (paid, period covers today)
        active_members = (
            GymMember.objects.filter(
                business__in=biz_qs,
                is_active=True,
                is_archived=False,
                payments__start_date__lte=today,
                payments__end_date__gte=today,
                payments__is_active=True,
            )
            .distinct()
            .count()
        )
        in_arrears = max(0, total_members - active_members)

        return [
            {
                "label": "Members tracked",
                "value": total_members,
                "sublabel": "across all gyms",
                "status": "neutral",
            },
            {
                "label": "Paid & active",
                "value": active_members,
                "sublabel": "valid membership today",
                "status": "positive",
            },
            {
                "label": "In arrears",
                "value": in_arrears,
                "sublabel": "overdue or pending",
                "status": "warning" if in_arrears > 0 else "neutral",
            },
        ]

    except Exception as exc:
        logger.warning("story_metrics: gym resolver error — %s", exc)
        return _fallback_gym()


def _fallback_gym() -> MetricList:
    return [
        {"label": "Members tracked", "value": "—", "sublabel": "live data", "status": "neutral"},
        {"label": "Paid & active", "value": "—", "sublabel": "valid membership today", "status": "positive"},
        {"label": "In arrears", "value": "—", "sublabel": "overdue or pending", "status": "warning"},
    ]


# ---------------------------------------------------------------------------
# Pharmacy resolver
# ---------------------------------------------------------------------------
def _resolve_pharmacy() -> MetricList:
    """Return live pharmacy KPIs aggregated across all pharmacy businesses."""
    try:
        from inventory.models_pharmacy import PharmacyBatch, PharmacySale
        from tenants.models import Business
        from inventory.business_kinds import BusinessKind
        from django.db.models import Sum
        from decimal import Decimal

        # Base queryset
        biz_qs = Business.objects.filter(business_kind=BusinessKind.PHARMACY)
        featured_id = _featured_biz_id("pharmacy")
        if featured_id:
            biz_qs = biz_qs.filter(pk=featured_id)

        sales_count = PharmacySale.objects.filter(
            business__in=biz_qs,
            is_deleted=False,
            is_reversed=False,
        ).count()

        if sales_count == 0:
            return _fallback_pharmacy()

        # Total stock value (selling price × quantity across active batches)
        stock_agg = PharmacyBatch.objects.filter(
            business__in=biz_qs,
            is_archived=False,
        ).aggregate(
            total_value=Sum(
                # selling_price * quantity per batch
                # Use F-expression workaround — compute in Python for compatibility
                __import__("django.db.models", fromlist=["F"]).F("quantity")
            )
        )
        # Compute stock value properly: iterate batches
        batches = PharmacyBatch.objects.filter(
            business__in=biz_qs,
            is_archived=False,
        ).only("quantity", "selling_price")
        stock_value = sum(
            (b.quantity * (b.selling_price or Decimal("0"))) for b in batches
        )

        # Total revenue from all non-deleted sales
        revenue_agg = PharmacySale.objects.filter(
            business__in=biz_qs,
            is_deleted=False,
            is_reversed=False,
        ).aggregate(total=Sum("total_amount"))
        revenue = revenue_agg.get("total") or Decimal("0")

        return [
            {
                "label": "Sales recorded",
                "value": f"{sales_count:,}",
                "sublabel": "all time",
                "status": "positive",
            },
            {
                "label": "Stock value",
                "value": _fmt_mwk(stock_value),
                "sublabel": "current inventory",
                "status": "neutral",
            },
            {
                "label": "Revenue tracked",
                "value": _fmt_mwk(revenue),
                "sublabel": "total sales",
                "status": "positive",
            },
        ]

    except Exception as exc:
        logger.warning("story_metrics: pharmacy resolver error — %s", exc)
        return _fallback_pharmacy()


def _fallback_pharmacy() -> MetricList:
    return [
        {"label": "Sales recorded", "value": "—", "sublabel": "all time", "status": "positive"},
        {"label": "Stock value", "value": "—", "sublabel": "current inventory", "status": "neutral"},
        {"label": "Revenue tracked", "value": "—", "sublabel": "total sales", "status": "positive"},
    ]


# ---------------------------------------------------------------------------
# Registry — maps vertical key → resolver callable
# ---------------------------------------------------------------------------
STORY_RESOLVERS = {
    "gym": _resolve_gym,
    "pharmacy": _resolve_pharmacy,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_story_metrics(vertical_key: str) -> MetricList:
    """
    Return a list of KPI dicts for the given vertical key.

    Always returns a valid list (never raises).
    Falls back to empty placeholder metrics if the vertical is unknown.
    """
    resolver = STORY_RESOLVERS.get(vertical_key)
    if resolver is None:
        logger.debug("story_metrics: no resolver for vertical '%s'", vertical_key)
        return []
    return resolver()


def get_all_story_metrics() -> Dict[str, Any]:
    """
    Return metrics for every registered vertical, plus story metadata.

    Used by the landing page view to build a single JSON-serialisable context
    value that the JS carousel reads to switch metric panels on story change.

    Returns:
        {
            "gym": {
                "meta": {label, accent, accent_light, icon},
                "metrics": [{label, value, sublabel, status}, ...],
            },
            "pharmacy": { ... },
        }
    """
    result: Dict[str, Any] = {}
    for vertical_key, resolver in STORY_RESOLVERS.items():
        result[vertical_key] = {
            "meta": STORY_META.get(vertical_key, {}),
            "metrics": resolver(),
        }
    return result
