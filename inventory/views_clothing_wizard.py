# inventory/views_clothing_wizard.py
"""
Redesigned Clothing Stock-In Wizard - Robust 2-Step Flow

This replaces the fragile 8-step wizard with a deterministic, testable flow:

Step A: Product Setup
  - Name (required)
  - Category (optional, defaults to 'other')
  - Stock Mode: Common Stock (no barcodes) vs Unique Stock (barcodes)
  - Quantity (required, >= 1)
  - Selling Price (required, > 0)
  - Cost Price (optional, >= 0)
  - Size (optional ALWAYS)
  - Brand (optional)

Step B: Barcodes (only if Unique Stock)
  - Barcode input + Add button
  - List of scanned barcodes
  - Progress: Scanned X / N
  - Continue enabled only when X == N

CRITICAL RULES:
- NO red toast on GET (validation only on POST/submit)
- Size is OPTIONAL by default
- Barcode Add works reliably (Enter key + button)
- Common Stock skips Step B
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.decorators import manager_required
from inventory.business_kinds import BusinessKind as BK
from inventory.models import Location, MerchProduct
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from tenants.middleware import get_active_business
from tenants.utils import require_business


# =============================================================================
# Helper Functions
# =============================================================================


def resolve_location(request, business):
    """
    Resolve active location with fallback logic.
    Returns Location or None.
    """
    # Try request attribute
    location = getattr(request, "active_location", None)
    if location:
        return location
    
    # Try session
    location_id = request.session.get("active_location_id")
    if location_id:
        try:
            location = Location.objects.get(id=location_id, business=business)
            request.active_location = location
            return location
        except Location.DoesNotExist:
            del request.session["active_location_id"]
    
    # Auto-select: prefer default, then first
    location = Location.objects.filter(business=business).order_by("-is_default", "id").first()
    if location:
        request.session["active_location_id"] = location.id
        request.active_location = location
    
    return location


def get_or_create_draft(request) -> dict:
    """
    Get or create a draft product session.
    Returns dict with draft data.
    """
    return request.session.get("clothing_stock_draft", {})


def save_draft(request, data: dict):
    """Save draft to session."""
    request.session["clothing_stock_draft"] = data
    request.session.modified = True


def clear_draft(request):
    """Clear draft from session."""
    if "clothing_stock_draft" in request.session:
        del request.session["clothing_stock_draft"]
        request.session.modified = True


# =============================================================================
# Step A: Product Setup
# =============================================================================


@login_required
@manager_required
@require_business
def step_a_product_setup(request):
    """
    Step A: Product Setup page.
    
    GET: Display empty form (NO validation errors on GET!)
    POST: Validate and save draft, redirect to Step B or finalize
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business. Please select a business first.")
        return redirect("/tenants/choose/")
    
    location = resolve_location(request, business)
    
    # Categories for dropdown
    categories = [
        ("shoes", "Shoes 👟"),
        ("shirts", "Shirts 👔"),
        ("tshirts", "T-Shirts 👕"),
        ("jeans", "Jeans 👖"),
        ("trousers", "Trousers 👖"),
        ("suits", "Suits 🤵"),
        ("dresses", "Dresses 👗"),
        ("jackets", "Jackets 🧥"),
        ("skirts", "Skirts 👗"),
        ("sweaters", "Sweaters 🧶"),
        ("accessories", "Accessories 👜"),
        ("other", "Other 📦"),
    ]
    
    # Context for GET (no errors on initial load)
    context = {
        "business": business,
        "location": location,
        "location_id": location.id if location else None,
        "categories": categories,
        "errors": {},  # CRITICAL: Empty on GET
        "form_data": {},  # Empty on GET
    }
    
    if request.method == "GET":
        # CRITICAL: No validation on GET! Just render the form.
        return render(request, "inventory/wizards/clothing_stockin_step_a.html", context)
    
    # POST: Validate and process
    errors = {}
    form_data = {}
    
    # Extract form data
    name = request.POST.get("name", "").strip()
    category = request.POST.get("category", "other").strip()
    stock_mode = request.POST.get("stock_mode", "common").strip()
    quantity_str = request.POST.get("quantity", "").strip()
    selling_price_str = request.POST.get("selling_price", "").strip().replace(",", "")
    cost_price_str = request.POST.get("cost_price", "").strip().replace(",", "")
    size = request.POST.get("size", "").strip()
    brand = request.POST.get("brand", "").strip()
    color = request.POST.get("color", "").strip()
    
    # Store for re-display
    form_data = {
        "name": name,
        "category": category,
        "stock_mode": stock_mode,
        "quantity": quantity_str,
        "selling_price": selling_price_str,
        "cost_price": cost_price_str,
        "size": size,
        "brand": brand,
        "color": color,
    }
    
    # Validate required fields
    if not name:
        errors["name"] = "Product name is required."
    
    # Validate quantity
    try:
        quantity = int(quantity_str) if quantity_str else 0
        if quantity < 1:
            errors["quantity"] = "Quantity must be at least 1."
    except ValueError:
        errors["quantity"] = "Quantity must be a valid number."
        quantity = 0
    
    # Validate selling price (REQUIRED, > 0)
    try:
        selling_price = Decimal(selling_price_str) if selling_price_str else Decimal("0")
        if selling_price <= 0:
            errors["selling_price"] = "Selling price must be greater than zero."
    except (ValueError, InvalidOperation):
        errors["selling_price"] = "Selling price must be a valid number."
        selling_price = Decimal("0")
    
    # Validate cost price (optional, >= 0)
    try:
        cost_price = Decimal(cost_price_str) if cost_price_str else Decimal("0")
        if cost_price < 0:
            errors["cost_price"] = "Cost price cannot be negative."
    except (ValueError, InvalidOperation):
        errors["cost_price"] = "Cost price must be a valid number."
        cost_price = Decimal("0")
    
    # Validate stock mode
    if stock_mode not in ("common", "unique"):
        stock_mode = "common"
    
    # Check location
    if not location:
        errors["location"] = "No active location. Please create a location first."
    
    # If errors, re-render with errors
    if errors:
        context["errors"] = errors
        context["form_data"] = form_data
        return render(request, "inventory/wizards/clothing_stockin_step_a.html", context)
    
    # All valid - create draft
    draft_id = str(uuid.uuid4())[:8]
    draft = {
        "draft_id": draft_id,
        "name": name,
        "category": category,
        "stock_mode": stock_mode,
        "quantity": quantity,
        "selling_price": str(selling_price),
        "cost_price": str(cost_price),
        "size": size,
        "brand": brand,
        "color": color,
        "location_id": location.id,
        "business_id": business.id,
        "scanned_barcodes": [],
    }
    save_draft(request, draft)
    
    # Route based on stock mode
    if stock_mode == "unique":
        # Go to Step B for barcode scanning
        return redirect(reverse("clothing:stockin_step_b", kwargs={"draft_id": draft_id}))
    else:
        # Common stock: finalize immediately (skip Step B)
        return _finalize_stock_in(request, draft)


def _finalize_stock_in(request, draft: dict):
    """
    Finalize stock-in: create product and optional barcode units.
    Returns redirect response.
    """
    business = get_active_business(request)
    location = Location.objects.get(id=draft["location_id"], business=business)
    
    with transaction.atomic():
        # Build product name with details
        name_parts = [draft["name"]]
        if draft.get("brand"):
            name_parts.insert(0, draft["brand"])
        if draft.get("size"):
            name_parts.append(f"Size {draft['size']}")
        product_name = " - ".join(name_parts)
        
        # Create MerchProduct for inventory tracking
        product = MerchProduct.objects.create(
            business=business,
            name=product_name,
            kind=BK.CLOTHING,
            category=draft["category"],
            size=draft.get("size", ""),
            color=draft.get("color", ""),
            spec_label=f"Size {draft.get('size', 'N/A')}" if draft.get("size") else "",
            selling_price=Decimal(draft["selling_price"]),
            cost_price=Decimal(draft["cost_price"]) if draft.get("cost_price") else None,
            quantity_in_stock=draft["quantity"] if draft["stock_mode"] == "common" else 0,
            is_active=True,
            track_inventory=True,
            scan_required=(draft["stock_mode"] == "unique"),
        )
        
        # For unique stock, create ClothingBarcodeUnit records
        if draft["stock_mode"] == "unique":
            for barcode in draft.get("scanned_barcodes", []):
                ClothingBarcodeUnit.objects.create(
                    business=business,
                    location=location,
                    product=product,
                    barcode=barcode.upper(),
                    category=draft["category"],
                    size=draft.get("size", ""),
                    brand=draft.get("brand", ""),
                    color=draft.get("color", ""),
                    cost_price=Decimal(draft["cost_price"]) if draft.get("cost_price") else Decimal("0"),
                    selling_price=Decimal(draft["selling_price"]),
                    status="IN_STOCK",
                    created_by=request.user,
                )
    
    # Clear draft
    clear_draft(request)
    
    # Success message
    mode_label = "Unique Stock (barcoded)" if draft["stock_mode"] == "unique" else "Common Stock"
    messages.success(
        request,
        f"✅ Product '{product_name}' added to stock! Mode: {mode_label}, Qty: {draft['quantity']}"
    )
    
    return redirect("verticals:clothing_dashboard")


# =============================================================================
# Step B: Barcodes (Unique Stock only)
# =============================================================================


@login_required
@manager_required
@require_business
def step_b_barcodes(request, draft_id):
    """
    Step B: Barcode scanning page.
    
    GET: Display barcode input form with progress
    POST: Add barcode or finalize
    """
    business = get_active_business(request)
    draft = get_or_create_draft(request)
    
    # Validate draft exists and matches
    if not draft or draft.get("draft_id") != draft_id:
        messages.error(request, "Draft not found. Please start over.")
        return redirect("clothing:stockin_step_a")
    
    # Ensure unique stock mode
    if draft.get("stock_mode") != "unique":
        return _finalize_stock_in(request, draft)
    
    location = Location.objects.get(id=draft["location_id"], business=business)
    
    # Calculate progress
    scanned_barcodes = draft.get("scanned_barcodes", [])
    quantity = draft["quantity"]
    scanned_count = len(scanned_barcodes)
    remaining = quantity - scanned_count
    is_complete = scanned_count >= quantity
    
    context = {
        "business": business,
        "location": location,
        "draft": draft,
        "draft_id": draft_id,
        "scanned_barcodes": scanned_barcodes,
        "quantity": quantity,
        "scanned_count": scanned_count,
        "remaining": remaining,
        "is_complete": is_complete,
        "error": None,  # No error on GET
    }
    
    if request.method == "GET":
        return render(request, "inventory/wizards/clothing_stockin_step_b.html", context)
    
    # POST: Handle action
    action = request.POST.get("action", "add_barcode")
    
    if action == "finalize":
        # Check if complete
        if not is_complete:
            context["error"] = f"Please scan all {quantity} barcodes before continuing. ({remaining} remaining)"
            return render(request, "inventory/wizards/clothing_stockin_step_b.html", context)
        
        return _finalize_stock_in(request, draft)
    
    elif action == "add_barcode":
        barcode = request.POST.get("barcode", "").strip().upper()
        
        if not barcode:
            context["error"] = "Please enter a barcode."
            return render(request, "inventory/wizards/clothing_stockin_step_b.html", context)
        
        if len(barcode) < 3:
            context["error"] = "Barcode must be at least 3 characters."
            return render(request, "inventory/wizards/clothing_stockin_step_b.html", context)
        
        # Check if already in current batch
        if barcode in scanned_barcodes:
            context["error"] = f"Barcode '{barcode}' is already in this batch."
            return render(request, "inventory/wizards/clothing_stockin_step_b.html", context)
        
        # Check if exists in database
        if ClothingBarcodeUnit.objects.filter(business=business, barcode=barcode, is_active=True).exists():
            context["error"] = f"Barcode '{barcode}' already exists in inventory."
            return render(request, "inventory/wizards/clothing_stockin_step_b.html", context)
        
        # Check if batch is already full
        if scanned_count >= quantity:
            context["error"] = f"Already scanned {quantity} barcodes. Click 'Save & Finish' to complete."
            return render(request, "inventory/wizards/clothing_stockin_step_b.html", context)
        
        # Add barcode
        scanned_barcodes.append(barcode)
        draft["scanned_barcodes"] = scanned_barcodes
        save_draft(request, draft)
        
        # Update context
        scanned_count = len(scanned_barcodes)
        remaining = quantity - scanned_count
        is_complete = scanned_count >= quantity
        
        context["scanned_barcodes"] = scanned_barcodes
        context["scanned_count"] = scanned_count
        context["remaining"] = remaining
        context["is_complete"] = is_complete
        context["success"] = f"✓ Barcode '{barcode}' added ({scanned_count}/{quantity})"
        
        return render(request, "inventory/wizards/clothing_stockin_step_b.html", context)
    
    elif action == "remove_barcode":
        index = request.POST.get("index")
        try:
            index = int(index)
            if 0 <= index < len(scanned_barcodes):
                removed = scanned_barcodes.pop(index)
                draft["scanned_barcodes"] = scanned_barcodes
                save_draft(request, draft)
                context["success"] = f"Barcode '{removed}' removed."
        except (ValueError, IndexError):
            pass
        
        # Update context
        scanned_count = len(scanned_barcodes)
        remaining = quantity - scanned_count
        is_complete = scanned_count >= quantity
        
        context["scanned_barcodes"] = scanned_barcodes
        context["scanned_count"] = scanned_count
        context["remaining"] = remaining
        context["is_complete"] = is_complete
        
        return render(request, "inventory/wizards/clothing_stockin_step_b.html", context)
    
    return redirect("clothing:stockin_step_b", draft_id=draft_id)


# =============================================================================
# API Endpoints (for AJAX/HTMX)
# =============================================================================


@login_required
@require_business
@require_http_methods(["POST"])
def api_add_barcode(request, draft_id):
    """
    AJAX API: Add barcode to draft.
    
    POST body: {"barcode": "ABC123"}
    Returns: {"ok": true, "scanned_count": 3, "remaining": 2, "complete": false}
    """
    business = get_active_business(request)
    draft = get_or_create_draft(request)
    
    if not draft or draft.get("draft_id") != draft_id:
        return JsonResponse({"ok": False, "error": "Draft not found"}, status=400)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    
    barcode = data.get("barcode", "").strip().upper()
    
    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode is required"})
    
    if len(barcode) < 3:
        return JsonResponse({"ok": False, "error": "Barcode must be at least 3 characters"})
    
    scanned_barcodes = draft.get("scanned_barcodes", [])
    quantity = draft["quantity"]
    
    # Check duplicate in batch
    if barcode in scanned_barcodes:
        return JsonResponse({"ok": False, "error": f"Barcode '{barcode}' already in this batch"})
    
    # Check exists in database
    if ClothingBarcodeUnit.objects.filter(business=business, barcode=barcode, is_active=True).exists():
        return JsonResponse({"ok": False, "error": f"Barcode '{barcode}' already exists in inventory"})
    
    # Check if full
    if len(scanned_barcodes) >= quantity:
        return JsonResponse({"ok": False, "error": "Batch is full"})
    
    # Add barcode
    scanned_barcodes.append(barcode)
    draft["scanned_barcodes"] = scanned_barcodes
    save_draft(request, draft)
    
    scanned_count = len(scanned_barcodes)
    remaining = quantity - scanned_count
    
    return JsonResponse({
        "ok": True,
        "barcode": barcode,
        "scanned_count": scanned_count,
        "remaining": remaining,
        "complete": scanned_count >= quantity,
        "scanned_barcodes": scanned_barcodes,
    })


@login_required
@require_business
@require_http_methods(["POST"])
def api_remove_barcode(request, draft_id):
    """
    AJAX API: Remove barcode from draft.
    
    POST body: {"index": 0}
    """
    draft = get_or_create_draft(request)
    
    if not draft or draft.get("draft_id") != draft_id:
        return JsonResponse({"ok": False, "error": "Draft not found"}, status=400)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    
    index = data.get("index")
    scanned_barcodes = draft.get("scanned_barcodes", [])
    
    try:
        index = int(index)
        if 0 <= index < len(scanned_barcodes):
            removed = scanned_barcodes.pop(index)
            draft["scanned_barcodes"] = scanned_barcodes
            save_draft(request, draft)
        else:
            return JsonResponse({"ok": False, "error": "Invalid index"})
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid index"})
    
    scanned_count = len(scanned_barcodes)
    remaining = draft["quantity"] - scanned_count
    
    return JsonResponse({
        "ok": True,
        "removed": removed,
        "scanned_count": scanned_count,
        "remaining": remaining,
        "complete": scanned_count >= draft["quantity"],
        "scanned_barcodes": scanned_barcodes,
    })


@login_required
@require_business
@require_http_methods(["POST"])
def api_finalize(request, draft_id):
    """
    AJAX API: Finalize stock-in.
    """
    draft = get_or_create_draft(request)
    
    if not draft or draft.get("draft_id") != draft_id:
        return JsonResponse({"ok": False, "error": "Draft not found"}, status=400)
    
    # For unique stock, check completeness
    if draft.get("stock_mode") == "unique":
        scanned = len(draft.get("scanned_barcodes", []))
        if scanned < draft["quantity"]:
            return JsonResponse({
                "ok": False,
                "error": f"Please scan all {draft['quantity']} barcodes. ({draft['quantity'] - scanned} remaining)"
            })
    
    # Finalize
    response = _finalize_stock_in(request, draft)
    
    # Return JSON for AJAX
    return JsonResponse({
        "ok": True,
        "redirect": reverse("verticals:clothing_dashboard"),
    })

