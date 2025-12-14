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


# Category-to-suggested products mapping for Stock In page
# This provides quick-fill suggestions when a category is selected
CATEGORY_SUGGESTIONS = {
    # Cosmetics & Personal Care
    "skin_care": [
        {"name": "Nivea Soft Cream", "icon": "✨"},
        {"name": "Nivea Men Face Wash", "icon": "🧴"},
        {"name": "Garnier Micellar Water", "icon": "💧"},
        {"name": "Dove Beauty Cream", "icon": "🕊️"},
        {"name": "CeraVe Moisturising Cream", "icon": "🌟"},
        {"name": "Neutrogena Hydro Boost", "icon": "💎"},
        {"name": "Vaseline Body Lotion", "icon": "✨"},
        {"name": "Olay Total Effects", "icon": "🌸"},
    ],
    "beauty_makeup": [
        {"name": "Pure Black Perfume", "icon": "🎩"},
        {"name": "Chris Adams Perfume", "icon": "💐"},
        {"name": "Rasasi (Arabic)", "icon": "🏺"},
        {"name": "Lattafa Perfume", "icon": "🌹"},
        {"name": "Ajmal Perfume", "icon": "✨"},
        {"name": "Designer Inspired Fragrance", "icon": "💎"},
    ],
    "hair_care": [
        {"name": "Dove Shampoo", "icon": "🧴"},
        {"name": "Garnier Fructis", "icon": "🍊"},
        {"name": "Pantene Pro-V", "icon": "✨"},
        {"name": "TRESemmé Shampoo", "icon": "💫"},
        {"name": "Head & Shoulders", "icon": "❄️"},
        {"name": "Sunsilk Hair Conditioner", "icon": "🌺"},
    ],
    "baby_care": [
        {"name": "Johnson's Baby Oil", "icon": "👶"},
        {"name": "Johnson's Baby Lotion", "icon": "🍼"},
        {"name": "Sudocrem Nappy Cream", "icon": "🛡️"},
        {"name": "Pampers Diapers", "icon": "🧷"},
        {"name": "Cetaphil Baby Wash", "icon": "🧼"},
    ],
    "oral_care": [
        {"name": "Colgate Total", "icon": "🦷"},
        {"name": "Oral-B Toothbrush", "icon": "🪥"},
        {"name": "Sensodyne Toothpaste", "icon": "❄️"},
        {"name": "Close Up Mouthwash", "icon": "💧"},
    ],
    "personal_care": [
        {"name": "Dove Body Wash", "icon": "🧼"},
        {"name": "Nivea Roll-On Deodorant", "icon": "🌀"},
        {"name": "Palmolive Soap", "icon": "🧴"},
        {"name": "Imperial Leather Soap", "icon": "👑"},
        {"name": "Vaseline Petroleum Jelly", "icon": "✨"},
    ],
    
    # Medicine Categories
    "analgesic": [
        {"name": "Paracetamol 500mg", "icon": "💊"},
        {"name": "Ibuprofen 400mg", "icon": "💊"},
        {"name": "Aspirin 75mg", "icon": "💊"},
        {"name": "Diclofenac 50mg", "icon": "💊"},
    ],
    "antibiotic": [
        {"name": "Amoxicillin 500mg", "icon": "💊"},
        {"name": "Azithromycin 250mg", "icon": "💊"},
        {"name": "Ciprofloxacin 500mg", "icon": "💊"},
        {"name": "Metronidazole 400mg", "icon": "💊"},
    ],
    "vitamin": [
        {"name": "Vitamin C 1000mg", "icon": "🍊"},
        {"name": "Zinc Tablets", "icon": "⚡"},
        {"name": "Multivitamin Complex", "icon": "💪"},
        {"name": "Vitamin D3", "icon": "☀️"},
        {"name": "Calcium + Vitamin D", "icon": "🦴"},
    ],
    "antipyretic": [
        {"name": "Paracetamol 500mg", "icon": "🌡️"},
        {"name": "Ibuprofen Suspension", "icon": "💊"},
        {"name": "Aspirin 300mg", "icon": "💊"},
    ],
    "antihistamine": [
        {"name": "Cetirizine 10mg", "icon": "💊"},
        {"name": "Loratadine 10mg", "icon": "💊"},
        {"name": "Chlorpheniramine 4mg", "icon": "💊"},
    ],
    "respiratory": [
        {"name": "Salbutamol Inhaler", "icon": "💨"},
        {"name": "Cough Syrup", "icon": "🍯"},
        {"name": "Lozenges", "icon": "🍬"},
    ],
    "gastrointestinal": [
        {"name": "Omeprazole 20mg", "icon": "💊"},
        {"name": "Antacid Tablets", "icon": "💊"},
        {"name": "Loperamide 2mg", "icon": "💊"},
        {"name": "ORS Sachets", "icon": "💧"},
    ],
}


def get_suggestions_for_category(category: str) -> list[dict]:
    """
    Get product suggestions for a specific category.
    Returns list of dicts with 'name' and 'icon' keys.
    """
    return CATEGORY_SUGGESTIONS.get(category, [])


def get_all_categories_with_icons() -> dict:
    """
    Get all categories with their icons for the category picker cards.
    Returns dict mapping category code to display info.
    """
    return {
        # Cosmetics & Personal Care
        "skin_care": {"label": "Skin Care", "icon": "✨", "color": "#ec4899"},
        "beauty_makeup": {"label": "Perfume & Beauty", "icon": "💄", "color": "#a855f7"},
        "hair_care": {"label": "Hair Care", "icon": "💇", "color": "#8b5cf6"},
        "baby_care": {"label": "Baby Care", "icon": "👶", "color": "#f97316"},
        "oral_care": {"label": "Oral Care", "icon": "🦷", "color": "#06b6d4"},
        "personal_care": {"label": "Personal Care", "icon": "🧴", "color": "#14b8a6"},
        
        # Medicine (Top categories)
        "analgesic": {"label": "Pain Relief", "icon": "💊", "color": "#ef4444"},
        "antibiotic": {"label": "Antibiotic", "icon": "🛡️", "color": "#3b82f6"},
        "vitamin": {"label": "Vitamins", "icon": "💪", "color": "#10b981"},
        "antipyretic": {"label": "Fever Relief", "icon": "🌡️", "color": "#f59e0b"},
        "antihistamine": {"label": "Allergy", "icon": "🌸", "color": "#ec4899"},
        "respiratory": {"label": "Respiratory", "icon": "💨", "color": "#06b6d4"},
        "gastrointestinal": {"label": "Digestive", "icon": "🩺", "color": "#8b5cf6"},
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

