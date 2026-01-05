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

# Malawian cement brands with display names and aliases
CEMENT_BRANDS = [
    {"name": "Dangote", "aliases": ["dangote"], "icon": "🏭"},
    {"name": "Akshar", "aliases": ["akshar", "aksher"], "icon": "🏗️"},
    {"name": "Nthanthwe", "aliases": ["nthanthwe"], "icon": "🏗️"},
    {"name": "Njati", "aliases": ["njati"], "icon": "🏗️"},
    {"name": "Njati Extra", "aliases": ["njati extra", "njatiextra"], "icon": "🏗️"},
    {"name": "Khoma", "aliases": ["khoma"], "icon": "🏗️"},
    {"name": "Nkope", "aliases": ["nkope"], "icon": "🏗️"},
    {"name": "Lime", "aliases": ["lime"], "icon": "🧱"},
    {"name": "Duracrete", "aliases": ["duracrete"], "icon": "🏗️"},
]


def seed_cement_defaults(business: Business) -> Dict[str, int]:
    """
    Seed default cement products for a cement business.
    Creates products with zero stock (managers will stock in as needed).

    This function is idempotent - safe to call multiple times.

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
        for brand_spec in CEMENT_BRANDS:
            brand_name = brand_spec["name"]

            # Check if product already exists (case-insensitive)
            # Check all possible aliases
            existing = None
            for alias in [brand_name] + brand_spec.get("aliases", []):
                existing = MerchProduct.objects.filter(
                    business=business,
                    name__iexact=alias,
                    kind=BusinessKind.CEMENT,
                ).first()
                if existing:
                    break

            if existing:
                skipped += 1
                continue

            # Create new cement product (zero stock, managers will stock in)
            MerchProduct.objects.create(
                business=business,
                name=brand_name,
                kind=BusinessKind.CEMENT,
                category="cement",
                base_unit="bag",  # Standard cement unit (50kg bags)
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
