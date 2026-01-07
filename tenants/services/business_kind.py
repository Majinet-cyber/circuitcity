# tenants/services/business_kind.py
"""
Business kind normalization service.

Ensures business_kind values are always canonical codes, not display labels.
Provides a single source of truth for business kind validation and normalization.
"""
from __future__ import annotations

from typing import Optional


def normalize_business_kind(value: str | None) -> str | None:
    """
    Normalize a business kind value to its canonical code.

    Handles common variants, display labels, and user input to ensure
    we always store canonical codes in the database.

    Args:
        value: Business kind value (could be canonical code, display label, or variant)

    Returns:
        Canonical business kind code or None if value is None/empty

    Examples:
        >>> normalize_business_kind("cement")
        'cement'
        >>> normalize_business_kind("Hardware & General Dealers")
        'cement'
        >>> normalize_business_kind("hardware and general dealers")
        'cement'
        >>> normalize_business_kind("Phones & Electronics")
        'phones'
        >>> normalize_business_kind("")
        None
    """
    if value is None:
        return None

    # Normalize to lowercase, stripped string
    normalized = str(value).strip().lower()

    if not normalized:
        return None

    # Mapping of all known variants to canonical codes
    # This includes:
    # - Canonical codes (pass-through)
    # - Display labels from BusinessKind choices
    # - Common user input variants
    # - Legacy names
    mapping = {
        # Phones & Electronics
        "phones": "phones",
        "phone": "phones",
        "phones & electronics": "phones",
        "electronics": "phones",
        "mobile": "phones",
        "mobiles": "phones",
        # Liquor / Bar
        "liquor": "liquor",
        "liquor / bar": "liquor",
        "bar": "liquor",
        "alcohol": "liquor",
        "pub": "liquor",
        "bottle store": "liquor",
        "bottle-store": "liquor",
        # Grocery / General
        "grocery": "grocery",
        "groceries": "grocery",
        "grocery / general": "grocery",
        "supermarket": "grocery",
        "retail": "grocery",
        "general": "grocery",
        # Pharmacy / Cosmetics
        "pharmacy": "pharmacy",
        "cosmetics & pharmacy": "pharmacy",
        "cosmetics": "pharmacy",
        "chemist": "pharmacy",
        "drugstore": "pharmacy",
        "medicine": "pharmacy",
        # Clothing
        "clothing": "clothing",
        "clothes": "clothing",
        "fashion": "clothing",
        "apparel": "clothing",
        # Gym / Fitness
        "gym": "gym",
        "gym / fitness": "gym",
        "fitness": "gym",
        "gym center": "gym",
        "fitness center": "gym",
        # Hardware & General Dealers (NEW: Separate from cement)
        "hardware": "hardware",
        "hardware & general dealers": "hardware",
        "hardware and general dealers": "hardware",
        "hardware / general dealers": "hardware",
        "general dealers": "hardware",
        "general dealer": "hardware",
        "hardware store": "hardware",
        # Cement / Building Materials (Legacy: Kept separate)
        "cement": "cement",
        "cement / building materials": "cement",
        "cement / hardware": "cement",  # Legacy mapping (before hardware split)
        "cement store": "cement",
        "building materials": "cement",
        "construction": "cement",
    }

    # Return canonical code if mapped, otherwise return normalized input
    # (allows future verticals to be added without breaking)
    return mapping.get(normalized, normalized)


def validate_business_kind(value: str | None) -> bool:
    """
    Check if a business kind value is valid (recognized).

    Args:
        value: Business kind value to validate

    Returns:
        True if value is a recognized business kind, False otherwise
    """
    if not value:
        return False

    normalized = normalize_business_kind(value)
    if not normalized:
        return False

    # List of valid canonical codes
    valid_kinds = [
        "phones",
        "liquor",
        "grocery",
        "pharmacy",
        "clothing",
        "gym",
        "hardware",  # NEW: Hardware & General Dealers
        "cement",  # Legacy: Cement / Building Materials
    ]

    return normalized in valid_kinds


def get_display_name(canonical_code: str | None) -> str:
    """
    Get the human-friendly display name for a business kind.

    Args:
        canonical_code: Canonical business kind code

    Returns:
        Display name for the business kind
    """
    if not canonical_code:
        return "Unknown"

    display_names = {
        "phones": "Phones & Electronics",
        "liquor": "Liquor / Bar",
        "grocery": "Grocery / General",
        "pharmacy": "Cosmetics & Pharmacy",
        "clothing": "Clothing",
        "gym": "Gym / Fitness",
        "hardware": "Hardware & General Dealers",  # NEW: Hardware vertical
        "cement": "Cement / Building Materials",  # Legacy: Cement vertical
    }

    return display_names.get(str(canonical_code).lower(), canonical_code.title())


__all__ = ["normalize_business_kind", "validate_business_kind", "get_display_name"]
