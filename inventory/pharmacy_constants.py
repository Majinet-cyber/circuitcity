# inventory/pharmacy_constants.py
"""
Pharmacy and Cosmetics constants, categories, and brand presets.

NOTE: PharmacyCategory enum is defined in models_pharmacy.py (source of truth).
Import from there, not here. This file contains only helper constants and functions.
"""

from django.db import models


# ==============================================================================
# GAMIFIED WIZARD: Top-Level Categories (Malawi Systematic)
# ==============================================================================

PHARMACY_TOP_CATEGORIES = [
    # ── Core Medicines ──
    {"key": "medicines", "label": "Medicines", "icon": "💊", "color": "#3b82f6",
     "description": "Prescription & common medicines"},
    {"key": "otc", "label": "OTC Products", "icon": "🛒", "color": "#0ea5e9",
     "description": "Over-the-counter — no prescription needed"},
    {"key": "first_aid", "label": "First Aid", "icon": "🩹", "color": "#ef4444",
     "description": "Bandages, antiseptics, wound care"},
    {"key": "chronic", "label": "Chronic Care", "icon": "❤️", "color": "#dc2626",
     "description": "BP, diabetes, long-term treatments"},
    {"key": "cold_flu", "label": "Cold & Flu", "icon": "🤧", "color": "#06b6d4",
     "description": "Cough, flu, sore throat"},
    {"key": "stomach", "label": "Stomach / Digestive", "icon": "🩺", "color": "#8b5cf6",
     "description": "Antacids, ORS, digestive health"},
    {"key": "vitamins", "label": "Vitamins & Supplements", "icon": "💪", "color": "#10b981",
     "description": "Vitamins C, D, multivitamins"},
    {"key": "womens_health", "label": "Women's Health", "icon": "💝", "color": "#f472b6",
     "description": "Contraception, maternity, pads"},
    {"key": "child_health", "label": "Child & Baby Care", "icon": "👶", "color": "#fbbf24",
     "description": "Paediatric syrups, baby products"},
    # ── Beauty & Personal Care ──
    {"key": "skincare", "label": "Skincare", "icon": "✨", "color": "#14b8a6",
     "description": "Lotions, creams, lip care, sunscreen"},
    {"key": "cosmetics", "label": "Cosmetics & Makeup", "icon": "💄", "color": "#a855f7",
     "description": "Perfumes, makeup, beauty products"},
    {"key": "personal_care", "label": "Personal Care", "icon": "🧴", "color": "#f59e0b",
     "description": "Soap, deodorant, toothpaste, shampoo"},
    {"key": "hygiene", "label": "Hygiene Products", "icon": "🧼", "color": "#6366f1",
     "description": "Sanitizers, feminine hygiene, wipes"},
    # ── Other ──
    {"key": "allergy", "label": "Allergy", "icon": "🌸", "color": "#ec4899",
     "description": "Antihistamines, allergy relief"},
    {"key": "other", "label": "Other / Custom", "icon": "📦", "color": "#94a3b8",
     "description": "Anything not listed above — enter custom name"},
]

# Medicine Subcategories (when user selects "Medicines")
MEDICINE_SUBCATEGORIES = [
    {"key": "painkillers", "label": "Pain Killers", "icon": "💊"},
    {"key": "antibiotics", "label": "Antibiotics", "icon": "🛡️"},
    {"key": "antimalarials", "label": "Antimalarials", "icon": "🦟"},
    {"key": "cough_throat", "label": "Cough & Sore Throat", "icon": "🍯"},
    {"key": "deworming", "label": "Deworming", "icon": "🪱"},
    {"key": "eye_ear", "label": "Eye/Ear Drops", "icon": "👁️"},
    {"key": "skin_treatments", "label": "Skin Treatments", "icon": "🧴"},
    {"key": "emergency", "label": "Emergency / Clinic Items", "icon": "🚨"},
    {"key": "other_medicine", "label": "Other Medicine", "icon": "📦"},
]

# Specific items for each medicine subcategory (Malawi-realistic)
MEDICINE_ITEMS = {
    "painkillers": [
        {"name": "Panado / Paracetamol (tabs)", "icon": "💊"},
        {"name": "Paracetamol Syrup", "icon": "🍼"},
        {"name": "Ibuprofen (tabs)", "icon": "💊"},
        {"name": "Diclofenac", "icon": "💊"},
        {"name": "Aspirin", "icon": "💊"},
        {"name": "Other painkiller", "icon": "📝"},
    ],
    "antibiotics": [
        {"name": "Azithromycin", "icon": "💊"},
        {"name": "Amoxicillin", "icon": "💊"},
        {"name": "Ciprofloxacin", "icon": "💊"},
        {"name": "Doxycycline", "icon": "💊"},
        {"name": "Metronidazole", "icon": "💊"},
        {"name": "Cotrimoxazole (Septrin)", "icon": "💊"},
        {"name": "Erythromycin", "icon": "💊"},
        {"name": "Other antibiotic", "icon": "📝"},
    ],
    "antimalarials": [
        {"name": "LA (Lumefantrine/Artemether)", "icon": "🦟"},
        {"name": "Coartem", "icon": "🦟"},
        {"name": "Fansidar", "icon": "💊"},
        {"name": "Quinine (tabs)", "icon": "💊"},
        {"name": "Quinine (IV)", "icon": "💉"},
        {"name": "Other antimalarial", "icon": "📝"},
    ],
    "cough_throat": [
        {"name": "Good Morning Malawi", "icon": "☀️"},
        {"name": "Actifed / Cold+Flu combos", "icon": "💊"},
        {"name": "Cough syrup", "icon": "🍯"},
        {"name": "Lozenges", "icon": "🍬"},
        {"name": "Other flu med", "icon": "📝"},
    ],
    "deworming": [
        {"name": "Mebendazole", "icon": "💊"},
        {"name": "Albendazole", "icon": "💊"},
        {"name": "Other deworming", "icon": "📝"},
    ],
    "eye_ear": [
        {"name": "Eye drops", "icon": "👁️"},
        {"name": "Ear drops", "icon": "👂"},
        {"name": "Other eye/ear", "icon": "📝"},
    ],
    "skin_treatments": [
        {"name": "Hydrocortisone cream", "icon": "🧴"},
        {"name": "Antifungal cream", "icon": "🧴"},
        {"name": "Betadine ointment", "icon": "🩹"},
        {"name": "Other skin treatment", "icon": "📝"},
    ],
    "emergency": [
        {"name": "IV fluids / Drips", "icon": "💉"},
        {"name": "ORS (Oral Rehydration Salts)", "icon": "💧"},
        {"name": "Syringes & needles", "icon": "💉"},
        {"name": "Other clinic item", "icon": "📝"},
    ],
    "other_medicine": [
        {"name": "Custom medicine", "icon": "📝"},
    ],
}

# Items for top-level categories (non-medicine)
STOMACH_ITEMS = [
    {"name": "ORS", "icon": "💧"},
    {"name": "Antacid", "icon": "💊"},
    {"name": "Omeprazole", "icon": "💊"},
    {"name": "Loperamide", "icon": "💊"},
    {"name": "Other stomach med", "icon": "📝"},
]

ALLERGY_ITEMS = [
    {"name": "Cetirizine", "icon": "💊"},
    {"name": "Chlorpheniramine", "icon": "💊"},
    {"name": "Hydrocortisone cream", "icon": "🧴"},
    {"name": "Other allergy med", "icon": "📝"},
]

CHRONIC_ITEMS = [
    {"name": "Amlodipine", "icon": "💊"},
    {"name": "Enalapril", "icon": "💊"},
    {"name": "Losartan", "icon": "💊"},
    {"name": "Hydrochlorothiazide", "icon": "💊"},
    {"name": "Metformin", "icon": "💊"},
    {"name": "Glibenclamide", "icon": "💊"},
    {"name": "Other BP/diabetes", "icon": "📝"},
]

FIRST_AID_ITEMS = [
    {"name": "Surgical spirit", "icon": "🧴"},
    {"name": "Hydrogen peroxide", "icon": "💧"},
    {"name": "Betadine (iodine)", "icon": "🩹"},
    {"name": "Plasters / bandages", "icon": "🩹"},
    {"name": "Gauze", "icon": "🩹"},
    {"name": "Cotton wool", "icon": "☁️"},
    {"name": "Savlon / antiseptic cream", "icon": "🧴"},
    {"name": "Other first aid", "icon": "📝"},
]

COLD_FLU_ITEMS = [
    {"name": "Good Morning Malawi", "icon": "☀️"},
    {"name": "Actifed", "icon": "💊"},
    {"name": "Cough syrup", "icon": "🍯"},
    {"name": "Lozenges", "icon": "🍬"},
    {"name": "Other cold/flu", "icon": "📝"},
]

WOMENS_HEALTH_ITEMS = [
    {"name": "Emergency pills", "icon": "💊"},
    {"name": "Pregnancy tests", "icon": "🧪"},
    {"name": "Sanitary pads", "icon": "🩹"},
    {"name": "Other", "icon": "📝"},
]

CHILD_HEALTH_ITEMS = [
    {"name": "Paracetamol syrup", "icon": "🍼"},
    {"name": "ORS", "icon": "💧"},
    {"name": "Zinc", "icon": "⚡"},
    {"name": "Other", "icon": "📝"},
]

OTC_ITEMS = [
    {"name": "Paracetamol / Panado", "icon": "💊"},
    {"name": "Ibuprofen", "icon": "💊"},
    {"name": "Antacid (Gaviscon, Mylanta)", "icon": "💊"},
    {"name": "ORS (Oral Rehydration Salts)", "icon": "💧"},
    {"name": "Antihistamine (Cetirizine)", "icon": "💊"},
    {"name": "Cough syrup", "icon": "🍯"},
    {"name": "Loperamide (anti-diarrhoea)", "icon": "💊"},
    {"name": "Antifungal cream", "icon": "🧴"},
    {"name": "Eye drops", "icon": "👁️"},
    {"name": "Deworming tablet", "icon": "💊"},
    {"name": "Other OTC product", "icon": "📝"},
]

SKINCARE_ITEMS = [
    {"name": "Vaseline / Petroleum Jelly", "icon": "🧴"},
    {"name": "Body lotion", "icon": "🧴"},
    {"name": "Face moisturiser", "icon": "✨"},
    {"name": "Sunscreen / SPF lotion", "icon": "☀️"},
    {"name": "Lip balm / Lip therapy", "icon": "💋"},
    {"name": "Hydrocortisone cream", "icon": "🧴"},
    {"name": "Glycerine", "icon": "💧"},
    {"name": "Palmer's Cocoa Butter", "icon": "🧴"},
    {"name": "Fair & Lovely / glow lotion", "icon": "✨"},
    {"name": "Baby lotion / Johnsons", "icon": "👶"},
    {"name": "Other skincare product", "icon": "📝"},
]

PERSONAL_CARE_ITEMS = [
    {"name": "Soap (bar or liquid)", "icon": "🧼"},
    {"name": "Shampoo", "icon": "🧴"},
    {"name": "Conditioner", "icon": "🧴"},
    {"name": "Deodorant / Roll-on", "icon": "🌿"},
    {"name": "Toothpaste", "icon": "🦷"},
    {"name": "Toothbrush", "icon": "🪥"},
    {"name": "Mouthwash", "icon": "💧"},
    {"name": "Razor / shaving kit", "icon": "🪒"},
    {"name": "Hair oil / cream", "icon": "💇"},
    {"name": "Other personal care", "icon": "📝"},
]

HYGIENE_ITEMS = [
    {"name": "Hand sanitizer", "icon": "🧼"},
    {"name": "Antiseptic soap", "icon": "🧴"},
    {"name": "Alcohol wipes", "icon": "🩹"},
    {"name": "Surgical masks", "icon": "😷"},
    {"name": "Gloves", "icon": "🧤"},
    {"name": "Sanitary pads", "icon": "🩸"},
    {"name": "Tampons", "icon": "🩸"},
    {"name": "Toilet paper / tissue", "icon": "🧻"},
    {"name": "Wet wipes / baby wipes", "icon": "🧻"},
    {"name": "Other hygiene product", "icon": "📝"},
]

VITAMINS_ITEMS = [
    {"name": "Vitamin C", "icon": "🍊"},
    {"name": "Multivitamin", "icon": "💪"},
    {"name": "Iron/Folic", "icon": "🦴"},
    {"name": "Vitamin D", "icon": "☀️"},
    {"name": "Calcium", "icon": "🦴"},
    {"name": "Other", "icon": "📝"},
]

# Cosmetics Subcategories (when user selects "Cosmetics & Personal Care")
COSMETICS_SUBCATEGORIES = [
    {"key": "perfumes", "label": "Perfumes", "icon": "🌹", "color": "#9333ea"},  # purple/indigo
    {"key": "skin_care", "label": "Skin Care", "icon": "✨", "color": "#14b8a6"},  # teal/green
    {"key": "hair_care", "label": "Hair Care", "icon": "💇", "color": "#3b82f6"},  # blue
    {"key": "body_care", "label": "Body Care", "icon": "🧴", "color": "#f59e0b"},  # amber
    {"key": "makeup", "label": "Makeup", "icon": "💄", "color": "#ec4899"},  # pink
    {"key": "mens_grooming", "label": "Men's Grooming", "icon": "🧔", "color": "#64748b"},  # neutral gray
    {"key": "other_cosmetics", "label": "Other", "icon": "📦", "color": "#94a3b8"},  # neutral gray
]

# ==============================================================================
# COSMETICS PREFILLS FOR STOCK-IN WIZARD (Lightweight, No DB Tables)
# ==============================================================================

COSMETICS_PREFILLS = {
    "perfumes": [
        "Arabic",
        "Emerald",
        "Monalisa",
        "Pure Black",
        "Bond",
        "Chris Adams",
        "Lattafa",
    ],
    "skin_care": [
        "CeraVe Lotion",
        "Vaseline Body Lotion",
        "Nivea Body Lotion",
        "Garnier Lotion",
        "Dove Cream",
        "Olay Total Effects",
        "Fair & Lovely",
    ],
    "hair_care": [
        "Relaxer",
        "Hair Food",
        "Shampoo",
        "Conditioner",
        "Hair Oil",
        "Pantene",
        "Dove Shampoo",
    ],
    "body_care": [
        "Body Spray",
        "Roll-on",
        "Body Wash",
        "Soap",
        "Petroleum Jelly",
        "Dove Soap",
        "Nivea Roll-on",
    ],
    "makeup": [
        "Lipstick",
        "Foundation",
        "Powder",
        "Mascara",
        "Eyeliner",
        "Blush",
    ],
    "mens_grooming": [
        "Aftershave",
        "Beard Oil",
        "Hair Gel",
        "Shaving Cream",
        "Cologne",
    ],
    "other_cosmetics": [
        "Cotton Wool",
        "Wet Wipes",
        "Tissue Paper",
        "Hand Sanitizer",
    ],
}

# Cosmetics Brand Items (common brands for each subcategory)
COSMETICS_BRAND_ITEMS = {
    "skin_care": [
        {"name": "Avon", "icon": "✨"},
        {"name": "CeraVe", "icon": "💎"},
        {"name": "Nivea", "icon": "🌟"},
        {"name": "Vaseline", "icon": "💧"},
        {"name": "Garnier", "icon": "🌿"},
        {"name": "Dove", "icon": "🕊️"},
        {"name": "Other brand", "icon": "📝"},
    ],
    "hair_care": [
        {"name": "Avon", "icon": "💇"},
        {"name": "Pantene", "icon": "✨"},
        {"name": "Dove", "icon": "🕊️"},
        {"name": "Garnier", "icon": "🌿"},
        {"name": "TRESemmé", "icon": "💫"},
        {"name": "Other brand", "icon": "📝"},
    ],
    "body_care": [
        {"name": "Dove", "icon": "🕊️"},
        {"name": "Nivea", "icon": "🌟"},
        {"name": "Vaseline", "icon": "💧"},
        {"name": "Palmolive", "icon": "🧴"},
        {"name": "Other brand", "icon": "📝"},
    ],
    "perfumes": [
        {"name": "Pure Black", "icon": "🖤"},
        {"name": "Emerald", "icon": "💎"},
        {"name": "Arabic perfumes", "icon": "🏺"},
        {"name": "Bond", "icon": "🎩"},
        {"name": "Avon", "icon": "✨"},
        {"name": "Other perfume", "icon": "📝"},
    ],
    "mens_grooming": [
        {"name": "Beard oil", "icon": "🧔"},
        {"name": "Hair gel", "icon": "💈"},
        {"name": "Aftershave", "icon": "💧"},
        {"name": "Other", "icon": "📝"},
    ],
    "makeup": [
        {"name": "Avon", "icon": "💄"},
        {"name": "Other brand", "icon": "📝"},
    ],
    "other_cosmetics": [
        {"name": "Custom product", "icon": "📝"},
    ],
}


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


# ==============================================================================
# GAMIFIED WIZARD HELPER FUNCTIONS
# ==============================================================================


def get_top_categories():
    """Get all top-level categories for the wizard."""
    return PHARMACY_TOP_CATEGORIES


def get_subcategories_for_category(category_key: str):
    """Get subcategories for a top-level category."""
    if category_key == "medicines":
        return MEDICINE_SUBCATEGORIES
    elif category_key == "cosmetics":
        return COSMETICS_SUBCATEGORIES
    return []


def get_items_for_subcategory(category_key: str, subcategory_key: str):
    """Get item suggestions for a specific subcategory."""
    # Medicine items
    if category_key == "medicines" and subcategory_key in MEDICINE_ITEMS:
        return MEDICINE_ITEMS[subcategory_key]

    # Cosmetics items (brands)
    if category_key == "cosmetics" and subcategory_key in COSMETICS_BRAND_ITEMS:
        return COSMETICS_BRAND_ITEMS[subcategory_key]

    return []


def get_prefills_for_cosmetics_category(category_key: str) -> list[str]:
    """
    Get prefill product names for a cosmetics category.
    Returns list of product names (strings).
    """
    return COSMETICS_PREFILLS.get(category_key, [])


def get_items_for_top_category(category_key: str):
    """Get item suggestions for top-level categories that don't have subcategories."""
    items_map = {
        "first_aid": FIRST_AID_ITEMS,
        "chronic": CHRONIC_ITEMS,
        "cold_flu": COLD_FLU_ITEMS,
        "stomach": STOMACH_ITEMS,
        "allergy": ALLERGY_ITEMS,
        "womens_health": WOMENS_HEALTH_ITEMS,
        "child_health": CHILD_HEALTH_ITEMS,
        "vitamins": VITAMINS_ITEMS,
        # New expanded categories
        "otc": OTC_ITEMS,
        "skincare": SKINCARE_ITEMS,
        "personal_care": PERSONAL_CARE_ITEMS,
        "hygiene": HYGIENE_ITEMS,
        "other": [{"name": "Custom product", "icon": "📝"}],
    }
    return items_map.get(category_key, [])


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
    badges.append(
        {
            "name": "Fresh Stock Hero",
            "icon": "✨",
            "description": "All medicine batches have more than 30 days to expiry",
            "earned": pharmacy_data.get("near_expiry_count", 999) == 0,
        }
    )

    # Cosmetics Champion - Cosmetics revenue >= 25%
    cosmetics_pct = pharmacy_data.get("cosmetics_revenue_pct", 0)
    badges.append(
        {
            "name": "Cosmetics Champion",
            "icon": "💄",
            "description": "Cosmetics revenue is 25% or more of total pharmacy revenue",
            "earned": cosmetics_pct >= 25,
        }
    )

    # Batch Guardian - All batches have 30+ days to expiry
    badges.append(
        {
            "name": "Batch Guardian",
            "icon": "🛡️",
            "description": "Managing batches perfectly with no near-expiry items",
            "earned": pharmacy_data.get("all_batches_fresh", False),
        }
    )

    # Stock Master - Has at least 20 active batches
    badges.append(
        {
            "name": "Stock Master",
            "icon": "📦",
            "description": "Maintaining healthy inventory with 20+ active batches",
            "earned": pharmacy_data.get("batches_count", 0) >= 20,
        }
    )

    return badges
