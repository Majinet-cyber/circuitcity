# inventory/verticals/farm_sales.py
"""
Farm Sales view with gamified Malawi-specific crop and livestock quick-pick cards.
Implements "sell only what is recorded" validation (Jan 2026).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_farm import (
    FarmCrop,
    FarmCropSale,
    FarmLedgerEntry,
    FarmLivestockBatch,
    FarmEntryType,
    FarmUnit,
    FarmPaymentMethod,
    MALAWI_CROP_CATALOG,
    FarmCropCategory,
)
from tenants.utils import require_business
from inventory.verticals import base


def ensure_farm_crops_seeded(business) -> None:
    """
    Ensure Malawi crops are seeded for this farm business.
    Idempotent - only creates crops that don't exist.
    """
    existing_crops = set(FarmCrop.objects.filter(business=business).values_list("name", flat=True))
    
    crops_to_create = []
    for category, crops in MALAWI_CROP_CATALOG.items():
        for crop_data in crops:
            if crop_data["name"] not in existing_crops:
                crops_to_create.append(FarmCrop(
                    business=business,
                    name=crop_data["name"],
                    category=category,
                    emoji=crop_data.get("emoji", "🌾"),
                    unit=crop_data.get("unit", "bag"),
                    is_active=True,
                ))
    
    if crops_to_create:
        FarmCrop.objects.bulk_create(crops_to_create, ignore_conflicts=True)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def sales_landing(request: HttpRequest) -> HttpResponse:
    """
    Farm Sales landing: Choose between Crops or Livestock.
    Shows empty-state CTA if no crops/livestock recorded.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    from inventory.services.farm_filters import parse_farm_filters, get_available_filter_options
    filter_state = parse_farm_filters(request, business)
    filter_options = get_available_filter_options(business)
    
    # Check if business has any recorded crops/livestock
    has_crops = FarmCrop.objects.filter(business=business, is_active=True).exists()
    has_livestock = FarmLivestockBatch.objects.filter(business=business, is_active=True).exists()
    
    ctx.update({
        "active_tab": "sales",
        "hero_title": "Farm Sales",
        "hero_blurb": "Record your crop and livestock sales quickly",
        "filter_state": filter_state,
        "filter_options": filter_options,
        "has_crops": has_crops,
        "has_livestock": has_livestock,
    })
    
    return render(request, "verticals/farm/sales_landing.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def sales_crops(request: HttpRequest) -> HttpResponse:
    """
    Crop Sales: Gamified Malawi crop cards.
    Seeds default crops on first access.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Ensure Malawi crops are seeded (idempotent)
    ensure_farm_crops_seeded(business)
    
    # Get all recorded crops for this business, grouped by category
    crops = FarmCrop.objects.filter(business=business, is_active=True).order_by("category", "name")
    
    # Group crops by category for display
    crops_by_category = {}
    for crop in crops:
        cat_display = crop.get_category_display()
        if cat_display not in crops_by_category:
            crops_by_category[cat_display] = []
        crops_by_category[cat_display].append(crop)
    
    ctx.update({
        "active_tab": "sales",
        "hero_title": "Crop Sales",
        "hero_blurb": "Select the crop you sold",
        "crops_by_category": crops_by_category,
        "has_crops": crops.exists(),
    })
    
    return render(request, "verticals/farm/sales_crops.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def sales_livestock(request: HttpRequest) -> HttpResponse:
    """
    Livestock Sales: Quick-pick from recorded livestock batches.
    Shows empty-state if no livestock recorded.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Get all active livestock batches
    batches = FarmLivestockBatch.objects.filter(
        business=business, 
        is_active=True
    ).order_by("animal_type", "name")
    
    ctx.update({
        "active_tab": "sales",
        "hero_title": "Livestock Sales",
        "hero_blurb": "Select the livestock batch you sold from",
        "batches": batches,
        "has_livestock": batches.exists(),
    })
    
    return render(request, "verticals/farm/sales_livestock.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def sales_record(request: HttpRequest) -> HttpResponse:
    """
    Record a new farm sale.
    Enforces "sell only what is recorded" validation.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    sale_type = request.GET.get("type", request.POST.get("type", "crop"))
    crop_id = request.GET.get("crop_id", request.POST.get("crop_id"))
    batch_id = request.GET.get("batch_id", request.POST.get("batch_id"))
    
    # Validate: crop/livestock must belong to this business
    selected_crop = None
    selected_batch = None
    
    if sale_type == "crop" and crop_id:
        try:
            selected_crop = FarmCrop.objects.get(id=crop_id, business=business, is_active=True)
        except FarmCrop.DoesNotExist:
            messages.error(request, "❌ Invalid crop selection. You can only sell recorded crops.")
            return redirect("verticals:farm_sales_crops")
    
    if sale_type == "livestock" and batch_id:
        try:
            selected_batch = FarmLivestockBatch.objects.get(id=batch_id, business=business, is_active=True)
        except FarmLivestockBatch.DoesNotExist:
            messages.error(request, "❌ Invalid livestock selection. You can only sell recorded livestock.")
            return redirect("verticals:farm_sales_livestock")
    
    if request.method == "POST":
        try:
            # Parse inputs
            quantity_str = request.POST.get("quantity", "").strip()
            unit_price_str = request.POST.get("unit_price", "").strip()
            
            try:
                quantity = Decimal(quantity_str) if quantity_str else Decimal("0")
                unit_price = Decimal(unit_price_str) if unit_price_str else Decimal("0")
            except (InvalidOperation, ValueError):
                messages.error(request, "Invalid quantity or price format.")
                raise ValueError("Invalid decimal")
            
            if quantity <= 0 or unit_price <= 0:
                messages.error(request, "Quantity and price must be greater than zero.")
                raise ValueError("Invalid values")
            
            total_amount = quantity * unit_price
            
            # SERVER-SIDE VALIDATION: Sell only what is recorded
            if sale_type == "crop":
                if not selected_crop:
                    messages.error(request, "❌ You cannot sell a crop that is not recorded. Please record crops first.")
                    return redirect("verticals:farm_crops_list")
                
                # Optional: Check quantity (if tracking is enabled)
                if selected_crop.quantity_available > 0 and quantity > selected_crop.quantity_available:
                    messages.error(
                        request, 
                        f"❌ Insufficient stock. Available: {selected_crop.quantity_available} {selected_crop.get_unit_display()}"
                    )
                    raise ValueError("Insufficient stock")
                
                description = f"{selected_crop.name} sale"
                enterprise_type = "crop"
                
            elif sale_type == "livestock":
                if not selected_batch:
                    messages.error(request, "❌ You cannot sell livestock that is not recorded. Please add livestock first.")
                    return redirect("verticals:farm_livestock_list")
                
                # Check batch count
                if quantity > selected_batch.count_current:
                    messages.error(
                        request, 
                        f"❌ Insufficient livestock. Available: {selected_batch.count_current} head in batch '{selected_batch.name}'"
                    )
                    raise ValueError("Insufficient livestock")
                
                description = f"{selected_batch.name} ({selected_batch.get_animal_type_display()}) sale"
                enterprise_type = selected_batch.animal_type
                
            else:
                description = request.POST.get("description", "Sale")
                enterprise_type = "general"
            
            # Create ledger entry
            ledger_entry = FarmLedgerEntry.objects.create(
                business=business,
                date=request.POST.get("date") or timezone.now().date(),
                entry_type=FarmEntryType.SALE,
                enterprise_type=enterprise_type,
                category="sale",
                description=description,
                amount_mwk=total_amount,
                quantity=quantity,
                unit=request.POST.get("unit", "item"),
                payment_method=request.POST.get("payment_method", "cash"),
                notes=request.POST.get("notes", ""),
                livestock_batch=selected_batch,
                created_by=request.user,
            )
            
            # Create FarmCropSale record if it's a crop sale
            if sale_type == "crop" and selected_crop:
                FarmCropSale.objects.create(
                    business=business,
                    crop=selected_crop,
                    ledger_entry=ledger_entry,
                    date=ledger_entry.date,
                    quantity=quantity,
                    unit_price_mwk=unit_price,
                    buyer_name=request.POST.get("buyer_name", ""),
                    created_by=request.user,
                )
                
                # Update crop stock if tracking
                if selected_crop.quantity_available > 0:
                    selected_crop.quantity_available -= quantity
                    selected_crop.save(update_fields=["quantity_available", "updated_at"])
            
            # Update livestock batch count if it's a livestock sale
            if sale_type == "livestock" and selected_batch:
                selected_batch.count_current = max(0, selected_batch.count_current - int(quantity))
                selected_batch.save(update_fields=["count_current"])
            
            messages.success(request, f"✅ Sale of MWK {total_amount:,.2f} recorded successfully!")
            return redirect("verticals:farm_sales")
        
        except ValueError:
            pass  # Error message already shown
        except Exception as e:
            messages.error(request, f"Error recording sale: {e}")
    
    # Get crops/batches for dropdown fallback
    crops = FarmCrop.objects.filter(business=business, is_active=True)
    batches = FarmLivestockBatch.objects.filter(business=business, is_active=True)
    
    ctx.update({
        "active_tab": "sales",
        "hero_title": "Record Sale",
        "sale_type": sale_type,
        "selected_crop": selected_crop,
        "selected_batch": selected_batch,
        "crops": crops,
        "batches": batches,
        "payment_methods": FarmPaymentMethod.choices,
        "units": FarmUnit.choices,
    })
    
    return render(request, "verticals/farm/sales_record.html", ctx)
