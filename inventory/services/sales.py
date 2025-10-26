# inventory/services/sales.py
from __future__ import annotations
from decimal import Decimal
from typing import Dict, Any
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from inventory.models import StockItem  # adjust if name differs
from sales.models import Sale
from tenants.models import Location  # adjust import if you use BusinessLocation/Store

def mark_item_sold(*, code: str, price: Decimal, commission_pct: Decimal | int,
                   sold_at, location_id: int, user) -> Dict[str, Any]:
    """
    Single source of truth: marks one item as SOLD and returns new aggregates.
    Atomic, idempotent (errors if already sold).
    """
    if not location_id:
        raise ValidationError("Location is required.")

    with transaction.atomic():
        # lock the row to avoid races
        item = (StockItem.objects
                .select_for_update()
                .select_related('product')
                .get(code=code))

        if item.status == StockItem.Status.SOLD:
            raise ValidationError("Item is already sold.")

        try:
            location = Location.objects.get(id=location_id, tenant=item.tenant)
        except ObjectDoesNotExist:
            raise ValidationError("Invalid location.")

        # Create Sale
        sale = Sale.objects.create(
            tenant=item.tenant,
            item=item,
            product=item.product,
            location=location,              # <-- fixes your NOT NULL
            seller=user if user.is_authenticated else None,
            price=price,
            commission_pct=commission_pct or 0,
            sold_at=sold_at or timezone.now(),
        )

        # Flip inventory state
        item.status = StockItem.Status.SOLD
        item.sold_at = sale.sold_at
        item.sold_price = price
        item.sold_location = location  # if you keep a copy on the item
        item.save(update_fields=["status","sold_at","sold_price","sold_location"])

        # Return fresh aggregates so UI updates instantly
        from django.db.models import Sum, Count
        qs_instock = StockItem.objects.filter(tenant=item.tenant, status=StockItem.Status.IN_STOCK)
        qs_sold = StockItem.objects.filter(tenant=item.tenant, status=StockItem.Status.SOLD)

        sum_order = qs_instock.aggregate(total=Sum("order_price"))["total"] or 0
        sum_selling = qs_instock.aggregate(total=Sum("selling_price"))["total"] or 0

        return {
            "sale_id": sale.id,
            "item_id": item.id,
            "counts": {
                "items_in_stock": qs_instock.count(),
                "sold_count": qs_sold.count(),
            },
            "sums": {
                "sum_order": sum_order,
                "sum_selling": sum_selling,
            }
        }
