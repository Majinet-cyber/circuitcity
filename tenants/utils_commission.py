# tenants/utils_commission.py
"""
Commission configuration helpers - SINGLE SOURCE OF TRUTH for commission calculations.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.apps import apps


def get_phone_commission_pct(business) -> Decimal:
    """
    Get the phone commission percentage for a business as a fraction (not percentage).
    
    Args:
        business: Business instance or business_id
        
    Returns:
        Decimal fraction (e.g., Decimal("0.10") for 10%)
        
    Example:
        >>> pct = get_phone_commission_pct(my_business)  # Returns Decimal("0.10")
        >>> commission = price * pct
    """
    try:
        CommissionConfig = apps.get_model("sales", "CommissionConfig")
    except LookupError:
        # Fallback if CommissionConfig doesn't exist yet
        return Decimal("0.10")
    
    business_id = business.id if hasattr(business, "id") else business
    config = CommissionConfig.objects.filter(
        business_id=business_id, 
        is_active=True
    ).first()
    
    if config:
        # Convert percentage to fraction (e.g., 10.00 → 0.10)
        return config.base_commission_pct / Decimal("100")
    
    # Default 10%
    return Decimal("0.10")


def get_phone_commission_config(business):
    """
    Get or create the active CommissionConfig for a business.
    
    Args:
        business: Business instance
        
    Returns:
        CommissionConfig instance
    """
    try:
        CommissionConfig = apps.get_model("sales", "CommissionConfig")
    except LookupError:
        return None
    
    return CommissionConfig.ensure_config(business)


def update_commission_percentage(business, new_pct: Decimal, *, updated_by=None) -> bool:
    """
    Update the commission percentage for a business.
    
    Args:
        business: Business instance
        new_pct: New percentage (e.g., 15.00 for 15%)
        updated_by: User making the change (optional)
        
    Returns:
        bool: True if successful, False otherwise
        
    Raises:
        ValueError: If percentage is invalid (not between 0-100)
    """
    if not (0 <= new_pct <= 100):
        raise ValueError(f"Commission percentage must be between 0 and 100, got {new_pct}")
    
    try:
        CommissionConfig = apps.get_model("sales", "CommissionConfig")
    except LookupError:
        return False
    
    config = CommissionConfig.ensure_config(business)
    config.base_commission_pct = new_pct
    config.save(update_fields=["base_commission_pct", "updated_at"])
    
    return True

