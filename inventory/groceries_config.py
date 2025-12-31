# inventory/groceries_config.py
"""
GROCERIES VERTICAL CONFIG - Single Source of Truth
Malawi-specific retail + wholesale configuration for groceries.

Key principles:
- Track inventory in BASE UNIT (smallest sellable unit)
- Pack units (carton/bale/bundle) are conversion shortcuts
- Barcode is ALWAYS OPTIONAL
- Both retail and wholesale flows supported
"""
from __future__ import annotations
from decimal import Decimal
from django.core.exceptions import ValidationError

# ==============================================================================
# CATEGORY GROUPS (Tiles for Product Add)
# ==============================================================================

CATEGORY_GROUPS = [
    {
        'key': 'drinks',
        'label': 'Drinks',
        'icon': '🥤',
        'description': 'Soft drinks, energy drinks, juices',
        'default_base_unit': 'can',
        'default_pack_label': 'carton',
        'default_pack_size': 24,
    },
    {
        'key': 'water',
        'label': 'Water',
        'icon': '💧',
        'description': 'Bottled water',
        'default_base_unit': 'bottle',
        'default_pack_label': 'carton',
        'default_pack_size': 12,
    },
    {
        'key': 'snacks',
        'label': 'Snacks',
        'icon': '🍿',
        'description': 'Chips, biscuits, sweets',
        'default_base_unit': 'pack',
        'default_pack_label': 'box',
        'default_pack_size': 12,
    },
    {
        'key': 'bread_bakery',
        'label': 'Bread & Bakery',
        'icon': '🍞',
        'description': 'Bread, buns, cakes',
        'default_base_unit': 'loaf',
        'default_pack_label': 'bundle',
        'default_pack_size': 10,
    },
    {
        'key': 'cooking_oil',
        'label': 'Cooking Oil',
        'icon': '🛢️',
        'description': 'Cooking oil bottles',
        'default_base_unit': 'bottle',
        'default_pack_label': 'carton',
        'default_pack_size': 12,
    },
    {
        'key': 'sugar_staples',
        'label': 'Sugar & Staples',
        'icon': '🌾',
        'description': 'Sugar, rice, flour, salt',
        'default_base_unit': 'pack',
        'default_pack_label': 'bale',
        'default_pack_size': 20,
    },
    {
        'key': 'toiletries',
        'label': 'Toiletries',
        'icon': '🧻',
        'description': 'Tissue, soap, detergent',
        'default_base_unit': 'roll',
        'default_pack_label': 'bale',
        'default_pack_size': 48,
    },
    {
        'key': 'household',
        'label': 'Household',
        'icon': '🏠',
        'description': 'Matches, candles, cleaning supplies',
        'default_base_unit': 'box',
        'default_pack_label': 'bundle',
        'default_pack_size': 10,
    },
    {
        'key': 'other',
        'label': 'Other',
        'icon': '📦',
        'description': 'Custom products',
        'default_base_unit': 'piece',
        'default_pack_label': None,
        'default_pack_size': None,
    },
]


# ==============================================================================
# CANONICAL UNIT STRINGS (prevent spelling drift)
# ==============================================================================

BASE_UNITS = [
    ('piece', 'Piece'),
    ('bottle', 'Bottle'),
    ('can', 'Can'),
    ('pack', 'Pack'),
    ('roll', 'Roll'),
    ('loaf', 'Loaf'),
    ('sachet', 'Sachet'),
    ('box', 'Box'),
    ('kg', 'Kilogram'),
    ('g', 'Gram'),
    ('litre', 'Litre'),
    ('ml', 'Millilitre'),
]

PACK_UNITS = [
    ('carton', 'Carton'),
    ('case', 'Case'),
    ('bale', 'Bale'),
    ('bundle', 'Bundle'),
    ('box', 'Box'),
]

# All valid units (base + pack)
ALL_UNITS = BASE_UNITS + PACK_UNITS


# ==============================================================================
# PACKAGING DEFAULTS SUGGESTIONS (editable by user)
# ==============================================================================

PACKAGING_SUGGESTIONS = {
    'soft_drink': {
        'base_unit': 'can',
        'pack_label': 'carton',
        'pack_size': 24,
        'description': 'Coca-Cola, Fanta, Sprite (cans)',
    },
    'energy_drink': {
        'base_unit': 'can',
        'pack_label': 'carton',
        'pack_size': 24,
        'description': 'Red Bull, Monster, etc.',
    },
    'water_bottle': {
        'base_unit': 'bottle',
        'pack_label': 'carton',
        'pack_size': 12,
        'description': '500ml water bottles',
    },
    'tissue': {
        'base_unit': 'roll',
        'pack_label': 'bale',
        'pack_size': 48,
        'description': 'Toilet tissue rolls',
    },
    'matches': {
        'base_unit': 'box',
        'pack_label': 'bundle',
        'pack_size': 10,
        'description': 'Match boxes',
    },
    'cooking_oil_1l': {
        'base_unit': 'bottle',
        'pack_label': 'carton',
        'pack_size': 12,
        'description': '1L cooking oil',
    },
    'cooking_oil_2l': {
        'base_unit': 'bottle',
        'pack_label': 'carton',
        'pack_size': 6,
        'description': '2L cooking oil',
    },
}


# ==============================================================================
# SELLING MODE RULES
# ==============================================================================

SALE_MODE_RETAIL = 'retail'
SALE_MODE_WHOLESALE = 'wholesale'

SALE_MODES = [
    (SALE_MODE_RETAIL, 'Retail'),
    (SALE_MODE_WHOLESALE, 'Wholesale'),
]


# ==============================================================================
# PAYMENT METHODS
# ==============================================================================

PAYMENT_METHODS = [
    ('CASH', 'Cash'),
    ('AIRTEL', 'Airtel Money'),
    ('TNM', 'TNM Mpamba'),
    ('BANK', 'Bank Transfer'),
]


# ==============================================================================
# CONVERSION HELPER (single source of truth)
# ==============================================================================

def to_base_units(qty: int | float, unit_label: str, product) -> int:
    """
    Convert quantity + unit_label to base units for a product.
    
    Args:
        qty: Quantity in the given unit
        unit_label: Unit label (e.g., 'carton', 'bottle', 'bale')
        product: MerchProduct instance with base_unit_label, pack_label, pack_size
    
    Returns:
        int: Quantity in base units
    
    Raises:
        ValidationError: If qty <= 0, or pack requested but not configured
    """
    if qty <= 0:
        raise ValidationError("Quantity must be greater than zero")
    
    # Normalize unit label
    unit_label = str(unit_label).strip().lower()
    
    # Get product's base unit
    base_unit = getattr(product, 'base_unit', 'piece').strip().lower()
    
    # If unit_label matches base unit, return qty as-is
    if unit_label == base_unit or unit_label == 'base':
        return int(qty)
    
    # If unit_label matches pack_label, convert using pack_size
    pack_label = getattr(product, 'pack_label', None)
    pack_size = getattr(product, 'pack_size', None)
    
    if pack_label:
        pack_label_normalized = pack_label.strip().lower()
        if unit_label == pack_label_normalized or unit_label == 'pack':
            if not pack_size or pack_size <= 0:
                raise ValidationError(
                    f"Product '{product.name}' has pack label '{pack_label}' "
                    f"but no pack_size configured"
                )
            return int(qty * pack_size)
    
    # Fallback: assume unit_label is base unit (tolerant)
    # This handles cases where user might type different variations
    return int(qty)


def from_base_units(qty_base: int, target_unit_label: str, product) -> tuple[int, int]:
    """
    Convert base units to target unit (e.g., for display or wholesale).
    
    Args:
        qty_base: Quantity in base units
        target_unit_label: Target unit ('base', 'pack', or specific label)
        product: MerchProduct instance
    
    Returns:
        tuple: (whole_units, remainder_base_units)
        Example: 50 bottles with pack=24 -> (2, 2) meaning 2 cartons + 2 bottles
    """
    target_unit_label = str(target_unit_label).strip().lower()
    base_unit = getattr(product, 'base_unit', 'piece').strip().lower()
    
    # If target is base unit, return as-is
    if target_unit_label == base_unit or target_unit_label == 'base':
        return (qty_base, 0)
    
    # If target is pack unit, divide by pack_size
    pack_label = getattr(product, 'pack_label', None)
    pack_size = getattr(product, 'pack_size', None)
    
    if pack_label and pack_size and pack_size > 0:
        pack_label_normalized = pack_label.strip().lower()
        if target_unit_label == pack_label_normalized or target_unit_label == 'pack':
            packs = qty_base // pack_size
            remainder = qty_base % pack_size
            return (packs, remainder)
    
    # Fallback: return as base units
    return (qty_base, 0)


# ==============================================================================
# PRICING HELPERS
# ==============================================================================

def get_unit_price(product, unit_label: str, sale_mode: str = SALE_MODE_RETAIL) -> Decimal:
    """
    Get the selling price for a given unit and sale mode.
    
    Args:
        product: MerchProduct instance
        unit_label: 'base' or 'pack' or specific label
        sale_mode: 'retail' or 'wholesale'
    
    Returns:
        Decimal: Unit price
    """
    unit_label = str(unit_label).strip().lower()
    base_unit = getattr(product, 'base_unit', 'piece').strip().lower()
    retail_price = getattr(product, 'selling_price', None) or Decimal('0')
    
    # If requesting base unit price (retail always uses base price)
    if unit_label == base_unit or unit_label == 'base':
        return retail_price
    
    # If requesting pack unit price
    pack_label = getattr(product, 'pack_label', None)
    pack_size = getattr(product, 'pack_size', None)
    
    if pack_label and pack_size and pack_size > 0:
        pack_label_normalized = pack_label.strip().lower()
        if unit_label == pack_label_normalized or unit_label == 'pack':
            # Check if wholesale price is explicitly set
            wholesale_price_per_pack = getattr(product, 'wholesale_price_per_pack', None)
            if wholesale_price_per_pack and wholesale_price_per_pack > 0:
                return wholesale_price_per_pack
            # Fallback: derive from retail price * pack_size
            return retail_price * Decimal(str(pack_size))
    
    # Default: return retail price
    return retail_price


def get_cost_price(product, unit_label: str) -> Decimal:
    """
    Get the cost price for a given unit.
    
    Args:
        product: MerchProduct instance
        unit_label: 'base' or 'pack' or specific label
    
    Returns:
        Decimal: Cost price per unit
    """
    unit_label = str(unit_label).strip().lower()
    base_unit = getattr(product, 'base_unit', 'piece').strip().lower()
    cost_price = getattr(product, 'cost_price', None) or Decimal('0')
    
    # If requesting base unit cost
    if unit_label == base_unit or unit_label == 'base':
        return cost_price
    
    # If requesting pack unit cost
    pack_label = getattr(product, 'pack_label', None)
    pack_size = getattr(product, 'pack_size', None)
    
    if pack_label and pack_size and pack_size > 0:
        pack_label_normalized = pack_label.strip().lower()
        if unit_label == pack_label_normalized or unit_label == 'pack':
            return cost_price * Decimal(str(pack_size))
    
    # Default: return base cost
    return cost_price


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_category_by_key(category_key: str) -> dict | None:
    """Get category config by key."""
    for cat in CATEGORY_GROUPS:
        if cat['key'] == category_key:
            return cat
    return None


def get_default_units_for_category(category_key: str) -> dict:
    """Get default base_unit, pack_label, pack_size for a category."""
    category = get_category_by_key(category_key)
    if not category:
        return {
            'base_unit': 'piece',
            'pack_label': None,
            'pack_size': None,
        }
    
    return {
        'base_unit': category.get('default_base_unit', 'piece'),
        'pack_label': category.get('default_pack_label'),
        'pack_size': category.get('default_pack_size'),
    }


def validate_product_packaging(product) -> list[str]:
    """
    Validate product packaging configuration.
    
    Returns:
        list: List of validation error messages (empty if valid)
    """
    errors = []
    
    # If pack_label is set, pack_size must be > 0
    pack_label = getattr(product, 'pack_label', None)
    pack_size = getattr(product, 'pack_size', None)
    
    if pack_label and pack_label.strip():
        if not pack_size or pack_size <= 0:
            errors.append(
                f"Pack label '{pack_label}' is set but pack_size is missing or invalid"
            )
    
    if pack_size and pack_size > 0:
        if not pack_label or not pack_label.strip():
            errors.append(
                f"Pack size {pack_size} is set but pack_label is missing"
            )
    
    # Base unit should not be empty
    base_unit = getattr(product, 'base_unit', None)
    if not base_unit or not str(base_unit).strip():
        errors.append("Base unit is required")
    
    return errors


