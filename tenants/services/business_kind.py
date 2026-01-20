# tenants/services/business_kind.py
"""
Business kind normalization service.

Ensures business_kind values are always canonical codes, not display labels.
Provides a single source of truth for business kind validation and normalization.

SSOT: This is the CANONICAL source for business kind mappings.
All signup forms, views, and routing should use this module.
"""
from __future__ import annotations

from typing import Optional


# ============================================================================
# SSOT: Canonical Business Kinds Registry
# ============================================================================
# This is the SINGLE SOURCE OF TRUTH for all supported business verticals.
# Add new verticals here and they will propagate to:
# - Signup forms (via BusinessKind.choices)
# - Validation (validate_business_kind)
# - Display names (get_display_name)
# - Normalization (normalize_business_kind)

CANONICAL_BUSINESS_KINDS = {
    # Core Retail Verticals
    "phones": {
        "display_name": "Phones & Electronics",
        "icon": "📱",
        "description": "Mobile phones, electronics, accessories",
        "dashboard_route": "inventory_verticals:phones_dashboard",
    },
    "liquor": {
        "display_name": "Liquor / Bar",
        "icon": "🍺",
        "description": "Bars, bottle stores, alcohol retail",
        "dashboard_route": "inventory_verticals:liquor_dashboard",
    },
    "grocery": {
        "display_name": "Grocery / General",
        "icon": "🛒",
        "description": "Supermarkets, grocery stores, general retail",
        "dashboard_route": "groceries:dashboard",
    },
    "pharmacy": {
        "display_name": "Cosmetics & Pharmacy",
        "icon": "💊",
        "description": "Pharmacies, cosmetics, health products",
        "dashboard_route": "inventory_verticals:pharmacy_dashboard",
    },
    "clothing": {
        "display_name": "Clothing",
        "icon": "👕",
        "description": "Fashion, apparel, clothing retail",
        "dashboard_route": "inventory_verticals:clothing_dashboard",
    },
    "gym": {
        "display_name": "Gym / Fitness",
        "icon": "🏋️",
        "description": "Gyms, fitness centers, memberships",
        "dashboard_route": "inventory_verticals:gym_dashboard",
    },
    "hardware": {
        "display_name": "Hardware & General Dealers",
        "icon": "🔧",
        "description": "Hardware stores, general dealers",
        "dashboard_route": "inventory:inventory_dashboard",
    },
    "cement": {
        "display_name": "Cement / Building Materials",
        "icon": "🧱",
        "description": "Cement, building materials, construction supplies",
        "dashboard_route": "verticals:cement_dashboard",
    },
    # NEW VERTICALS (fix/cypress-pharmacy + feat/vertical-farm-welding)
    "farm": {
        "display_name": "Farm Manager",
        "icon": "🌾",
        "description": "Farm profitability tracking, crop and livestock management",
        "dashboard_route": "verticals:farm_dashboard",  # Farm has its own dashboard
    },
    "welding": {
        "display_name": "Welding Workshop",
        "icon": "⚡",
        "description": "Welding job estimation, invoicing, workshop management",
        "dashboard_route": "verticals:welding_dashboard",  # Welding has its own dashboard
    },
    "car_hire": {
        "display_name": "Car Hire Service",
        "icon": "🚗",
        "description": "Vehicle rental, fleet management, trip bookings",
        "dashboard_route": "verticals:car_hire_dashboard",  # Car Hire has its own dashboard
    },
}


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
        'hardware'
        >>> normalize_business_kind("Farm Manager")
        'farm'
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
        # Hardware & General Dealers
        "hardware": "hardware",
        "hardware & general dealers": "hardware",
        "hardware and general dealers": "hardware",
        "hardware / general dealers": "hardware",
        "general dealers": "hardware",
        "general dealer": "hardware",
        "hardware store": "hardware",
        # Cement / Building Materials
        "cement": "cement",
        "cement / building materials": "cement",
        "cement / hardware": "cement",  # Legacy mapping (before hardware split)
        "cement store": "cement",
        "building materials": "cement",
        "construction": "cement",
        # Farm Manager (NEW)
        "farm": "farm",
        "farm manager": "farm",
        "farming": "farm",
        "agriculture": "farm",
        "agribusiness": "farm",
        "crop": "farm",
        "livestock": "farm",
        # Welding Workshop (NEW)
        "welding": "welding",
        "welding workshop": "welding",
        "welder": "welding",
        "welding shop": "welding",
        "metal work": "welding",
        "metalwork": "welding",
        "fabrication": "welding",
        # Car Hire Service (NEW)
        "car_hire": "car_hire",
        "car hire": "car_hire",
        "car hire service": "car_hire",
        "car rental": "car_hire",
        "vehicle hire": "car_hire",
        "vehicle rental": "car_hire",
        "fleet": "car_hire",
        "fleet management": "car_hire",
        "taxi": "car_hire",
        "transport": "car_hire",
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

    # Use the SSOT registry for valid kinds
    return normalized in CANONICAL_BUSINESS_KINDS


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

    code = str(canonical_code).lower()
    if code in CANONICAL_BUSINESS_KINDS:
        return CANONICAL_BUSINESS_KINDS[code]["display_name"]
    
    # Fallback for unknown codes
    return canonical_code.replace("_", " ").title()


def get_business_kind_info(canonical_code: str | None) -> dict:
    """
    Get full info for a business kind (icon, description, dashboard route).

    Args:
        canonical_code: Canonical business kind code

    Returns:
        Dict with display_name, icon, description, dashboard_route
    """
    if not canonical_code:
        return {
            "display_name": "Unknown",
            "icon": "📦",
            "description": "Unknown business type",
            "dashboard_route": "inventory:inventory_dashboard",
        }

    code = str(canonical_code).lower()
    if code in CANONICAL_BUSINESS_KINDS:
        return CANONICAL_BUSINESS_KINDS[code].copy()
    
    return {
        "display_name": canonical_code.replace("_", " ").title(),
        "icon": "📦",
        "description": f"{canonical_code} business",
        "dashboard_route": "inventory:inventory_dashboard",
    }


def get_all_business_kinds() -> list[tuple[str, str]]:
    """
    Get all business kinds as choices for forms.
    
    Returns:
        List of (code, display_name) tuples suitable for Django form choices
    """
    return [(code, info["display_name"]) for code, info in CANONICAL_BUSINESS_KINDS.items()]


__all__ = [
    "normalize_business_kind",
    "validate_business_kind",
    "get_display_name",
    "get_business_kind_info",
    "get_all_business_kinds",
    "CANONICAL_BUSINESS_KINDS",
]
