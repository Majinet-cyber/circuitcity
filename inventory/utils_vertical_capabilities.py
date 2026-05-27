# inventory/utils_vertical_capabilities.py
"""
Vertical capability checks - single source of truth for feature availability per vertical.

This module defines which features are available for each business vertical.
Use these functions to guard routes, sidebar items, and UI components.
"""
from __future__ import annotations


# ============================================================================
# INVENTORY / SALES / STOCK VERTICALS
# ============================================================================
# These verticals deal with physical products that can be bought/sold/inventoried

INVENTORY_VERTICALS = frozenset(
    [
        "phones",
        "liquor",
        "pharmacy",
        "clothing",
        # NOT gym - gym is membership-based, not product-based
    ]
)


# ============================================================================
# MEMBERSHIP / SUBSCRIPTION VERTICALS
# ============================================================================
# These verticals deal with members/subscribers, not physical products

MEMBERSHIP_VERTICALS = frozenset(
    [
        "gym",
    ]
)


# ============================================================================
# FEATURE CAPABILITY CHECKS
# ============================================================================


def vertical_supports_fast_sell(vertical_slug: str) -> bool:
    """
    Check if a vertical supports Fast Sell feature.

    Fast Sell is ONLY enabled for pharmacy and clothing.
    Phones, liquor, and gym do NOT support fast sell.

    Args:
        vertical_slug: Business kind slug (e.g., "phones", "gym", "liquor")

    Returns:
        bool: True if vertical supports Fast Sell, False otherwise

    Examples:
        >>> vertical_supports_fast_sell("pharmacy")
        True
        >>> vertical_supports_fast_sell("clothing")
        True
        >>> vertical_supports_fast_sell("phones")
        False
        >>> vertical_supports_fast_sell("liquor")
        False
        >>> vertical_supports_fast_sell("gym")
        False
    """
    if not vertical_slug:
        return False

    vertical_slug = str(vertical_slug).strip().lower()
    # Fast Sell ONLY for pharmacy and clothing
    return vertical_slug in ("pharmacy", "clothing")


def vertical_supports_inventory(vertical_slug: str) -> bool:
    """
    Check if a vertical supports inventory/stock management.

    Args:
        vertical_slug: Business kind slug

    Returns:
        bool: True if vertical supports inventory features
    """
    if not vertical_slug:
        return False

    vertical_slug = str(vertical_slug).strip().lower()
    return vertical_slug in INVENTORY_VERTICALS


def vertical_supports_barcode_workflow(vertical_slug: str) -> bool:
    """
    Check if a vertical supports barcode scanning workflow.

    Only inventory verticals support barcodes.

    Args:
        vertical_slug: Business kind slug

    Returns:
        bool: True if vertical supports barcode workflow
    """
    return vertical_supports_inventory(vertical_slug)


def vertical_is_membership_based(vertical_slug: str) -> bool:
    """
    Check if a vertical is membership/subscription based.

    Args:
        vertical_slug: Business kind slug

    Returns:
        bool: True if vertical is membership-based
    """
    if not vertical_slug:
        return False

    vertical_slug = str(vertical_slug).strip().lower()
    return vertical_slug in MEMBERSHIP_VERTICALS


def get_vertical_capabilities(vertical_slug: str) -> dict:
    """
    Get all capabilities for a vertical as a dictionary.

    Useful for template context or debugging.

    Args:
        vertical_slug: Business kind slug

    Returns:
        dict: Dictionary of capability flags

    Example:
        >>> get_vertical_capabilities("gym")
        {
            'supports_fast_sell': False,
            'supports_inventory': False,
            'supports_barcode': False,
            'is_membership_based': True
        }
    """
    return {
        "supports_fast_sell": vertical_supports_fast_sell(vertical_slug),
        "supports_inventory": vertical_supports_inventory(vertical_slug),
        "supports_barcode": vertical_supports_barcode_workflow(vertical_slug),
        "is_membership_based": vertical_is_membership_based(vertical_slug),
    }


__all__ = [
    "INVENTORY_VERTICALS",
    "MEMBERSHIP_VERTICALS",
    "vertical_supports_fast_sell",
    "vertical_supports_inventory",
    "vertical_supports_barcode_workflow",
    "vertical_is_membership_based",
    "get_vertical_capabilities",
]
