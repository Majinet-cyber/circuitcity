# inventory/mixed_retail_seed.py
"""
Mixed Retail seed data — departments and categories.

This module defines the canonical seeded catalog.
It is safe to run multiple times (idempotent).

Usage:
    from inventory.mixed_retail_seed import seed_mixed_retail_catalog
    seed_mixed_retail_catalog()  # Seeds all departments and categories globally
"""
from __future__ import annotations

SEED_CATALOG = [
    {
        "name": "Electronics",
        "slug": "electronics",
        "icon": "bi-phone",
        "sort_order": 10,
        "categories": [
            {"name": "Smartphones", "slug": "smartphones", "sort_order": 10},
            {"name": "Feature Phones", "slug": "feature-phones", "sort_order": 20},
            {"name": "Laptops", "slug": "laptops", "sort_order": 30},
            {"name": "Tablets", "slug": "tablets", "sort_order": 40},
            {"name": "TVs", "slug": "tvs", "sort_order": 50},
            {"name": "Speakers", "slug": "speakers", "sort_order": 60},
            {"name": "Radios", "slug": "radios", "sort_order": 70},
            {"name": "Earphones", "slug": "earphones", "sort_order": 80},
            {"name": "Headphones", "slug": "headphones", "sort_order": 90},
            {"name": "Chargers", "slug": "chargers", "sort_order": 100},
            {"name": "Power Banks", "slug": "power-banks", "sort_order": 110},
            {"name": "Cables", "slug": "cables", "sort_order": 120},
            {"name": "Memory Cards", "slug": "memory-cards", "sort_order": 130},
            {"name": "Flash Drives", "slug": "flash-drives", "sort_order": 140},
            {"name": "Phone Cases", "slug": "phone-cases", "sort_order": 150},
            {"name": "Screen Protectors", "slug": "screen-protectors", "sort_order": 160},
            {"name": "Smart Watches", "slug": "smart-watches", "sort_order": 170},
            {"name": "Routers", "slug": "routers", "sort_order": 180},
            {"name": "Batteries", "slug": "batteries", "sort_order": 190},
            {"name": "Remote Controls", "slug": "remote-controls", "sort_order": 200},
            {"name": "Electronic Accessories", "slug": "electronic-accessories", "sort_order": 210},
        ],
    },
    {
        "name": "Home Appliances",
        "slug": "home-appliances",
        "icon": "bi-house-gear",
        "sort_order": 20,
        "categories": [
            {"name": "Kettles", "slug": "kettles", "sort_order": 10},
            {"name": "Microwaves", "slug": "microwaves", "sort_order": 20},
            {"name": "Blenders", "slug": "blenders", "sort_order": 30},
            {"name": "Irons", "slug": "irons", "sort_order": 40},
            {"name": "Fans", "slug": "fans", "sort_order": 50},
            {"name": "Rice Cookers", "slug": "rice-cookers", "sort_order": 60},
            {"name": "Fridges", "slug": "fridges", "sort_order": 70},
            {"name": "Freezers", "slug": "freezers", "sort_order": 80},
            {"name": "Gas Cookers", "slug": "gas-cookers", "sort_order": 90},
            {"name": "Electric Cookers", "slug": "electric-cookers", "sort_order": 100},
            {"name": "Toasters", "slug": "toasters", "sort_order": 110},
            {"name": "Heaters", "slug": "heaters", "sort_order": 120},
            {"name": "Extension Leads", "slug": "extension-leads", "sort_order": 130},
            {"name": "Washing Machines", "slug": "washing-machines", "sort_order": 140},
            {"name": "Appliance Accessories", "slug": "appliance-accessories", "sort_order": 150},
        ],
    },
    {
        "name": "Furniture",
        "slug": "furniture",
        "icon": "bi-lamp",
        "sort_order": 30,
        "categories": [
            {"name": "Tables", "slug": "tables", "sort_order": 10},
            {"name": "Chairs", "slug": "chairs", "sort_order": 20},
            {"name": "Beds", "slug": "beds", "sort_order": 30},
            {"name": "Sofas", "slug": "sofas", "sort_order": 40},
            {"name": "Wardrobes", "slug": "wardrobes", "sort_order": 50},
            {"name": "TV Stands", "slug": "tv-stands", "sort_order": 60},
            {"name": "Desks", "slug": "desks", "sort_order": 70},
            {"name": "Shelves", "slug": "shelves", "sort_order": 80},
            {"name": "Cupboards", "slug": "cupboards", "sort_order": 90},
            {"name": "Mattresses", "slug": "mattresses", "sort_order": 100},
            {"name": "Stools", "slug": "stools", "sort_order": 110},
            {"name": "Dining Sets", "slug": "dining-sets", "sort_order": 120},
            {"name": "Office Chairs", "slug": "office-chairs", "sort_order": 130},
            {"name": "Coffee Tables", "slug": "coffee-tables", "sort_order": 140},
            {"name": "Bedside Tables", "slug": "bedside-tables", "sort_order": 150},
        ],
    },
    {
        "name": "Clothing & Fashion",
        "slug": "clothing-fashion",
        "icon": "bi-bag-heart",
        "sort_order": 40,
        "categories": [
            {"name": "Shirts", "slug": "shirts", "sort_order": 10},
            {"name": "T-Shirts", "slug": "t-shirts", "sort_order": 20},
            {"name": "Dresses", "slug": "dresses", "sort_order": 30},
            {"name": "Trousers", "slug": "trousers", "sort_order": 40},
            {"name": "Jeans", "slug": "jeans", "sort_order": 50},
            {"name": "Suits", "slug": "suits", "sort_order": 60},
            {"name": "Jackets", "slug": "jackets", "sort_order": 70},
            {"name": "Skirts", "slug": "skirts", "sort_order": 80},
            {"name": "Shoes", "slug": "shoes", "sort_order": 90},
            {"name": "Sandals", "slug": "sandals", "sort_order": 100},
            {"name": "Bags", "slug": "bags", "sort_order": 110},
            {"name": "Belts", "slug": "belts", "sort_order": 120},
            {"name": "Caps", "slug": "caps", "sort_order": 130},
            {"name": "Children's Wear", "slug": "childrens-wear", "sort_order": 140},
            {"name": "School Uniforms", "slug": "school-uniforms", "sort_order": 150},
            {"name": "Underwear", "slug": "underwear", "sort_order": 160},
            {"name": "Fabrics", "slug": "fabrics", "sort_order": 170},
            {"name": "Traditional Wear", "slug": "traditional-wear", "sort_order": 180},
            {"name": "Sweaters", "slug": "sweaters", "sort_order": 190},
            {"name": "Sportswear", "slug": "sportswear", "sort_order": 200},
        ],
    },
    {
        "name": "Beauty & Cosmetics",
        "slug": "beauty-cosmetics",
        "icon": "bi-stars",
        "sort_order": 50,
        "categories": [
            {"name": "Lotions", "slug": "lotions", "sort_order": 10},
            {"name": "Perfumes", "slug": "perfumes", "sort_order": 20},
            {"name": "Hair Products", "slug": "hair-products", "sort_order": 30},
            {"name": "Makeup", "slug": "makeup", "sort_order": 40},
            {"name": "Body Sprays", "slug": "body-sprays", "sort_order": 50},
            {"name": "Skin Care", "slug": "skin-care", "sort_order": 60},
            {"name": "Wigs", "slug": "wigs", "sort_order": 70},
            {"name": "Hair Extensions", "slug": "hair-extensions", "sort_order": 80},
            {"name": "Nail Products", "slug": "nail-products", "sort_order": 90},
            {"name": "Barber Products", "slug": "barber-products", "sort_order": 100},
            {"name": "Salon Products", "slug": "salon-products", "sort_order": 110},
        ],
    },
    {
        "name": "General Goods",
        "slug": "general-goods",
        "icon": "bi-box-seam",
        "sort_order": 60,
        "categories": [
            {"name": "Groceries", "slug": "groceries", "sort_order": 10},
            {"name": "Stationery", "slug": "stationery", "sort_order": 20},
            {"name": "Hardware Basics", "slug": "hardware-basics", "sort_order": 30},
            {"name": "Gift Items", "slug": "gift-items", "sort_order": 40},
            {"name": "Household Items", "slug": "household-items", "sort_order": 50},
            {"name": "Cleaning Products", "slug": "cleaning-products", "sort_order": 60},
            {"name": "Toys", "slug": "toys", "sort_order": 70},
            {"name": "Kitchenware", "slug": "kitchenware", "sort_order": 80},
            {"name": "Plasticware", "slug": "plasticware", "sort_order": 90},
            {"name": "Accessories", "slug": "accessories", "sort_order": 100},
            {"name": "Small Tools", "slug": "small-tools", "sort_order": 110},
        ],
    },
    {
        "name": "Services & Non-stock",
        "slug": "services-non-stock",
        "icon": "bi-wrench-adjustable",
        "sort_order": 70,
        "categories": [
            {"name": "Repairs", "slug": "repairs", "sort_order": 10},
            {"name": "Delivery", "slug": "delivery", "sort_order": 20},
            {"name": "Installation", "slug": "installation", "sort_order": 30},
            {"name": "Consultation", "slug": "consultation", "sort_order": 40},
            {"name": "Labour", "slug": "labour", "sort_order": 50},
            {"name": "Custom Service", "slug": "custom-service", "sort_order": 60},
            {"name": "Other Non-stock Income", "slug": "other-non-stock", "sort_order": 70},
        ],
    },
]


def seed_mixed_retail_catalog() -> dict:
    """
    Seed global (business=None) departments and categories from SEED_CATALOG.
    Idempotent — safe to run multiple times. Will not duplicate records.

    Returns:
        dict with 'depts_created', 'depts_skipped', 'cats_created', 'cats_skipped'
    """
    from inventory.models_mixed_retail import RetailDepartment, RetailCategory

    # Temporarily clear thread-local business ID so the _tenant_save wrapper does
    # not auto-assign the current request's business to these global (business=None)
    # seed records. Restore the original value after seeding completes.
    # NOTE: tenants.models and tenants.tenants use separate thread-locals; clear both.
    try:
        from tenants.models import get_current_business_id, set_current_business_id
        _prev_biz_id = get_current_business_id()
        set_current_business_id(None)
    except Exception:
        _prev_biz_id = None
        get_current_business_id = None
        set_current_business_id = None

    # Also clear the legacy tenants.tenants._local used by older middleware
    try:
        from tenants.tenants import _local as _legacy_local
        _legacy_prev = getattr(_legacy_local, "biz_id", None)
        _legacy_local.biz_id = None
    except Exception:
        _legacy_local = None
        _legacy_prev = None

    try:
        return _do_seed_mixed_retail_catalog(RetailDepartment, RetailCategory)
    finally:
        if set_current_business_id is not None:
            set_current_business_id(_prev_biz_id)
        if _legacy_local is not None:
            if _legacy_prev is not None:
                _legacy_local.biz_id = _legacy_prev
            else:
                try:
                    del _legacy_local.biz_id
                except AttributeError:
                    pass


def _do_seed_mixed_retail_catalog(RetailDepartment, RetailCategory) -> dict:
    depts_created = 0
    depts_skipped = 0
    cats_created = 0
    cats_skipped = 0

    for dept_data in SEED_CATALOG:
        dept, created = RetailDepartment.objects.get_or_create(
            business=None,
            slug=dept_data["slug"],
            defaults={
                "name": dept_data["name"],
                "icon": dept_data.get("icon", "bi-bag"),
                "sort_order": dept_data.get("sort_order", 0),
                "is_seeded": True,
                "is_enabled": True,
            },
        )
        if created:
            depts_created += 1
        else:
            depts_skipped += 1
            # Update sort_order and icon on existing seeded departments
            dept.sort_order = dept_data.get("sort_order", dept.sort_order)
            dept.icon = dept_data.get("icon", dept.icon)
            dept.save(update_fields=["sort_order", "icon"])

        for cat_data in dept_data.get("categories", []):
            cat, created = RetailCategory.objects.get_or_create(
                department=dept,
                business=None,
                slug=cat_data["slug"],
                defaults={
                    "name": cat_data["name"],
                    "sort_order": cat_data.get("sort_order", 0),
                    "is_seeded": True,
                    "is_enabled": True,
                },
            )
            if created:
                cats_created += 1
            else:
                cats_skipped += 1

    return {
        "depts_created": depts_created,
        "depts_skipped": depts_skipped,
        "cats_created": cats_created,
        "cats_skipped": cats_skipped,
    }


def get_departments_for_business(business) -> list:
    """
    Returns all departments available to a business:
    - Global seeded departments (business=None, is_enabled=True)
    - Business-specific custom departments
    """
    from inventory.models_mixed_retail import RetailDepartment
    from django.db.models import Q

    return list(
        RetailDepartment.objects.filter(
            Q(business=None, is_seeded=True) | Q(business=business)
        ).filter(is_enabled=True).order_by("sort_order", "name")
    )


def get_categories_for_department(department, business=None) -> list:
    """Returns all enabled categories for a department (global + business-specific)."""
    from inventory.models_mixed_retail import RetailCategory
    from django.db.models import Q

    qs = RetailCategory.objects.filter(department=department, is_enabled=True)
    if business:
        qs = qs.filter(Q(business=None) | Q(business=business))
    else:
        qs = qs.filter(business=None)
    return list(qs.order_by("sort_order", "name"))
