# inventory/catalog/construction_materials.py
"""
Construction Materials SSOT Catalog (Cement Vertical)
======================================================

Single Source of Truth for ALL cement/construction materials product definitions.
This module is the ONLY place where product categories, brands, sizes, and variants
are defined. All pages (catalog, stock-in, stock list, seeding) MUST use this.

Malawi-specific configuration:
- Paint sizes: 1L, 5L, 20L (NO 4L - legacy URLs handled separately)
- Cement brands: No duplicates (clean canonical list)
- Ready for future expansion (iron sheets, angle iron, etc.)
"""
from __future__ import annotations

from typing import Dict, List, Optional
from urllib.parse import urlencode


# ============================================================
# CATEGORIES
# ============================================================
CONSTRUCTION_CATEGORIES = [
    {
        "slug": "construction-materials",
        "name": "Construction Materials",
        "icon": "🏗️",
        "description": "Cement, Paint, Iron Sheets, and building materials",
    },
]


# ============================================================
# CEMENT BRANDS (Canonical List - NO DUPLICATES)
# ============================================================
CEMENT_BRANDS = [
    {"key": "dangote", "name": "Dangote", "icon": "🏭", "aliases": ["dangote"]},
    {"key": "akshar", "name": "Akshar", "icon": "🏗️", "aliases": ["akshar", "aksher"]},  # Normalized from "Aksher"
    {"key": "duracrete", "name": "Duracrete", "icon": "🏗️", "aliases": ["duracrete"]},
    {"key": "khoma", "name": "Khoma", "icon": "🏗️", "aliases": ["khoma"]},
    {"key": "lime", "name": "Lime", "icon": "🧱", "aliases": ["lime"]},
    {"key": "njati", "name": "Njati", "icon": "🏗️", "aliases": ["njati"]},
    {"key": "njati_extra", "name": "Njati Extra", "icon": "🏗️", "aliases": ["njati extra", "njatiextra"]},  # Distinct from "Njati"
    {"key": "nkope", "name": "Nkope", "icon": "🏗️", "aliases": ["nkope"]},
    {"key": "nthanthwe", "name": "Nthanthwe", "icon": "🏗️", "aliases": ["nthanthwe"]},
]


# ============================================================
# PAINT BRANDS & SIZES (Malawi-specific)
# ============================================================
PAINT_BRANDS = [
    {"key": "rainbow", "name": "Rainbow", "icon": "🌈"},
    {"key": "crown", "name": "Crown", "icon": "👑"},
    {"key": "plascon", "name": "Plascon", "icon": "🎨"},
    {"key": "dulux", "name": "Dulux", "icon": "🎨"},
]

# CRITICAL: Malawi paint sizes are 1L, 5L, 20L (NOT 4L)
PAINT_SIZES = ["1L", "5L", "20L"]

PAINT_FINISHES = ["Emulsion", "Gloss", "Matt"]

PAINT_COLORS = [
    "White",
    "Black",
    "Red",
    "Blue",
    "Green",
    "Yellow",
    "Orange",
    "Brown",
    "Grey",
    "Other",
]


# ============================================================
# IRON SHEETS (Future expansion ready)
# ============================================================
IRON_SHEET_LENGTHS = ["2.4m", "2.7m", "3.0m", "3.6m"]
IRON_SHEET_GAUGES = ["26", "28", "30", "32"]
IRON_SHEET_COLORS = ["Galvanized", "Green", "Red", "Blue", "Brown"]


# ============================================================
# ANGLE IRON (Future expansion ready)
# ============================================================
ANGLE_IRON_DIMENSIONS = ["25x25mm", "40x40mm", "50x50mm", "75x75mm"]


# ============================================================
# PRODUCT DEFINITIONS (SSOT)
# ============================================================
CONSTRUCTION_PRODUCTS = [
    # ========== CEMENT ==========
    {
        "slug": "cement",
        "category": "construction-materials",
        "base_name": "Cement",
        "icon": "🏗️",
        "default_unit": "bag",
        "brands": CEMENT_BRANDS,
        "sizes": [{"key": "50kg", "label": "BAG (50KG)", "pack_size": 50}],
        "variants": None,  # Cement only has brand + size
        "keywords": ["cement", "dangote", "akshar", "portland", "building"],
    },
    # ========== PAINT ==========
    {
        "slug": "paint",
        "category": "construction-materials",
        "base_name": "Paint",
        "icon": "🎨",
        "default_unit": "tin",
        "brands": PAINT_BRANDS,
        "sizes": [{"key": size, "label": size, "pack_size": None} for size in PAINT_SIZES],
        "variants": {
            "finishes": PAINT_FINISHES,
            "colors": PAINT_COLORS,
        },
        "keywords": ["paint", "rainbow", "crown", "plascon", "emulsion", "gloss"],
    },
    # ========== IRON SHEETS ==========
    {
        "slug": "iron-sheets",
        "category": "construction-materials",
        "base_name": "Iron Sheets",
        "icon": "📐",
        "default_unit": "sheet",
        "brands": None,  # Generic product
        "sizes": [{"key": length, "label": length, "pack_size": None} for length in IRON_SHEET_LENGTHS],
        "variants": {
            "gauges": IRON_SHEET_GAUGES,
            "colors": IRON_SHEET_COLORS,
        },
        "keywords": ["iron sheets", "roofing", "corrugated", "galvanized", "gi sheets"],
    },
    # ========== ANGLE IRON ==========
    {
        "slug": "angle-iron",
        "category": "construction-materials",
        "base_name": "Angle Iron",
        "icon": "📏",
        "default_unit": "piece",
        "brands": None,
        "sizes": [{"key": "6m", "label": "6m", "pack_size": None}],
        "variants": {
            "dimensions": ANGLE_IRON_DIMENSIONS,
        },
        "keywords": ["angle iron", "steel", "angle", "metal", "framework"],
    },
]


# ============================================================
# LEGACY SIZE HANDLING (4L → 5L)
# ============================================================
LEGACY_PAINT_SIZE_MAP = {
    "4L": "5L",  # Old URLs with 4L redirect to 5L
    "4l": "5L",
}


def normalize_paint_size(size: str) -> str:
    """
    Normalize paint size, handling legacy 4L → 5L conversion.
    
    Args:
        size: Paint size string (e.g., "4L", "5L", "20L")
    
    Returns:
        Normalized size (e.g., "5L")
    """
    if not size:
        return PAINT_SIZES[0]  # Default to first size (1L)
    
    # Check legacy mapping
    if size in LEGACY_PAINT_SIZE_MAP:
        return LEGACY_PAINT_SIZE_MAP[size]
    
    # Return as-is if valid
    if size in PAINT_SIZES:
        return size
    
    # Default to 5L if unrecognized
    return "5L"


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def get_categories() -> List[Dict]:
    """Get all construction material categories"""
    return CONSTRUCTION_CATEGORIES


def get_all_products() -> List[Dict]:
    """Get all construction products"""
    return CONSTRUCTION_PRODUCTS


def get_product_by_slug(slug: str) -> Optional[Dict]:
    """Get a single product by slug"""
    for product in CONSTRUCTION_PRODUCTS:
        if product["slug"] == slug:
            return product
    return None


def get_cement_brands() -> List[Dict]:
    """Get canonical cement brand list (for UI display)"""
    return CEMENT_BRANDS


def get_paint_brands() -> List[Dict]:
    """Get paint brand list"""
    return PAINT_BRANDS


def get_paint_sizes() -> List[str]:
    """Get valid paint sizes (1L, 5L, 20L)"""
    return PAINT_SIZES


def get_paint_finishes() -> List[str]:
    """Get paint finishes"""
    return PAINT_FINISHES


def get_paint_colors() -> List[str]:
    """Get paint colors"""
    return PAINT_COLORS


def normalize_brand(brand_name: str, product_slug: str = "cement") -> str:
    """
    Normalize a brand name to its canonical form, handling aliases.
    
    Args:
        brand_name: Brand name or alias (e.g., "aksher", "Akshar")
        product_slug: Product type (e.g., "cement", "paint")
    
    Returns:
        Canonical brand name (e.g., "Akshar") or original name if not found
    
    Examples:
        >>> normalize_brand("aksher", "cement")
        "Akshar"
        >>> normalize_brand("AKSHAR", "cement")
        "Akshar"
    """
    name_lower = brand_name.lower().strip()
    
    # Get brands for this product
    product = get_product_by_slug(product_slug)
    if not product or not product.get("brands"):
        return brand_name
    
    brands = product["brands"]
    
    for brand_spec in brands:
        # Check main name
        if name_lower == brand_spec["name"].lower():
            return brand_spec["name"]
        # Check key
        if name_lower == brand_spec["key"].lower():
            return brand_spec["name"]
        # Check aliases
        if "aliases" in brand_spec:
            for alias in brand_spec["aliases"]:
                if name_lower == alias.lower():
                    return brand_spec["name"]
    
    # Return original if not found (custom brand)
    return brand_name


def is_valid_paint_size(size: str) -> bool:
    """Check if paint size is valid (handles legacy 4L as valid for redirect)"""
    return size in PAINT_SIZES or size in LEGACY_PAINT_SIZE_MAP


def build_product_name(product_slug: str, brand: str = None, size: str = None, **variants) -> str:
    """
    Build a standardized product name from components.
    
    Args:
        product_slug: Product slug (e.g., "cement", "paint")
        brand: Brand name (e.g., "Dangote", "Rainbow")
        size: Size (e.g., "50kg", "5L")
        **variants: Additional variants (finish, color, gauge, dimension, etc.)
    
    Returns:
        Standardized product name (e.g., "Dangote Cement BAG (50KG)")
    
    Examples:
        >>> build_product_name("cement", brand="Dangote", size="50kg")
        "Dangote Cement BAG (50KG)"
        
        >>> build_product_name("paint", brand="Rainbow", size="5L", finish="Emulsion", color="White")
        "Rainbow Paint 5L Emulsion White"
    """
    product = get_product_by_slug(product_slug)
    if not product:
        return f"Unknown Product ({product_slug})"
    
    parts = []
    
    # Brand
    if brand:
        parts.append(brand)
    
    # Base name
    parts.append(product["base_name"])
    
    # Size (with label if available)
    if size and product.get("sizes"):
        size_obj = next((s for s in product["sizes"] if s["key"] == size), None)
        if size_obj:
            parts.append(size_obj["label"])
        else:
            parts.append(size)
    elif size:
        parts.append(size)
    
    # Additional variants (finish, color, gauge, dimension)
    if "finish" in variants and variants["finish"]:
        parts.append(variants["finish"])
    if "color" in variants and variants["color"]:
        parts.append(variants["color"])
    if "gauge" in variants and variants["gauge"]:
        parts.append(f"Gauge {variants['gauge']}")
    if "dimension" in variants and variants["dimension"]:
        parts.append(variants["dimension"])
    
    return " ".join(parts)


def get_brand_by_key(product_slug: str, brand_key: str) -> Optional[Dict]:
    """
    Get brand dict by key for a given product.
    
    Args:
        product_slug: Product slug (e.g., "cement", "paint")
        brand_key: Brand key (e.g., "dangote", "rainbow")
    
    Returns:
        Brand dict with 'key', 'name', 'icon' or None
    """
    product = get_product_by_slug(product_slug)
    if not product or not product.get("brands"):
        return None
    
    brand_key_lower = brand_key.lower()
    for brand in product["brands"]:
        if brand["key"] == brand_key_lower:
            return brand
    
    return None


def search_products(query: str) -> List[Dict]:
    """
    Search construction products by name or keywords.
    
    Args:
        query: Search query string
    
    Returns:
        List of matching products
    """
    if not query:
        return CONSTRUCTION_PRODUCTS
    
    query_lower = query.lower().strip()
    results = []
    
    for product in CONSTRUCTION_PRODUCTS:
        # Check base name
        if query_lower in product["base_name"].lower():
            results.append(product)
            continue
        
        # Check keywords
        for keyword in product.get("keywords", []):
            if query_lower in keyword.lower():
                results.append(product)
                break
    
    return results


# ============================================================
# URL HELPERS
# ============================================================
def build_product_url(base_url: str, **params) -> str:
    """
    Build product URL with query parameters.
    
    Args:
        base_url: Base URL (e.g., "/cement/products/paint/")
        **params: Query parameters (brand, size, finish, color, etc.)
    
    Returns:
        Full URL with query string
    """
    if not params:
        return base_url
    
    # Normalize paint size if present
    if "size" in params and params.get("product") == "paint":
        params["size"] = normalize_paint_size(params["size"])
    
    query_string = urlencode({k: v for k, v in params.items() if v})
    return f"{base_url}?{query_string}" if query_string else base_url


__all__ = [
    "CONSTRUCTION_CATEGORIES",
    "CONSTRUCTION_PRODUCTS",
    "CEMENT_BRANDS",
    "PAINT_BRANDS",
    "PAINT_SIZES",
    "PAINT_FINISHES",
    "PAINT_COLORS",
    "LEGACY_PAINT_SIZE_MAP",
    "get_categories",
    "get_all_products",
    "get_product_by_slug",
    "get_cement_brands",
    "get_paint_brands",
    "get_paint_sizes",
    "get_paint_finishes",
    "get_paint_colors",
    "is_valid_paint_size",
    "normalize_paint_size",
    "normalize_brand",
    "build_product_name",
    "get_brand_by_key",
    "search_products",
    "build_product_url",
]

