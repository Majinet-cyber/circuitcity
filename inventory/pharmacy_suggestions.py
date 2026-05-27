"""
Curated product suggestions for pharmacy stock-in flow.
Used to provide smart recommendations when users select a category.
"""

PHARMACY_CATEGORY_SUGGESTIONS = {
    "medicine": [
        {"name": "Paracetamol 500mg", "brand": "", "unit": "tabs"},
        {"name": "Ibuprofen 200mg", "brand": "", "unit": "tabs"},
        {"name": "Amoxicillin 500mg", "brand": "", "unit": "caps"},
        {"name": "ORS Sachets", "brand": "", "unit": "sachets"},
        {"name": "Cetirizine 10mg", "brand": "", "unit": "tabs"},
        {"name": "Aspirin 300mg", "brand": "", "unit": "tabs"},
        {"name": "Metformin 500mg", "brand": "", "unit": "tabs"},
        {"name": "Omeprazole 20mg", "brand": "", "unit": "caps"},
        {"name": "Amoxicillin + Clavulanic Acid 625mg", "brand": "", "unit": "tabs"},
        {"name": "Ciprofloxacin 500mg", "brand": "", "unit": "tabs"},
        {"name": "Vitamin C 1000mg", "brand": "", "unit": "tabs"},
        {"name": "Diclofenac 50mg", "brand": "", "unit": "tabs"},
    ],
    "supplements": [
        {"name": "Multivitamin Complex", "brand": "", "unit": "tabs"},
        {"name": "Vitamin D3 1000IU", "brand": "", "unit": "caps"},
        {"name": "Omega-3 Fish Oil", "brand": "", "unit": "caps"},
        {"name": "Calcium + Vitamin D", "brand": "", "unit": "tabs"},
        {"name": "Vitamin B Complex", "brand": "", "unit": "tabs"},
        {"name": "Iron Supplement", "brand": "", "unit": "tabs"},
        {"name": "Zinc 50mg", "brand": "", "unit": "tabs"},
        {"name": "Magnesium 400mg", "brand": "", "unit": "tabs"},
    ],
    "skin_care": [
        {"name": "CeraVe Moisturizing Lotion", "brand": "CeraVe", "unit": "ml"},
        {"name": "CeraVe Moisturizing Cream", "brand": "CeraVe", "unit": "g"},
        {"name": "Vaseline Petroleum Jelly", "brand": "Vaseline", "unit": "g"},
        {"name": "Vaseline Intensive Care Lotion", "brand": "Vaseline", "unit": "ml"},
        {"name": "Nivea Soft Cream", "brand": "Nivea", "unit": "g"},
        {"name": "Nivea Nourishing Body Milk", "brand": "Nivea", "unit": "ml"},
        {"name": "Neutrogena Hydro Boost", "brand": "Neutrogena", "unit": "ml"},
        {"name": "Aveeno Daily Moisturizing Lotion", "brand": "Aveeno", "unit": "ml"},
        {"name": "Cetaphil Gentle Cleanser", "brand": "Cetaphil", "unit": "ml"},
        {"name": "La Roche-Posay Effaclar Gel", "brand": "La Roche-Posay", "unit": "ml"},
        {"name": "Olay Regenerist Cream", "brand": "Olay", "unit": "g"},
        {"name": "Eucerin Original Healing Cream", "brand": "Eucerin", "unit": "g"},
        {"name": "Garnier Micellar Water", "brand": "Garnier", "unit": "ml"},
        {"name": "Jergens Ultra Healing Lotion", "brand": "Jergens", "unit": "ml"},
        {"name": "Shea Butter", "brand": "", "unit": "g"},
        {"name": "Glycerine", "brand": "", "unit": "ml"},
    ],
    "hair_care": [
        {"name": "Pantene Pro-V Shampoo", "brand": "Pantene", "unit": "ml"},
        {"name": "Dove Intense Repair Conditioner", "brand": "Dove", "unit": "ml"},
        {"name": "TRESemmé Keratin Smooth", "brand": "TRESemmé", "unit": "ml"},
        {"name": "Head & Shoulders Anti-Dandruff", "brand": "Head & Shoulders", "unit": "ml"},
        {"name": "L'Oréal Elvive Hair Oil", "brand": "L'Oréal", "unit": "ml"},
        {"name": "Sunsilk Shampoo", "brand": "Sunsilk", "unit": "ml"},
        {"name": "Garnier Fructis Conditioner", "brand": "Garnier", "unit": "ml"},
    ],
    "body_care": [
        {"name": "Dawn Body Lotion", "brand": "Dawn", "unit": "ml"},
        {"name": "Nivea Body Lotion", "brand": "Nivea", "unit": "ml"},
        {"name": "Nivea Nourishing Body Milk", "brand": "Nivea", "unit": "ml"},
        {"name": "Vaseline Intensive Care Lotion", "brand": "Vaseline", "unit": "ml"},
        {"name": "CeraVe Moisturizing Lotion", "brand": "CeraVe", "unit": "ml"},
        {"name": "CeraVe Moisturizing Cream", "brand": "CeraVe", "unit": "g"},
        {"name": "Aveeno Daily Moisturizing Lotion", "brand": "Aveeno", "unit": "ml"},
        {"name": "Jergens Ultra Healing Lotion", "brand": "Jergens", "unit": "ml"},
        {"name": "Johnson's Body Lotion", "brand": "Johnson's", "unit": "ml"},
        {"name": "Palmer's Cocoa Butter Lotion", "brand": "Palmer's", "unit": "ml"},
        {"name": "Neutrogena Hydro Boost", "brand": "Neutrogena", "unit": "ml"},
        {"name": "Dove Body Wash", "brand": "Dove", "unit": "ml"},
        {"name": "St. Ives Body Lotion", "brand": "St. Ives", "unit": "ml"},
        {"name": "Shea Butter", "brand": "", "unit": "g"},
        {"name": "Glycerine", "brand": "", "unit": "ml"},
    ],
    "baby_care": [
        {"name": "Johnson's Baby Oil", "brand": "Johnson's", "unit": "ml"},
        {"name": "Pampers Size 3", "brand": "Pampers", "unit": "pcs"},
        {"name": "Pampers Size 4", "brand": "Pampers", "unit": "pcs"},
        {"name": "Huggies Size 3", "brand": "Huggies", "unit": "pcs"},
        {"name": "Johnson's Baby Powder", "brand": "Johnson's", "unit": "g"},
        {"name": "Johnson's Baby Shampoo", "brand": "Johnson's", "unit": "ml"},
        {"name": "Bepanthen Nappy Cream", "brand": "Bepanthen", "unit": "g"},
        {"name": "Cetaphil Baby Lotion", "brand": "Cetaphil", "unit": "ml"},
    ],
    "oral_care": [
        {"name": "Colgate Total Toothpaste", "brand": "Colgate", "unit": "g"},
        {"name": "Sensodyne Rapid Relief", "brand": "Sensodyne", "unit": "g"},
        {"name": "Oral-B Toothbrush", "brand": "Oral-B", "unit": "pcs"},
        {"name": "Listerine Mouthwash", "brand": "Listerine", "unit": "ml"},
        {"name": "Aquafresh Toothpaste", "brand": "Aquafresh", "unit": "g"},
        {"name": "Colgate Mouthwash", "brand": "Colgate", "unit": "ml"},
        {"name": "Crest Toothpaste", "brand": "Crest", "unit": "g"},
    ],
    "perfumes": [
        # Arabic / Middle Eastern fragrances
        {"name": "Lattafa Asad", "brand": "Lattafa", "unit": "ml"},
        {"name": "Lattafa Khamrah", "brand": "Lattafa", "unit": "ml"},
        {"name": "Lattafa Oud for Glory", "brand": "Lattafa", "unit": "ml"},
        {"name": "Lattafa Bade'e Al Oud", "brand": "Lattafa", "unit": "ml"},
        {"name": "Lattafa Raghba", "brand": "Lattafa", "unit": "ml"},
        {"name": "Ard Al Zaafaran Dirham", "brand": "Ard Al Zaafaran", "unit": "ml"},
        {"name": "Ard Al Zaafaran Midnight Oud", "brand": "Ard Al Zaafaran", "unit": "ml"},
        {"name": "Afnan 9PM", "brand": "Afnan", "unit": "ml"},
        {"name": "Afnan Supremacy Not Only Intense", "brand": "Afnan", "unit": "ml"},
        {"name": "Rasasi Hawas", "brand": "Rasasi", "unit": "ml"},
        {"name": "Ajmal Amber Wood", "brand": "Ajmal", "unit": "ml"},
        {"name": "Al Rehab Choco Musk", "brand": "Al Rehab", "unit": "ml"},
        {"name": "Swiss Arabian Shaghaf Oud", "brand": "Swiss Arabian", "unit": "ml"},
        # Popular mainstream perfumes
        {"name": "Avon Far Away", "brand": "Avon", "unit": "ml"},
        {"name": "Avon Little Black Dress", "brand": "Avon", "unit": "ml"},
        {"name": "Calvin Klein Euphoria", "brand": "Calvin Klein", "unit": "ml"},
        {"name": "Dior Sauvage", "brand": "Dior", "unit": "ml"},
        {"name": "Versace Eros", "brand": "Versace", "unit": "ml"},
        {"name": "Hugo Boss Bottled", "brand": "Hugo Boss", "unit": "ml"},
        {"name": "Guess Seductive", "brand": "Guess", "unit": "ml"},
        {"name": "Zara Man Gold", "brand": "Zara", "unit": "ml"},
        # Generic types sold locally
        {"name": "Oud Perfume Oil", "brand": "", "unit": "ml"},
        {"name": "Musk Perfume Oil", "brand": "", "unit": "ml"},
        {"name": "Bakhoor Incense", "brand": "", "unit": "g"},
    ],
    "deodorants": [
        {"name": "Nivea Men Deodorant", "brand": "Nivea", "unit": "ml"},
        {"name": "Dove Deodorant Spray", "brand": "Dove", "unit": "ml"},
        {"name": "Rexona Deodorant Roll-On", "brand": "Rexona", "unit": "ml"},
        {"name": "Axe Body Spray", "brand": "Axe", "unit": "ml"},
        {"name": "Old Spice Deodorant", "brand": "Old Spice", "unit": "ml"},
        {"name": "Sure Antiperspirant", "brand": "Sure", "unit": "ml"},
        {"name": "Nivea Fresh Active", "brand": "Nivea", "unit": "ml"},
    ],
    "makeup": [
        {"name": "Maybelline Mascara", "brand": "Maybelline", "unit": "pcs"},
        {"name": "L'Oréal Foundation", "brand": "L'Oréal", "unit": "ml"},
        {"name": "Revlon Lipstick", "brand": "Revlon", "unit": "pcs"},
        {"name": "Rimmel Eyeliner", "brand": "Rimmel", "unit": "pcs"},
        {"name": "NYX Setting Spray", "brand": "NYX", "unit": "ml"},
        {"name": "Maybelline Fit Me Powder", "brand": "Maybelline", "unit": "g"},
        {"name": "Covergirl Mascara", "brand": "Covergirl", "unit": "pcs"},
    ],
    "soap_hygiene": [
        {"name": "Dettol Antibacterial Soap", "brand": "Dettol", "unit": "g"},
        {"name": "Dove Beauty Bar", "brand": "Dove", "unit": "g"},
        {"name": "Lux Soap", "brand": "Lux", "unit": "g"},
        {"name": "Lifebuoy Soap", "brand": "Lifebuoy", "unit": "g"},
        {"name": "Imperial Leather Soap", "brand": "Imperial Leather", "unit": "g"},
        {"name": "Carex Hand Wash", "brand": "Carex", "unit": "ml"},
        {"name": "Palmolive Soap", "brand": "Palmolive", "unit": "g"},
        {"name": "Dettol Hand Sanitizer", "brand": "Dettol", "unit": "ml"},
    ],
    "first_aid": [
        {"name": "Band-Aid Adhesive Bandages", "brand": "Band-Aid", "unit": "pcs"},
        {"name": "Cotton Wool", "brand": "", "unit": "g"},
        {"name": "Gauze Bandage", "brand": "", "unit": "pcs"},
        {"name": "Surgical Tape", "brand": "", "unit": "pcs"},
        {"name": "Betadine Antiseptic", "brand": "Betadine", "unit": "ml"},
        {"name": "Hydrogen Peroxide 3%", "brand": "", "unit": "ml"},
        {"name": "Disposable Gloves", "brand": "", "unit": "pcs"},
        {"name": "Thermometer", "brand": "", "unit": "pcs"},
    ],
    "other": [
        {"name": "Cotton Swabs", "brand": "", "unit": "pcs"},
        {"name": "Tissues Box", "brand": "", "unit": "pcs"},
        {"name": "Wet Wipes", "brand": "", "unit": "pcs"},
        {"name": "Sanitary Pads", "brand": "", "unit": "pcs"},
        {"name": "Condoms", "brand": "", "unit": "pcs"},
    ],
}


def get_suggestions_for_category(category: str) -> list[dict]:
    """
    Get product suggestions for a given category.
    
    Args:
        category: Category code (e.g., "medicine", "skin_care")
    
    Returns:
        List of suggestion dicts with name, brand, unit keys
    """
    return PHARMACY_CATEGORY_SUGGESTIONS.get(category, [])

