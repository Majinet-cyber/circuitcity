# inventory/verticals/groceries_seed.py
"""
Groceries Seed Catalog - Starter catalog of common Malawian grocery items
"""

# Categories
CATEGORIES = [
    {"key": "sugar", "name": "Sugar", "icon": "🍬"},
    {"key": "cooking_oil", "name": "Cooking Oil", "icon": "🛢️"},
    {"key": "water", "name": "Water", "icon": "💧"},
    {"key": "bread", "name": "Bread", "icon": "🍞"},
    {"key": "milk", "name": "Milk", "icon": "🥛"},
    {"key": "rice", "name": "Rice/Grains", "icon": "🌾"},
    {"key": "flour", "name": "Flour", "icon": "🌾"},
    {"key": "salt", "name": "Salt/Spices", "icon": "🧂"},
    {"key": "eggs", "name": "Eggs", "icon": "🥚"},
    {"key": "soft_drinks", "name": "Soft Drinks", "icon": "🥤"},
    {"key": "snacks", "name": "Snacks", "icon": "🍪"},
    {"key": "soap", "name": "Soap/Detergent", "icon": "🧼"},
    {"key": "other", "name": "Other", "icon": "📦"},
]

# Seed items with variants
SEED_ITEMS = [
    # Sugar
    {
        "category": "sugar",
        "name": "Sugar",
        "variants": [
            {"label": "Packet 1kg", "unit_type": "kg", "unit_value": 1.0, "sku_hint": "SUG-1KG"},
            {"label": "Packet 2kg", "unit_type": "kg", "unit_value": 2.0, "sku_hint": "SUG-2KG"},
            {"label": "Bale 25kg", "unit_type": "kg", "unit_value": 25.0, "sku_hint": "SUG-25KG"},
            {"label": "Bale 50kg", "unit_type": "kg", "unit_value": 50.0, "sku_hint": "SUG-50KG"},
        ],
    },
    # Cooking Oil
    {
        "category": "cooking_oil",
        "name": "Cooking Oil",
        "variants": [
            {"label": "0.5L", "unit_type": "litre", "unit_value": 0.5, "sku_hint": "OIL-0.5L"},
            {"label": "1L", "unit_type": "litre", "unit_value": 1.0, "sku_hint": "OIL-1L"},
            {"label": "2L", "unit_type": "litre", "unit_value": 2.0, "sku_hint": "OIL-2L"},
            {"label": "5L", "unit_type": "litre", "unit_value": 5.0, "sku_hint": "OIL-5L"},
            {"label": "20L", "unit_type": "litre", "unit_value": 20.0, "sku_hint": "OIL-20L"},
        ],
    },
    # Water
    {
        "category": "water",
        "name": "Water",
        "variants": [
            {"label": "0.5L", "unit_type": "litre", "unit_value": 0.5, "sku_hint": "WAT-0.5L"},
            {"label": "1L", "unit_type": "litre", "unit_value": 1.0, "sku_hint": "WAT-1L"},
            {"label": "1.5L", "unit_type": "litre", "unit_value": 1.5, "sku_hint": "WAT-1.5L"},
            {"label": "5L", "unit_type": "litre", "unit_value": 5.0, "sku_hint": "WAT-5L"},
        ],
    },
    # Bread
    {
        "category": "bread",
        "name": "Bread",
        "variants": [
            {"label": "Loaf", "unit_type": "pcs", "unit_value": 1.0, "sku_hint": "BRD-LOAF"},
            {"label": "Half loaf", "unit_type": "pcs", "unit_value": 1.0, "sku_hint": "BRD-HALF"},
        ],
    },
    # Milk
    {
        "category": "milk",
        "name": "Milk",
        "variants": [
            {"label": "Powder 500g", "unit_type": "kg", "unit_value": 0.5, "sku_hint": "MLK-POW-500G"},
            {"label": "Powder 1kg", "unit_type": "kg", "unit_value": 1.0, "sku_hint": "MLK-POW-1KG"},
            {"label": "UHT 150ml", "unit_type": "litre", "unit_value": 0.15, "sku_hint": "MLK-UHT-150ML"},
            {"label": "UHT 500ml", "unit_type": "litre", "unit_value": 0.5, "sku_hint": "MLK-UHT-500ML"},
            {"label": "UHT 1L", "unit_type": "litre", "unit_value": 1.0, "sku_hint": "MLK-UHT-1L"},
        ],
    },
    # Rice
    {
        "category": "rice",
        "name": "Rice",
        "variants": [
            {"label": "1kg", "unit_type": "kg", "unit_value": 1.0, "sku_hint": "RICE-1KG"},
            {"label": "2kg", "unit_type": "kg", "unit_value": 2.0, "sku_hint": "RICE-2KG"},
            {"label": "5kg", "unit_type": "kg", "unit_value": 5.0, "sku_hint": "RICE-5KG"},
            {"label": "25kg", "unit_type": "kg", "unit_value": 25.0, "sku_hint": "RICE-25KG"},
        ],
    },
    # Flour - Maize
    {
        "category": "flour",
        "name": "Maize Flour",
        "variants": [
            {"label": "1kg", "unit_type": "kg", "unit_value": 1.0, "sku_hint": "FLR-MAIZE-1KG"},
            {"label": "2kg", "unit_type": "kg", "unit_value": 2.0, "sku_hint": "FLR-MAIZE-2KG"},
            {"label": "5kg", "unit_type": "kg", "unit_value": 5.0, "sku_hint": "FLR-MAIZE-5KG"},
            {"label": "25kg", "unit_type": "kg", "unit_value": 25.0, "sku_hint": "FLR-MAIZE-25KG"},
        ],
    },
    # Flour - Wheat
    {
        "category": "flour",
        "name": "Wheat Flour",
        "variants": [
            {"label": "1kg", "unit_type": "kg", "unit_value": 1.0, "sku_hint": "FLR-WHEAT-1KG"},
            {"label": "2kg", "unit_type": "kg", "unit_value": 2.0, "sku_hint": "FLR-WHEAT-2KG"},
            {"label": "5kg", "unit_type": "kg", "unit_value": 5.0, "sku_hint": "FLR-WHEAT-5KG"},
            {"label": "25kg", "unit_type": "kg", "unit_value": 25.0, "sku_hint": "FLR-WHEAT-25KG"},
        ],
    },
    # Salt
    {
        "category": "salt",
        "name": "Salt",
        "variants": [
            {"label": "500g", "unit_type": "kg", "unit_value": 0.5, "sku_hint": "SALT-500G"},
            {"label": "1kg", "unit_type": "kg", "unit_value": 1.0, "sku_hint": "SALT-1KG"},
        ],
    },
    # Eggs
    {
        "category": "eggs",
        "name": "Eggs",
        "variants": [
            {"label": "Tray (30)", "unit_type": "tray", "unit_value": 30.0, "sku_hint": "EGG-TRAY-30"},
            {"label": "Half tray (15)", "unit_type": "tray", "unit_value": 15.0, "sku_hint": "EGG-HALF-15"},
            {"label": "Single egg", "unit_type": "pcs", "unit_value": 1.0, "sku_hint": "EGG-SINGLE"},
        ],
    },
    # Soft Drinks
    {
        "category": "soft_drinks",
        "name": "Coke",
        "variants": [
            {"label": "300ml", "unit_type": "litre", "unit_value": 0.3, "sku_hint": "COKE-300ML"},
            {"label": "500ml", "unit_type": "litre", "unit_value": 0.5, "sku_hint": "COKE-500ML"},
            {"label": "1L", "unit_type": "litre", "unit_value": 1.0, "sku_hint": "COKE-1L"},
            {"label": "2L", "unit_type": "litre", "unit_value": 2.0, "sku_hint": "COKE-2L"},
        ],
    },
    {
        "category": "soft_drinks",
        "name": "Fanta",
        "variants": [
            {"label": "300ml", "unit_type": "litre", "unit_value": 0.3, "sku_hint": "FANTA-300ML"},
            {"label": "500ml", "unit_type": "litre", "unit_value": 0.5, "sku_hint": "FANTA-500ML"},
            {"label": "1L", "unit_type": "litre", "unit_value": 1.0, "sku_hint": "FANTA-1L"},
        ],
    },
    {
        "category": "soft_drinks",
        "name": "Sprite",
        "variants": [
            {"label": "300ml", "unit_type": "litre", "unit_value": 0.3, "sku_hint": "SPRITE-300ML"},
            {"label": "500ml", "unit_type": "litre", "unit_value": 0.5, "sku_hint": "SPRITE-500ML"},
            {"label": "1L", "unit_type": "litre", "unit_value": 1.0, "sku_hint": "SPRITE-1L"},
        ],
    },
    # Snacks
    {
        "category": "snacks",
        "name": "Biscuits",
        "variants": [
            {"label": "Pack", "unit_type": "pcs", "unit_value": 1.0, "sku_hint": "BISC-PACK"},
        ],
    },
    # Soap
    {
        "category": "soap",
        "name": "Soap",
        "variants": [
            {"label": "Bar", "unit_type": "pcs", "unit_value": 1.0, "sku_hint": "SOAP-BAR"},
            {"label": "500g", "unit_type": "kg", "unit_value": 0.5, "sku_hint": "SOAP-500G"},
            {"label": "1kg", "unit_type": "kg", "unit_value": 1.0, "sku_hint": "SOAP-1KG"},
        ],
    },
    # Detergent
    {
        "category": "soap",
        "name": "Detergent",
        "variants": [
            {"label": "500g", "unit_type": "kg", "unit_value": 0.5, "sku_hint": "DET-500G"},
            {"label": "1kg", "unit_type": "kg", "unit_value": 1.0, "sku_hint": "DET-1KG"},
        ],
    },
    # Tea
    {
        "category": "other",
        "name": "Tea",
        "variants": [
            {"label": "Small pack", "unit_type": "pcs", "unit_value": 1.0, "sku_hint": "TEA-SMALL"},
        ],
    },
    # Matches
    {
        "category": "other",
        "name": "Matches",
        "variants": [
            {"label": "Box", "unit_type": "pcs", "unit_value": 1.0, "sku_hint": "MATCH-BOX"},
        ],
    },
]


def get_category_by_key(key: str) -> dict | None:
    """Get category by key"""
    for cat in CATEGORIES:
        if cat["key"] == key:
            return cat
    return None


def get_items_by_category(category_key: str) -> list[dict]:
    """Get all items for a category"""
    return [item for item in SEED_ITEMS if item["category"] == category_key]


def get_item_by_key(category_key: str, item_name: str) -> dict | None:
    """Get item by category and name"""
    for item in SEED_ITEMS:
        if item["category"] == category_key and item["name"] == item_name:
            return item
    return None


def get_variant_by_label(item: dict, variant_label: str) -> dict | None:
    """Get variant by label from an item"""
    for variant in item.get("variants", []):
        if variant["label"] == variant_label:
            return variant
    return None


def get_seed_key(category_key: str, item_name: str, variant_label: str) -> str:
    """Generate a unique seed key for lookup"""
    return f"{category_key}::{item_name}::{variant_label}"


def parse_seed_key(seed_key: str) -> tuple[str, str, str] | None:
    """Parse seed key into (category, item, variant)"""
    parts = seed_key.split("::")
    if len(parts) == 3:
        return tuple(parts)
    return None
