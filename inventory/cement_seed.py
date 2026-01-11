# inventory/cement_seed.py
"""
Cement/Hardware default product seeding.
Creates starter catalog of common Malawian cement brands.

IMPORTANT: This module now uses the SSOT catalog from:
    inventory/catalog/construction_materials.py

All product definitions come from that module to ensure consistency.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

from django.db import transaction

from inventory.business_kinds import BusinessKind
from inventory.catalog.construction_materials import (
    CEMENT_BRANDS,
    build_product_name,
    get_cement_brands,
)
from inventory.models import MerchProduct
from tenants.models import Business

# CEMENT CATALOG - Generated from SSOT
# Each cement brand gets a 50KG bag product
CEMENT_CATALOG = [
    {
        "category": "cement",
        "name": build_product_name("cement", brand=brand["name"], size="50kg"),
        "unit": "bag",
        "pack_size": 50,
        "icon": brand["icon"],
    }
    for brand in CEMENT_BRANDS
]


def seed_cement_defaults(business: Business) -> Dict[str, int]:
    """
    Seed default cement products for a cement business.
    Creates ONLY 50KG cement bags for canonical brands from SSOT catalog (NO duplicates).
    Products start with zero stock (managers will stock in as needed).

    This function is idempotent - safe to call multiple times.
    If a brand already exists, it will be skipped (not recreated).

    Args:
        business: Business instance (must have business_kind='cement')

    Returns:
        Dict with 'created' and 'skipped' counts
    """
    if not business:
        return {"created": 0, "skipped": 0, "error": "No business provided"}

    # Only seed for cement businesses
    business_kind = getattr(business, "business_kind", None)
    if business_kind != BusinessKind.CEMENT:
        return {"created": 0, "skipped": 0, "error": f"Wrong business kind: {business_kind}"}

    created = 0
    skipped = 0

    with transaction.atomic():
        # Seed ONLY 50KG cement bags (canonical brands from SSOT)
        for item_spec in CEMENT_CATALOG:
            item_name = item_spec["name"]
            category = item_spec["category"]
            unit = item_spec.get("unit", "bag")
            pack_size = item_spec.get("pack_size", 50)

            # Check if product already exists (case-insensitive)
            existing = MerchProduct.objects.filter(
                business=business,
                name__iexact=item_name,
                kind=BusinessKind.CEMENT,
            ).first()

            if existing:
                skipped += 1
                continue

            # Create new cement product (zero stock, managers will stock in)
            MerchProduct.objects.create(
                business=business,
                name=item_name,
                kind=BusinessKind.CEMENT,
                category=category,
                spec_label="",  # Prevent NULL constraint
                base_unit=unit,
                pack_size=pack_size,
                cost_price=Decimal("0.00"),  # Will be set during first stock-in
                selling_price=Decimal("0.00"),  # Will be set during first stock-in
                quantity_in_stock=0,  # Start with zero stock
                is_active=True,
                track_inventory=True,
            )
            created += 1

    return {"created": created, "skipped": skipped}


def get_cement_brands_list() -> List[Dict[str, str]]:
    """
    Get list of cement brands for display in UI (from SSOT catalog).

    Returns:
        List of dicts with 'key', 'name', and 'icon' fields
    """
    return get_cement_brands()


def is_cement_brand(name: str) -> bool:
    """
    Check if a product name matches a known cement brand.
    Case-insensitive check against canonical SSOT brand list.
    Supports aliases (e.g., "aksher" → "Akshar").

    Args:
        name: Product name to check

    Returns:
        True if name matches a cement brand (including aliases)
    """
    name_lower = name.lower().strip()

    for brand_spec in CEMENT_BRANDS:
        # Check main name
        if name_lower == brand_spec["name"].lower():
            return True
        # Check key
        if name_lower == brand_spec["key"].lower():
            return True
        # Check aliases
        if "aliases" in brand_spec:
            for alias in brand_spec["aliases"]:
                if name_lower == alias.lower():
                    return True

    return False


def normalize_cement_brand_name(name: str) -> str:
    """
    Normalize a cement brand name to the canonical display name (from SSOT).
    Supports aliases (e.g., "aksher" → "Akshar").

    Args:
        name: Brand name or alias (e.g., "aksher", "Akshar", "AKSHAR")

    Returns:
        Canonical brand name (e.g., "Akshar") or original name if not found
    """
    name_lower = name.lower().strip()

    for brand_spec in CEMENT_BRANDS:
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
    return name
