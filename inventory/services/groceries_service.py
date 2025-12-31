# inventory/services/groceries_service.py
"""
GROCERIES SERVICE LAYER - Atomic, concurrency-safe operations
Single source of truth for all groceries stock and sales operations.

NON-NEGOTIABLES:
- Strict multi-tenant: active business + active location scoping on every query
- Vertical gating: wrong vertical returns error (not 200)
- No cross-business leakage
- Use transaction.atomic + select_for_update for all writes
- Barcode ALWAYS OPTIONAL
- Prevent overselling with stock checks
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Dict, List, Any
from datetime import datetime

from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import GrocerySale
from inventory.groceries_config import (
    to_base_units,
    get_unit_price,
    get_cost_price,
    SALE_MODE_RETAIL,
    SALE_MODE_WHOLESALE,
)
from tenants.models import Business, Location


# ==============================================================================
# VALIDATION HELPERS
# ==============================================================================

def _validate_business_vertical(business: Business) -> None:
    """Ensure business is groceries vertical."""
    if not business:
        raise ValidationError("Business is required")
    
    # Check business kind
    kind = getattr(business, 'business_kind', None)
    if kind != BusinessKind.GROCERY:
        raise PermissionDenied(
            f"This operation is only available for groceries businesses. "
            f"Your business type is: {kind}"
        )


def _validate_location(business: Business, location: Optional[Location]) -> Location:
    """Validate location belongs to business."""
    if not location:
        raise ValidationError("Location is required")
    
    if location.business_id != business.id:
        raise PermissionDenied("Location does not belong to this business")
    
    return location


def _validate_product(business: Business, product: MerchProduct) -> None:
    """Validate product belongs to business and is groceries."""
    if not product:
        raise ValidationError("Product is required")
    
    if product.business_id != business.id:
        raise PermissionDenied("Product does not belong to this business")
    
    if product.kind != BusinessKind.GROCERY:
        raise ValidationError(
            f"Product '{product.name}' is not a groceries product (kind={product.kind})"
        )
    
    if not product.is_active:
        raise ValidationError(f"Product '{product.name}' is archived or inactive")


# ==============================================================================
# STOCK-IN SERVICE
# ==============================================================================

@transaction.atomic
def stock_in_groceries(
    *,
    business: Business,
    location: Location,
    product: MerchProduct,
    qty: int | float,
    unit_label: str,
    cost_price_per_base_unit: Optional[Decimal] = None,
    selling_price_per_base_unit: Optional[Decimal] = None,
    user,
    expiry_date: Optional[datetime] = None,
    batch_number: Optional[str] = None,
    notes: str = '',
) -> Dict[str, Any]:
    """
    Stock-in groceries products atomically.
    
    Args:
        business: Business instance
        location: Location instance
        product: MerchProduct instance
        qty: Quantity in the given unit
        unit_label: Unit label ('base', 'pack', or specific like 'carton')
        cost_price_per_base_unit: Optional cost price update (per base unit)
        selling_price_per_base_unit: Optional selling price update (per base unit)
        user: User performing the operation
        expiry_date: Optional expiry date (if track_expiry is enabled)
        batch_number: Optional batch number
        notes: Optional notes
    
    Returns:
        dict: {
            'success': True,
            'product_id': int,
            'product_name': str,
            'qty_added_base_units': int,
            'new_stock_level': int,
            'unit_label': str,
        }
    
    Raises:
        ValidationError: If validation fails
        PermissionDenied: If vertical/tenant mismatch
    """
    # Validate vertical gating
    _validate_business_vertical(business)
    _validate_location(business, location)
    
    # Lock product row for update (prevent race conditions)
    product = MerchProduct.objects.select_for_update().get(pk=product.pk)
    _validate_product(business, product)
    
    # Convert qty to base units
    try:
        qty_base_units = to_base_units(qty, unit_label, product)
    except ValidationError as e:
        raise ValidationError(f"Invalid quantity/unit: {e}")
    
    if qty_base_units <= 0:
        raise ValidationError("Quantity must be greater than zero")
    
    # Update product prices if provided
    if cost_price_per_base_unit is not None:
        if cost_price_per_base_unit < 0:
            raise ValidationError("Cost price cannot be negative")
        product.cost_price = cost_price_per_base_unit
    
    if selling_price_per_base_unit is not None:
        if selling_price_per_base_unit < 0:
            raise ValidationError("Selling price cannot be negative")
        product.selling_price = selling_price_per_base_unit
    
    # Update stock
    old_stock = product.quantity_in_stock or 0
    product.quantity_in_stock = old_stock + qty_base_units
    
    # Save product
    product.save(update_fields=['quantity_in_stock', 'cost_price', 'selling_price'])
    
    # TODO: If expiry tracking is enabled, create PharmacyBatch-like records
    # For V1, we skip expiry tracking (can be added in Phase 2)
    
    return {
        'success': True,
        'product_id': product.id,
        'product_name': product.name,
        'qty_added_base_units': qty_base_units,
        'qty_added_display': f"{qty} {unit_label}",
        'new_stock_level': product.quantity_in_stock,
        'unit_label': product.base_unit,
    }


# ==============================================================================
# SELL SERVICE
# ==============================================================================

@transaction.atomic
def sell_groceries(
    *,
    business: Business,
    location: Location,
    cart_lines: List[Dict[str, Any]],
    sale_mode: str = SALE_MODE_RETAIL,
    payment_method: str = 'CASH',
    user,
    customer_name: str = '',
    notes: str = '',
    allow_price_override: bool = True,
) -> Dict[str, Any]:
    """
    Sell groceries products atomically (cart-based).
    
    Args:
        business: Business instance
        location: Location instance
        cart_lines: List of cart items, each dict with:
            {
                'product_id': int,
                'qty': int|float,
                'unit_label': str,  # 'base', 'pack', or specific
                'price_override': Optional[Decimal],  # per unit in the given unit_label
            }
        sale_mode: 'retail' or 'wholesale'
        payment_method: 'CASH', 'AIRTEL', 'TNM', 'BANK'
        user: User performing the sale
        customer_name: Optional customer name
        notes: Optional notes
        allow_price_override: Allow price overrides (important for wholesale negotiations)
    
    Returns:
        dict: {
            'success': True,
            'sale_ids': List[int],
            'total_revenue': Decimal,
            'total_cost': Decimal,
            'total_profit': Decimal,
            'items_sold': int,
        }
    
    Raises:
        ValidationError: If validation fails or insufficient stock
        PermissionDenied: If vertical/tenant mismatch
    """
    # Validate vertical gating
    _validate_business_vertical(business)
    _validate_location(business, location)
    
    if not cart_lines:
        raise ValidationError("Cart is empty")
    
    if sale_mode not in [SALE_MODE_RETAIL, SALE_MODE_WHOLESALE]:
        raise ValidationError(f"Invalid sale mode: {sale_mode}")
    
    # Lock all products in cart (prevent race conditions)
    product_ids = [line['product_id'] for line in cart_lines]
    products = {
        p.id: p
        for p in MerchProduct.objects.select_for_update().filter(
            id__in=product_ids,
            business=business,
            kind=BusinessKind.GROCERY,
            is_active=True,
        )
    }
    
    # Validate all products exist and belong to business
    for line in cart_lines:
        product_id = line['product_id']
        if product_id not in products:
            raise ValidationError(
                f"Product ID {product_id} not found or not available for sale"
            )
    
    # Process each cart line
    sale_records = []
    total_revenue = Decimal('0')
    total_cost = Decimal('0')
    items_sold_count = 0
    
    for line in cart_lines:
        product = products[line['product_id']]
        qty = line['qty']
        unit_label = line.get('unit_label', 'base')
        price_override = line.get('price_override')
        
        # Convert qty to base units
        try:
            qty_base_units = to_base_units(qty, unit_label, product)
        except ValidationError as e:
            raise ValidationError(
                f"Invalid quantity/unit for '{product.name}': {e}"
            )
        
        if qty_base_units <= 0:
            raise ValidationError(f"Quantity must be > 0 for '{product.name}'")
        
        # Check stock availability
        available_stock = product.quantity_in_stock or 0
        if available_stock < qty_base_units:
            raise ValidationError(
                f"Insufficient stock for '{product.name}'. "
                f"Available: {available_stock} {product.base_unit}, "
                f"Requested: {qty_base_units} {product.base_unit}"
            )
        
        # Calculate pricing
        if price_override and allow_price_override:
            # Price override is per unit in the given unit_label
            # Convert to per-base-unit
            if unit_label == 'base' or unit_label == product.base_unit:
                unit_price_base = price_override
            else:
                # Price override is for pack, convert to base
                pack_size = product.pack_size or 1
                unit_price_base = price_override / Decimal(str(pack_size))
        else:
            # Use standard pricing
            unit_price_base = get_unit_price(product, 'base', sale_mode)
        
        unit_cost_base = get_cost_price(product, 'base')
        
        # Calculate totals for this line
        line_revenue = unit_price_base * Decimal(str(qty_base_units))
        line_cost = unit_cost_base * Decimal(str(qty_base_units))
        line_profit = line_revenue - line_cost
        
        # Deduct stock
        product.quantity_in_stock -= qty_base_units
        product.save(update_fields=['quantity_in_stock'])
        
        # Create sale record
        sale = GrocerySale.objects.create(
            business=business,
            product=product,
            quantity=qty_base_units,
            unit_price=unit_price_base,
            total_price=line_revenue,
            unit_cost=unit_cost_base,
            total_cost=line_cost,
            sale_mode=sale_mode,
            payment_method=payment_method,
            sold_by=user,
            notes=f"{customer_name}: {notes}" if customer_name else notes,
        )
        
        sale_records.append(sale)
        total_revenue += line_revenue
        total_cost += line_cost
        items_sold_count += qty_base_units
    
    total_profit = total_revenue - total_cost
    
    return {
        'success': True,
        'sale_ids': [s.id for s in sale_records],
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'total_profit': total_profit,
        'items_sold': items_sold_count,
        'sale_mode': sale_mode,
        'payment_method': payment_method,
    }


# ==============================================================================
# STOCK ADJUSTMENT SERVICE
# ==============================================================================

@transaction.atomic
def adjust_groceries_stock(
    *,
    business: Business,
    location: Location,
    product: MerchProduct,
    qty_base_units_delta: int,
    reason: str,
    user,
    notes: str = '',
) -> Dict[str, Any]:
    """
    Adjust stock level for a groceries product (manager-only).
    
    Args:
        business: Business instance
        location: Location instance
        product: MerchProduct instance
        qty_base_units_delta: Change in stock (positive or negative, in base units)
        reason: Reason for adjustment ('damaged', 'expired', 'found', 'correction', etc.)
        user: User performing the adjustment
        notes: Optional notes
    
    Returns:
        dict: {
            'success': True,
            'product_id': int,
            'old_stock': int,
            'new_stock': int,
            'delta': int,
        }
    
    Raises:
        ValidationError: If validation fails or would result in negative stock
        PermissionDenied: If vertical/tenant mismatch
    """
    # Validate vertical gating
    _validate_business_vertical(business)
    _validate_location(business, location)
    
    # Lock product row
    product = MerchProduct.objects.select_for_update().get(pk=product.pk)
    _validate_product(business, product)
    
    if qty_base_units_delta == 0:
        raise ValidationError("Stock delta cannot be zero")
    
    old_stock = product.quantity_in_stock or 0
    new_stock = old_stock + qty_base_units_delta
    
    if new_stock < 0:
        raise ValidationError(
            f"Stock adjustment would result in negative stock. "
            f"Current: {old_stock}, Delta: {qty_base_units_delta}, "
            f"Result: {new_stock}"
        )
    
    # Update stock
    product.quantity_in_stock = new_stock
    product.save(update_fields=['quantity_in_stock'])
    
    # TODO: Create audit log entry (StockAdjustment model)
    # For V1, we rely on Django admin history
    
    return {
        'success': True,
        'product_id': product.id,
        'product_name': product.name,
        'old_stock': old_stock,
        'new_stock': new_stock,
        'delta': qty_base_units_delta,
        'reason': reason,
    }


# ==============================================================================
# BARCODE LOOKUP (OPTIONAL)
# ==============================================================================

def lookup_product_by_barcode(
    *,
    business: Business,
    barcode: str,
) -> Optional[MerchProduct]:
    """
    Look up a groceries product by barcode (optional, business-scoped).
    
    Args:
        business: Business instance
        barcode: Barcode string
    
    Returns:
        MerchProduct or None
    """
    if not barcode or not barcode.strip():
        return None
    
    barcode = barcode.strip()
    
    try:
        product = MerchProduct.objects.get(
            business=business,
            kind=BusinessKind.GROCERY,
            barcode=barcode,
            is_active=True,
        )
        return product
    except MerchProduct.DoesNotExist:
        return None
    except MerchProduct.MultipleObjectsReturned:
        # Should not happen with proper unique constraints, but handle gracefully
        return MerchProduct.objects.filter(
            business=business,
            kind=BusinessKind.GROCERY,
            barcode=barcode,
            is_active=True,
        ).first()


# ==============================================================================
# HELPER: Get product by ID (with validation)
# ==============================================================================

def get_groceries_product(
    *,
    business: Business,
    product_id: int,
) -> MerchProduct:
    """
    Get a groceries product by ID with validation.
    
    Raises:
        ValidationError: If product not found or validation fails
    """
    try:
        product = MerchProduct.objects.get(
            id=product_id,
            business=business,
            kind=BusinessKind.GROCERY,
            is_active=True,
        )
        return product
    except MerchProduct.DoesNotExist:
        raise ValidationError(f"Product ID {product_id} not found")


