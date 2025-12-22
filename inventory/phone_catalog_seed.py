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


# Flagship phone definitions - 7 BRANDS (Latest models + Malawi common + Wholesale 12/08)
# Updated with wholesale list from "wholesale 12 08 (2).xlsx"
# Includes Tecno, Itel, Samsung, Redmi models commonly sold in Malawi
FLAGSHIP_PHONES = [
    # ========== TECNO (Latest 2024-2025 + Malawi common + WHOLESALE LIST) ==========
    # CAMON 40 Series (Latest + Wholesale)
    {"brand": "TECNO", "model": "CAMON 40", "ram": 8, "rom": 256},  # Wholesale
    {"brand": "TECNO", "model": "CAMON 40 Pro", "ram": 8, "rom": 256},  # Wholesale
    {"brand": "TECNO", "model": "CAMON 40 Pro 5G", "ram": 8, "rom": 256},
    {"brand": "TECNO", "model": "CAMON 40 Premier 5G", "ram": 8, "rom": 256},
    
    # SPARK 40 Series (Latest + Wholesale)
    {"brand": "TECNO", "model": "SPARK 40", "ram": 4, "rom": 128},  # Wholesale
    {"brand": "TECNO", "model": "SPARK 40 Pro", "ram": 8, "rom": 256},  # Wholesale
    {"brand": "TECNO", "model": "SPARK 40 Pro+", "ram": 8, "rom": 256},  # Wholesale (SPARK40 PRO+)
    {"brand": "TECNO", "model": "SPARK 40 5G", "ram": 8, "rom": 256},
    
    # SPARK 30 Series (Wholesale)
    {"brand": "TECNO", "model": "SPARK 30", "ram": 4, "rom": 128},  # Wholesale
    {"brand": "TECNO", "model": "SPARK 30", "ram": 8, "rom": 256},  # Wholesale (2nd variant)
    
    # POVA 7 Series (Latest)
    {"brand": "TECNO", "model": "POVA 7", "ram": 8, "rom": 128},
    {"brand": "TECNO", "model": "POVA 7 Pro 5G", "ram": 8, "rom": 256},
    
    # POP Series (Malawi Common + Wholesale)
    {"brand": "TECNO", "model": "POP 10", "ram": 4, "rom": 128},  # Wholesale
    {"brand": "TECNO", "model": "POP 10C", "ram": 4, "rom": 128},  # Wholesale (POP 10C 128+4)
    {"brand": "TECNO", "model": "POP 10", "ram": 2, "rom": 64},  # Legacy
    {"brand": "TECNO", "model": "POVA Neo 6", "ram": 8, "rom": 128},
    
    # ========== ITEL (Latest 2 years + Malawi common + WHOLESALE LIST) ==========
    # S Series (Latest)
    {"brand": "ITEL", "model": "S25 Ultra", "ram": 8, "rom": 256},
    {"brand": "ITEL", "model": "S25", "ram": 4, "rom": 128},
    {"brand": "ITEL", "model": "RS4", "ram": 8, "rom": 256},
    {"brand": "ITEL", "model": "S24", "ram": 4, "rom": 128},
    {"brand": "ITEL", "model": "S23+", "ram": 8, "rom": 128},
    {"brand": "ITEL", "model": "S23", "ram": 4, "rom": 128},
    
    # P Series (Latest + Wholesale)
    {"brand": "ITEL", "model": "Power 70", "ram": 8, "rom": 256},
    {"brand": "ITEL", "model": "P65C", "ram": 4, "rom": 128},  # Wholesale
    {"brand": "ITEL", "model": "P65", "ram": 4, "rom": 128},
    {"brand": "ITEL", "model": "P55 5G", "ram": 8, "rom": 128},
    
    # A Series (Latest + Wholesale)
    {"brand": "ITEL", "model": "A100C", "ram": 2, "rom": 64},  # Wholesale
    {"brand": "ITEL", "model": "A100C", "ram": 3, "rom": 64},  # Legacy
    {"brand": "ITEL", "model": "A90", "ram": 3, "rom": 64},  # Wholesale
    {"brand": "ITEL", "model": "A90", "ram": 3, "rom": 128},  # Wholesale (2nd variant)
    {"brand": "ITEL", "model": "A80", "ram": 3, "rom": 128},
    
    # V Series (Wholesale - non-standard specs handled as custom/other)
    {"brand": "ITEL", "model": "V40", "ram": 4, "rom": 64},  # Wholesale V40S 64+4 (promoted to standard)
    # NOTE: V40 32+2 and V40S 32+3 excluded from primary list (non-standard specs)
    # Will be available via "Custom/Other spec" option in wizard
    
    # Malawi Common (budget-friendly)
    {"brand": "ITEL", "model": "A50", "ram": 2, "rom": 64},
    {"brand": "ITEL", "model": "City 100", "ram": 4, "rom": 128},
    
    # ========== SAMSUNG (Latest 2 years + WHOLESALE LIST) ==========
    # Galaxy S25 Series (Latest 2025)
    {"brand": "SAMSUNG", "model": "Galaxy S25 Ultra", "ram": 12, "rom": 256},
    {"brand": "SAMSUNG", "model": "Galaxy S25+", "ram": 8, "rom": 256},
    {"brand": "SAMSUNG", "model": "Galaxy S25", "ram": 8, "rom": 128},
    
    # Galaxy S24 Series (2024)
    {"brand": "SAMSUNG", "model": "Galaxy S24 Ultra", "ram": 12, "rom": 256},
    {"brand": "SAMSUNG", "model": "Galaxy S24+", "ram": 8, "rom": 256},
    {"brand": "SAMSUNG", "model": "Galaxy S24", "ram": 8, "rom": 128},
    
    # Galaxy Foldables (Latest)
    {"brand": "SAMSUNG", "model": "Galaxy Z Fold6", "ram": 12, "rom": 256},
    {"brand": "SAMSUNG", "model": "Galaxy Z Flip6", "ram": 8, "rom": 256},
    
    # Galaxy A Series (Mid-range + Wholesale)
    {"brand": "SAMSUNG", "model": "Galaxy A56", "ram": 8, "rom": 256},  # Wholesale
    {"brand": "SAMSUNG", "model": "Galaxy A55 5G", "ram": 8, "rom": 128},
    {"brand": "SAMSUNG", "model": "Galaxy A36", "ram": 8, "rom": 256},  # Wholesale
    {"brand": "SAMSUNG", "model": "Galaxy A35 5G", "ram": 8, "rom": 128},
    {"brand": "SAMSUNG", "model": "Galaxy A16", "ram": 4, "rom": 128},  # Wholesale
    {"brand": "SAMSUNG", "model": "Galaxy A15", "ram": 4, "rom": 128},  # Wholesale
    {"brand": "SAMSUNG", "model": "Galaxy A06", "ram": 4, "rom": 128},  # Wholesale
    {"brand": "SAMSUNG", "model": "Galaxy A05", "ram": 4, "rom": 64},  # Wholesale
    # NOTE: A03 32+2 excluded from primary list (non-standard) - available via Custom/Other
    
    # Galaxy M/F Series (Wholesale)
    {"brand": "SAMSUNG", "model": "Galaxy M05", "ram": 4, "rom": 64},  # Wholesale
    {"brand": "SAMSUNG", "model": "Galaxy F05", "ram": 4, "rom": 64},  # Wholesale
    
    # ========== IPHONE (Latest 2 years) ==========
    # iPhone 16 Series (Latest 2024)
    {"brand": "IPHONE", "model": "iPhone 16 Pro Max", "ram": 8, "rom": 256},
    {"brand": "IPHONE", "model": "iPhone 16 Pro", "ram": 8, "rom": 128},
    {"brand": "IPHONE", "model": "iPhone 16 Plus", "ram": 8, "rom": 128},
    {"brand": "IPHONE", "model": "iPhone 16", "ram": 8, "rom": 128},
    
    # iPhone 15 Series (2023)
    {"brand": "IPHONE", "model": "iPhone 15 Pro Max", "ram": 8, "rom": 256},
    {"brand": "IPHONE", "model": "iPhone 15 Pro", "ram": 8, "rom": 128},
    {"brand": "IPHONE", "model": "iPhone 15 Plus", "ram": 8, "rom": 128},
    {"brand": "IPHONE", "model": "iPhone 15", "ram": 8, "rom": 128},
    
    # ========== HUAWEI (Latest 2 years) ==========
    # Pura 70 Series (Latest 2024)
    {"brand": "HUAWEI", "model": "Pura 70 Ultra", "ram": 16, "rom": 256},
    {"brand": "HUAWEI", "model": "Pura 70 Pro+", "ram": 12, "rom": 256},
    {"brand": "HUAWEI", "model": "Pura 70 Pro", "ram": 12, "rom": 256},
    {"brand": "HUAWEI", "model": "Pura 70", "ram": 8, "rom": 256},
    
    # Mate 60 Series (2024)
    {"brand": "HUAWEI", "model": "Mate 60 RS Ultimate", "ram": 16, "rom": 256},
    {"brand": "HUAWEI", "model": "Mate 60 Pro+", "ram": 12, "rom": 256},
    {"brand": "HUAWEI", "model": "Mate 60 Pro", "ram": 12, "rom": 256},
    {"brand": "HUAWEI", "model": "Mate 60", "ram": 8, "rom": 256},
    
    # Foldables (Latest)
    {"brand": "HUAWEI", "model": "Mate XT Ultimate Design", "ram": 16, "rom": 256},
    {"brand": "HUAWEI", "model": "Mate X5", "ram": 12, "rom": 256},
    
    # ========== REDMI/Xiaomi (Latest 2 years + WHOLESALE LIST) ==========
    # Redmi Note 14 Series (Latest 2024-2025 + Wholesale)
    {"brand": "REDMI", "model": "Redmi Note 14 Pro+ 5G", "ram": 8, "rom": 256},
    {"brand": "REDMI", "model": "Redmi Note 14 Pro 5G", "ram": 8, "rom": 256},
    {"brand": "REDMI", "model": "Redmi Note 14 5G", "ram": 8, "rom": 128},
    {"brand": "REDMI", "model": "Redmi Note 14 (4G)", "ram": 8, "rom": 128},
    {"brand": "REDMI", "model": "NOTE 14", "ram": 8, "rom": 256},  # Wholesale (simplified name)
    
    # Redmi Note 13 Series (2023-2024)
    {"brand": "REDMI", "model": "Redmi Note 13 Pro+ 5G", "ram": 8, "rom": 256},
    {"brand": "REDMI", "model": "Redmi Note 13 Pro 5G", "ram": 8, "rom": 256},
    {"brand": "REDMI", "model": "Redmi Note 13", "ram": 8, "rom": 128},
    
    # Redmi Numbered Series (Latest + Wholesale)
    {"brand": "REDMI", "model": "15C", "ram": 4, "rom": 128},  # Wholesale
    {"brand": "REDMI", "model": "15C", "ram": 8, "rom": 256},  # Wholesale (2nd variant)
    {"brand": "REDMI", "model": "14C", "ram": 4, "rom": 128},
    {"brand": "REDMI", "model": "13", "ram": 8, "rom": 128},
    {"brand": "REDMI", "model": "13C", "ram": 4, "rom": 128},
    
    # Redmi A Series (Wholesale)
    {"brand": "REDMI", "model": "A3", "ram": 3, "rom": 64},  # Wholesale
    {"brand": "REDMI", "model": "A3", "ram": 4, "rom": 128},  # Wholesale (2nd variant)
    {"brand": "REDMI", "model": "A3X", "ram": 4, "rom": 128},  # Wholesale
    {"brand": "REDMI", "model": "A4 5G", "ram": 4, "rom": 128},  # Wholesale
    {"brand": "REDMI", "model": "A5", "ram": 3, "rom": 64},  # Wholesale
    {"brand": "REDMI", "model": "A5", "ram": 4, "rom": 128},  # Wholesale (2nd variant)
    
    # Redmi PAD (Wholesale)
    {"brand": "REDMI", "model": "PAD 2", "ram": 8, "rom": 256},  # Wholesale
    
    # ========== GOOGLE PIXEL (Latest 2 years) ==========
    # Pixel 10 Series (Latest 2025 - projected)
    {"brand": "GOOGLE PIXEL", "model": "Pixel 10", "ram": 8, "rom": 128},
    {"brand": "GOOGLE PIXEL", "model": "Pixel 10 Pro", "ram": 12, "rom": 256},
    {"brand": "GOOGLE PIXEL", "model": "Pixel 10 Pro XL", "ram": 12, "rom": 256},
    {"brand": "GOOGLE PIXEL", "model": "Pixel 10 Pro Fold", "ram": 12, "rom": 256},
    
    # Pixel 9 Series (2024)
    {"brand": "GOOGLE PIXEL", "model": "Pixel 9", "ram": 8, "rom": 128},
    {"brand": "GOOGLE PIXEL", "model": "Pixel 9 Pro", "ram": 12, "rom": 256},
    {"brand": "GOOGLE PIXEL", "model": "Pixel 9 Pro XL", "ram": 12, "rom": 256},
    {"brand": "GOOGLE PIXEL", "model": "Pixel 9 Pro Fold", "ram": 12, "rom": 256},
    
    # Pixel A Series (Budget)
    {"brand": "GOOGLE PIXEL", "model": "Pixel 9a", "ram": 8, "rom": 128},
    {"brand": "GOOGLE PIXEL", "model": "Pixel 8a", "ram": 8, "rom": 128},
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

