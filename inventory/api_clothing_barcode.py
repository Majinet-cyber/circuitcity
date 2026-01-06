# inventory/api_clothing_barcode.py
"""
API endpoints for clothing barcode operations.

Supports:
- Barcode duplicate checking (AJAX validation during scanning)
- Barcode batch creation (Step 1: pricing + Step 2: scanning)
- Fast sell barcode lookup and sale creation
"""
import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from inventory.services.clothing_barcode_service import (
    check_barcode_duplicate,
    create_barcode_batch_session,
    create_fast_sell_from_barcode,
    lookup_barcode_for_fast_sell,
    scan_barcode_unit,
)
from tenants.utils import get_active_business, require_business


@login_required
@require_business
@require_http_methods(["POST"])
def check_barcode_duplicate_api(request):
    """
    Check if a barcode already exists (AJAX validation).

    POST /inventory/api/clothing/check-barcode-duplicate/
    Body: {"barcode": "ABC123"}

    Returns:
        {"ok": true, "exists": false}
        {"ok": true, "exists": true, "message": "Barcode already exists"}
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    barcode = data.get("barcode", "").strip()

    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode is required"}, status=400)

    result = check_barcode_duplicate(business=business, barcode=barcode)

    if result["exists"]:
        unit = result["unit"]
        return JsonResponse(
            {
                "ok": True,
                "exists": True,
                "message": f"Barcode {barcode} already exists (Status: {unit.get_status_display()})",
            }
        )

    return JsonResponse({"ok": True, "exists": False})


@login_required
@require_business
@require_http_methods(["POST"])
def barcode_batch_step1_api(request):
    """
    Step 1: Validate and store batch details in session.

    POST /inventory/api/clothing/barcode-batch/step1/
    Body: {
        "category": "shoes",
        "subcategory": "sneaker",
        "size": "42",
        "quantity": 5,
        "cost_price": "10000.00",
        "selling_price": "15000.00",
        "brand": "Nike",
        "color": "Black",
        "product_name": "Nike Air Max"
    }

    Returns:
        {"ok": true, "message": "Batch details saved. Ready to scan."}
        {"ok": false, "error": "Validation error message"}
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)

    location = getattr(request, "active_location", None)
    if not location:
        return JsonResponse({"ok": False, "error": "No active location"}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    # Extract fields
    category = data.get("category", "").strip()
    subcategory = data.get("subcategory", "").strip()
    size = data.get("size", "").strip()
    quantity = data.get("quantity")
    cost_price = data.get("cost_price", "0")
    selling_price = data.get("selling_price", "0")
    brand = data.get("brand", "").strip()
    color = data.get("color", "").strip()
    product_name = data.get("product_name", "").strip()

    # Validate required fields
    if not category:
        return JsonResponse({"ok": False, "error": "Category is required"}, status=200)

    if not size:
        return JsonResponse({"ok": False, "error": "Size is required"}, status=200)

    try:
        quantity = int(quantity)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Quantity must be a valid number"}, status=200)

    try:
        cost_price = Decimal(cost_price)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Cost price must be a valid number"}, status=200)

    try:
        selling_price = Decimal(selling_price)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Selling price must be a valid number"}, status=200)

    # Create batch session
    try:
        session_data = create_barcode_batch_session(
            business=business,
            location=location,
            user=request.user,
            category=category,
            subcategory=subcategory,
            size=size,
            quantity=quantity,
            cost_price=cost_price,
            selling_price=selling_price,
            brand=brand,
            color=color,
            product_name=product_name,
        )

        # Store in session
        request.session["clothing_barcode_batch"] = session_data
        request.session.modified = True

        return JsonResponse(
            {
                "ok": True,
                "message": "Batch details saved. Ready to scan.",
                "quantity": quantity,
            }
        )

    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=200)


@login_required
@require_business
@require_http_methods(["POST"])
def barcode_batch_scan_api(request):
    """
    Step 2: Scan a barcode and create unit.

    POST /inventory/api/clothing/barcode-batch/scan/
    Body: {"barcode": "ABC123"}

    Returns:
        {
            "ok": true,
            "unit_id": 123,
            "barcode": "ABC123",
            "scanned_count": 3,
            "remaining": 2,
            "complete": false
        }
        {"ok": false, "error": "Barcode already exists"}
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)

    location = getattr(request, "active_location", None)
    if not location:
        return JsonResponse({"ok": False, "error": "No active location"}, status=400)

    # Get session data
    session_data = request.session.get("clothing_barcode_batch")
    if not session_data:
        return JsonResponse({"ok": False, "error": "No active batch. Please complete Step 1 first."}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    barcode = data.get("barcode", "").strip()

    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode is required"}, status=200)

    # Scan barcode
    result = scan_barcode_unit(
        session_data=session_data,
        barcode=barcode,
        business=business,
        location=location,
        user=request.user,
    )

    if result["ok"]:
        # Update session with new scanned_barcodes
        session_data["scanned_barcodes"] = result["scanned_barcodes"]
        session_data["scanned_count"] = result["scanned_count"]
        request.session["clothing_barcode_batch"] = session_data
        request.session.modified = True

        # If complete, clear session
        if result["complete"]:
            del request.session["clothing_barcode_batch"]
            request.session.modified = True

    return JsonResponse(result, status=200)


@login_required
@require_business
@require_http_methods(["POST"])
def fast_sell_lookup_api(request):
    """
    Fast sell: Lookup barcode.

    POST /inventory/api/clothing/fast-sell/lookup/
    Body: {"barcode": "ABC123"}

    Returns:
        {
            "found": true,
            "barcode": "ABC123",
            "size": "42",
            "category": "shoes",
            "selling_price": "15000.00"
        }
        {"found": false, "error": "Barcode not found"}
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)

    location = getattr(request, "active_location", None)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    barcode = data.get("barcode", "").strip()

    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode is required"}, status=400)

    result = lookup_barcode_for_fast_sell(
        business=business,
        barcode=barcode,
        location=location,
    )

    return JsonResponse(result)


@login_required
@require_business
@require_http_methods(["POST"])
def fast_sell_create_api(request):
    """
    Fast sell: Create sale from barcode.

    POST /inventory/api/clothing/fast-sell/create/
    Body: {
        "barcode": "ABC123",
        "payment_method": "cash"
    }

    Returns:
        {
            "ok": true,
            "sale_id": 456,
            "barcode": "ABC123",
            "amount": "15000.00",
            "profit": "5000.00"
        }
        {"ok": false, "error": "Barcode not found"}
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)

    location = getattr(request, "active_location", None)
    if not location:
        return JsonResponse({"ok": False, "error": "No active location"}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    barcode = data.get("barcode", "").strip()
    payment_method = data.get("payment_method", "cash").strip().lower()

    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode is required"}, status=400)

    result = create_fast_sell_from_barcode(
        business=business,
        location=location,
        user=request.user,
        barcode=barcode,
        payment_method=payment_method,
    )

    return JsonResponse(result)
