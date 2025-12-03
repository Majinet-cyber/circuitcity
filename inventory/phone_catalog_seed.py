# inventory/phone_catalog_seed.py
"""
Seed flagship phone products for PHONES businesses.

This module provides utilities to populate the PhoneProductCatalog with
curated, editable phone models for TECNO, ITEL, and SAMSUNG brands.

Each business gets their own copy of these products, which they can customize.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Dict, Any

from django.db import transaction

from tenants.models import Business


# Flagship phone definitions
FLAGSHIP_PHONES = [
    # TECNO
    {"brand": "TECNO", "model": "Spark 40", "ram": 4, "rom": 128},
    {"brand": "TECNO", "model": "Spark 40", "ram": 8, "rom": 256},
    {"brand": "TECNO", "model": "Pop 10", "ram": 2, "rom": 64},
    {"brand": "TECNO", "model": "Pop 10", "ram": 3, "rom": 64},
    {"brand": "TECNO", "model": "Pop 10", "ram": 4, "rom": 128},
    {"brand": "TECNO", "model": "Pop 10c", "ram": 2, "rom": 64},
    {"brand": "TECNO", "model": "Camon 40", "ram": 8, "rom": 256},
    
    # ITEL
    {"brand": "ITEL", "model": "City 100", "ram": 4, "rom": 128},
    {"brand": "ITEL", "model": "A90", "ram": 3, "rom": 128},
    {"brand": "ITEL", "model": "A80", "ram": 3, "rom": 128},
    {"brand": "ITEL", "model": "A50", "ram": 2, "rom": 64},
    {"brand": "ITEL", "model": "S25", "ram": 4, "rom": 128},
    
    # SAMSUNG (common models with sensible RAM/ROM)
    {"brand": "SAMSUNG", "model": "Galaxy A15", "ram": 4, "rom": 128},
    {"brand": "SAMSUNG", "model": "Galaxy A15", "ram": 6, "rom": 128},
    {"brand": "SAMSUNG", "model": "Galaxy A25", "ram": 6, "rom": 128},
    {"brand": "SAMSUNG", "model": "Galaxy A25", "ram": 8, "rom": 256},
    {"brand": "SAMSUNG", "model": "Galaxy A05s", "ram": 4, "rom": 64},
    {"brand": "SAMSUNG", "model": "Galaxy A05s", "ram": 4, "rom": 128},
]


def should_seed_phone_catalog(business: Business) -> bool:
    """
    Check if a PHONES business needs catalog seeding.
    
    Returns True if:
    - Business kind is PHONES
    - Business has no phone catalog products yet
    """
    if not business:
        return False
    
    # Check if business is PHONES vertical
    from inventory.business_kinds import BusinessKind
    if getattr(business, 'kind', None) != BusinessKind.PHONES:
        return False
    
    # Check if catalog is empty
    try:
        from inventory.models_phone_products import PhoneProductCatalog
        existing_count = PhoneProductCatalog.objects.filter(business=business).count()
        return existing_count == 0
    except Exception:
        # If model doesn't exist or import fails, skip seeding
        return False


@transaction.atomic
def seed_phone_catalog(business: Business, created_by=None) -> int:
    """
    Seed the phone catalog for a business with flagship models.
    
    Args:
        business: The Business instance to seed
        created_by: Optional User who triggered the seeding
    
    Returns:
        Number of products created
    """
    if not business:
        return 0
    
    try:
        from inventory.models_phone_products import PhoneProductCatalog
    except ImportError:
        return 0
    
    created_count = 0
    
    for phone_def in FLAGSHIP_PHONES:
        brand = phone_def["brand"]
        model = phone_def["model"]
        ram = phone_def["ram"]
        rom = phone_def["rom"]
        variant_label = f"{ram}+{rom}"
        
        # Create or update (in case of re-seeding)
        product, created = PhoneProductCatalog.objects.get_or_create(
            business=business,
            brand=brand,
            model_name=model,
            ram_gb=ram,
            rom_gb=rom,
            defaults={
                "variant_label": variant_label,
                "is_active": True,
                "is_flagship": True,
                "created_by": created_by,
            }
        )
        
        if created:
            created_count += 1
    
    return created_count


def get_catalog_for_business(business: Business, brand: str = None, active_only: bool = True):
    """
    Get phone catalog products for a business.
    
    Args:
        business: The Business instance
        brand: Optional brand filter (e.g., "TECNO", "ITEL", "SAMSUNG")
        active_only: If True, only return active products
    
    Returns:
        QuerySet of PhoneProductCatalog
    """
    try:
        from inventory.models_phone_products import PhoneProductCatalog
    except ImportError:
        return []
    
    qs = PhoneProductCatalog.objects.filter(business=business)
    
    if active_only:
        qs = qs.filter(is_active=True)
    
    if brand:
        qs = qs.filter(brand__iexact=brand.strip())
    
    return qs.order_by("brand", "model_name", "ram_gb", "rom_gb")


def get_brands_for_business(business: Business) -> List[str]:
    """
    Get list of unique brands in a business's catalog.
    
    Returns:
        List of brand names (e.g., ["ITEL", "SAMSUNG", "TECNO"])
    """
    try:
        from inventory.models_phone_products import PhoneProductCatalog
    except ImportError:
        return []
    
    brands = (
        PhoneProductCatalog.objects
        .filter(business=business, is_active=True)
        .values_list("brand", flat=True)
        .distinct()
        .order_by("brand")
    )
    
    return list(brands)


def get_models_for_brand(business: Business, brand: str) -> List[Dict[str, Any]]:
    """
    Get all model variants for a specific brand.
    
    Returns:
        List of dicts with model info:
        [
            {
                "id": 1,
                "model_name": "Spark 40",
                "variant_label": "4+128",
                "ram_gb": 4,
                "rom_gb": 128,
                "default_cost_price": Decimal("450000.00"),
                "default_selling_price": Decimal("550000.00"),
            },
            ...
        ]
    """
    try:
        from inventory.models_phone_products import PhoneProductCatalog
    except ImportError:
        return []
    
    products = PhoneProductCatalog.objects.filter(
        business=business,
        brand__iexact=brand.strip(),
        is_active=True
    ).order_by("model_name", "ram_gb", "rom_gb")
    
    return [
        {
            "id": p.id,
            "model_name": p.model_name,
            "variant_label": p.variant_label,
            "ram_gb": p.ram_gb,
            "rom_gb": p.rom_gb,
            "default_cost_price": p.default_cost_price,
            "default_selling_price": p.default_selling_price,
            "display_name": p.display_name,
        }
        for p in products
    ]

