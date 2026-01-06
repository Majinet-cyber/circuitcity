# inventory/clothing_size_validation.py
"""
Size validation rules for clothing vertical.

CRITICAL RULE: Shoes (footwear) must ONLY accept numeric sizes (30-50).
Other categories may accept alpha sizes (XS, S, M, L, XL, XXL, etc).
"""
import re
from typing import List, Tuple

from django.core.exceptions import ValidationError

from inventory.clothing_config import ClothingItemType, get_item_type_for_category

# Size ranges by category type
FOOTWEAR_SIZE_MIN = 30
FOOTWEAR_SIZE_MAX = 50

# Regex patterns
NUMERIC_SIZE_PATTERN = re.compile(r"^[0-9]{2,3}$")  # 2-3 digits only
ALPHA_SIZE_PATTERN = re.compile(r"^[A-Z]{1,4}$", re.IGNORECASE)  # XS, S, M, L, XL, XXL, XXXL
TROUSER_SIZE_PATTERN = re.compile(r"^[0-9]{2}(x[0-9]{2})?$")  # 32 or 32x30


def is_footwear_category(category: str, subcategory: str = "") -> bool:
    """
    Check if category/subcategory is footwear (shoes).

    Args:
        category: Main category (e.g., "shoes", "sneaker", "boot")
        subcategory: Subcategory (e.g., "sports", "casual")

    Returns:
        True if this is footwear/shoes
    """
    # Check by category value
    item_type = get_item_type_for_category(category)
    if item_type == ClothingItemType.FOOTWEAR:
        return True

    # Also check common footwear keywords
    footwear_keywords = ["shoe", "sneaker", "boot", "sandal", "slipper", "footwear"]
    category_lower = category.lower()
    subcategory_lower = subcategory.lower() if subcategory else ""

    for keyword in footwear_keywords:
        if keyword in category_lower or keyword in subcategory_lower:
            return True

    return False


def validate_shoe_size(size: str) -> Tuple[bool, str]:
    """
    Validate shoe size (numeric only, 30-50).

    Args:
        size: Size string to validate

    Returns:
        (is_valid, error_message)
    """
    size = size.strip()

    if not size:
        return False, "Size is required for shoes"

    # Check if numeric
    if not NUMERIC_SIZE_PATTERN.match(size):
        return (
            False,
            f"Shoe size must be numeric only (e.g., 40, 42). Alpha sizes like XL, XXL, S, M, L are not allowed for shoes.",
        )

    # Check range
    try:
        size_int = int(size)
        if size_int < FOOTWEAR_SIZE_MIN or size_int > FOOTWEAR_SIZE_MAX:
            return False, f"Shoe size must be between {FOOTWEAR_SIZE_MIN} and {FOOTWEAR_SIZE_MAX}"
    except ValueError:
        return False, "Invalid shoe size format"

    return True, ""


def validate_clothing_size(size: str, category: str, subcategory: str = "") -> Tuple[bool, str]:
    """
    Validate clothing size based on category.

    CRITICAL: Shoes must be numeric only (30-50).
    Other categories can be alpha (XS, S, M, L, XL, XXL) or numeric.

    Args:
        size: Size string to validate
        category: Main category (e.g., "shoes", "shirt", "jeans")
        subcategory: Subcategory (optional)

    Returns:
        (is_valid, error_message)

    Raises:
        ValidationError: If validation fails (for use in Django forms/models)
    """
    size = size.strip()

    if not size:
        return False, "Size is required"

    # CRITICAL: Shoes must be numeric only
    if is_footwear_category(category, subcategory):
        return validate_shoe_size(size)

    # For other categories, allow alpha or numeric
    # Alpha sizes: XS, S, M, L, XL, XXL, XXXL
    if ALPHA_SIZE_PATTERN.match(size):
        return True, ""

    # Numeric sizes: 28, 30, 32, 34, 36, 38, 40, 42, 44
    if NUMERIC_SIZE_PATTERN.match(size):
        return True, ""

    # Trouser sizes: 32x30, 34x32, etc
    if TROUSER_SIZE_PATTERN.match(size):
        return True, ""

    return False, f"Invalid size format. Use numeric (e.g., 32) or alpha (e.g., M, L, XL) sizes."


def get_allowed_sizes_for_category(category: str, subcategory: str = "") -> List[str]:
    """
    Get list of allowed sizes for a category.

    Args:
        category: Main category
        subcategory: Subcategory (optional)

    Returns:
        List of allowed size strings
    """
    from inventory.clothing_config import get_sizes_for_category

    # Get base sizes from config
    sizes = get_sizes_for_category(category)

    # For shoes, ensure only numeric sizes are returned
    if is_footwear_category(category, subcategory):
        # Filter to numeric only, range 30-50
        return [str(i) for i in range(FOOTWEAR_SIZE_MIN, FOOTWEAR_SIZE_MAX + 1)]

    return sizes


def validate_size_for_django_form(size: str, category: str, subcategory: str = "") -> str:
    """
    Django form validator for size field.

    Args:
        size: Size to validate
        category: Category
        subcategory: Subcategory (optional)

    Returns:
        Cleaned size string

    Raises:
        ValidationError: If validation fails
    """
    is_valid, error_msg = validate_clothing_size(size, category, subcategory)

    if not is_valid:
        raise ValidationError(error_msg)

    return size.strip().upper()


# Export validation function for use in views/services
__all__ = [
    "validate_clothing_size",
    "validate_shoe_size",
    "is_footwear_category",
    "get_allowed_sizes_for_category",
    "validate_size_for_django_form",
    "FOOTWEAR_SIZE_MIN",
    "FOOTWEAR_SIZE_MAX",
]
