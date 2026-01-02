# inventory/services/liquor_sale.py
"""
Liquor Sale Service - centralized business logic for all liquor sales.
Ensures all sales are atomic and safe against race conditions.

SIMPLIFICATION RULES:
- NO BARCODE required for liquor (barcode is optional)
- Enforce real-world unit rules (beer=bottle/crate, cider=bottle/6-pack, etc.)
- Use shared conversion helper from liquor_config
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
    LiquorSale,
    LiquorCredit,
    LiquorWalletEntry,
    LiquorUnitType,
    LiquorSaleType,
    LiquorCreditStatus,
)
from inventory.business_kinds import BusinessKind
from inventory.liquor_config import (
    to_base_units,
    validate_unit_for_kind,
    get_base_unit_default,
    LiquorKind,
    DEFAULT_SHOTS_PER_BOTTLE,
    DEFAULT_BARMAN_SHOTS_PER_BOTTLE,
)

logger = logging.getLogger(__name__)


class OutOfStockError(Exception):
    """Raised when there's insufficient stock for a sale"""

    pass


@transaction.atomic
def stock_in_liquor(
    *,
    business,
    product_id: int,
    user,
    quantity: int,
    unit: str,  # "bottle" only for spirits/whisky
    cost_per_unit: Decimal,
    location=None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stock in liquor products with automatic barman shots accounting.

    NEW RULES (Spirits/Whisky):
    - Stock-in is BOTTLE-ONLY (no case, no crate, no pack)
    - When stocking spirits/whisky bottles for shot-selling:
      * Add sellable shots_per_bottle to inventory (default 24)
      * Automatically record 2 barman shots per bottle as staff consumption (non-sellable)
      * These 2 shots are tracked separately and do not appear in sellable stock

    Args:
        business: Business instance
        product_id: ID of the MerchProduct to stock in
        user: User performing the stock-in
        quantity: Quantity to add
        unit: Unit type ("bottle" for spirits/whisky, "bottle"/"crate"/"6-pack" for others)
        cost_per_unit: Cost per unit
        location: Location instance (optional)
        notes: Stock-in notes (optional)

    Returns:
        Dict with:
            - ok: bool
            - message: str
            - sellable_added: int (base units added to sellable stock)
            - barman_shots_recorded: int (staff shots recorded, if applicable)
            - error: str (if not ok)

    Raises:
        ValidationError: If validation fails
    """
    # Lock and fetch product
    try:
        product = MerchProduct.objects.select_for_update().get(
            pk=product_id, business=business, kind=BusinessKind.LIQUOR, is_active=True
        )
    except MerchProduct.DoesNotExist:
        raise ValidationError("Product not found or not available")

    # Get liquor kind
    liquor_kind = (product.category or "").lower()

    # Validate unit is allowed for stock-in
    pack_enabled = product.pack_label is not None and product.bottles_per_crate is not None
    validate_unit_for_kind(liquor_kind, unit, pack_enabled=pack_enabled, for_stock_in=True)

    # Convert to base units
    try:
        qty_base_units = to_base_units(quantity, unit, product)
    except ValidationError as e:
        raise ValidationError(f"Cannot stock in {product.name}: {str(e)}")

    # Initialize tracking variables
    sellable_added = qty_base_units
    barman_shots_recorded = 0

    # BARMAN SHOTS LOGIC: For spirits/whisky with shot-selling enabled
    if liquor_kind in (LiquorKind.SPIRITS, LiquorKind.WHISKY):
        # Check if product is configured for shot-selling
        base_unit = get_base_unit_default(liquor_kind)
        if base_unit == "shot" and unit.lower() == "bottle":
            # Calculate barman shots (2 per bottle)
            barman_shots_recorded = quantity * DEFAULT_BARMAN_SHOTS_PER_BOTTLE

            # Deduct barman shots from sellable stock
            # Sellable stock = (bottles * shots_per_bottle) - barman_shots
            sellable_added = qty_base_units - barman_shots_recorded

            # Create a stock adjustment record for barman shots (expense/usage)
            try:
                from inventory.models_verticals import LiquorStockAdjustment

                LiquorStockAdjustment.objects.create(
                    business=business,
                    product=product,
                    quantity_change=-barman_shots_recorded,  # Negative = consumed
                    reason="BARMAN_SHOTS",
                    notes=f"Automatic barman shots deduction: {quantity} bottle(s) × {DEFAULT_BARMAN_SHOTS_PER_BOTTLE} shots/bottle = {barman_shots_recorded} staff shots",
                    adjusted_by=user,
                    location=location,
                )
            except Exception as e:
                # If LiquorStockAdjustment model doesn't exist, log it
                logger.warning(
                    f"Could not create barman shots adjustment record: {e}. "
                    f"Barman shots ({barman_shots_recorded}) still deducted from sellable stock."
                )

    # Update product stock (add sellable quantity only)
    product.quantity_in_stock = (product.quantity_in_stock or 0) + sellable_added

    # Update cost per base unit if provided
    if cost_per_unit > 0:
        # Calculate cost per base unit
        if unit.lower() == "bottle":
            if liquor_kind in (LiquorKind.SPIRITS, LiquorKind.WHISKY):
                # For spirits/whisky, cost_per_unit is per bottle
                # Convert to cost per shot
                shots_per_bottle = product.shots_per_bottle or DEFAULT_SHOTS_PER_BOTTLE
                product.cost_per_shot = cost_per_unit / Decimal(shots_per_bottle)
            else:
                # For beer/cider/wine, cost_per_unit is per bottle
                product.cost_per_bottle = cost_per_unit
        else:
            # For pack/crate, calculate cost per bottle
            pack_size = product.bottles_per_crate or 1
            product.cost_per_bottle = cost_per_unit / Decimal(pack_size)

    product.save()

    # Build success message
    base_unit = get_base_unit_default(liquor_kind)
    message = f"✅ Stocked in: {quantity} {unit}(s) = {sellable_added} sellable {base_unit}(s) — {product.name}"

    if barman_shots_recorded > 0:
        message += f" (Barman shots: {barman_shots_recorded} automatically recorded)"

    return {
        "ok": True,
        "message": message,
        "sellable_added": sellable_added,
        "barman_shots_recorded": barman_shots_recorded,
    }


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
    payment_method: Optional[str] = None,  # "cash", "bank", "mobile_money"
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
            pk=product_id, business=business, kind=BusinessKind.LIQUOR, is_active=True
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

    # Validate unit is allowed for this liquor kind
    liquor_kind = (product.category or "").lower()
    pack_enabled = product.pack_label is not None and product.bottles_per_crate is not None
    validate_unit_for_kind(liquor_kind, unit, pack_enabled=pack_enabled)

    # Calculate totals
    total = Decimal(quantity) * unit_price
    if total <= 0:
        raise ValidationError("Sale total must be greater than zero")

    # Get cost for profit tracking
    unit_cost = product.get_cost_for_unit(unit) or Decimal("0.00")
    total_cost = Decimal(quantity) * unit_cost

    # Convert to base units for stock tracking
    try:
        qty_base_units = to_base_units(quantity, unit, product)
    except ValidationError as e:
        # Re-raise with product context
        raise ValidationError(f"Cannot sell {product.name}: {str(e)}")

    # For credit sales, ensure payment mix is zero
    if is_credit:
        cash_amount = Decimal("0.00")
        bank_amount = Decimal("0.00")
        mobile_money_amount = Decimal("0.00")

    # Determine payment_method if not provided
    payment_mix_total = cash_amount + bank_amount + mobile_money_amount
    if payment_method is None:
        if payment_mix_total > 0:
            # Determine from payment amounts
            if cash_amount > 0 and bank_amount == 0 and mobile_money_amount == 0:
                payment_method = "cash"
            elif bank_amount > 0 and cash_amount == 0 and mobile_money_amount == 0:
                payment_method = "bank"
            elif mobile_money_amount > 0 and cash_amount == 0 and bank_amount == 0:
                payment_method = "mobile_money"
            else:
                payment_method = "cash"  # Default for mixed payments
        else:
            payment_method = "cash"  # Default

    # If payment_method is specified but all amounts are zero, set the appropriate amount
    if payment_mix_total == 0 and not is_credit:
        if payment_method.lower() == "cash":
            cash_amount = total
        elif payment_method.lower() == "bank":
            bank_amount = total
        elif payment_method.lower() in ("mobile_money", "mobile"):
            mobile_money_amount = total
        else:
            cash_amount = total  # Default to cash
        payment_mix_total = total

    # Validate payment mix
    if payment_mix_total > 0 and payment_mix_total != total:
        raise ValidationError(f"Payment mix total (K{payment_mix_total}) must equal sale total (K{total})")

    # Normalize payment_method
    from inventory.models_verticals import PaymentMethod

    payment_method_map = {
        "cash": PaymentMethod.CASH,
        "bank": PaymentMethod.BANK,
        "mobile_money": PaymentMethod.MOBILE_MONEY,
        "mobile": PaymentMethod.MOBILE_MONEY,
    }
    payment_method_enum = payment_method_map.get(payment_method.lower(), PaymentMethod.CASH)

    # CRITICAL: Decrement stock atomically using conditional update
    # This prevents overselling even under high concurrency
    # Stock is tracked in base units (bottles/cans/glasses/shots)
    if product.track_inventory:
        # Use F() expression for atomic decrement in BASE UNITS
        updated = MerchProduct.objects.filter(pk=product.pk, quantity_in_stock__gte=qty_base_units).update(
            quantity_in_stock=F("quantity_in_stock") - qty_base_units
        )

        if updated == 0:
            # Re-fetch to get current stock for error message
            product.refresh_from_db()
            current_stock = product.quantity_in_stock or 0
            base_unit = get_base_unit_default(liquor_kind)
            raise OutOfStockError(
                f"Insufficient stock: {product.name}. "
                f"Available: {current_stock} {base_unit}(s), "
                f"Requested: {qty_base_units} {base_unit}(s) ({quantity} {unit})"
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
        notes=notes or "",
        payment_method=payment_method_enum,
        cash_amount=cash_amount,
        bank_amount=bank_amount,
        mobile_money_amount=mobile_money_amount,
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
            created_by=user,
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
                created_by=user,
            )
        except Exception as wallet_err:
            # Don't block sale if wallet entry fails - log and continue
            logger.warning(f"Failed to create wallet entry for sale #{sale.id}: {wallet_err}", exc_info=True)

    return {
        "ok": True,
        "sale_id": sale.id,
        "credit_id": credit.id if credit else None,
        "message": f"Sold {quantity} × {product.name} ({unit})"
        if not is_credit
        else f"Credit sale recorded: {quantity} × {product.name} ({unit}) for {customer_name}",
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
    payment_method: Optional[str] = None,  # "cash", "bank", "mobile_money"
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
            business=business, kind=BusinessKind.LIQUOR, is_active=True, barcode=barcode
        )
    except MerchProduct.DoesNotExist:
        raise ValidationError(f"Product with barcode '{barcode}' not found")
    except MerchProduct.MultipleObjectsReturned:
        # If multiple products have same barcode, get first one
        product = (
            MerchProduct.objects.select_for_update()
            .filter(business=business, kind=BusinessKind.LIQUOR, is_active=True, barcode=barcode)
            .first()
        )
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
            # For bottle, try price_per_bottle first, then fall back to selling_price
            unit_price = product.price_per_bottle or getattr(product, "selling_price", None) or Decimal("0.00")

        if unit_price == Decimal("0.00"):
            raise ValidationError(f"{product.name} does not have a price per {unit} set")
    else:
        # If unit_price is provided, update the product's price for this unit
        if unit == "shot":
            product.price_per_shot = unit_price
        elif unit == "glass":
            product.price_per_glass = unit_price
        else:
            product.price_per_bottle = unit_price
        # Also update selling_price for backward compatibility
        product.selling_price = unit_price
        product.save(update_fields=["price_per_shot", "price_per_glass", "price_per_bottle", "selling_price"])

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
        payment_method=payment_method,
        shift=shift,
    )
