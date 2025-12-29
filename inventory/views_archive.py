# inventory/views_archive.py
"""
Premium Archive Flow - 4-step safety process for archiving stock across all verticals.

This provides a safe, premium UX for managers to archive stock without deleting data.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.decorators import manager_required
from core.decorators_bar_manager import manager_only_no_bar_manager
from tenants.decorators import require_business_access as require_business
from tenants.middleware import get_active_business
from inventory.models import (
    MerchProduct, InventoryItem, Location
)
from inventory.models_stock_barcodes import ArchiveBatch, InventoryBarcode
from inventory.models_laptops import LaptopSerial


@login_required
@manager_only_no_bar_manager  # Bar managers cannot archive
@require_business
@require_http_methods(["GET", "POST"])
def archive_flow_start(request: HttpRequest) -> HttpResponse:
    """
    Step 1: Choose scope (location vs entire business)
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business")
        return redirect("dashboard:home")
    
    # Get locations for this business
    locations = Location.objects.filter(business=business, is_active=True).order_by("name")
    
    if request.method == "POST":
        scope = request.POST.get("scope", "").strip()
        location_id = request.POST.get("location_id", "").strip()
        
        if scope == "location" and not location_id:
            messages.error(request, "Please select a location")
            return render(request, "inventory/archive/step1_scope.html", {
                "business": business,
                "locations": locations,
            })
        
        # Store in session for next steps
        request.session["archive_scope"] = scope
        request.session["archive_location_id"] = int(location_id) if location_id else None
        request.session["archive_step"] = 2
        
        return redirect("inventory:archive_flow_summary")
    
    return render(request, "inventory/archive/step1_scope.html", {
        "business": business,
        "locations": locations,
    })


@login_required
@manager_only_no_bar_manager  # Bar managers cannot archive
@require_business
@require_http_methods(["GET", "POST"])
def archive_flow_summary(request: HttpRequest) -> HttpResponse:
    """
    Step 2: Show impact summary (counts)
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business")
        return redirect("dashboard:home")
    
    # Get scope from session
    scope = request.session.get("archive_scope")
    location_id = request.session.get("archive_location_id")
    
    if not scope:
        messages.error(request, "Please start from step 1")
        return redirect("inventory:archive_flow_start")
    
    location = None
    if scope == "location" and location_id:
        try:
            location = Location.objects.get(pk=location_id, business=business)
        except Location.DoesNotExist:
            messages.error(request, "Location not found")
            return redirect("inventory:archive_flow_start")
    
    # Calculate counts
    # Products count - products that have stock in the selected scope
    product_filters = Q(business=business, is_archived=False)
    if location:
        # For products, we check if they have stock items in this location
        # Get product IDs that have stock in this location
        product_ids_with_stock = InventoryItem.objects.filter(
            business=business,
            current_location=location,
            is_active=True,
            archived_at__isnull=True
        ).values_list('product_id', flat=True).distinct()
        
        # Also check MerchProduct directly (for clothing, etc.)
        merch_product_ids = set()
        # For MerchProduct, we'd need to check if they have barcodes or stock in this location
        # For now, count all non-archived products if location is selected
        # (This is a simplified approach - can be enhanced later)
        products_count = MerchProduct.objects.filter(
            business=business,
            is_archived=False
        ).count()
    else:
        # Entire business - count all non-archived products
        products_count = MerchProduct.objects.filter(
            business=business,
            is_archived=False
        ).count()
    
    # Stock items count (InventoryItem for phones)
    stock_items_count = InventoryItem.objects.filter(
        business=business,
        is_active=True,
        archived_at__isnull=True
    )
    if location:
        stock_items_count = stock_items_count.filter(current_location=location)
    stock_items_count = stock_items_count.count()
    
    # Barcodes count
    barcodes_count = InventoryBarcode.objects.filter(
        business=business,
        is_archived=False
    )
    if location:
        barcodes_count = barcodes_count.filter(location=location)
    barcodes_count = barcodes_count.count()
    
    # Laptop serials count
    laptop_serials_count = LaptopSerial.objects.filter(
        business=business,
        is_active=True,
        archived_at__isnull=True
    )
    if location:
        laptop_serials_count = laptop_serials_count.filter(location=location)
    laptop_serials_count = laptop_serials_count.count()
    
    # Sales records note (we don't delete sales, just hide from dashboards)
    sales_note = "Sales records will remain but can be hidden from default dashboards if you choose."
    
    counts = {
        "products": products_count,
        "stock_items": stock_items_count,
        "barcodes": barcodes_count,
        "laptop_serials": laptop_serials_count,
        "sales_note": sales_note,
    }
    
    # Store counts in session for final step
    request.session["archive_counts"] = counts
    
    if request.method == "POST":
        # Move to confirmation step
        request.session["archive_step"] = 3
        return redirect("inventory:archive_flow_confirm")
    
    return render(request, "inventory/archive/step2_summary.html", {
        "business": business,
        "location": location,
        "scope": scope,
        "counts": counts,
    })


@login_required
@manager_only_no_bar_manager  # Bar managers cannot archive
@require_business
@require_http_methods(["GET", "POST"])
def archive_flow_confirm(request: HttpRequest) -> HttpResponse:
    """
    Step 3: Confirmation (type ARCHIVE + name, checkbox)
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business")
        return redirect("dashboard:home")
    
    scope = request.session.get("archive_scope")
    location_id = request.session.get("archive_location_id")
    counts = request.session.get("archive_counts", {})
    
    if not scope or not counts:
        messages.error(request, "Please start from step 1")
        return redirect("inventory:archive_flow_start")
    
    location = None
    if scope == "location" and location_id:
        try:
            location = Location.objects.get(pk=location_id, business=business)
        except Location.DoesNotExist:
            pass
    
    if request.method == "POST":
        confirmation_text = request.POST.get("confirmation_text", "").strip().upper()
        confirm_checkbox = request.POST.get("confirm_checkbox") == "on"
        
        # Validate confirmation text
        expected_text = "ARCHIVE"
        if confirmation_text != expected_text:
            messages.error(request, f'Please type "{expected_text}" exactly to confirm')
            return render(request, "inventory/archive/step3_confirm.html", {
                "business": business,
                "location": location,
                "scope": scope,
                "counts": counts,
            })
        
        # Validate checkbox
        if not confirm_checkbox:
            messages.error(request, "Please check the confirmation checkbox")
            return render(request, "inventory/archive/step3_confirm.html", {
                "business": business,
                "location": location,
                "scope": scope,
                "counts": counts,
            })
        
        # Validate name match
        name_to_match = location.name if location else business.name
        name_input = request.POST.get("name_input", "").strip()
        if name_input.lower() != name_to_match.lower():
            messages.error(request, f'Name must match exactly: "{name_to_match}"')
            return render(request, "inventory/archive/step3_confirm.html", {
                "business": business,
                "location": location,
                "scope": scope,
                "counts": counts,
            })
        
        # Move to final step
        request.session["archive_step"] = 4
        return redirect("inventory:archive_flow_execute")
    
    return render(request, "inventory/archive/step3_confirm.html", {
        "business": business,
        "location": location,
        "scope": scope,
        "counts": counts,
    })


@login_required
@manager_only_no_bar_manager  # Bar managers cannot archive
@require_business
@require_http_methods(["GET", "POST"])
@transaction.atomic
def archive_flow_execute(request: HttpRequest) -> HttpResponse:
    """
    Step 4: Execute archive and show success
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business")
        return redirect("dashboard:home")
    
    scope = request.session.get("archive_scope")
    location_id = request.session.get("archive_location_id")
    counts = request.session.get("archive_counts", {})
    
    if not scope or not counts:
        messages.error(request, "Please start from step 1")
        return redirect("inventory:archive_flow_start")
    
    location = None
    if scope == "location" and location_id:
        try:
            location = Location.objects.get(pk=location_id, business=business)
        except Location.DoesNotExist:
            pass
    
    # Create ArchiveBatch
    archive_batch = ArchiveBatch.objects.create(
        business=business,
        location=location,
        created_by=request.user,
        reason=request.POST.get("reason", "").strip() if request.method == "POST" else "",
        counts_snapshot=counts,
    )
    
    # Archive records
    now = timezone.now()
    archived_counts = {
        "products": 0,
        "stock_items": 0,
        "barcodes": 0,
        "laptop_serials": 0,
    }
    
    # Archive products (MerchProduct for clothing, shoes, etc.)
    # Note: For phones, products are in PhoneProductCatalog, not MerchProduct
    product_filters = Q(business=business, is_archived=False)
    products = MerchProduct.objects.filter(product_filters)
    
    if location:
        # For location-specific archive, only archive products that have:
        # 1. Barcodes in this location, OR
        # 2. Stock items linked to this product in this location (for clothing/merch)
        products_to_archive = []
        for product in products:
            # Check barcodes in this location
            has_barcodes = InventoryBarcode.objects.filter(
                product=product,
                location=location,
                is_archived=False
            ).exists()
            
            # For MerchProduct, we can't directly link to InventoryItem (that's for phones)
            # So we archive if it has barcodes in this location
            if has_barcodes:
                products_to_archive.append(product)
        
        for product in products_to_archive:
            product.is_archived = True
            product.archived_at = now
            product.archived_by = request.user
            product.is_active = False
            product.save(update_fields=["is_archived", "archived_at", "archived_by", "is_active"])
            archived_counts["products"] += 1
    else:
        # Archive all products for entire business
        archived_counts["products"] = products.update(
            is_archived=True,
            archived_at=now,
            archived_by=request.user,
            is_active=False
        )
    
    # Archive stock items
    stock_filters = Q(business=business, is_active=True, archived_at__isnull=True)
    if location:
        stock_filters &= Q(current_location=location)
    
    stock_items = InventoryItem.objects.filter(stock_filters)
    archived_counts["stock_items"] = stock_items.update(
        archived_at=now,
        archived_by=request.user,
        is_active=False
    )
    
    # Archive barcodes
    barcode_filters = Q(business=business, is_archived=False)
    if location:
        barcode_filters &= Q(location=location)
    
    barcodes = InventoryBarcode.objects.filter(barcode_filters)
    archived_counts["barcodes"] = barcodes.update(
        is_archived=True,
        archived_at=now,
        archived_by=request.user
    )
    
    # Archive laptop serials
    laptop_filters = Q(business=business, is_active=True, archived_at__isnull=True)
    if location:
        laptop_filters &= Q(location=location)
    
    laptop_serials = LaptopSerial.objects.filter(laptop_filters)
    archived_counts["laptop_serials"] = laptop_serials.update(
        is_active=False,
        archived_at=now,
        archived_by=request.user
    )
    
    # Update archive batch with actual counts
    archive_batch.counts_snapshot = {
        **counts,
        "archived": archived_counts,
    }
    archive_batch.save(update_fields=["counts_snapshot"])
    
    # Clear session
    request.session.pop("archive_scope", None)
    request.session.pop("archive_location_id", None)
    request.session.pop("archive_counts", None)
    request.session.pop("archive_step", None)
    
    messages.success(
        request,
        f"✅ Archive completed successfully! "
        f"Archived {archived_counts['products']} products, "
        f"{archived_counts['stock_items']} stock items, "
        f"{archived_counts['barcodes']} barcodes, "
        f"and {archived_counts['laptop_serials']} laptop serials."
    )
    
    return render(request, "inventory/archive/step4_success.html", {
        "business": business,
        "location": location,
        "scope": scope,
        "archived_counts": archived_counts,
        "archive_batch": archive_batch,
    })

