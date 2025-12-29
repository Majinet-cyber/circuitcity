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


def normalize_barcode_enhanced(barcode: str) -> str:
    """
    Enhanced barcode normalization for robust matching.
    
    Rules:
    1. Trim whitespace
    2. Remove spaces and hyphens
    3. Uppercase
    4. Keep only alphanumeric characters
    5. For numeric-only codes (EAN/UPC), keep digits only
    6. Handle leading zeros consistently
    
    Args:
        barcode: Raw barcode string
        
    Returns:
        Normalized barcode string (empty string if invalid/empty)
    """
    if not barcode:
        return ""
    
    # Step 1: Convert to string and trim
    code = str(barcode).strip()
    
    if not code:
        return ""
    
    # Step 2: Remove common separators
    code = code.replace(" ", "").replace("-", "").replace("_", "")
    
    # Step 3: Uppercase
    code = code.upper()
    
    # Step 4: For numeric-only codes (EAN, UPC), keep digits only
    if code.isdigit():
        # Keep digits only - preserves leading zeros
        return code
    
    # Step 5: For alphanumeric codes (Code128, QR, etc.), keep alphanumeric only
    import re
    code = re.sub(r'[^A-Z0-9]', '', code)
    
    return code if code else ""


def is_valid_barcode_format(barcode: str) -> bool:
    """
    Check if a barcode string has a valid format.
    
    Args:
        barcode: Barcode string to check
        
    Returns:
        True if valid format, False otherwise
    """
    if not barcode or not isinstance(barcode, str):
        return False
    
    # Min 3 chars, max 100 chars
    if len(barcode) < 3 or len(barcode) > 100:
        return False
    
    # Must contain at least one alphanumeric character
    import re
    if not re.search(r'[A-Za-z0-9]', barcode):
        return False
    
    return True


def register_barcode(
    business,
    raw_code: str,
    product=None,
    batch=None,
    created_by=None
):
    """
    Register a barcode in the barcode registry.
    
    Args:
        business: Business instance
        raw_code: Raw barcode string
        product: MerchProduct instance (optional)
        batch: PharmacyBatch instance (optional)
        created_by: User instance (optional)
        
    Returns:
        BarcodeRegistry instance or None if failed
    """
    if not business or not raw_code:
        return None
    
    try:
        from inventory.models_barcodes import BarcodeRegistry
        
        normalized = normalize_barcode_enhanced(raw_code)
        if not normalized:
            return None
        
        # Check if barcode already exists for this business
        # Use for_business to explicitly scope the query (bypasses TenantManager's thread-local filtering)
        existing = BarcodeRegistry.objects.for_business(business).filter(
            normalized_code=normalized,
            is_active=True
        ).first()
        
        if existing:
            # Update existing entry
            if product:
                existing.product = product
            if batch:
                existing.batch = batch
            existing.raw_code = raw_code  # Update to latest raw format
            existing.save()
            return existing
        
        # Create new entry
        # Use for_business to explicitly scope (though create doesn't use the queryset, it's for consistency)
        return BarcodeRegistry.objects.for_business(business).create(
            business=business,
            raw_code=raw_code,
            normalized_code=normalized,
            product=product,
            batch=batch,
            created_by=created_by,
            is_active=True
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"Failed to register barcode: {e}")
        return None


def lookup_barcode(business, raw_code: str, location=None):
    """
    Look up a barcode in the registry with fallback to real data and auto-registration.
    
    This function implements a resilient, self-healing barcode lookup:
    1. Normalizes input barcode
    2. Checks BarcodeRegistry first (business-scoped, location tolerant)
    3. Falls back to MerchProduct.barcode with normalized comparison
    4. Auto-registers found products in the registry for future fast lookups
    
    Args:
        business: Business instance
        raw_code: Raw barcode string
        location: Optional location for filtering (not currently used in registry lookup)
        
    Returns:
        Dict with:
            - found: bool
            - product: MerchProduct instance or None
            - batch: PharmacyBatch instance or None
            - registry_entry: BarcodeRegistry instance or None
    """
    if not business or not raw_code:
        return {"found": False, "product": None, "batch": None, "registry_entry": None}
    
    try:
        from inventory.models_barcodes import BarcodeRegistry
        from django.db import transaction
        
        # Normalize input barcode
        normalized = normalize_barcode_enhanced(raw_code)
        if not normalized:
            return {"found": False, "product": None, "batch": None, "registry_entry": None}
        
        # 1) Registry first (location tolerant - location filtering not currently supported)
        # Use for_business to explicitly scope the query (bypasses TenantManager's thread-local filtering)
        reg = BarcodeRegistry.objects.for_business(business).filter(
            normalized_code=normalized,
            is_active=True
        ).select_related("product", "batch").first()
        
        if reg:
            return {
                "found": True,
                "product": reg.product,
                "batch": reg.batch,
                "registry_entry": reg
            }
        
        # 2) Fallback: MerchProduct by barcode (self-heal)
        from inventory.models import MerchProduct
        
        # Get products with barcodes for this business
        products = MerchProduct.objects.filter(
            business=business,
            is_active=True
        ).exclude(barcode__isnull=True).exclude(barcode="")
        
        # Normalize and compare barcodes
        mp = None
        for product in products:
            if product.barcode:
                product_barcode_normalized = normalize_barcode_enhanced(product.barcode)
                if product_barcode_normalized == normalized:
                    mp = product
                    break
        
        if mp:
            # Auto-register: create/update BarcodeRegistry entry
            # Use for_business to explicitly scope the query (bypasses TenantManager's thread-local filtering)
            with transaction.atomic():
                reg_entry, created = BarcodeRegistry.objects.for_business(business).update_or_create(
                    normalized_code=normalized,
                    is_active=True,
                    defaults={
                        "business": business,
                        "raw_code": raw_code,
                        "product": mp,
                        "batch": None,
                    }
                )
                # Ensure it's active (in case it was inactive)
                if not reg_entry.is_active:
                    reg_entry.is_active = True
                    reg_entry.save()
            
            return {
                "found": True,
                "product": mp,
                "batch": None,
                "registry_entry": reg_entry
            }
        
        return {"found": False, "product": None, "batch": None, "registry_entry": None}
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"Failed to lookup barcode: {e}")
        return {"found": False, "product": None, "batch": None, "registry_entry": None}