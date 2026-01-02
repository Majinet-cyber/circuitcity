# inventory/api_fast_sell.py
"""
Universal Fast Sell API for all verticals.
Provides barcode lookup and quick sell functionality.
"""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone

from inventory.utils_barcodes import find_sellable_by_barcode, normalize_barcode, validate_barcode
from tenants.utils import get_active_business, require_business


@login_required
@require_business
@require_http_methods(["GET"])
def fast_sell_lookup(request):
    """
    Lookup product by barcode for Fast Sell.

    GET /inventory/api/fast-sell/lookup/?barcode=<code>&vertical=<slug>

    Returns:
        {
            "ok": true,
            "found": true,
            "product": {
                "id": 123,
                "name": "Product Name",
                "barcode": "ABC123",
                "available_qty": 5,
                "selling_price": "25000.00",
                "needs_price": false
            }
        }
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)

    barcode = request.GET.get("barcode", "").strip()
    vertical = request.GET.get("vertical", "").strip()

    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode is required"}, status=400)

    # Validate barcode
    is_valid, error_msg = validate_barcode(barcode)
    if not is_valid:
        return JsonResponse({"ok": False, "error": error_msg}, status=400)

    barcode = normalize_barcode(barcode)

    # Find sellable items
    items = find_sellable_by_barcode(barcode, business, vertical)

    if not items or not items.exists():
        return JsonResponse({"ok": True, "found": False, "message": f"No in-stock items found for barcode: {barcode}"})

    # Get first available item
    item = items.first()
    product = item.product

    # Count available quantity
    available_qty = items.count()

    # Check if product has selling price
    selling_price = getattr(product, "selling_price", None) or getattr(item, "selling_price", None)
    needs_price = not selling_price or selling_price <= 0

    return JsonResponse(
        {
            "ok": True,
            "found": True,
            "product": {
                "id": product.id,
                "name": product.name,
                "barcode": barcode,
                "available_qty": available_qty,
                "selling_price": str(selling_price) if selling_price else None,
                "needs_price": needs_price,
                "item_id": item.id,
            },
        }
    )


@login_required
@require_business
@require_http_methods(["POST"])
def fast_sell_sell(request):
    """
    Quick sell an item by barcode.

    POST /inventory/api/fast-sell/sell/
    Body:
        {
            "barcode": "ABC123",
            "vertical": "phones",
            "payment_method": "CASH",
            "selling_price": "25000.00",  // optional, only if needs_price
            "quantity": 1  // optional, default 1
        }

    Returns:
        {
            "ok": true,
            "sale_id": 456,
            "message": "Sale completed successfully",
            "kpis": {
                "today_sales": 5,
                "today_revenue": "125000.00"
            }
        }
    """
    import json

    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    barcode = data.get("barcode", "").strip()
    vertical = data.get("vertical", "").strip()
    payment_method = data.get("payment_method", "CASH").upper()
    selling_price_str = data.get("selling_price")
    quantity = int(data.get("quantity", 1))

    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode is required"}, status=400)

    if quantity < 1:
        return JsonResponse({"ok": False, "error": "Quantity must be at least 1"}, status=400)

    # Validate barcode
    is_valid, error_msg = validate_barcode(barcode)
    if not is_valid:
        return JsonResponse({"ok": False, "error": error_msg}, status=400)

    barcode = normalize_barcode(barcode)

    # Find sellable items
    items = find_sellable_by_barcode(barcode, business, vertical)

    if not items or not items.exists():
        return JsonResponse({"ok": False, "error": f"No in-stock items found for barcode: {barcode}"}, status=404)

    # Check available quantity
    available_qty = items.count()
    if quantity > available_qty:
        return JsonResponse(
            {"ok": False, "error": f"Insufficient stock. Available: {available_qty}, Requested: {quantity}"}, status=400
        )

    # Get item and product
    item = items.first()
    product = item.product

    # Determine selling price
    selling_price = getattr(product, "selling_price", None) or getattr(item, "selling_price", None)

    if not selling_price or selling_price <= 0:
        # Price is required
        if not selling_price_str:
            return JsonResponse({"ok": False, "error": "Selling price is required for this product"}, status=400)

        try:
            selling_price = Decimal(selling_price_str)
            if selling_price <= 0:
                return JsonResponse({"ok": False, "error": "Selling price must be greater than 0"}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({"ok": False, "error": "Invalid selling price format"}, status=400)

        # Persist the price on the product for next time
        try:
            product.selling_price = selling_price
            product.save(update_fields=["selling_price"])
        except Exception:
            pass  # Non-critical if save fails

    # Create sale using existing Sale model
    try:
        with transaction.atomic():
            from sales.models import Sale
            from tenants.models import Location

            # Get active location
            location = getattr(request, "active_location", None)
            if not location:
                # Try to get first active location for business
                location = Location.objects.filter(business=business, is_active=True).first()

                if not location:
                    return JsonResponse(
                        {"ok": False, "error": "No active location found. Please set up a location first."}, status=400
                    )

            # Mark item as sold
            item.status = "SOLD"
            item.sold_at = timezone.now().date()
            item.save(update_fields=["status", "sold_at"])

            # Create sale record
            sale = Sale.objects.create(
                item=item,
                agent=request.user,
                location=location,
                sold_at=timezone.now().date(),
                price=selling_price,
                payment_method=payment_method,
                commission_pct=Decimal("0"),  # Default, can be updated by signals
            )

            # Get updated KPIs
            from sales.models import Sale
            from django.db.models import Sum, Count

            today = timezone.now().date()
            today_sales = Sale.objects.filter(
                business=business, sold_by=request.user, created_at__date=today
            ).aggregate(count=Count("id"), revenue=Sum("price"))

            return JsonResponse(
                {
                    "ok": True,
                    "sale_id": sale.id,
                    "message": "Sale completed successfully",
                    "kpis": {
                        "today_sales": today_sales["count"] or 0,
                        "today_revenue": str(today_sales["revenue"] or 0),
                    },
                }
            )

    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Sale failed: {str(e)}"}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def fast_sell_kpis(request):
    """
    Get Fast Sell KPIs for the current user or global.

    GET /inventory/api/fast-sell/kpis/?vertical=<slug>&scope=<me|global>&range=<today|mtd|custom>

    Returns:
        {
            "ok": true,
            "kpis": {
                "today_sales": 5,
                "today_revenue": "125000.00",
                "mtd_sales": 150,
                "mtd_revenue": "3750000.00"
            }
        }
    """
    from sales.models import Sale
    from django.db.models import Sum, Count

    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)

    scope = request.GET.get("scope", "me")
    range_type = request.GET.get("range", "today")

    # Base queryset
    qs = Sale.objects.filter(business=business)

    # Scope filter
    if scope == "me":
        qs = qs.filter(sold_by=request.user)

    # Date range filter
    today = timezone.now().date()

    if range_type == "today":
        qs_today = qs.filter(created_at__date=today)
        today_stats = qs_today.aggregate(count=Count("id"), revenue=Sum("price"))

        return JsonResponse(
            {
                "ok": True,
                "kpis": {"today_sales": today_stats["count"] or 0, "today_revenue": str(today_stats["revenue"] or 0)},
            }
        )

    elif range_type == "mtd":
        # Month to date
        month_start = today.replace(day=1)
        qs_mtd = qs.filter(created_at__date__gte=month_start)
        mtd_stats = qs_mtd.aggregate(count=Count("id"), revenue=Sum("price"))

        return JsonResponse(
            {"ok": True, "kpis": {"mtd_sales": mtd_stats["count"] or 0, "mtd_revenue": str(mtd_stats["revenue"] or 0)}}
        )

    else:
        return JsonResponse({"ok": False, "error": "Invalid range type. Use 'today' or 'mtd'"}, status=400)
