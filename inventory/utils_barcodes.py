# inventory/utils_barcodes.py
"""
Barcode utilities for all verticals.
Provides a single source of truth for barcode storage and retrieval.

Strategy:
- MerchProduct.barcode is the canonical field for products
- InventoryItem.barcode is used for item-level tracking (phones with IMEI)
- For batch-tracked items (pharmacy), barcode can be stored at batch level
"""
from typing import Optional, Union
from django.db import models


def get_barcode(obj) -> Optional[str]:
    """
    Get barcode from a product or inventory item.
    
    Args:
        obj: MerchProduct, InventoryItem, or PharmacyBatch instance
        
    Returns:
        Barcode string or None
    """
    if obj is None:
        return None
    
    # Try direct barcode attribute first
    barcode = getattr(obj, 'barcode', None)
    if barcode:
        barcode_str = str(barcode).strip()
        return barcode_str if barcode_str else None
    
    # For InventoryItem, try product's barcode
    if hasattr(obj, 'product'):
        product = getattr(obj, 'product', None)
        if product:
            barcode = getattr(product, 'barcode', None)
            if barcode:
                barcode_str = str(barcode).strip()
                return barcode_str if barcode_str else None
    
    # For PharmacyBatch, check batch_barcode or barcode
    if hasattr(obj, 'batch_barcode'):
        batch_barcode = getattr(obj, 'batch_barcode', None)
        if batch_barcode:
            barcode_str = str(batch_barcode).strip()
            return barcode_str if barcode_str else None
    
    return None


def set_barcode(obj, barcode: str) -> bool:
    """
    Set barcode on a product or inventory item.
    
    Args:
        obj: MerchProduct, InventoryItem, or PharmacyBatch instance
        barcode: Barcode string to set
        
    Returns:
        True if barcode was set successfully, False otherwise
    """
    if obj is None or not barcode:
        return False
    
    barcode = str(barcode).strip()
    if not barcode:
        return False
    
    # Try to set on the object directly
    if hasattr(obj, 'barcode'):
        try:
            obj.barcode = barcode
            return True
        except Exception:
            pass
    
    # For PharmacyBatch, try batch_barcode
    if hasattr(obj, 'batch_barcode'):
        try:
            obj.batch_barcode = barcode
            return True
        except Exception:
            pass
    
    return False


def product_has_barcode(product) -> bool:
    """
    Check if a product has a barcode set.
    
    Args:
        product: MerchProduct instance
        
    Returns:
        True if product has a non-empty barcode
    """
    if product is None:
        return False
    
    barcode = get_barcode(product)
    return bool(barcode and barcode.strip())


def find_by_barcode(barcode: str, business=None, vertical: str = None):
    """
    Find products or items by barcode.
    
    Args:
        barcode: Barcode to search for
        business: Business instance for scoping (optional)
        vertical: Vertical slug to filter by (optional)
        
    Returns:
        QuerySet of matching products
    """
    if not barcode:
        return []
    
    barcode = str(barcode).strip()
    
    try:
        from inventory.models import MerchProduct
        
        qs = MerchProduct.objects.filter(barcode=barcode)
        
        if business:
            qs = qs.filter(business=business)
        
        if vertical:
            qs = qs.filter(vertical=vertical)
        
        return qs
    except Exception:
        return []


def find_sellable_by_barcode(barcode: str, business, vertical: str = None):
    """
    Find in-stock sellable items by barcode.
    
    For Fast Sell: returns items that can be sold right now.
    
    Args:
        barcode: Barcode to search for
        business: Business instance (required for scoping)
        vertical: Vertical slug to filter by (optional)
        
    Returns:
        QuerySet of in-stock InventoryItem instances
    """
    if not barcode or not business:
        return []
    
    barcode = str(barcode).strip()
    
    try:
        from inventory.models import InventoryItem
        
        qs = InventoryItem.objects.filter(
            business=business,
            status='IN_STOCK'
        ).select_related('product')
        
        # Try to match by item barcode first (phones with IMEI)
        item_matches = qs.filter(barcode=barcode)
        if item_matches.exists():
            return item_matches
        
        # Fall back to product barcode
        product_matches = qs.filter(product__barcode=barcode)
        if product_matches.exists():
            return product_matches
        
        # For pharmacy batches, check batch_barcode
        if vertical == 'pharmacy':
            try:
                from inventory.models import PharmacyBatch
                
                batches = PharmacyBatch.objects.filter(
                    business=business,
                    quantity__gt=0
                ).filter(
                    models.Q(batch_barcode=barcode) | models.Q(product__barcode=barcode)
                ).select_related('product')
                
                if batches.exists():
                    # Return items from matching batches (FEFO - earliest expiry first)
                    batch = batches.order_by('expiry_date').first()
                    return qs.filter(
                        product=batch.product,
                        batch_id=batch.id
                    )
            except Exception:
                pass
        
        return qs.none()
    except Exception:
        return []


def validate_barcode(barcode: str) -> tuple[bool, str]:
    """
    Validate a barcode string.
    
    Args:
        barcode: Barcode string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not barcode:
        return False, "Barcode cannot be empty"
    
    barcode = str(barcode).strip()
    
    if len(barcode) < 3:
        return False, "Barcode must be at least 3 characters"
    
    if len(barcode) > 100:
        return False, "Barcode is too long (max 100 characters)"
    
    # Allow alphanumeric, hyphens, underscores
    import re
    if not re.match(r'^[A-Za-z0-9\-_]+$', barcode):
        return False, "Barcode can only contain letters, numbers, hyphens, and underscores"
    
    return True, ""


def normalize_barcode(barcode: str) -> str:
    """
    Normalize a barcode string (uppercase, strip whitespace).
    
    Args:
        barcode: Raw barcode string
        
    Returns:
        Normalized barcode string
    """
    if not barcode:
        return ""
    
    return str(barcode).strip().upper()

