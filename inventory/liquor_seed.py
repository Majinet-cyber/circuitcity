"""
Liquor product seeding for Malawi market.
Creates default categories and products for new liquor businesses.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from tenants.models import Business


# Default product catalog for Malawi liquor businesses
MALAWI_LIQUOR_CATALOG = {
    "beer": {
        "name": "Beer",
        "has_shots": False,
        "products": [
            {"name": "Kuche Kuche", "price": 800, "cost": 600},
            {"name": "Special (Carlsberg Special)", "price": 1000, "cost": 750},
            {"name": "Castel", "price": 900, "cost": 700},
            {"name": "Chill", "price": 850, "cost": 650},
        ],
    },
    "cider": {
        "name": "Cider",
        "has_shots": False,
        "products": [
            {"name": "Savanna Dry", "price": 1200, "cost": 900},
            {"name": "Savanna Light", "price": 1200, "cost": 900},
            {"name": "Hunters Dry", "price": 1100, "cost": 850},
            {"name": "Hunters Gold", "price": 1100, "cost": 850},
            {"name": "Esprit", "price": 1000, "cost": 800},
        ],
    },
    "wine": {
        "name": "Wine",
        "has_shots": False,
        "products": [
            {"name": "Drostdy-Hof Red", "price": 3500, "cost": 2800},
            {"name": "Drostdy-Hof White", "price": 3500, "cost": 2800},
            {"name": "4th Street Red", "price": 2500, "cost": 2000},
            {"name": "4th Street White", "price": 2500, "cost": 2000},
        ],
    },
    "spirits": {
        "name": "Spirits",
        "has_shots": True,
        "products": [
            {"name": "Malawi Gin", "price": 8000, "cost": 6000, "shot_price": 500, "shots_per_bottle": 20},
            {"name": "Premier Brandy", "price": 7500, "cost": 5500, "shot_price": 500, "shots_per_bottle": 20},
            {"name": "Amarula", "price": 12000, "cost": 9000, "shot_price": 700, "shots_per_bottle": 18},
            {"name": "Kachasu (Local Spirit)", "price": 5000, "cost": 3500, "shot_price": 300, "shots_per_bottle": 25},
        ],
    },
    "whiskey": {
        "name": "Whiskey",
        "has_shots": True,
        "products": [
            {"name": "Jameson", "price": 15000, "cost": 12000, "shot_price": 1000, "shots_per_bottle": 20},
            {"name": "Jack Daniel's", "price": 18000, "cost": 14000, "shot_price": 1200, "shots_per_bottle": 20},
            {
                "name": "Johnnie Walker Red Label",
                "price": 16000,
                "cost": 13000,
                "shot_price": 1000,
                "shots_per_bottle": 20,
            },
            {
                "name": "Johnnie Walker Black Label",
                "price": 25000,
                "cost": 20000,
                "shot_price": 1500,
                "shots_per_bottle": 20,
            },
            {"name": "Grants", "price": 12000, "cost": 9500, "shot_price": 800, "shots_per_bottle": 20},
        ],
    },
}


@transaction.atomic
def create_default_liquor_catalog(business: Business, location: Optional = None, overwrite: bool = False) -> dict:
    """
    Create default liquor product catalog for a business.

    Args:
        business: The business to create products for
        location: Optional location to associate products with
        overwrite: If True, will update existing products. If False, skips existing.

    Returns:
        Dictionary with counts of created/updated products by category
    """
    if not business:
        raise ValueError("Business is required")

    results = {"created": 0, "updated": 0, "skipped": 0, "categories": {}}

    for category_key, category_data in MALAWI_LIQUOR_CATALOG.items():
        category_name = category_data["name"]
        has_shots = category_data["has_shots"]
        products_data = category_data["products"]

        category_results = {"created": 0, "updated": 0, "skipped": 0}

        for product_data in products_data:
            product_name = product_data["name"]

            # Check if product already exists
            existing = MerchProduct.objects.filter(
                business=business, kind=BusinessKind.LIQUOR, name=product_name, category__iexact=category_key
            ).first()

            if existing and not overwrite:
                category_results["skipped"] += 1
                results["skipped"] += 1
                continue

            # Prepare product fields
            product_fields = {
                "business": business,
                "kind": BusinessKind.LIQUOR,
                "name": product_name,
                "category": category_key,
                "price_per_bottle": Decimal(str(product_data["price"])),
                "cost_per_bottle": Decimal(str(product_data.get("cost", 0))),
                "is_active": True,
                "track_inventory": True,
                "has_shots": has_shots,
                # MALAWI STANDARDS: Beer=20 bottles/crate, Cider=6-pack only, Wine=varies
                "bottles_per_crate": 6 if category_key == "cider" else 20,
                "supports_crates": category_key
                in ["beer", "cider", "wine"],  # Beer/cider/wine support crates; spirits don't
            }

            # Add location if provided
            if location:
                product_fields["location"] = location

            # Add shot-specific fields
            if has_shots and "shot_price" in product_data:
                product_fields["price_per_shot"] = Decimal(str(product_data["shot_price"]))
                product_fields["cost_per_shot"] = Decimal(str(product_data.get("shot_price", 0))) * Decimal(
                    "0.6"
                )  # Approximate cost
                product_fields["shots_per_bottle"] = product_data.get("shots_per_bottle", 20)

            if existing:
                # Update existing product
                for key, value in product_fields.items():
                    if key != "business":  # Don't update business FK
                        setattr(existing, key, value)
                existing.save()
                category_results["updated"] += 1
                results["updated"] += 1
            else:
                # Create new product
                MerchProduct.objects.create(**product_fields)
                category_results["created"] += 1
                results["created"] += 1

        results["categories"][category_name] = category_results

    return results


def should_seed_liquor_products(business: Business) -> bool:
    """
    Check if a business should be seeded with default liquor products.
    Returns True if the business has no liquor products yet.
    """
    if not business:
        return False

    liquor_count = MerchProduct.objects.filter(business=business, kind=BusinessKind.LIQUOR, is_active=True).count()

    return liquor_count == 0


def get_catalog_summary() -> dict:
    """
    Get a summary of the default catalog.
    Useful for displaying what will be created.
    """
    summary = {"total_categories": len(MALAWI_LIQUOR_CATALOG), "total_products": 0, "categories": {}}

    for category_key, category_data in MALAWI_LIQUOR_CATALOG.items():
        category_name = category_data["name"]
        product_count = len(category_data["products"])
        summary["total_products"] += product_count
        summary["categories"][category_name] = {
            "key": category_key,
            "product_count": product_count,
            "has_shots": category_data["has_shots"],
        }

    return summary
