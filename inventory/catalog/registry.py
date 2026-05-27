# inventory/catalog/registry.py
"""
Catalog Registry - SSOT for all Stock-In Categories
====================================================

This module serves as the Single Source of Truth for all product categories
available in the Stock-In wizard across all verticals.

Each category defines:
- key: Unique identifier (slug)
- label: Display name
- icon: Emoji/icon for UI
- description: Brief description
- handler: Which flow to use (route or handler reference)
- enabled: Whether this category is currently active

This registry enables the Stock-In wizard to dynamically show available
product categories without hardcoding them in templates.
"""
from __future__ import annotations

from typing import Dict, List, Optional


# ============================================================
# CATEGORY REGISTRY (SSOT)
# ============================================================
STOCK_IN_CATEGORIES = [
    {
        "key": "construction-materials",
        "label": "Construction Materials",
        "icon": "🏗️",
        "description": "Cement, Iron Sheets, Bricks & core building materials",
        "handler": "cement_flow",
        "enabled": True,
        "data_testid": "category-construction-materials",
        "bg_color": "#dbeafe",
        "accent": "#2563eb",
    },
    {
        "key": "paint-and-finishing",
        "label": "Paint & Finishing",
        "icon": "🎨",
        "description": "Paints, varnishes, primers, putty & finishing materials",
        "handler": "generic_form",
        "enabled": True,
        "data_testid": "category-paint",
        "bg_color": "#fce7f3",
        "accent": "#db2777",
    },
    {
        "key": "plumbing-supplies",
        "label": "Plumbing",
        "icon": "🔧",
        "description": "Pipes, fittings, taps, valves & plumbing accessories",
        "handler": "generic_form",
        "enabled": True,
        "data_testid": "category-plumbing",
        "bg_color": "#d1fae5",
        "accent": "#059669",
    },
    {
        "key": "electrical-supplies",
        "label": "Electrical",
        "icon": "⚡",
        "description": "Cables, switches, sockets, breakers & electrical fittings",
        "handler": "generic_form",
        "enabled": True,
        "data_testid": "category-electrical",
        "bg_color": "#fef3c7",
        "accent": "#d97706",
    },
    {
        "key": "tools-and-hardware",
        "label": "Tools & Hardware",
        "icon": "🛠️",
        "description": "Hand tools, power tools, drill bits, saws & workshop items",
        "handler": "generic_form",
        "enabled": True,
        "data_testid": "category-tools",
        "bg_color": "#e0e7ff",
        "accent": "#4338ca",
    },
    {
        "key": "roofing-materials",
        "label": "Roofing",
        "icon": "🏠",
        "description": "Roofing sheets, ridges, gutters, tiles & waterproofing",
        "handler": "generic_form",
        "enabled": True,
        "data_testid": "category-roofing",
        "bg_color": "#fee2e2",
        "accent": "#dc2626",
    },
    {
        "key": "fasteners-and-fixings",
        "label": "Fasteners & Fixings",
        "icon": "🔩",
        "description": "Bolts, nuts, screws, nails, anchors & fixings",
        "handler": "generic_form",
        "enabled": True,
        "data_testid": "category-fasteners",
        "bg_color": "#f0fdf4",
        "accent": "#16a34a",
    },
    {
        "key": "welding-materials",
        "label": "Welding Materials",
        "icon": "🔥",
        "description": "Welding rods, gas cylinders, safety equipment & consumables",
        "handler": "generic_form",
        "enabled": True,
        "data_testid": "category-welding-materials",
        "bg_color": "#fff7ed",
        "accent": "#ea580c",
    },
    {
        "key": "adhesives-and-sealants",
        "label": "Adhesives & Sealants",
        "icon": "🧴",
        "description": "Glues, silicones, epoxy, sealants & bonding agents",
        "handler": "generic_form",
        "enabled": True,
        "data_testid": "category-adhesives",
        "bg_color": "#f5f3ff",
        "accent": "#7c3aed",
    },
    {
        "key": "car-spares",
        "label": "Car Spares",
        "icon": "🚗",
        "description": "Automotive parts, oils, filters, batteries & accessories",
        "handler": "generic_form",
        "enabled": True,
        "data_testid": "category-car-spares",
        "bg_color": "#f1f5f9",
        "accent": "#475569",
    },
]


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def get_all_stock_in_categories() -> List[Dict]:
    """
    Get all enabled stock-in categories.
    
    Returns:
        List of category dictionaries with metadata
    """
    return [cat for cat in STOCK_IN_CATEGORIES if cat.get("enabled", True)]


def get_category_by_key(key: str) -> Optional[Dict]:
    """
    Get a single category by its key.
    
    Args:
        key: Category key (e.g., "construction-materials")
    
    Returns:
        Category dict or None if not found
    """
    for category in STOCK_IN_CATEGORIES:
        if category["key"] == key:
            return category
    return None


def is_category_enabled(key: str) -> bool:
    """
    Check if a category is enabled.
    
    Args:
        key: Category key
    
    Returns:
        True if enabled, False otherwise
    """
    category = get_category_by_key(key)
    return category.get("enabled", False) if category else False


def get_category_handler(key: str) -> Optional[str]:
    """
    Get the handler/flow type for a category.
    
    Args:
        key: Category key
    
    Returns:
        Handler string or None
    """
    category = get_category_by_key(key)
    return category.get("handler") if category else None


def add_category(category_dict: Dict) -> None:
    """
    Add a new category to the registry (for extensibility).
    
    Args:
        category_dict: Category definition with required keys
    
    Note:
        This is for runtime extensions. Prefer editing STOCK_IN_CATEGORIES directly.
    """
    required_keys = ["key", "label", "icon", "description", "handler"]
    if not all(k in category_dict for k in required_keys):
        raise ValueError(f"Category must have keys: {required_keys}")
    
    # Check for duplicate keys
    existing_keys = [cat["key"] for cat in STOCK_IN_CATEGORIES]
    if category_dict["key"] in existing_keys:
        raise ValueError(f"Category with key '{category_dict['key']}' already exists")
    
    # Set defaults
    category_dict.setdefault("enabled", True)
    category_dict.setdefault("data_testid", f"category-{category_dict['key']}")
    
    STOCK_IN_CATEGORIES.append(category_dict)


__all__ = [
    "STOCK_IN_CATEGORIES",
    "get_all_stock_in_categories",
    "get_category_by_key",
    "is_category_enabled",
    "get_category_handler",
    "add_category",
]

