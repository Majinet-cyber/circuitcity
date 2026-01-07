# inventory/api_barcode_lookup.py
"""
Fast Barcode Lookup API - Ultra-fast barcode → product lookup for instant sales.

This API is the engine for barcode-first scanning in Clothing and Pharmacy.
It must be FAST (indexed queries) and SAFE (multi-tenant scoped).
"""
from decimal import Decimal
from typing import Dict, Any

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from inventory.decorators import require_business
from inventory.utils_barcodes import lookup_barcode, normalize_barcode_enhanced


@login_required
@require_business
@require_http_methods(["GET"])
def barcode_lookup_api(request):
    """
    Fast barcode lookup API endpoint.

    GET /inventory/api/barcode/lookup?code=<barcode>

    Returns:
        {
            "found": bool,
            "product_id": int or null,
            "product_name": str or null,
            "selling_price": float or null,
            "order_price": float or null (cost price),
            "stock_available": int or null,
            "category": str or null,
            "size": str or null (clothing),
            "color": str or null (clothing),
            "batch_id": int or null (pharmacy),
            "batch_number": str or null (pharmacy),
            "expiry_date": str or null (pharmacy),
            "needs_price": bool (true if selling_price is 0 or missing),
            "vertical": str or null (clothing, pharmacy, etc.)
        }
    """
    business = request.business
    code = request.GET.get("code", "").strip()

    if not code:
        return JsonResponse({"found": False, "error": "Barcode code is required"}, status=400)

    # Normalize for consistent lookup
    normalized = normalize_barcode_enhanced(code)

    # Lookup in registry
    result = lookup_barcode(business, code)

    if not result["found"]:
        return JsonResponse(
            {
                "found": False,
                "product_id": None,
                "product_name": None,
                "selling_price": None,
                "order_price": None,
                "stock_available": None,
                "needs_price": False,
                "vertical": None,
            }
        )

    product = result["product"]
    batch = result["batch"]

    # Build response based on what we found
    response_data = {"found": True, "vertical": None, "needs_price": False}

    # Pharmacy batch-level tracking
    if batch:
        from inventory.models_pharmacy import PharmacyBatch

        selling_price = batch.selling_price or Decimal("0.00")
        cost_price = batch.cost_price or Decimal("0.00")

        response_data.update(
            {
                "product_id": product.id if product else None,
                "product_name": product.name if product else batch.product_name,
                "selling_price": float(selling_price),
                "order_price": float(cost_price),
                "stock_available": batch.quantity,
                "category": getattr(product, "category", "") if product else "",
                "batch_id": batch.id,
                "batch_number": batch.batch_number or "N/A",
                "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else None,
                "needs_price": selling_price == 0,
                "vertical": "pharmacy",
            }
        )

    # Product-level tracking (clothing, etc.)
    elif product:
        from inventory.models import MerchProduct

        selling_price = product.selling_price or Decimal("0.00")
        cost_price = product.cost_price or Decimal("0.00")
        stock = getattr(product, "quantity_in_stock", 0) or 0

        response_data.update(
            {
                "product_id": product.id,
                "product_name": product.name,
                "selling_price": float(selling_price),
                "order_price": float(cost_price),
                "stock_available": stock,
                "category": getattr(product, "category", ""),
                "size": getattr(product, "size", ""),
                "color": getattr(product, "color", ""),
                "batch_id": None,
                "batch_number": None,
                "expiry_date": None,
                "needs_price": selling_price == 0,
                "vertical": product.kind if hasattr(product, "kind") else None,
            }
        )

    return JsonResponse(response_data)


@login_required
@require_business
@require_http_methods(["POST"])
def barcode_quick_create_api(request):
    """
    Quick create product with barcode (for unknown barcodes during scan).

    POST /inventory/api/barcode/quick-create

    Body:
        {
            "barcode": str,
            "vertical": str (clothing, pharmacy),
            "product_name": str,
            "category": str,
            "selling_price": float,
            "order_price": float (cost),
            "quantity": int,

            // Clothing-specific
            "size": str,
            "color": str,

            // Pharmacy-specific
            "batch_number": str,
            "expiry_date": str (ISO format)
        }

    Returns:
        {
            "ok": bool,
            "product_id": int,
            "message": str,
            "error": str (if not ok)
        }
    """
    import json
    from django.db import transaction
    from inventory.models import MerchProduct
    from inventory.models_pharmacy import PharmacyBatch
    from inventory.utils_barcodes import register_barcode, is_valid_barcode_format
    from inventory.business_kinds import BusinessKind

    business = request.business

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    # Extract fields
    barcode = data.get("barcode", "").strip()
    vertical = data.get("vertical", "").strip().lower()
    product_name = data.get("product_name", "").strip()
    category = data.get("category", "").strip()
    selling_price_str = data.get("selling_price", "0")
    order_price_str = data.get("order_price", "0")
    quantity = int(data.get("quantity", 1))

    # Validate
    errors = []

    if not barcode or not is_valid_barcode_format(barcode):
        errors.append("Valid barcode is required")

    if not vertical or vertical not in ["clothing", "pharmacy"]:
        errors.append("Vertical must be 'clothing' or 'pharmacy'")

    if not product_name:
        errors.append("Product name is required")

    if quantity < 1:
        errors.append("Quantity must be at least 1")

    try:
        selling_price = Decimal(str(selling_price_str))
        if selling_price < 0:
            errors.append("Selling price cannot be negative")
    except (ValueError, TypeError):
        errors.append("Invalid selling price")
        selling_price = Decimal("0.00")

    try:
        order_price = Decimal(str(order_price_str))
        if order_price < 0:
            errors.append("Order price cannot be negative")
    except (ValueError, TypeError):
        errors.append("Invalid order price")
        order_price = Decimal("0.00")

    if errors:
        return JsonResponse({"ok": False, "error": "; ".join(errors)}, status=400)

    # Create product + register barcode
    try:
        with transaction.atomic():
            if vertical == "clothing":
                # Clothing product
                size = data.get("size", "").strip()
                color = data.get("color", "").strip()

                # CRITICAL FIX: Set spec_label for clothing (use size, prevents NULL constraint)
                spec_label_value = size if size else ""
                if spec_label_value and not spec_label_value.startswith("Size "):
                    spec_label_value = f"Size {spec_label_value}"

                product = MerchProduct.objects.create(
                    business=business,
                    name=product_name,
                    kind=BusinessKind.CLOTHING,
                    category=category,
                    size=size,
                    color=color,
                    spec_label=spec_label_value,  # CRITICAL: Always set spec_label (prevents NULL constraint)
                    barcode=barcode,  # Store on product too (legacy compatibility)
                    selling_price=selling_price,
                    cost_price=order_price,
                    quantity_in_stock=quantity,
                    is_active=True,
                    track_inventory=True,
                )

                # Register barcode
                register_barcode(business=business, raw_code=barcode, product=product, created_by=request.user)

                # Log stock-in
                try:
                    from inventory.models_verticals import ClothingProductLog, ClothingProductAction

                    ClothingProductLog.objects.create(
                        product=product,
                        action=ClothingProductAction.STOCK_IN,
                        quantity=quantity,
                        notes=f"Quick create via barcode scan: {barcode}",
                        metadata={"barcode": barcode, "quick_create": True},
                        performed_by=request.user,
                    )
                except:
                    pass  # Don't fail if logging fails

                return JsonResponse(
                    {
                        "ok": True,
                        "product_id": product.id,
                        "message": f"Created {product_name} with {quantity} in stock",
                    }
                )

            elif vertical == "pharmacy":
                # Pharmacy batch
                batch_number = data.get("batch_number", "").strip()
                expiry_date_str = data.get("expiry_date", "").strip()

                # Auto-generate batch number if missing
                if not batch_number:
                    import uuid

                    batch_number = f"BATCH-{uuid.uuid4().hex[:8].upper()}"

                # Parse expiry date (optional for cosmetics)
                expiry_date = None
                if expiry_date_str:
                    from datetime import datetime

                    try:
                        expiry_date = datetime.fromisoformat(expiry_date_str).date()
                    except:
                        pass

                # Create or get product
                product, _ = MerchProduct.objects.get_or_create(
                    business=business,
                    name=product_name,
                    kind=BusinessKind.PHARMACY,
                    defaults={
                        "category": category,
                        "spec_label": "",  # CRITICAL: Always set spec_label (prevents NULL constraint)
                        "barcode": barcode,
                        "is_active": True,
                        "track_inventory": True,
                    },
                )

                # Create batch
                batch = PharmacyBatch.objects.create(
                    business=business,
                    merch_product=product,
                    product_name=product_name,
                    batch_number=batch_number,
                    barcode=barcode,  # Store on batch too
                    quantity=quantity,
                    cost_price=order_price,
                    selling_price=selling_price,
                    expiry_date=expiry_date,
                    is_archived=False,
                )

                # Register barcode (batch-level)
                register_barcode(
                    business=business, raw_code=barcode, product=product, batch=batch, created_by=request.user
                )

                return JsonResponse(
                    {
                        "ok": True,
                        "product_id": product.id,
                        "batch_id": batch.id,
                        "message": f"Created {product_name} batch with {quantity} in stock",
                    }
                )

            else:
                return JsonResponse({"ok": False, "error": "Unsupported vertical"}, status=400)

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.exception(f"Quick create failed: {e}")
        return JsonResponse({"ok": False, "error": str(e)}, status=500)
