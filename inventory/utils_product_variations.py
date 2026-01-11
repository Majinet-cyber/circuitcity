"""
Product variation grouping utilities.

For products that vary by size (Paint litres, etc.), this module provides
helpers to:
1. Extract base product name (e.g., "Paint" from "Paint 1L")
2. Group products by base name
3. Get unique variations for a base product
4. Prevent duplicate variations

Usage:
    from inventory.utils_product_variations import group_products_by_base_name
    
    products = MerchProduct.objects.filter(business=business, category="paint")
    grouped = group_products_by_base_name(products)
    # Returns: {"Paint": [product1_1L, product2_4L, product3_20L], ...}
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List


def normalize_product_base_name(product_name: str) -> str:
    """
    Extract base product name by removing size/variation suffix.

    Examples:
        "Paint 1L" -> "Paint"
        "Paint - 4L" -> "Paint"
        "Dangote Cement 50kg" -> "Dangote Cement"
        "Nails 2inch" -> "Nails"

    Args:
        product_name: Full product name with potential variation

    Returns:
        Base product name without variation
    """
    import re

    # Remove common size patterns: 1L, 4L, 20L, 50kg, 2inch, etc.
    # Pattern: number + unit (L, kg, g, ml, inch, cm, mm, etc.)
    size_pattern = r"\s*[-–—]?\s*\d+(\.\d+)?\s*(L|l|kg|g|ml|ML|inch|cm|mm|Kg|KG)\b"
    base_name = re.sub(size_pattern, "", product_name).strip()

    # Remove trailing dashes/hyphens
    base_name = re.sub(r"[-–—]\s*$", "", base_name).strip()

    return base_name if base_name else product_name


def extract_variation_from_name(product_name: str) -> str:
    """
    Extract the variation/size from product name.

    Examples:
        "Paint 1L" -> "1L"
        "Paint - 4L" -> "4L"
        "Dangote Cement 50kg" -> "50kg"

    Args:
        product_name: Full product name

    Returns:
        Variation string (e.g., "1L", "4L") or empty string if none found
    """
    import re

    # Match size patterns
    match = re.search(r"\d+(\.\d+)?\s*(L|l|kg|g|ml|ML|inch|cm|mm|Kg|KG)\b", product_name)
    if match:
        return match.group(0).strip()

    return ""


def get_variation_display(product) -> str:
    """
    Get the display label for a product variation.

    Priority:
    1. spec_label field (e.g., "1L", "4L")
    2. Extract from name (e.g., "Paint 1L" -> "1L")
    3. base_unit (e.g., "litre")

    Args:
        product: MerchProduct instance

    Returns:
        Variation display string
    """
    # 1. Check spec_label first (most explicit)
    if hasattr(product, "spec_label") and product.spec_label:
        return product.spec_label

    # 2. Try extracting from name
    variation = extract_variation_from_name(product.name)
    if variation:
        return variation

    # 3. Fallback to base_unit
    if hasattr(product, "base_unit") and product.base_unit:
        return product.base_unit

    return "Standard"


def group_products_by_base_name(products) -> Dict[str, List]:
    """
    Group products by their base name (without variation).

    Example:
        Input: [Paint 1L, Paint 4L, Paint 20L, Cement 50kg]
        Output: {
            "Paint": [Paint 1L, Paint 4L, Paint 20L],
            "Cement": [Cement 50kg]
        }

    Args:
        products: QuerySet or list of MerchProduct instances

    Returns:
        Dict mapping base_name -> list of product instances
    """
    grouped = defaultdict(list)

    for product in products:
        base_name = normalize_product_base_name(product.name)
        grouped[base_name].append(product)

    return dict(grouped)


def get_unique_variations(products) -> List[Dict]:
    """
    Get unique variations from a list of products.
    Removes duplicates based on variation label.

    Args:
        products: List of MerchProduct instances

    Returns:
        List of dicts with keys: 'product', 'variation', 'display'
        Ordered by variation (e.g., 1L, 4L, 20L)
    """
    seen_variations = set()
    unique_variations = []

    for product in products:
        variation = get_variation_display(product)

        # Skip if we've already seen this variation
        if variation in seen_variations:
            continue

        seen_variations.add(variation)
        unique_variations.append(
            {
                "product": product,
                "variation": variation,
                "display": variation,
            }
        )

    # Sort by numeric value if possible (1L < 4L < 20L)
    def sort_key(item):
        import re

        match = re.search(r"(\d+(\.\d+)?)", item["variation"])
        if match:
            return float(match.group(1))
        return 999999  # Non-numeric variations go last

    unique_variations.sort(key=sort_key)

    return unique_variations


def should_use_variation_picker(products, category: str = None) -> bool:
    """
    Determine if a variation picker should be shown.

    Criteria:
    - Multiple products with same base name
    - Category is paint, cement, or other size-based products
    - Products have different spec_labels or size patterns in name

    Args:
        products: List of products with same base name
        category: Optional category hint

    Returns:
        True if variation picker should be used
    """
    if not products or len(products) < 2:
        return False

    # Check if category suggests size variations
    size_based_categories = ["paint", "cement", "hardware", "building_materials"]
    if category and category.lower() in size_based_categories:
        return True

    # Check if products have different spec_labels
    spec_labels = {getattr(p, "spec_label", "") for p in products if hasattr(p, "spec_label")}
    if len(spec_labels) > 1:
        return True

    # Check if names contain size patterns
    variations = {extract_variation_from_name(p.name) for p in products}
    if len(variations) > 1:
        return True

    return False
