# inventory/views_phone_products.py
"""
Phone Products Catalog Views

Provides CRUD operations for the curated phone products catalog.
Follows the Liquor products pattern for consistency.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from tenants.utils import require_business
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_phone_products import PhoneProductCatalog
from inventory.phone_catalog_seed import (
    should_seed_phone_catalog,
    seed_phone_catalog,
    get_brands_for_business,
    get_models_for_brand,
)
from inventory.verticals import base


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def phone_products_list(request):
    """
    Display the phone products catalog for the business.
    
    Shows:
    - Filter by brand (TECNO, ITEL, SAMSUNG, etc.)
    - Cards/table of models and variants
    - Actions: Add to stock, Edit, Delete
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Auto-seed catalog if empty
    if should_seed_phone_catalog(business):
        try:
            created_count = seed_phone_catalog(business, created_by=request.user)
            if created_count > 0:
                messages.success(
                    request,
                    f"✨ Initialized your phone catalog with {created_count} flagship models!"
                )
        except Exception as e:
            messages.warning(
                request,
                f"Could not auto-seed phone catalog: {e}"
            )
    
    # Get filter params
    brand_filter = request.GET.get("brand", "").strip().upper()
    
    # Get all brands for filter dropdown
    all_brands = get_brands_for_business(business)
    
    # Get products (filtered by brand if specified)
    if brand_filter and brand_filter in all_brands:
        products = PhoneProductCatalog.objects.filter(
            business=business,
            brand=brand_filter,
            is_active=True
        ).order_by("model_name", "ram_gb", "rom_gb")
    else:
        products = PhoneProductCatalog.objects.filter(
            business=business,
            is_active=True
        ).order_by("brand", "model_name", "ram_gb", "rom_gb")
    
    # Group products by brand for display
    products_by_brand = {}
    for product in products:
        if product.brand not in products_by_brand:
            products_by_brand[product.brand] = []
        products_by_brand[product.brand].append(product)
    
    ctx.update({
        "products_by_brand": products_by_brand,
        "all_brands": all_brands,
        "brand_filter": brand_filter,
        "total_products": products.count(),
        "hero_title": "Phone Products Catalog",
        "hero_blurb": "Manage your curated phone models and variants",
        "active_tab": "products",
    })
    
    return render(request, "verticals/phones/products.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@require_http_methods(["GET", "POST"])
def phone_product_create(request):
    """
    Create a new phone product in the catalog.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        # Extract form data
        brand = request.POST.get("brand", "").strip().upper()
        model_name = request.POST.get("model_name", "").strip()
        ram_gb = request.POST.get("ram_gb", "").strip()
        rom_gb = request.POST.get("rom_gb", "").strip()
        model_number = request.POST.get("model_number", "").strip()
        default_cost_price = request.POST.get("default_cost_price", "").strip()
        default_selling_price = request.POST.get("default_selling_price", "").strip()
        
        # Validation
        errors = []
        if not brand:
            errors.append("Brand is required")
        if not model_name:
            errors.append("Model name is required")
        if not ram_gb or not ram_gb.isdigit():
            errors.append("Valid RAM (GB) is required")
        if not rom_gb or not rom_gb.isdigit():
            errors.append("Valid ROM (GB) is required")
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect("inventory:phone_products")
        
        # Convert to proper types
        ram_gb = int(ram_gb)
        rom_gb = int(rom_gb)
        cost_price = Decimal(default_cost_price) if default_cost_price else None
        selling_price = Decimal(default_selling_price) if default_selling_price else None
        
        # Check for duplicates
        existing = PhoneProductCatalog.objects.filter(
            business=business,
            brand=brand,
            model_name=model_name,
            ram_gb=ram_gb,
            rom_gb=rom_gb
        ).first()
        
        if existing:
            messages.error(
                request,
                f"Product {brand} {model_name} ({ram_gb}+{rom_gb}) already exists in your catalog"
            )
            return redirect("inventory:phone_products")
        
        # Create product
        product = PhoneProductCatalog.objects.create(
            business=business,
            brand=brand,
            model_name=model_name,
            ram_gb=ram_gb,
            rom_gb=rom_gb,
            model_number=model_number,
            default_cost_price=cost_price,
            default_selling_price=selling_price,
            created_by=request.user,
        )
        
        messages.success(
            request,
            f"✅ Added {product.display_name} to your catalog"
        )
        return redirect("inventory:phone_products")
    
    # GET: Show form
    ctx.update({
        "hero_title": "Add Phone Product",
        "hero_blurb": "Add a new phone model to your catalog",
    })
    return render(request, "verticals/phones/product_form.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@require_http_methods(["GET", "POST"])
def phone_product_edit(request, product_id):
    """
    Edit an existing phone product in the catalog.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    product = get_object_or_404(
        PhoneProductCatalog,
        id=product_id,
        business=business
    )
    
    if request.method == "POST":
        # Extract form data
        model_number = request.POST.get("model_number", "").strip()
        default_cost_price = request.POST.get("default_cost_price", "").strip()
        default_selling_price = request.POST.get("default_selling_price", "").strip()
        is_active = request.POST.get("is_active") == "on"
        
        # Update product (brand/model/RAM/ROM are immutable after creation)
        product.model_number = model_number
        product.default_cost_price = Decimal(default_cost_price) if default_cost_price else None
        product.default_selling_price = Decimal(default_selling_price) if default_selling_price else None
        product.is_active = is_active
        product.save()
        
        messages.success(request, f"✅ Updated {product.display_name}")
        return redirect("inventory:phone_products")
    
    # GET: Show form
    ctx.update({
        "product": product,
        "hero_title": f"Edit {product.display_name}",
        "hero_blurb": "Update product details and pricing",
    })
    return render(request, "verticals/phones/product_form.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@require_http_methods(["POST"])
def phone_product_delete(request, product_id):
    """
    Delete (deactivate) a phone product from the catalog.
    """
    business = base.base_context(request).get("business")
    
    product = get_object_or_404(
        PhoneProductCatalog,
        id=product_id,
        business=business
    )
    
    # Soft delete by deactivating
    product.is_active = False
    product.save()
    
    messages.success(request, f"🗑️ Removed {product.display_name} from catalog")
    return redirect("inventory:phone_products")


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def phone_products_api_models(request):
    """
    API endpoint: Get models for a specific brand.
    
    Used by the gamified sale wizard to populate model dropdown
    after brand selection.
    
    Query params:
        brand: Brand name (e.g., "TECNO", "ITEL", "SAMSUNG")
    
    Returns:
        JSON array of models:
        [
            {
                "id": 1,
                "model_name": "Spark 40",
                "variant_label": "4+128",
                "ram_gb": 4,
                "rom_gb": 128,
                "default_cost_price": "450000.00",
                "default_selling_price": "550000.00",
                "display_name": "TECNO Spark 40 (4+128)"
            },
            ...
        ]
    """
    business = base.base_context(request).get("business")
    brand = request.GET.get("brand", "").strip()
    
    if not brand:
        return JsonResponse({"error": "Brand parameter required"}, status=400)
    
    models = get_models_for_brand(business, brand)
    
    # Convert Decimal to string for JSON serialization
    for model in models:
        if model.get("default_cost_price"):
            model["default_cost_price"] = str(model["default_cost_price"])
        if model.get("default_selling_price"):
            model["default_selling_price"] = str(model["default_selling_price"])
    
    return JsonResponse({"models": models})

