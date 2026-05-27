# inventory/services/services_recalc.py
"""
Recalculation services for inventory totals, stock values, and KPIs.
Called after admin edits/deletes to ensure dashboards reflect changes immediately.
"""
from decimal import Decimal
from typing import Optional
import logging

from django.db.models import Sum, Q, F, Count, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

logger = logging.getLogger(__name__)


def recalc_inventory_kpis(business_id: int, location_id: Optional[int] = None) -> dict:
    """
    Recalculate inventory KPIs for a business (and optionally a location).
    This ensures dashboards reflect the latest stock values and totals.

    Args:
        business_id: Business ID to recalculate for
        location_id: Optional location ID to scope to

    Returns:
        dict with:
            - total_stock_value (Decimal) - cost basis
            - total_retail_value (Decimal) - selling price basis
            - total_items (int) - count of active stock items
            - on_hand_quantity (int) - total quantity in stock
    """
    from inventory.models import InventoryItem
    from tenants.models import Business

    try:
        business = Business.objects.get(pk=business_id)
    except Business.DoesNotExist:
        logger.warning(f"Business {business_id} not found for KPI recalculation")
        return {
            "total_stock_value": Decimal("0.00"),
            "total_retail_value": Decimal("0.00"),
            "total_items": 0,
            "on_hand_quantity": 0,
        }

    # Query active, in-stock items
    qs = InventoryItem.objects.filter(
        business=business,
        is_active=True,
        status="IN_STOCK",
        sold_at__isnull=True,
    )

    if location_id:
        qs = qs.filter(current_location_id=location_id)

    # Aggregate stock value (cost basis) and retail value (selling price basis)
    agg = qs.aggregate(
        total_stock_value=Coalesce(
            Sum("order_price"), Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2)
        ),
        total_retail_value=Coalesce(
            Sum(
                Coalesce(
                    F("selling_price"), F("order_price"), output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            ),
            Decimal("0.00"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        total_items=Count("id"),
    )

    result = {
        "total_stock_value": Decimal(str(agg.get("total_stock_value") or 0)),
        "total_retail_value": Decimal(str(agg.get("total_retail_value") or 0)),
        "total_items": agg.get("total_items") or 0,
        "on_hand_quantity": agg.get("total_items") or 0,
    }

    logger.info(
        f"Recalculated inventory KPIs for business={business_id}, location={location_id}: "
        f"stock_value={result['total_stock_value']}, items={result['total_items']}"
    )

    return result


def recalc_product_stock(product_id: int) -> dict:
    """
    Recalculate stock totals for a specific product.

    Args:
        product_id: Product ID to recalculate for

    Returns:
        dict with:
            - on_hand_quantity (int) - total in-stock items for this product
            - stock_value (Decimal) - total cost value
            - retail_value (Decimal) - total selling price value
    """
    from inventory.models import InventoryItem, Product

    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        logger.warning(f"Product {product_id} not found for stock recalculation")
        return {
            "on_hand_quantity": 0,
            "stock_value": Decimal("0.00"),
            "retail_value": Decimal("0.00"),
        }

    # Query active, in-stock items for this product
    qs = InventoryItem.objects.filter(
        product=product,
        is_active=True,
        status="IN_STOCK",
        sold_at__isnull=True,
    )

    agg = qs.aggregate(
        on_hand_quantity=Count("id"),
        stock_value=Coalesce(
            Sum("order_price"), Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2)
        ),
        retail_value=Coalesce(
            Sum(
                Coalesce(
                    F("selling_price"), F("order_price"), output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            ),
            Decimal("0.00"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
    )

    result = {
        "on_hand_quantity": agg.get("on_hand_quantity") or 0,
        "stock_value": Decimal(str(agg.get("stock_value") or 0)),
        "retail_value": Decimal(str(agg.get("retail_value") or 0)),
    }

    logger.info(
        f"Recalculated stock for product={product_id}: "
        f"quantity={result['on_hand_quantity']}, value={result['stock_value']}"
    )

    return result


def recalc_merch_product_stock(merch_product_id: int) -> dict:
    """
    Recalculate stock totals for a MerchProduct (liquor, clothing, etc.).
    Uses quantity_in_stock field for non-IMEI products.

    Args:
        merch_product_id: MerchProduct ID to recalculate for

    Returns:
        dict with:
            - on_hand_quantity (int) - from quantity_in_stock field
            - stock_value (Decimal) - cost_price * quantity
            - retail_value (Decimal) - selling_price * quantity
    """
    from inventory.models import MerchProduct

    try:
        product = MerchProduct.objects.get(pk=merch_product_id)
    except MerchProduct.DoesNotExist:
        logger.warning(f"MerchProduct {merch_product_id} not found for stock recalculation")
        return {
            "on_hand_quantity": 0,
            "stock_value": Decimal("0.00"),
            "retail_value": Decimal("0.00"),
        }

    qty = product.quantity_in_stock or 0
    cost_price = product.cost_price or Decimal("0.00")
    selling_price = product.selling_price or Decimal("0.00")

    result = {
        "on_hand_quantity": qty,
        "stock_value": cost_price * Decimal(qty),
        "retail_value": selling_price * Decimal(qty),
    }

    logger.info(
        f"Recalculated stock for MerchProduct={merch_product_id}: "
        f"quantity={result['on_hand_quantity']}, value={result['stock_value']}"
    )

    return result
