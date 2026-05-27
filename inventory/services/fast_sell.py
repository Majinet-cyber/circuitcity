# inventory/services/fast_sell.py
"""
Fast Sell services - centralized business logic for barcode-scanning fast-sell flows.
ONLY enabled for pharmacy and clothing verticals.
Phones and liquor use their own dedicated scan/sell flows.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone


def lookup_product_by_barcode(
    *,
    business,
    vertical: str,
    barcode: str,
) -> Dict[str, Any]:
    """
    Look up a product by barcode for Fast Sell.

    Supports pharmacy, clothing, and liquor verticals.
    Phones are NOT supported (they use dedicated flows).

    Returns dict with:
        - ok: bool
        - found: bool
        - product: dict (if found)
        - stock_qty: int (if found)
        - selling_price: Decimal (if found)
        - needs_price: bool
        - error: str (if not ok)
    """
    from inventory.models import MerchProduct
    from inventory.models_pharmacy import PharmacyBatch
    from inventory.utils_vertical_capabilities import vertical_supports_fast_sell

    # Allow lookup for pharmacy, clothing, and liquor (even though liquor doesn't support full fast sell)
    if vertical not in ("pharmacy", "clothing", "liquor"):
        return {
            "ok": False,
            "error": f"Fast Sell lookup is not enabled for {vertical}. Use the dedicated scan/sell flow instead.",
        }

    try:
        if vertical == "pharmacy":
            # Pharmacy: Look up by barcode in PharmacyBatch or MerchProduct
            # Try batch barcode first (most specific)
            batch = (
                PharmacyBatch.objects.filter(business=business, is_archived=False, barcode=barcode, quantity__gt=0)
                .select_related("merch_product")
                .order_by("expiry_date")
                .first()
            )

            # Fall back to product barcode if batch not found
            if not batch:
                batch = (
                    PharmacyBatch.objects.filter(
                        business=business, is_archived=False, merch_product__barcode=barcode, quantity__gt=0
                    )
                    .select_related("merch_product")
                    .order_by("expiry_date")
                    .first()
                )

            if not batch:
                return {"ok": True, "found": False, "error": "Batch not found or out of stock"}

            product = batch.merch_product
            selling_price = batch.selling_price or Decimal("0.00")
            needs_price = selling_price == 0

            return {
                "ok": True,
                "found": True,
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "category": getattr(product, "category", ""),
                },
                "batch_id": batch.id,
                "batch_number": batch.batch_number or "N/A",
                "batch_code": batch.batch_number or "N/A",
                "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else None,
                "stock_qty": batch.quantity,
                "selling_price": float(selling_price),
                "needs_price": needs_price,
            }

        elif vertical == "clothing":
            # Clothing: MUST use ClothingBarcodeUnit lookup (barcoded items only)
            from inventory.services.clothing_barcode_service import lookup_barcode_for_fast_sell

            result = lookup_barcode_for_fast_sell(business=business, barcode=barcode)

            if not result.get("found"):
                return {"ok": True, "found": False, "error": result.get("error", "Barcode not found")}

            unit = result["unit"]

            return {
                "ok": True,
                "found": True,
                "product": {
                    "id": unit.id,
                    "name": f"{unit.category.title()} - Size {unit.size}",
                    "category": unit.category or "",
                    "size": unit.size,
                    "color": unit.color or "",
                },
                "stock_qty": 1,  # Always 1 for barcoded units
                "selling_price": float(unit.selling_price),
                "needs_price": False,  # Price is pre-stored
            }

        elif vertical == "liquor":
            # Liquor: Look up by barcode in MerchProduct (similar to clothing)
            product = MerchProduct.objects.filter(
                business=business, kind="liquor", is_active=True, barcode=barcode
            ).first()

            if not product:
                return {"ok": True, "found": False, "error": "Product not found"}

            stock_qty = product.quantity_in_stock or 0
            if stock_qty <= 0:
                return {"ok": True, "found": False, "error": "Out of stock"}

            selling_price = product.selling_price or Decimal("0.00")
            needs_price = selling_price == 0

            return {
                "ok": True,
                "found": True,
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "category": product.category or "",
                },
                "stock_qty": stock_qty,
                "selling_price": float(selling_price),
                "needs_price": needs_price,
            }

        else:
            return {"ok": False, "error": f"Unsupported vertical: {vertical}"}

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.exception(f"Fast Sell lookup error: {e}")
        return {"ok": False, "error": "Internal server error"}


@transaction.atomic
def create_fast_sell(
    *,
    business,
    vertical: str,
    user,
    barcode: str,
    quantity: int = 1,
    payment_method: str = "cash",
    selling_price: Optional[Decimal] = None,
    attributed_to_agent_id: Optional[int] = None,  # DEPRECATED: No longer used (liquor removed)
) -> Dict[str, Any]:
    """
    Create a Fast Sell sale.

    ONLY supports pharmacy and clothing verticals.
    Phones and liquor are NOT supported (they use dedicated flows).

    Returns dict with:
        - ok: bool
        - sale_id: int (if ok)
        - message: str
        - kpis: dict (updated KPIs)
        - error: str (if not ok)
    """
    from django.contrib.auth import get_user_model

    from inventory.models import MerchProduct
    from inventory.models_pharmacy import PharmacyBatch, PharmacySale
    from inventory.models_verticals import ClothingSale
    from inventory.models_verticals import PaymentMethod as VPaymentMethod
    from inventory.utils_vertical_capabilities import vertical_supports_fast_sell

    User = get_user_model()

    # CRITICAL: Capability check - Fast Sell ONLY for pharmacy + clothing
    if not vertical_supports_fast_sell(vertical):
        return {
            "ok": False,
            "error": f"Fast Sell is not enabled for {vertical}. Use the dedicated scan/sell flow instead.",
        }

    try:
        # Normalize payment method
        payment_map = {
            "cash": "cash",
            "bank": "bank",
            "mobile_money": "mobile_money",
            "mobile": "mobile_money",
        }
        payment_method = payment_map.get(payment_method.lower(), "cash")

        if vertical == "pharmacy":
            # Pharmacy Fast Sell - lookup by barcode (batch or product)
            batch = (
                PharmacyBatch.objects.select_for_update()
                .filter(business=business, is_archived=False, barcode=barcode, quantity__gte=quantity)
                .select_related("merch_product")
                .order_by("expiry_date")
                .first()
            )

            # Fall back to product barcode if batch barcode not found
            if not batch:
                batch = (
                    PharmacyBatch.objects.select_for_update()
                    .filter(
                        business=business, is_archived=False, merch_product__barcode=barcode, quantity__gte=quantity
                    )
                    .select_related("merch_product")
                    .order_by("expiry_date")
                    .first()
                )

            if not batch:
                return {"ok": False, "error": "Batch not found or insufficient stock"}

            product = batch.merch_product

            # Determine selling price
            if selling_price is None:
                selling_price = batch.selling_price or Decimal("0.00")

            if selling_price == 0:
                if selling_price is None:
                    return {"ok": False, "needs_price": True, "error": "Selling price required"}
                else:
                    # Update batch selling price
                    batch.selling_price = selling_price
                    batch.save(update_fields=["selling_price"])

            # Calculate totals
            unit_price = selling_price
            total_amount = unit_price * quantity
            unit_cost = batch.cost_price or Decimal("0.00")

            # Decrease batch stock
            batch.quantity -= quantity
            batch.save(update_fields=["quantity"])

            # Create sale
            sale = PharmacySale.objects.create(
                business=business,
                batch=batch,
                quantity=quantity,
                unit_price=unit_price,
                unit_cost=unit_cost,
                total_amount=total_amount,
                payment_method=payment_method,
                sold_by=user,
            )

            return {
                "ok": True,
                "sale_id": sale.id,
                "message": f"Sold {quantity} × {product.name} (Batch: {batch.batch_number})",
            }

        elif vertical == "clothing":
            # Clothing Fast Sell - MUST use ClothingBarcodeUnit (unique barcoded items)
            # Import here to avoid circular dependency
            from inventory.services.clothing_barcode_service import create_fast_sell_from_barcode

            # Get active location (required for clothing)
            location = None
            if hasattr(user, "active_location"):
                location = user.active_location

            if not location:
                # Try to get from business's default location, or any location
                from inventory.models import Location

                # Prefer default location, fallback to any location
                location = (
                    Location.objects.filter(business=business, is_default=True).first()
                    or Location.objects.filter(business=business).first()
                )

                if not location:
                    return {"ok": False, "error": "No location found for this business"}

            # Use clothing barcode service to create sale
            result = create_fast_sell_from_barcode(
                business=business,
                location=location,
                user=user,
                barcode=barcode,
                quantity=quantity,
                payment_method=payment_method,
            )

            return result

        else:
            return {"ok": False, "error": f"Unsupported vertical: {vertical}"}

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.exception(f"Fast Sell create error: {e}")
        return {"ok": False, "error": str(e)}


def get_fast_sell_kpis(
    *,
    business,
    vertical: str,
    date_range: str = "today",  # today, mtd, custom
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Get Fast Sell KPIs for dashboard display.

    ONLY supports pharmacy and clothing verticals.
    Phones and liquor are NOT supported (they use dedicated flows).

    Returns dict with:
        - sold_today: int
        - revenue_today: Decimal
        - profit_today: Decimal (if cost tracking available)
    """
    from inventory.models_pharmacy import PharmacySale
    from inventory.models_verticals import ClothingSale
    from inventory.utils_vertical_capabilities import vertical_supports_fast_sell

    # CRITICAL: Capability check - Fast Sell ONLY for pharmacy + clothing
    if not vertical_supports_fast_sell(vertical):
        return {"ok": False, "error": f"Fast Sell is not enabled for {vertical}."}

    try:
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Determine date range
        if date_range == "today":
            start = today_start
            end = today_end
        elif date_range == "mtd":
            start = today_start.replace(day=1)
            end = today_end
        elif date_range == "custom" and start_date and end_date:
            start = start_date
            end = end_date
        else:
            start = today_start
            end = today_end

        if vertical == "pharmacy":
            sales = PharmacySale.objects.filter(business=business, sold_at__gte=start, sold_at__lt=end)
            sold_count = sales.aggregate(total=Sum("quantity"))["total"] or 0
            revenue = sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
            # Pharmacy cost calculation
            cost = Decimal("0.00")
            for sale in sales:
                cost += sale.unit_cost * sale.quantity
            profit = revenue - cost

        elif vertical == "clothing":
            sales = ClothingSale.objects.filter(business=business, sold_at__gte=start, sold_at__lt=end)
            sold_count = sales.aggregate(total=Sum("quantity"))["total"] or 0
            revenue = sales.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
            cost = sales.aggregate(total=Sum("total_cost"))["total"] or Decimal("0.00")
            profit = revenue - cost

        else:
            return {"ok": False, "error": f"Unsupported vertical: {vertical}"}

        return {
            "ok": True,
            "sold_today": sold_count,
            "revenue_today": float(revenue),
            "profit_today": float(profit),
        }

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.exception(f"Fast Sell KPIs error: {e}")
        return {"ok": False, "error": "Internal server error"}
