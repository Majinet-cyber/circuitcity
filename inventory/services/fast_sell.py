# inventory/services/fast_sell.py
"""
Fast Sell services - centralized business logic for barcode-scanning fast-sell flows.
ONLY enabled for pharmacy and clothing verticals.
Phones and liquor use their own dedicated scan/sell flows.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.exceptions import ValidationError


def lookup_product_by_barcode(
    *,
    business,
    vertical: str,
    barcode: str,
) -> Dict[str, Any]:
    """
    Look up a product by barcode for Fast Sell.
    
    ONLY supports pharmacy and clothing verticals.
    Phones and liquor are NOT supported (they use dedicated flows).
    
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
    
    # CRITICAL: Capability check - Fast Sell ONLY for pharmacy + clothing
    if not vertical_supports_fast_sell(vertical):
        return {
            "ok": False,
            "error": f"Fast Sell is not enabled for {vertical}. Use the dedicated scan/sell flow instead."
        }
    
    try:
        if vertical == "pharmacy":
            # Pharmacy: Look up by barcode in PharmacyBatch
            batch = PharmacyBatch.objects.filter(
                business=business,
                is_archived=False,
                barcode=barcode,
                units_remaining__gt=0
            ).select_related("merch_product").order_by("expiry_date").first()
            
            if not batch:
                return {"ok": True, "found": False, "error": "Batch not found or out of stock"}
            
            product = batch.merch_product
            selling_price = batch.selling_price_per_unit or Decimal("0.00")
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
                "batch_number": batch.batch_number,
                "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else None,
                "stock_qty": batch.units_remaining,
                "selling_price": float(selling_price),
                "needs_price": needs_price,
            }
        
        elif vertical == "clothing":
            # Clothing: Look up by barcode in MerchProduct
            product = MerchProduct.objects.filter(
                business=business,
                kind="clothing",
                is_active=True,
                barcode=barcode
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
                    "size": getattr(product, "size", ""),
                    "color": getattr(product, "color", ""),
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
    from inventory.models import MerchProduct
    from inventory.models_verticals import ClothingSale, PaymentMethod as VPaymentMethod
    from inventory.models_pharmacy import PharmacySale, PharmacyBatch
    from inventory.utils_vertical_capabilities import vertical_supports_fast_sell
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # CRITICAL: Capability check - Fast Sell ONLY for pharmacy + clothing
    if not vertical_supports_fast_sell(vertical):
        return {
            "ok": False,
            "error": f"Fast Sell is not enabled for {vertical}. Use the dedicated scan/sell flow instead."
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
            # Pharmacy Fast Sell
            batch = PharmacyBatch.objects.select_for_update().filter(
                business=business,
                is_archived=False,
                barcode=barcode,
                units_remaining__gte=quantity
            ).select_related("merch_product").order_by("expiry_date").first()
            
            if not batch:
                return {"ok": False, "error": "Batch not found or insufficient stock"}
            
            product = batch.merch_product
            
            # Determine selling price
            if selling_price is None:
                selling_price = batch.selling_price_per_unit or Decimal("0.00")
            
            if selling_price == 0:
                if selling_price is None:
                    return {"ok": False, "needs_price": True, "error": "Selling price required"}
                else:
                    # Update batch selling price
                    batch.selling_price_per_unit = selling_price
                    batch.save(update_fields=["selling_price_per_unit"])
            
            # Calculate totals
            unit_price = selling_price
            total_amount = unit_price * quantity
            unit_cost = batch.cost_price_per_unit or Decimal("0.00")
            
            # Decrease batch stock
            batch.units_remaining -= quantity
            batch.save(update_fields=["units_remaining"])
            
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
            # Clothing Fast Sell
            product = MerchProduct.objects.select_for_update().filter(
                business=business,
                kind="clothing",
                is_active=True,
                barcode=barcode
            ).first()
            
            if not product:
                return {"ok": False, "error": "Product not found"}
            
            stock_qty = product.quantity_in_stock or 0
            if stock_qty < quantity:
                return {"ok": False, "error": f"Insufficient stock (available: {stock_qty})"}
            
            # Determine selling price
            if selling_price is None:
                selling_price = product.selling_price or Decimal("0.00")
            
            if selling_price == 0:
                if selling_price is None:
                    return {"ok": False, "needs_price": True, "error": "Selling price required"}
                else:
                    # Update product selling price
                    product.selling_price = selling_price
                    product.save(update_fields=["selling_price"])
            
            # Calculate totals
            unit_price = selling_price
            total_price = unit_price * quantity
            unit_cost = product.cost_price or Decimal("0.00")
            total_cost = unit_cost * quantity
            
            # Decrease stock
            product.quantity_in_stock -= quantity
            product.save(update_fields=["quantity_in_stock"])
            
            # Create sale
            sale = ClothingSale.objects.create(
                business=business,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                total_price=total_price,
                unit_cost=unit_cost,
                total_cost=total_cost,
                payment_method=payment_method,
                sold_by=user,
            )
            
            return {
                "ok": True,
                "sale_id": sale.id,
                "message": f"Sold {quantity} × {product.name}",
            }
        
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
    from inventory.models_verticals import ClothingSale
    from inventory.models_pharmacy import PharmacySale
    from inventory.utils_vertical_capabilities import vertical_supports_fast_sell
    
    # CRITICAL: Capability check - Fast Sell ONLY for pharmacy + clothing
    if not vertical_supports_fast_sell(vertical):
        return {
            "ok": False,
            "error": f"Fast Sell is not enabled for {vertical}."
        }
    
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
            sales = PharmacySale.objects.filter(
                business=business,
                sold_at__gte=start,
                sold_at__lt=end
            )
            sold_count = sales.aggregate(total=Sum("quantity"))["total"] or 0
            revenue = sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
            # Pharmacy cost calculation
            cost = Decimal("0.00")
            for sale in sales:
                cost += (sale.unit_cost * sale.quantity)
            profit = revenue - cost
            
        elif vertical == "clothing":
            sales = ClothingSale.objects.filter(
                business=business,
                sold_at__gte=start,
                sold_at__lt=end
            )
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

