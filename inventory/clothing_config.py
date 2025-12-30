# inventory/clothing_config.py
"""
Single source of truth for CLOTHING vertical configuration.
Defines categories, sizes, colors, SKU format, and QR signing helpers.
"""
from __future__ import annotations

from typing import Dict, List, Tuple, Optional
from decimal import Decimal
import secrets
import hashlib
import json
from django.conf import settings
from django.core.signing import Signer, BadSignature


# ============================================================================
# CLOTHING CATEGORIES & ITEM TYPES
# ============================================================================

class ClothingItemType:
    """Top-level item type classification"""
    APPAREL = "apparel"
    FOOTWEAR = "footwear"
    ACCESSORY = "accessory"
    FRAGRANCE = "fragrance"
    OTHER = "other"
    
    CHOICES = [
        (APPAREL, "Apparel"),
        (FOOTWEAR, "Footwear"),
        (ACCESSORY, "Accessory"),
        (FRAGRANCE, "Fragrance"),
        (OTHER, "Other"),
    ]


# Category definitions: (value, display_name, icon, item_type)
CLOTHING_CATEGORIES: List[Tuple[str, str, str, str]] = [
    # Apparel
    ("shirt", "Shirt", "👔", ClothingItemType.APPAREL),
    ("t-shirt", "T-Shirt", "👕", ClothingItemType.APPAREL),
    ("trouser", "Trouser", "👖", ClothingItemType.APPAREL),
    ("jeans", "Jeans", "👖", ClothingItemType.APPAREL),
    ("dress", "Dress", "👗", ClothingItemType.APPAREL),
    ("jacket", "Jacket", "🧥", ClothingItemType.APPAREL),
    ("suit", "Suit", "🤵", ClothingItemType.APPAREL),
    ("shorts", "Shorts", "🩳", ClothingItemType.APPAREL),
    ("skirt", "Skirt", "🩱", ClothingItemType.APPAREL),
    
    # Footwear
    ("sneaker", "Sneaker", "👟", ClothingItemType.FOOTWEAR),
    ("boot", "Boot", "🥾", ClothingItemType.FOOTWEAR),
    ("office-shoe", "Office Shoe", "👞", ClothingItemType.FOOTWEAR),
    ("sports-shoe", "Sports Shoe", "⚽", ClothingItemType.FOOTWEAR),
    
    # Accessories
    ("belt", "Belt", "🔗", ClothingItemType.ACCESSORY),
    ("bag", "Bag", "👜", ClothingItemType.ACCESSORY),
    ("handbag", "Handbag", "👜", ClothingItemType.ACCESSORY),
    ("schoolbag", "School Bag", "🎒", ClothingItemType.ACCESSORY),
    ("hat", "Hat", "🧢", ClothingItemType.ACCESSORY),
    ("socks", "Socks", "🧦", ClothingItemType.ACCESSORY),
    
    # Fragrance
    ("perfume", "Perfume", "🌸", ClothingItemType.FRAGRANCE),
    
    # Other
    ("other", "Other", "👕", ClothingItemType.OTHER),
]


def get_category_display(category_value: str) -> str:
    """Get human-readable category name"""
    for val, display, _, _ in CLOTHING_CATEGORIES:
        if val == category_value:
            return display
    return category_value.title()


def get_category_icon(category_value: str) -> str:
    """Get emoji icon for category"""
    for val, _, icon, _ in CLOTHING_CATEGORIES:
        if val == category_value:
            return icon
    return "👕"


def get_item_type_for_category(category_value: str) -> str:
    """Get item type for a category"""
    for val, _, _, item_type in CLOTHING_CATEGORIES:
        if val == category_value:
            return item_type
    return ClothingItemType.OTHER


# ============================================================================
# SIZES & COLORS
# ============================================================================

# Apparel sizes (XS to XXL)
APPAREL_SIZES = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]

# Footwear sizes (EU sizing, common in Africa)
FOOTWEAR_SIZES = [str(i) for i in range(36, 47)]  # 36-46

# Trouser/Jeans waist sizes (inches)
TROUSER_SIZES = [str(i) for i in range(28, 45, 2)]  # 28, 30, 32, ..., 44

# Combined size list (for generic use)
ALL_SIZES = sorted(set(APPAREL_SIZES + FOOTWEAR_SIZES + TROUSER_SIZES), 
                   key=lambda x: (len(x), x))


def get_sizes_for_category(category_value: str) -> List[str]:
    """Get appropriate size list for a category"""
    item_type = get_item_type_for_category(category_value)
    
    if item_type == ClothingItemType.FOOTWEAR:
        return FOOTWEAR_SIZES
    elif category_value in ("trouser", "jeans"):
        return TROUSER_SIZES
    elif item_type == ClothingItemType.APPAREL:
        return APPAREL_SIZES
    else:
        # Accessories/Fragrance typically don't have sizes
        return []


# Standard color palette
CLOTHING_COLORS = [
    "Black",
    "White",
    "Navy",
    "Grey",
    "Beige",
    "Brown",
    "Blue",
    "Red",
    "Green",
    "Yellow",
    "Pink",
    "Purple",
    "Orange",
    "Multi",
    "Other",
]


# ============================================================================
# AUTO-GENERATED SKU SYSTEM
# ============================================================================

def generate_internal_sku(
    business_id: int,
    category: str,
    brand: Optional[str] = None,
    sequence: Optional[int] = None
) -> str:
    """
    Generate a business-scoped internal SKU.
    
    Format: BIZ{business_id}-{CATEGORY_CODE}-{SEQ}
    Example: BIZ42-SNK-001 (Sneaker #1 for business 42)
    
    Args:
        business_id: Business ID
        category: Category value (e.g., "sneaker")
        brand: Optional brand name (not used in SKU, but can be for future)
        sequence: Optional sequence number (auto-generated if None)
    
    Returns:
        Internal SKU string
    """
    # Category code: first 3 letters uppercase
    category_code = category[:3].upper() if category else "GEN"
    
    # If sequence not provided, generate random 3-digit
    if sequence is None:
        sequence = secrets.randbelow(1000)
    
    sku = f"BIZ{business_id}-{category_code}-{sequence:03d}"
    return sku


def generate_variant_sku(base_sku: str, size: Optional[str] = None, color: Optional[str] = None) -> str:
    """
    Generate variant SKU from base SKU + size/color.
    
    Format: {BASE_SKU}-{SIZE}-{COLOR_CODE}
    Example: BIZ42-SNK-001-42-BLK
    
    Args:
        base_sku: Base product SKU
        size: Size value (e.g., "42", "M")
        color: Color value (e.g., "Black")
    
    Returns:
        Variant SKU string
    """
    parts = [base_sku]
    
    if size:
        parts.append(size.upper())
    
    if color:
        # Color code: first 3 letters
        color_code = color[:3].upper()
        parts.append(color_code)
    
    return "-".join(parts)


# ============================================================================
# QR CODE SIGNING (for secure product labels)
# ============================================================================

def sign_product_qr_data(
    business_id: int,
    product_id: int,
    variant_id: Optional[int] = None,
    expiry_days: int = 365
) -> str:
    """
    Create a signed token for QR code that encodes product/variant info.
    
    Token format: {business_id}:{product_id}:{variant_id}:{timestamp}:{signature}
    
    Args:
        business_id: Business ID
        product_id: Product ID
        variant_id: Optional variant ID
        expiry_days: Token validity in days (default 1 year)
    
    Returns:
        Signed token string
    """
    import time
    
    timestamp = int(time.time())
    variant_part = str(variant_id) if variant_id else "0"
    
    # Payload: business:product:variant:timestamp
    payload = f"{business_id}:{product_id}:{variant_part}:{timestamp}"
    
    # Sign with Django's Signer
    signer = Signer(salt="clothing_qr_v1")
    signed_token = signer.sign(payload)
    
    return signed_token


def verify_product_qr_token(token: str, max_age_days: int = 365) -> Optional[Dict]:
    """
    Verify and decode a QR token.
    
    Args:
        token: Signed token string
        max_age_days: Maximum age in days
    
    Returns:
        Dict with {business_id, product_id, variant_id} or None if invalid
    """
    import time
    
    try:
        signer = Signer(salt="clothing_qr_v1")
        payload = signer.unsign(token)
        
        # Parse payload
        parts = payload.split(":")
        if len(parts) != 4:
            return None
        
        business_id = int(parts[0])
        product_id = int(parts[1])
        variant_id = int(parts[2]) if parts[2] != "0" else None
        timestamp = int(parts[3])
        
        # Check expiry
        age_seconds = time.time() - timestamp
        age_days = age_seconds / 86400
        
        if age_days > max_age_days:
            return None
        
        return {
            "business_id": business_id,
            "product_id": product_id,
            "variant_id": variant_id,
            "timestamp": timestamp,
        }
    
    except (BadSignature, ValueError, IndexError):
        return None


# ============================================================================
# PRICE TIERS (for smart filtering)
# ============================================================================

def get_price_tier(price: Decimal) -> str:
    """
    Classify product into price tier for filtering.
    
    Args:
        price: Selling price
    
    Returns:
        Tier name: "budget", "mid", "premium", "luxury"
    """
    if price < Decimal("50"):
        return "budget"
    elif price < Decimal("200"):
        return "mid"
    elif price < Decimal("500"):
        return "premium"
    else:
        return "luxury"


PRICE_TIER_LABELS = {
    "budget": "Budget (< K50)",
    "mid": "Mid-Range (K50-200)",
    "premium": "Premium (K200-500)",
    "luxury": "Luxury (K500+)",
}


# ============================================================================
# STOCK STATUS HELPERS
# ============================================================================

def get_stock_status(quantity: int, low_threshold: int = 3) -> str:
    """
    Get stock status label.
    
    Args:
        quantity: Current stock quantity
        low_threshold: Threshold for low stock warning
    
    Returns:
        Status: "out", "low", "in"
    """
    if quantity <= 0:
        return "out"
    elif quantity <= low_threshold:
        return "low"
    else:
        return "in"


# ============================================================================
# GAMIFICATION CONFIG
# ============================================================================

# Daily sales targets (configurable per business)
DEFAULT_DAILY_SALES_TARGET = 10  # items
DEFAULT_DAILY_REVENUE_TARGET = Decimal("1000.00")  # Kwacha

# Badges
BADGES = {
    "first_sale": {"name": "First Sale", "icon": "🎯", "description": "Recorded your first sale today"},
    "ten_items": {"name": "Top Seller", "icon": "🔥", "description": "Sold 10+ items today"},
    "stock_hero": {"name": "Stock Hero", "icon": "📦", "description": "Stocked in 20+ items today"},
    "profit_king": {"name": "Profit King", "icon": "💰", "description": "Made K500+ profit today"},
    "streak_3": {"name": "3-Day Streak", "icon": "⚡", "description": "Sales for 3 days straight"},
    "streak_7": {"name": "Week Warrior", "icon": "🏆", "description": "Sales for 7 days straight"},
}


def check_badges_earned(sales_count: int, revenue: Decimal, profit: Decimal, streak_days: int) -> List[str]:
    """
    Check which badges have been earned based on metrics.
    
    Returns:
        List of badge keys
    """
    earned = []
    
    if sales_count >= 1:
        earned.append("first_sale")
    
    if sales_count >= 10:
        earned.append("ten_items")
    
    if profit >= Decimal("500"):
        earned.append("profit_king")
    
    if streak_days >= 3:
        earned.append("streak_3")
    
    if streak_days >= 7:
        earned.append("streak_7")
    
    return earned


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "ClothingItemType",
    "CLOTHING_CATEGORIES",
    "APPAREL_SIZES",
    "FOOTWEAR_SIZES",
    "TROUSER_SIZES",
    "ALL_SIZES",
    "CLOTHING_COLORS",
    "get_category_display",
    "get_category_icon",
    "get_item_type_for_category",
    "get_sizes_for_category",
    "generate_internal_sku",
    "generate_variant_sku",
    "sign_product_qr_data",
    "verify_product_qr_token",
    "get_price_tier",
    "PRICE_TIER_LABELS",
    "get_stock_status",
    "DEFAULT_DAILY_SALES_TARGET",
    "DEFAULT_DAILY_REVENUE_TARGET",
    "BADGES",
    "check_badges_earned",
]

