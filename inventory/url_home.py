# inventory/url_home.py
"""
Single source of truth for the "Home" URL based on business_kind.

This ensures:
- Recognized verticals go to their correct dashboard
- Unknown/legacy verticals go to generic dashboard (not dispatcher)
- NULL business_kind goes to settings
- No redirect loops
"""
from __future__ import annotations

from typing import Optional


def get_home_url_for_business(business) -> str:
    """
    Returns the correct "Home" dashboard URL for a business based on its business_kind.
    
    This is a single source of truth used by:
    - Context processors
    - Templates
    - Navigation components
    
    Args:
        business: Business model instance (or None)
    
    Returns:
        str: URL path to the correct dashboard
        
    Logic:
    - business_kind NULL/blank → /accounts/settings/
    - business_kind recognized → vertical-specific dashboard
    - business_kind unknown/legacy → /inventory/generic-dashboard/
    - phones → /inventory/dashboard/
    
    CRITICAL: This function returns actual URL paths, NOT view names,
    to avoid reverse() failures in templates.
    """
    if business is None:
        return "/accounts/settings/"
    
    business_kind = getattr(business, "business_kind", None)
    
    # Case 1: business_kind is NULL/blank → settings
    if not business_kind:
        return "/accounts/settings/"
    
    # Normalize to lowercase string
    if hasattr(business_kind, "value"):
        business_kind = business_kind.value
    business_kind = str(business_kind).strip().lower()
    
    # Case 2: Map recognized verticals to their dashboards
    # Using hardcoded paths to avoid reverse() failures
    vertical_home_map = {
        "gym": "/verticals/gym/dashboard/",
        "pharmacy": "/verticals/pharmacy/hub/",
        "clothing": "/verticals/clothing/dashboard/",
        "liquor": "/verticals/liquor/dashboard/",
        "grocery": "/groceries/dashboard/",
        "phones": "/inventory/dashboard/",
        # Hardware and cement use generic dashboard (for now)
        "hardware": "/inventory/generic-dashboard/",
        "cement": "/inventory/generic-dashboard/",  # Treat cement as legacy for now
        # Farm and Welding verticals
        "farm": "/verticals/farm/dashboard/",
        "welding": "/verticals/welding/dashboard/",
    }
    
    # If recognized, return the vertical-specific home
    if business_kind in vertical_home_map:
        return vertical_home_map[business_kind]
    
    # Case 3: Unknown/legacy vertical → generic dashboard (NOT dispatcher)
    # This prevents redirect loops for unrecognized business_kind values
    return "/inventory/generic-dashboard/"


def get_home_url_name_for_business(business) -> str:
    """
    Returns the Django URL name for the home dashboard.
    
    This is used when you need the URL name (for reverse()) instead of the path.
    
    Args:
        business: Business model instance (or None)
    
    Returns:
        str: Django URL name (e.g., "inventory:generic_dashboard")
    """
    if business is None:
        return "accounts:settings_unified"
    
    business_kind = getattr(business, "business_kind", None)
    
    # Case 1: business_kind is NULL/blank → settings
    if not business_kind:
        return "accounts:settings_unified"
    
    # Normalize to lowercase string
    if hasattr(business_kind, "value"):
        business_kind = business_kind.value
    business_kind = str(business_kind).strip().lower()
    
    # Case 2: Map recognized verticals to their URL names
    vertical_url_name_map = {
        "gym": "verticals:gym_dashboard",
        "pharmacy": "verticals:pharmacy_hub",
        "clothing": "verticals:clothing_dashboard",
        "liquor": "verticals:liquor_dashboard",
        "grocery": "groceries:dashboard",
        "phones": "inventory:inventory_dashboard",
        "hardware": "inventory:generic_dashboard",
        "cement": "inventory:generic_dashboard",  # Treat cement as legacy
        # Farm and Welding verticals
        "farm": "verticals:farm_dashboard",
        "welding": "verticals:welding_dashboard",
    }
    
    # If recognized, return the URL name
    if business_kind in vertical_url_name_map:
        return vertical_url_name_map[business_kind]
    
    # Case 3: Unknown/legacy vertical → generic dashboard
    return "inventory:generic_dashboard"

