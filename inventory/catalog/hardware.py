# inventory/catalog/hardware.py
"""
Hardware & General Dealers Product Catalog
===========================================

Premium, stupid-simple hardware product catalog with:
- Category-based organization
- No duplicate base names
- Variation-based selection (brand → size → color flow)
- Search by product name + keywords

CATALOG CONTENT: Curated for Malawian hardware dealers based on local demand
"""
from __future__ import annotations

from typing import List, Optional, TypedDict


class ProductVariation(TypedDict):
    """Variation specification for a hardware product"""

    brands: List[str]
    sizes: List[str]
    colors: Optional[List[str]]
    finishes: Optional[List[str]]
    dimensions: Optional[List[str]]
    viscosity: Optional[List[str]]
    gauges: Optional[List[str]]


class CatalogProduct(TypedDict):
    """A hardware product in the catalog"""

    slug: str
    category: str
    base_name: str
    keywords: List[str]
    default_unit: str
    variation_schema: ProductVariation


# ============================================================
# CATEGORY DEFINITIONS
# ============================================================
HARDWARE_CATEGORIES = [
    {"slug": "construction", "name": "Construction Materials", "icon": "bi-bricks"},
    {"slug": "car-spares", "name": "Car Spares", "icon": "bi-car-front"},
    {"slug": "welding", "name": "Welding Materials", "icon": "bi-fire"},
    {"slug": "safety", "name": "Safety Equipment", "icon": "bi-shield-check"},
    {"slug": "carpentry", "name": "Carpentry Equipment", "icon": "bi-hammer"},
]


# ============================================================
# HARDWARE PRODUCT CATALOG (Minimum Viable Set)
# ============================================================
HARDWARE_CATALOG: List[CatalogProduct] = [
    # ========== CONSTRUCTION MATERIALS ==========
    {
        "slug": "cement",
        "category": "construction",
        "base_name": "Cement",
        "keywords": ["dangote", "lafarge", "portland", "building", "concrete"],
        "default_unit": "bag",
        "variation_schema": {
            "brands": ["Dangote", "Lafarge", "Other"],
            "sizes": ["25kg", "50kg"],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "paint",
        "category": "construction",
        "base_name": "Paint",
        "keywords": ["rainbow", "crown", "plascon", "emulsion", "gloss", "coating"],
        "default_unit": "tin",
        "variation_schema": {
            "brands": ["Rainbow", "Crown", "Plascon", "Other"],
            "sizes": ["1L", "4L", "20L"],
            "colors": ["White", "Red", "Blue", "Green", "Yellow", "Black", "Other"],
            "finishes": ["Emulsion", "Gloss", "Matt"],
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "iron-sheets",
        "category": "construction",
        "base_name": "Iron Sheets",
        "keywords": ["roofing", "corrugated", "galvanized", "gi", "zinc"],
        "default_unit": "sheet",
        "variation_schema": {
            "brands": ["Standard", "Premium", "Other"],
            "sizes": ["2.4m", "2.7m", "3.0m", "3.6m"],
            "colors": ["Galvanized", "Green", "Red", "Blue", "Brown"],
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": ["26", "28", "30", "32"],
        },
    },
    {
        "slug": "angle-iron",
        "category": "construction",
        "base_name": "Angle Iron",
        "keywords": ["steel", "angle", "metal", "construction", "framework"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": None,
            "sizes": ["6m"],
            "colors": None,
            "finishes": None,
            "dimensions": ["25x25mm", "40x40mm", "50x50mm", "75x75mm"],
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "square-tube",
        "category": "construction",
        "base_name": "Square Tube",
        "keywords": ["steel", "tube", "square", "hollow", "metal"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": None,
            "sizes": ["6m"],
            "colors": None,
            "finishes": None,
            "dimensions": ["20x20mm", "25x25mm", "40x40mm", "50x50mm"],
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "binding-wire",
        "category": "construction",
        "base_name": "Binding Wire",
        "keywords": ["wire", "binding", "tie", "construction"],
        "default_unit": "kg",
        "variation_schema": {
            "brands": None,
            "sizes": ["1kg", "5kg", "10kg"],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": ["16", "18", "20"],
        },
    },
    {
        "slug": "nails",
        "category": "construction",
        "base_name": "Nails",
        "keywords": ["nail", "fastener", "building", "carpentry"],
        "default_unit": "kg",
        "variation_schema": {
            "brands": None,
            "sizes": ['1"', '1.5"', '2"', '2.5"', '3"', '4"', '6"'],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "boards",
        "category": "construction",
        "base_name": "Boards",
        "keywords": ["plywood", "board", "timber", "wood", "panel"],
        "default_unit": "sheet",
        "variation_schema": {
            "brands": None,
            "sizes": ["6mm", "9mm", "12mm", "18mm"],
            "colors": ["White", "Brown", "Navy"],
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    # ========== CAR SPARES ==========
    {
        "slug": "engine-oil",
        "category": "car-spares",
        "base_name": "Engine Oil",
        "keywords": ["motor", "oil", "lubricant", "puma", "extreme", "total"],
        "default_unit": "litre",
        "variation_schema": {
            "brands": ["Puma", "Extreme", "Total", "Shell", "Castrol", "Other"],
            "sizes": ["1L", "4L", "5L", "20L"],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": ["10W-30", "10W-40", "15W-40", "20W-50"],
            "gauges": None,
        },
    },
    {
        "slug": "brake-pads",
        "category": "car-spares",
        "base_name": "Brake Pads",
        "keywords": ["brake", "pad", "disc", "automotive"],
        "default_unit": "set",
        "variation_schema": {
            "brands": ["Standard", "Premium", "OEM", "Other"],
            "sizes": None,
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "car-lights",
        "category": "car-spares",
        "base_name": "Car Lights & Bulbs",
        "keywords": ["headlight", "bulb", "lamp", "light", "indicator"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": ["Standard", "Premium", "LED", "Other"],
            "sizes": ["H1", "H4", "H7", "H11", "9005", "9006"],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "oil-filter",
        "category": "car-spares",
        "base_name": "Oil Filter",
        "keywords": ["filter", "oil", "engine", "automotive"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": ["Standard", "OEM", "Premium", "Other"],
            "sizes": None,
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "air-filter",
        "category": "car-spares",
        "base_name": "Air Filter",
        "keywords": ["filter", "air", "engine", "automotive"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": ["Standard", "OEM", "Premium", "Other"],
            "sizes": None,
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    # ========== WELDING MATERIALS ==========
    {
        "slug": "welding-rods",
        "category": "welding",
        "base_name": "Welding Rods",
        "keywords": ["electrode", "welding", "rod", "e6013", "stick"],
        "default_unit": "kg",
        "variation_schema": {
            "brands": None,
            "sizes": ["2.5mm", "3.2mm", "4.0mm", "5.0mm"],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "cutting-disc",
        "category": "welding",
        "base_name": "Cutting Disc",
        "keywords": ["disc", "cutting", "grinder", "metal"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": ["Standard", "Premium", "Other"],
            "sizes": ['4"', '5"', '7"', '9"', '12"'],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "grinding-disc",
        "category": "welding",
        "base_name": "Grinding Disc",
        "keywords": ["disc", "grinding", "grinder", "metal"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": ["Standard", "Premium", "Other"],
            "sizes": ['4"', '5"', '7"', '9"'],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "welding-gloves",
        "category": "welding",
        "base_name": "Welding Gloves",
        "keywords": ["gloves", "welding", "safety", "protective"],
        "default_unit": "pair",
        "variation_schema": {
            "brands": ["Standard", "Heavy Duty", "Other"],
            "sizes": None,
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    # ========== SAFETY EQUIPMENT ==========
    {
        "slug": "safety-helmet",
        "category": "safety",
        "base_name": "Safety Helmet",
        "keywords": ["helmet", "hard hat", "safety", "ppe", "construction"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": ["Standard", "Premium", "Other"],
            "sizes": None,
            "colors": ["Yellow", "White", "Red", "Blue", "Orange"],
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "reflector-jacket",
        "category": "safety",
        "base_name": "Reflector Jacket",
        "keywords": ["jacket", "vest", "reflective", "safety", "hi-vis"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": ["Standard", "Premium", "Other"],
            "sizes": ["S", "M", "L", "XL", "XXL"],
            "colors": ["Yellow", "Orange"],
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "safety-boots",
        "category": "safety",
        "base_name": "Safety Boots",
        "keywords": ["boots", "safety", "shoes", "steel toe", "ppe"],
        "default_unit": "pair",
        "variation_schema": {
            "brands": ["Standard", "Premium", "Other"],
            "sizes": ["39", "40", "41", "42", "43", "44", "45", "46"],
            "colors": ["Black", "Brown"],
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "safety-goggles",
        "category": "safety",
        "base_name": "Safety Goggles",
        "keywords": ["goggles", "glasses", "safety", "eye protection", "ppe"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": ["Standard", "Premium", "Other"],
            "sizes": None,
            "colors": ["Clear", "Tinted"],
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    # ========== CARPENTRY EQUIPMENT ==========
    {
        "slug": "hinges",
        "category": "carpentry",
        "base_name": "Hinges",
        "keywords": ["hinge", "door", "cabinet", "hardware"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": None,
            "sizes": ['2"', '3"', '4"', '6"'],
            "colors": ["Silver", "Bronze", "Black"],
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "locks",
        "category": "carpentry",
        "base_name": "Locks",
        "keywords": ["lock", "door", "security", "padlock", "deadbolt"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": ["Standard", "Heavy Duty", "Other"],
            "sizes": ["Small", "Medium", "Large"],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "handles",
        "category": "carpentry",
        "base_name": "Handles",
        "keywords": ["handle", "door", "cabinet", "knob", "pull"],
        "default_unit": "piece",
        "variation_schema": {
            "brands": None,
            "sizes": None,
            "colors": ["Silver", "Bronze", "Black", "Gold"],
            "finishes": ["Chrome", "Brushed", "Matt"],
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "sandpaper",
        "category": "carpentry",
        "base_name": "Sandpaper",
        "keywords": ["sandpaper", "abrasive", "sanding", "finishing"],
        "default_unit": "sheet",
        "variation_schema": {
            "brands": None,
            "sizes": ["40 Grit", "60 Grit", "80 Grit", "120 Grit", "180 Grit", "240 Grit"],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
    {
        "slug": "wood-glue",
        "category": "carpentry",
        "base_name": "Wood Glue",
        "keywords": ["glue", "adhesive", "wood", "pva", "bond"],
        "default_unit": "bottle",
        "variation_schema": {
            "brands": ["Standard", "Premium", "Other"],
            "sizes": ["125ml", "250ml", "500ml", "1L"],
            "colors": None,
            "finishes": None,
            "dimensions": None,
            "viscosity": None,
            "gauges": None,
        },
    },
]


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def get_catalog_products() -> List[CatalogProduct]:
    """Returns the complete hardware catalog"""
    return HARDWARE_CATALOG


def get_products_by_category(category_slug: str) -> List[CatalogProduct]:
    """Returns all products for a given category"""
    return [p for p in HARDWARE_CATALOG if p["category"] == category_slug]


def get_product_by_slug(slug: str) -> Optional[CatalogProduct]:
    """Returns a single product by slug"""
    for product in HARDWARE_CATALOG:
        if product["slug"] == slug:
            return product
    return None


def search_products(query: str) -> List[CatalogProduct]:
    """
    Search products by base name and keywords (case-insensitive).
    Returns products matching the query string.
    """
    query_lower = query.lower().strip()
    if not query_lower:
        return HARDWARE_CATALOG

    results = []
    for product in HARDWARE_CATALOG:
        # Check base name
        if query_lower in product["base_name"].lower():
            results.append(product)
            continue

        # Check keywords
        for keyword in product["keywords"]:
            if query_lower in keyword.lower():
                results.append(product)
                break

    return results


def get_popular_products(limit: int = 12) -> List[CatalogProduct]:
    """
    Returns top popular products for quick access.
    Currently returns first N products; can be enhanced with actual popularity metrics.
    """
    return HARDWARE_CATALOG[:limit]


__all__ = [
    "HARDWARE_CATEGORIES",
    "HARDWARE_CATALOG",
    "get_catalog_products",
    "get_products_by_category",
    "get_product_by_slug",
    "search_products",
    "get_popular_products",
]
