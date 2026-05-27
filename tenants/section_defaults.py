# tenants/section_defaults.py
"""
Centralized helper for building section flag defaults by vertical.
Prevents NOT NULL constraint errors when creating businesses.
"""
from typing import Dict


def build_section_defaults(vertical_key: str) -> Dict[str, bool]:
    """
    Build a dict of all Business model section flags with appropriate defaults.
    
    All flags default to False, then we enable the ones needed for the vertical.
    Only returns fields that actually exist on the Business model.
    
    Args:
        vertical_key: Business kind (e.g., "phones", "grocery", "cement", "pharmacy")
    
    Returns:
        Dict of field_name -> bool values to merge into Business.objects.create()
    """
    try:
        from tenants.models import Business
        # Get all fields that start with 'has_' and end with '_section'
        existing_fields = [
            f.name for f in Business._meta.get_fields()
            if hasattr(f, 'name') and f.name.startswith('has_') and f.name.endswith('_section')
        ]
    except Exception:
        # Fallback: only known fields that we've added
        existing_fields = [
            "has_cosmetics_section",
            "has_groceries_section",
            "has_cement_section",
        ]
    
    # Start with all existing section flags set to False
    defaults = {field: False for field in existing_fields}
    
    # Enable flags based on vertical
    vertical_key = (vertical_key or "").lower().strip()
    
    if vertical_key == "pharmacy":
        if "has_pharmacy_section" in existing_fields:
            defaults["has_pharmacy_section"] = True
        if "has_cosmetics_section" in existing_fields:
            defaults["has_cosmetics_section"] = True  # Pharmacy includes cosmetics
    elif vertical_key == "grocery":
        if "has_groceries_section" in existing_fields:
            defaults["has_groceries_section"] = True
    elif vertical_key == "cement":
        if "has_cement_section" in existing_fields:
            defaults["has_cement_section"] = True
    elif vertical_key == "liquor":
        if "has_liquor_section" in existing_fields:
            defaults["has_liquor_section"] = True
    elif vertical_key == "clothing":
        if "has_clothing_section" in existing_fields:
            defaults["has_clothing_section"] = True
    elif vertical_key == "gym":
        if "has_gym_section" in existing_fields:
            defaults["has_gym_section"] = True
    elif vertical_key == "phones":
        if "has_phones_section" in existing_fields:
            defaults["has_phones_section"] = True
    
    return defaults


def get_existing_section_fields() -> list[str]:
    """
    Get list of section fields that actually exist on Business model.
    Used for defensive filtering.
    """
    try:
        from tenants.models import Business
        field_names = [f.name for f in Business._meta.get_fields() if isinstance(f, Business._meta.get_field('name').__class__)]
        return [f for f in field_names if f.startswith('has_') and f.endswith('_section')]
    except Exception:
        # Fallback: return known fields
        return [
            "has_cosmetics_section",
            "has_groceries_section",
            "has_cement_section",
            "has_pharmacy_section",
            "has_liquor_section",
            "has_clothing_section",
            "has_gym_section",
            "has_phones_section",
        ]

