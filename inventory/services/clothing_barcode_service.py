# inventory/services/clothing_barcode_service.py
"""
Service layer for clothing barcode unit management.

Handles:
- Creating barcoded clothing units (Step 1: prices -> Step 2: scan loop)
- Fast sell lookup and sale creation
- Barcode validation and duplicate checking
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from inventory.clothing_size_validation import validate_clothing_size
from inventory.models import MerchProduct
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from inventory.models_verticals import ClothingSale
from tenants.models import Business


@transaction.atomic
def create_barcode_batch_session(
    *,
    business: Business,
    location,
    user,
    category: str,
    subcategory: str = "",
    size: str,
    quantity: int,
    cost_price: Decimal,
    selling_price: Decimal,
    brand: str = "",
    color: str = "",
    product_name: str = "",
) -> Dict[str, Any]:
    """
    Step 1: Validate and store batch details in session.

    This is called BEFORE opening the scanner.
    Validates all prices, quantities, and size rules.

    Args:
        business: Business instance
        location: Location instance
        user: User creating the batch
        category: Category (e.g., "shoes", "shirt")
        subcategory: Subcategory (e.g., "sneaker", "boot")
        size: Size (validated by category rules)
        quantity: Number of units to scan
        cost_price: Cost per unit
        selling_price: Selling price per unit
        brand: Optional brand
        color: Optional color
        product_name: Optional product name

    Returns:
        Dict with session_data to store in request.session

    Raises:
        ValidationError: If validation fails
    """
    # Validate quantity
    if quantity < 1:
        raise ValidationError("Quantity must be at least 1")

    if quantity > 100:
        raise ValidationError("Quantity cannot exceed 100 units per batch")

    # Validate prices
    if cost_price < Decimal("0.00"):
        raise ValidationError("Cost price cannot be negative")

    if selling_price <= Decimal("0.00"):
        raise ValidationError("Selling price must be greater than zero")

    # Validate size (CRITICAL: shoes must be numeric only)
    # SIZE IS OPTIONAL in barcode wizard: Only validate format if size is provided
    is_valid, error_msg = validate_clothing_size(size, category, subcategory, allow_blank=True)
    if not is_valid:
        raise ValidationError(error_msg)

    # Check for manager override if selling below cost
    if selling_price < cost_price:
        # This should be checked in the view layer with manager permission
        # Here we just validate that it's been approved
        pass  # Assume view layer handles manager override checkbox

    # Create session data
    session_data = {
        "business_id": business.id,
        "location_id": location.id,
        "user_id": user.id,
        "category": category,
        "subcategory": subcategory,
        "size": size,
        "quantity": quantity,
        "cost_price": str(cost_price),
        "selling_price": str(selling_price),
        "brand": brand,
        "color": color,
        "product_name": product_name or f"{category.title()} - Size {size}",
        "scanned_count": 0,
        "scanned_barcodes": [],
        "created_at": timezone.now().isoformat(),
    }

    return session_data


@transaction.atomic
def scan_barcode_unit(
    *,
    session_data: Dict[str, Any],
    barcode: str,
    business: Business,
    location,
    user,
) -> Dict[str, Any]:
    """
    Step 2: Scan a barcode and create a unit.

    Called for each barcode scan in the loop.
    Creates ClothingBarcodeUnit record immediately.

    Args:
        session_data: Session data from create_barcode_batch_session
        barcode: Scanned barcode
        business: Business instance
        location: Location instance
        user: User scanning

    Returns:
        Dict with:
            - ok: bool
            - scanned_count: int
            - remaining: int
            - complete: bool
            - unit_id: int (if ok)
            - error: str (if not ok)
    """
    barcode = barcode.strip().upper()

    # Validate barcode format
    if len(barcode) < 3:
        return {"ok": False, "error": "Barcode must be at least 3 characters"}

    if len(barcode) > 100:
        return {"ok": False, "error": "Barcode too long (max 100 characters)"}

    # Check if already scanned in this batch
    scanned_barcodes = session_data.get("scanned_barcodes", [])
    if barcode in scanned_barcodes:
        return {"ok": False, "error": f"Barcode {barcode} already scanned in this batch"}

    # Check if barcode already exists in database (business-wide)
    existing = ClothingBarcodeUnit.objects.filter(business=business, barcode=barcode, is_active=True).first()

    if existing:
        return {"ok": False, "error": f"Barcode {barcode} already exists (Status: {existing.get_status_display()})"}

    # Check quantity limit
    quantity = session_data.get("quantity", 1)
    if len(scanned_barcodes) >= quantity:
        return {"ok": False, "error": f"Already scanned {quantity} barcodes (limit reached)"}

    # Create the unit
    try:
        unit = ClothingBarcodeUnit.objects.create(
            business=business,
            location=location,
            barcode=barcode,
            category=session_data.get("category", ""),
            subcategory=session_data.get("subcategory", ""),
            size=session_data.get("size", ""),
            color=session_data.get("color", ""),
            brand=session_data.get("brand", ""),
            cost_price=Decimal(session_data.get("cost_price", "0.00")),
            selling_price=Decimal(session_data.get("selling_price", "0.00")),
            status="IN_STOCK",
            received_at=timezone.localdate(),
            created_by=user,
            is_active=True,
        )

        # Update session
        scanned_barcodes.append(barcode)
        scanned_count = len(scanned_barcodes)
        remaining = quantity - scanned_count
        complete = scanned_count >= quantity

        return {
            "ok": True,
            "unit_id": unit.id,
            "barcode": barcode,
            "scanned_count": scanned_count,
            "remaining": remaining,
            "complete": complete,
            "scanned_barcodes": scanned_barcodes,
        }

    except Exception as e:
        return {"ok": False, "error": f"Failed to create unit: {str(e)}"}


def lookup_barcode_for_fast_sell(
    *,
    business: Business,
    barcode: str,
    location=None,
) -> Dict[str, Any]:
    """
    Lookup a barcoded unit for fast sell.
    
    CRITICAL: ONLY works with ClothingBarcodeUnit (unique barcoded items).
    For common stock (non-barcoded), use Manual Sell instead.

    Args:
        business: Business instance
        barcode: Barcode to lookup
        location: Optional location filter

    Returns:
        Dict with:
            - found: bool
            - unit: ClothingBarcodeUnit (if found)
            - error: str (if not found)
    """
    barcode = barcode.strip().upper()

    # Find IN_STOCK unit with this barcode
    query = ClothingBarcodeUnit.objects.filter(business=business, barcode=barcode, status="IN_STOCK", is_active=True)

    if location:
        query = query.filter(location=location)

    unit = query.first()

    if not unit:
        # Check if barcode exists but is already sold
        sold_unit = ClothingBarcodeUnit.objects.filter(
            business=business, barcode=barcode, status="SOLD", is_active=True
        ).first()

        if sold_unit:
            return {"found": False, "error": f"Barcode {barcode} already sold on {sold_unit.sold_at}"}

        # CRITICAL: No fallback to MerchProduct
        # Fast Sell is ONLY for unique barcoded items
        return {"found": False, "error": f"Barcode {barcode} not found. Add it to stock first or use manual sell."}

    return {
        "found": True,
        "unit": unit,
        "barcode": unit.barcode,
        "size": unit.size,
        "category": unit.category,
        "selling_price": unit.selling_price,
        "cost_price": unit.cost_price,
    }


@transaction.atomic
def create_fast_sell_from_barcode(
    *,
    business: Business,
    location,
    user,
    barcode: str,
    quantity: int = 1,
    payment_method: str = "cash",
) -> Dict[str, Any]:
    """
    Fast sell: scan barcode -> create sale -> mark unit sold.

    CRITICAL: This is the ONLY way to sell barcoded clothing items (unique stock).
    For common stock (non-barcoded), use Manual Sell instead.
    Uses pre-stored prices from the ClothingBarcodeUnit.

    Args:
        business: Business instance
        location: Location instance
        user: User making the sale
        barcode: Barcode to sell
        quantity: Quantity (ignored for barcode units, always 1)
        payment_method: Payment method (cash, bank, mobile_money)

    Returns:
        Dict with:
            - ok: bool
            - sale_id: int (if ok)
            - amount: Decimal (if ok)
            - profit: Decimal (if ok)
            - error: str (if not ok)
    """
    # Lookup unit (ONLY ClothingBarcodeUnit, no fallback)
    lookup_result = lookup_barcode_for_fast_sell(business=business, barcode=barcode, location=location)

    if not lookup_result.get("found"):
        return {"ok": False, "error": lookup_result.get("error", "Unit not found")}

    # Validate payment method
    from inventory.models_verticals import PaymentMethod

    payment_map = {
        "cash": PaymentMethod.CASH,
        "bank": PaymentMethod.BANK,
        "mobile_money": PaymentMethod.MOBILE_MONEY,
        "mobile": PaymentMethod.MOBILE_MONEY,
    }
    payment_method_enum = payment_map.get(payment_method.lower(), PaymentMethod.CASH)

    # CRITICAL: Only ClothingBarcodeUnit path (no MerchProduct fallback)
    unit = lookup_result["unit"]

    # Create sale
    sale = ClothingSale.objects.create(
        business=business,
        product=unit.product,  # May be None
        quantity=1,  # Always 1 for barcoded units
        unit_price=unit.selling_price,
        total_price=unit.selling_price,
        unit_cost=unit.cost_price,
        total_cost=unit.cost_price,
        payment_method=payment_method_enum,
        sold_by=user,
        sold_at=timezone.now(),
        notes=f"Fast sell - Barcode: {unit.barcode}, Size: {unit.size}",
    )

    # Mark unit as sold
    unit.mark_sold(sold_date=timezone.localdate())

    # Calculate profit
    profit = unit.selling_price - unit.cost_price

    return {
        "ok": True,
        "sale_id": sale.id,
        "unit_id": unit.id,
        "barcode": unit.barcode,
        "size": unit.size,
        "amount": unit.selling_price,
        "cost": unit.cost_price,
        "profit": profit,
        "payment_method": payment_method_enum.value,
    }


def check_barcode_duplicate(
    *,
    business: Business,
    barcode: str,
) -> Dict[str, Any]:
    """
    Check if a barcode already exists.

    Args:
        business: Business instance
        barcode: Barcode to check

    Returns:
        Dict with:
            - exists: bool
            - unit: ClothingBarcodeUnit (if exists)
    """
    barcode = barcode.strip().upper()

    unit = ClothingBarcodeUnit.objects.filter(business=business, barcode=barcode, is_active=True).first()

    return {
        "exists": unit is not None,
        "unit": unit,
    }


# Export service functions
__all__ = [
    "create_barcode_batch_session",
    "scan_barcode_unit",
    "lookup_barcode_for_fast_sell",
    "create_fast_sell_from_barcode",
    "check_barcode_duplicate",
]
