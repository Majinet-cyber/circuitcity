# inventory/cement_seed.py
"""
Cement/Hardware default product seeding.
Creates starter catalog of common Malawian cement brands.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

from django.db import transaction

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from tenants.models import Business

# Malawian cement brands - ONLY 50KG bags (HARD CONSTRAINT)
# This list is FIXED and COMPLETE - do not add or remove brands
CEMENT_BRANDS = [
    {"name": "Dangote", "aliases": ["dangote"], "icon": "🏭"},
    {"name": "Aksher", "aliases": ["akshar", "aksher"], "icon": "🏗️"},
    {"name": "Duracrete", "aliases": ["duracrete"], "icon": "🏗️"},
    {"name": "Njati", "aliases": ["njati"], "icon": "🏗️"},
    {"name": "Njati Extra", "aliases": ["njati extra", "njatiextra"], "icon": "🏗️"},
    {"name": "Khoma", "aliases": ["khoma"], "icon": "🏗️"},
    {"name": "Nkope", "aliases": ["nkope"], "icon": "🏗️"},
    {"name": "Lime", "aliases": ["lime"], "icon": "🧱"},
    {"name": "Nthanthwe", "aliases": ["nthanthwe"], "icon": "🏗️"},
]

# CEMENT CATALOG - ONLY 50KG BAGS (HARD CONSTRAINT)
# NO 25KG, NO sand, NO stones, NO aggregates, NO other items
# This vertical sells ONLY 50KG cement bags from the brands above
CEMENT_CATALOG = [
    {"category": "cement", "name": "Dangote Cement", "unit": "Bag (50KG)", "pack_size": 50, "icon": "🏭"},
    {"category": "cement", "name": "Aksher Cement", "unit": "Bag (50KG)", "pack_size": 50, "icon": "🏗️"},
    {"category": "cement", "name": "Duracrete Cement", "unit": "Bag (50KG)", "pack_size": 50, "icon": "🏗️"},
    {"category": "cement", "name": "Njati Cement", "unit": "Bag (50KG)", "pack_size": 50, "icon": "🏗️"},
    {"category": "cement", "name": "Njati Extra Cement", "unit": "Bag (50KG)", "pack_size": 50, "icon": "🏗️"},
    {"category": "cement", "name": "Khoma Cement", "unit": "Bag (50KG)", "pack_size": 50, "icon": "🏗️"},
    {"category": "cement", "name": "Nkope Cement", "unit": "Bag (50KG)", "pack_size": 50, "icon": "🏗️"},
    {"category": "cement", "name": "Lime Cement", "unit": "Bag (50KG)", "pack_size": 50, "icon": "🧱"},
    {"category": "cement", "name": "Nthanthwe Cement", "unit": "Bag (50KG)", "pack_size": 50, "icon": "🏗️"},
]


def seed_cement_defaults(business: Business) -> Dict[str, int]:
    """
    Seed default cement products for a cement business.
    Creates ONLY 50KG cement bags for the 9 approved brands (NO 25KG, NO sand, NO stones).
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
        # Seed ONLY 50KG cement bags (9 brands)
        for item_spec in CEMENT_CATALOG:
            item_name = item_spec["name"]
            category = item_spec["category"]
            unit = item_spec.get("unit", "piece")
            pack_size = item_spec.get("pack_size", 1)

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
    Get list of cement brands for display in UI.

    Returns:
        List of dicts with 'key', 'name', and 'icon' fields
    """
    return [
        {
            "key": brand["name"].lower().replace(" ", "_"),
            "name": brand["name"],
            "icon": brand.get("icon", "📦"),
        }
        for brand in CEMENT_BRANDS
    ]


def is_cement_brand(name: str) -> bool:
    """
    Check if a product name matches a known cement brand.
    Case-insensitive, checks aliases.

    Args:
        name: Product name to check

    Returns:
        True if name matches a cement brand or alias
    """
    name_lower = name.lower().strip()

    for brand_spec in CEMENT_BRANDS:
        # Check main name
        if name_lower == brand_spec["name"].lower():
            return True

        # Check aliases
        for alias in brand_spec.get("aliases", []):
            if name_lower == alias.lower():
                return True

    return False


def normalize_cement_brand_name(name: str) -> str:
    """
    Normalize a cement brand name/alias to the canonical display name.

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

        # Check aliases
        for alias in brand_spec.get("aliases", []):
            if name_lower == alias.lower():
                return brand_spec["name"]

    # Return original if not found (custom brand)
    return name
