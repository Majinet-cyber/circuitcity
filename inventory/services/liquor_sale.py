# inventory/services/liquor_sale.py
"""
Liquor Sale Service - centralized business logic for all liquor sales.
Ensures all sales are atomic and safe against race conditions.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Optional
import logging

from django.db import transaction
from django.db.models import F
from django.core.exceptions import ValidationError

from inventory.models import MerchProduct
from inventory.models_verticals import (
    LiquorSale, LiquorCredit, LiquorWalletEntry,
    LiquorUnitType, LiquorSaleType, LiquorCreditStatus
)
from inventory.business_kinds import BusinessKind

logger = logging.getLogger(__name__)


class OutOfStockError(Exception):
    """Raised when there's insufficient stock for a sale"""
    pass


@transaction.atomic
def create_liquor_sale(
    *,
    business,
    product_id: int,
    user,
    quantity: int,
    unit: str,  # LiquorUnitType enum value
    unit_price: Decimal,
    sale_type: str = "cash",  # "cash" or "credit"
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    notes: Optional[str] = None,
    cash_amount: Decimal = Decimal("0.00"),
    bank_amount: Decimal = Decimal("0.00"),
    mobile_money_amount: Decimal = Decimal("0.00"),
    shift=None,
) -> Dict[str, Any]:
    """
    Create a liquor sale atomically.
    
    This function ensures:
    - All database operations happen in a single transaction
    - Stock is locked and decremented safely
    - No race conditions can cause overselling
    - All related records (sale, credit, wallet) are created consistently
    
    Args:
        business: Business instance
        product_id: ID of the MerchProduct to sell
        user: User making the sale
        quantity: Quantity to sell
        unit: Unit type ("bottle", "shot", or "glass")
        unit_price: Price per unit
        sale_type: "cash" or "credit"
        customer_name: Customer name (required for credit sales)
        customer_phone: Customer phone (optional)
        notes: Sale notes (optional)
        cash_amount: Cash payment amount
        bank_amount: Bank payment amount
        mobile_money_amount: Mobile money payment amount
        shift: LiquorShift instance (optional)
    
    Returns:
        Dict with:
            - ok: bool
            - sale_id: int (if ok)
            - message: str
            - error: str (if not ok)
    
    Raises:
        OutOfStockError: If insufficient stock
        ValidationError: If validation fails
    """
    # Lock and fetch product within transaction
    try:
        product = MerchProduct.objects.select_for_update().get(
            pk=product_id,
            business=business,
            kind=BusinessKind.LIQUOR,
            is_active=True
        )
    except MerchProduct.DoesNotExist:
        raise ValidationError("Product not found or not available")
    
    # Validate sale type
    is_credit = sale_type == "credit"
    if is_credit and not customer_name:
        raise ValidationError("Customer name is required for credit sales")
    
    # Map unit string to enum
    if unit == "shot":
        unit_enum = LiquorUnitType.SHOT
    elif unit == "glass":
        unit_enum = LiquorUnitType.GLASS
    else:
        unit_enum = LiquorUnitType.BOTTLE
    
    # Validate unit capabilities
    if unit == "shot" and not product.has_shots:
        raise ValidationError(f"{product.name} does not support shot sales")
    if unit == "glass" and not product.has_glasses:
        raise ValidationError(f"{product.name} does not support glass sales")
    
    # Validate category-specific unit rules
    category = (product.category or "").lower()
    if category in ("beer", "cider") and unit != "bottle":
        raise ValidationError(f"{product.name} ({category.title()}) must be sold by bottle only")
    if category == "wine" and unit != "glass":
        raise ValidationError(f"{product.name} (Wine) must be sold by glass only")
    if category in ("spirits", "whiskey") and unit != "shot":
        raise ValidationError(f"{product.name} ({category.title()}) must be sold by shot only")
    
    # Calculate totals
    total = Decimal(quantity) * unit_price
    if total <= 0:
        raise ValidationError("Sale total must be greater than zero")
    
    # Get cost for profit tracking
    unit_cost = product.get_cost_for_unit(unit) or Decimal("0.00")
    total_cost = Decimal(quantity) * unit_cost
    
    # Validate payment mix
    payment_mix_total = cash_amount + bank_amount + mobile_money_amount
    if payment_mix_total > 0 and payment_mix_total != total:
        raise ValidationError(
            f"Payment mix total (K{payment_mix_total}) must equal sale total (K{total})"
        )
    
    # For credit sales, ensure payment mix is zero
    if is_credit:
        cash_amount = Decimal("0.00")
        bank_amount = Decimal("0.00")
        mobile_money_amount = Decimal("0.00")
    
    # CRITICAL: Decrement stock atomically using conditional update
    # This prevents overselling even under high concurrency
    if unit == "bottle":
        # Use F() expression for atomic decrement
        updated = MerchProduct.objects.filter(
            pk=product.pk,
            quantity_in_stock__gte=quantity
        ).update(
            quantity_in_stock=F('quantity_in_stock') - quantity
        )
        
        if updated == 0:
            # Re-fetch to get current stock for error message
            product.refresh_from_db()
            current_stock = product.quantity_in_stock or 0
            raise OutOfStockError(
                f"Insufficient stock: {product.name}. Available: {current_stock}, Requested: {quantity}"
            )
    
    # Create sale record
    liquor_sale_type = LiquorSaleType.CREDIT if is_credit else LiquorSaleType.SALE
    sale = LiquorSale.objects.create(
        business=business,
        product=product,
        shift=shift,
        unit=unit_enum,
        quantity=quantity,
        unit_price=unit_price,
        total_price=total,
        unit_cost=unit_cost,
        total_cost=total_cost,
        sale_type=liquor_sale_type,
        is_credit=is_credit,
        sold_by=user,
        notes=notes,
        cash_amount=cash_amount,
        bank_amount=bank_amount,
        mobile_money_amount=mobile_money_amount
    )
    
    # Create credit record if needed
    credit = None
    if is_credit:
        credit = LiquorCredit.objects.create(
            business=business,
            customer_name=customer_name,
            customer_phone=customer_phone or "",
            amount=total,
            amount_paid=Decimal("0.00"),
            status=LiquorCreditStatus.OPEN,
            notes=notes or f"{product.name} - {quantity} {unit}",
            related_sale=sale,
            created_by=user
        )
    else:
        # Create wallet entry for cash sale
        try:
            LiquorWalletEntry.objects.create(
                business=business,
                amount=total,
                description=f"Sale: {product.name} ({quantity} {unit})",
                entry_type="income",
                related_sale=sale,
                created_by=user
            )
        except Exception as wallet_err:
            # Don't block sale if wallet entry fails - log and continue
            logger.warning(
                f"Failed to create wallet entry for sale #{sale.id}: {wallet_err}",
                exc_info=True
            )
    
    return {
        "ok": True,
        "sale_id": sale.id,
        "credit_id": credit.id if credit else None,
        "message": f"Sold {quantity} × {product.name} ({unit})" if not is_credit else f"Credit sale recorded: {quantity} × {product.name} ({unit}) for {customer_name}",
    }


@transaction.atomic
def create_liquor_sale_by_barcode(
    *,
    business,
    user,
    barcode: str,
    quantity: int = 1,
    unit: str = "bottle",  # "bottle", "shot", or "glass"
    unit_price: Optional[Decimal] = None,
    sale_type: str = "cash",
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    notes: Optional[str] = None,
    cash_amount: Decimal = Decimal("0.00"),
    bank_amount: Decimal = Decimal("0.00"),
    mobile_money_amount: Decimal = Decimal("0.00"),
    shift=None,
) -> Dict[str, Any]:
    """
    Create a liquor sale by barcode (for Quick Sell / Fast Sell).
    
    This function:
    - Looks up product by barcode
    - Determines appropriate unit and price
    - Creates sale atomically
    
    Args:
        business: Business instance
        user: User making the sale
        barcode: Product barcode
        quantity: Quantity to sell
        unit: Unit type ("bottle", "shot", or "glass") - defaults to "bottle"
        unit_price: Price per unit (if None, uses product's default price)
        sale_type: "cash" or "credit"
        customer_name: Customer name (required for credit sales)
        customer_phone: Customer phone (optional)
        notes: Sale notes (optional)
        cash_amount: Cash payment amount
        bank_amount: Bank payment amount
        mobile_money_amount: Mobile money payment amount
        shift: LiquorShift instance (optional)
    
    Returns:
        Dict with:
            - ok: bool
            - sale_id: int (if ok)
            - message: str
            - error: str (if not ok)
    
    Raises:
        OutOfStockError: If insufficient stock
        ValidationError: If validation fails
    """
    from inventory.utils_barcodes import normalize_barcode
    
    # Normalize barcode
    barcode = normalize_barcode(barcode)
    if not barcode:
        raise ValidationError("Invalid barcode")
    
    # Find product by barcode
    try:
        product = MerchProduct.objects.select_for_update().get(
            business=business,
            kind=BusinessKind.LIQUOR,
            is_active=True,
            barcode=barcode
        )
    except MerchProduct.DoesNotExist:
        raise ValidationError(f"Product with barcode '{barcode}' not found")
    except MerchProduct.MultipleObjectsReturned:
        # If multiple products have same barcode, get first one
        product = MerchProduct.objects.select_for_update().filter(
            business=business,
            kind=BusinessKind.LIQUOR,
            is_active=True,
            barcode=barcode
        ).first()
        if not product:
            raise ValidationError(f"Product with barcode '{barcode}' not found")
    
    # Determine unit if not provided (default to bottle)
    if not unit or unit not in ("bottle", "shot", "glass"):
        # Auto-detect based on category
        category = (product.category or "").lower()
        if category in ("beer", "cider"):
            unit = "bottle"
        elif category == "wine":
            unit = "glass"
        elif category in ("spirits", "whiskey"):
            unit = "shot"
        else:
            unit = "bottle"  # Default
    
    # Determine price if not provided
    if unit_price is None:
        if unit == "shot":
            unit_price = product.price_per_shot or Decimal("0.00")
        elif unit == "glass":
            unit_price = product.price_per_glass or Decimal("0.00")
        else:
            unit_price = product.price_per_bottle or Decimal("0.00")
        
        if unit_price == Decimal("0.00"):
            raise ValidationError(f"{product.name} does not have a price per {unit} set")
    
    # Use the main sale creation function
    return create_liquor_sale(
        business=business,
        product_id=product.id,
        user=user,
        quantity=quantity,
        unit=unit,
        unit_price=unit_price,
        sale_type=sale_type,
        customer_name=customer_name,
        customer_phone=customer_phone,
        notes=notes,
        cash_amount=cash_amount,
        bank_amount=bank_amount,
        mobile_money_amount=mobile_money_amount,
        shift=shift,
    )

