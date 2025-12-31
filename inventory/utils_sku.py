"""
SKU generation utilities for MerchProduct.
Auto-generates business-scoped unique SKUs.
"""
import secrets
from typing import Optional
from django.utils.text import slugify


def generate_sku(*, business_id: int, name: str, existing_sku: Optional[str] = None) -> str:
    """
    Generate a unique internal SKU for a MerchProduct.
    
    Format: BIZ{business_id}-{name_slug}-{random}
    Example: BIZ17-paracetamol-syrup-A3F9
    
    Args:
        business_id: Business ID for scoping
        name: Product name
        existing_sku: If provided and non-empty, returns it unchanged
    
    Returns:
        Generated SKU string (max 64 chars)
    """
    # If SKU already exists and is non-empty, keep it
    if existing_sku and existing_sku.strip():
        return existing_sku.strip()
    
    # Slugify the name (lowercase, hyphens, safe chars only)
    name_slug = slugify(name)[:30]  # Limit to 30 chars
    if not name_slug:
        name_slug = "product"
    
    # Add random suffix for uniqueness (4 uppercase hex chars)
    random_suffix = secrets.token_hex(2).upper()  # 4 chars
    
    # Format: BIZ{id}-{slug}-{random}
    sku = f"BIZ{business_id}-{name_slug}-{random_suffix}"
    
    # Ensure it fits in 64 chars
    return sku[:64]

