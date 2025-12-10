# inventory/pharmacy_constants.py
"""
Pharmacy and Cosmetics constants, categories, and brand presets.

NOTE: PharmacyCategory enum is defined in models_pharmacy.py (source of truth).
Import from there, not here. This file contains only helper constants and functions.
"""

from django.db import models


# Premium cosmetics brands for quick selection
# Keys match the category values from PharmacyCategory in models_pharmacy.py
COSMETICS_BRANDS = {
    "skin_care": [
        "Nivea",
        "Garnier",
        "Dove",
        "CeraVe",
        "Olay",
        "Vaseline",
        "Neutrogena",
        "L'Oréal",
    ],
    "personal_care": [  # Personal care includes body care products
        "Dove",
        "Nivea",
        "Vaseline",
        "Palmolive",
        "Johnson & Johnson",
        "Imperial Leather",
    ],
    "hair_care": [
        "Pantene",
        "Head & Shoulders",
        "Garnier",
        "L'Oréal",
        "Tresemmé",
        "Sunsilk",
    ],
    "beauty_makeup": [  # Perfumes fall under beauty & makeup
        "Pure Black",
        "Chris Adams",
        "Lattafa",
        "Rasasi",
        "Ard Al Zaafaran",
        "Arabic Collection",
        "Designer Inspired",
    ],
    "baby_care": [
        "Johnson's Baby",
        "Pampers",
        "Huggies",
        "Cetaphil Baby",
    ],
    "oral_care": [
        "Colgate",
        "Oral-B",
        "Sensodyne",
        "Close Up",
    ],
}


def get_brands_for_category(category: str) -> list[str]:
    """Get brand list for a specific category."""
    return COSMETICS_BRANDS.get(category, [])


def get_all_brands() -> list[str]:
    """Get all unique brands across all categories."""
    brands = set()
    for brand_list in COSMETICS_BRANDS.values():
        brands.update(brand_list)
    return sorted(brands)


# Gamification badge conditions
def calculate_pharmacy_badges(pharmacy_data: dict) -> list[dict]:
    """
    Calculate gamification badges for pharmacy dashboard.
    
    Args:
        pharmacy_data: Dictionary with keys like:
            - near_expiry_count: int
            - cosmetics_revenue_pct: float (0-100)
            - batches_count: int
            - etc.
    
    Returns:
        List of badge dictionaries with keys: name, icon, description, earned
    """
    badges = []
    
    # Fresh Stock Hero - No near-expiry batches
    badges.append({
        "name": "Fresh Stock Hero",
        "icon": "✨",
        "description": "All medicine batches have more than 30 days to expiry",
        "earned": pharmacy_data.get("near_expiry_count", 999) == 0,
    })
    
    # Cosmetics Champion - Cosmetics revenue >= 25%
    cosmetics_pct = pharmacy_data.get("cosmetics_revenue_pct", 0)
    badges.append({
        "name": "Cosmetics Champion",
        "icon": "💄",
        "description": "Cosmetics revenue is 25% or more of total pharmacy revenue",
        "earned": cosmetics_pct >= 25,
    })
    
    # Batch Guardian - All batches have 30+ days to expiry
    badges.append({
        "name": "Batch Guardian",
        "icon": "🛡️",
        "description": "Managing batches perfectly with no near-expiry items",
        "earned": pharmacy_data.get("all_batches_fresh", False),
    })
    
    # Stock Master - Has at least 20 active batches
    badges.append({
        "name": "Stock Master",
        "icon": "📦",
        "description": "Maintaining healthy inventory with 20+ active batches",
        "earned": pharmacy_data.get("batches_count", 0) >= 20,
    })
    
    return badges

