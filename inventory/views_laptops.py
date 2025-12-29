# inventory/views_laptops.py
"""
Laptop product and stock management views.

Laptops are tracked by serial number (not IMEI like phones).
Each laptop has a unique serial per business.
"""
from __future__ import annotations

from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.decorators import manager_required
from tenants.decorators import require_business_access as require_business
from tenants.middleware import get_active_business
from tenants.scope import resolve_location_for_user
from inventory.models import Location
from inventory.models_laptops import LaptopProduct, LaptopSerial, LaptopBrand
from inventory.business_kinds import BusinessKind


@login_required
@manager_required
@require_business
@require_http_methods(["GET", "POST"])
def laptop_stock_in(request: HttpRequest) -> HttpResponse:
    """
    Laptop stock-in wizard.
    
    Flow:
    1. Brand selection
    2. Model name (optional, can create new)
    3. RAM, Storage, Battery life
    4. Serial number (required, unique)
    5. Order price, Selling price
    6. Save
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("inventory:dashboard")
    
    # Get location (required for LaptopSerial)
    location_id = resolve_location_for_user(request)
    location = None
    if location_id:
        try:
            location = Location.objects.get(pk=location_id, business=business)
        except Location.DoesNotExist:
            pass
    
    if not location:
        location = Location.default_for(business)
    
    if not location:
        location = Location.ensure_default_for_business(business)
    
    if not location:
        messages.error(request, "No location available. Please create a location first.")
        return redirect("inventory:locations")
    
    if request.method == "POST":
        brand = request.POST.get("brand", "").strip()
        model_name = request.POST.get("model_name", "").strip()
        ram = request.POST.get("ram", "").strip()
        storage = request.POST.get("storage", "").strip()
        battery_life = request.POST.get("battery_life", "").strip()
        serial = request.POST.get("serial", "").strip()
        order_price = request.POST.get("order_price", "0").strip()
        selling_price = request.POST.get("selling_price", "").strip()
        
        # Validation
        if not brand:
            messages.error(request, "Brand is required")
            return redirect("inventory:laptop_stock_in")
        
        if not serial:
            messages.error(request, "Serial number is required")
            return redirect("inventory:laptop_stock_in")
        
        # Check for duplicate serial
        existing = LaptopSerial.objects.filter(
            business=business,
            serial=serial,
            is_active=True
        ).first()
        
        if existing:
            messages.error(
                request,
                f"Serial number '{serial}' already exists in your inventory. "
                "Each laptop must have a unique serial number."
            )
            return redirect("inventory:laptop_stock_in")
        
        # Parse prices
        try:
            order_price_decimal = Decimal(order_price) if order_price else Decimal("0.00")
            selling_price_decimal = Decimal(selling_price) if selling_price else None
        except Exception as e:
            messages.error(request, f"Invalid price format: {str(e)}")
            return redirect("inventory:laptop_stock_in")
        
        # Get or create laptop product
        with transaction.atomic():
            # Use get_or_create with all unique fields
            try:
                laptop_product = LaptopProduct.objects.get(
                    business=business,
                    brand=brand,
                    model_name=model_name or "Unknown Model",
                    ram=ram or "",
                    storage=storage or "",
                )
                created = False
            except LaptopProduct.DoesNotExist:
                laptop_product = LaptopProduct.objects.create(
                    business=business,
                    brand=brand,
                    model_name=model_name or "Unknown Model",
                    ram=ram or "",
                    storage=storage or "",
                    battery_life=battery_life or "",
                    default_cost_price=order_price_decimal if order_price_decimal > 0 else None,
                    default_selling_price=selling_price_decimal,
                    is_active=True,
                )
                created = True
            
            # Update prices if product already exists
            if not created:
                if order_price_decimal > 0:
                    laptop_product.default_cost_price = order_price_decimal
                if selling_price_decimal:
                    laptop_product.default_selling_price = selling_price_decimal
                laptop_product.save()
            
            # Create laptop serial
            laptop_serial = LaptopSerial.objects.create(
                business=business,
                location=location,
                product=laptop_product,
                serial=serial,
                order_price=order_price_decimal,
                selling_price=selling_price_decimal or laptop_product.default_selling_price,
                status="IN_STOCK",
                is_active=True,
            )
        
        messages.success(
            request,
            f"✅ Laptop '{laptop_product.display_name}' (Serial: {serial}) stocked successfully!"
        )
        return redirect("inventory:laptop_stock_in")
    
    # GET: Show form
    # Get existing laptop products for quick selection
    existing_products = LaptopProduct.objects.filter(
        business=business,
        is_active=True
    ).order_by("brand", "model_name")[:50]
    
    # Group by brand
    products_by_brand = {}
    for product in existing_products:
        brand_key = product.brand
        if brand_key not in products_by_brand:
            products_by_brand[brand_key] = []
        products_by_brand[brand_key].append(product)
    
    context = {
        "business": business,
        "location": location,
        "brands": LaptopBrand.choices,
        "products_by_brand": products_by_brand,
        "page_title": "Stock In Laptop",
    }
    
    return render(request, "inventory/laptops/stock_in.html", context)


@login_required
@require_business
@require_http_methods(["GET", "POST"])
def laptop_sell(request: HttpRequest) -> HttpResponse:
    """
    Sell a laptop by selecting serial number.
    
    Flow:
    1. Search/select laptop by serial or product
    2. Confirm sale details
    3. Complete sale (mark serial as SOLD)
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("inventory:dashboard")
    
    if request.method == "POST":
        serial_id = request.POST.get("serial_id", "").strip()
        
        if not serial_id:
            messages.error(request, "Please select a laptop to sell")
            return redirect("inventory:laptop_sell")
        
        try:
            laptop_serial = LaptopSerial.objects.get(
                pk=serial_id,
                business=business,
                status="IN_STOCK",
                is_active=True
            )
        except LaptopSerial.DoesNotExist:
            messages.error(request, "Laptop not found or already sold")
            return redirect("inventory:laptop_sell")
        
        # Mark as sold
        with transaction.atomic():
            laptop_serial.status = "SOLD"
            laptop_serial.save(update_fields=["status"])
        
        messages.success(
            request,
            f"✅ Laptop '{laptop_serial.product.display_name}' (Serial: {laptop_serial.serial}) sold successfully!"
        )
        return redirect("inventory:laptop_sell")
    
    # GET: Show available laptops
    available_laptops = LaptopSerial.objects.filter(
        business=business,
        status="IN_STOCK",
        is_active=True
    ).select_related("product", "location").order_by("product__brand", "product__model_name")
    
    context = {
        "business": business,
        "available_laptops": available_laptops,
        "page_title": "Sell Laptop",
    }
    
    return render(request, "inventory/laptops/sell.html", context)


@login_required
@manager_required
@require_business
def laptop_products_list(request: HttpRequest) -> HttpResponse:
    """List all laptop products in catalog"""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("inventory:dashboard")
    
    products = LaptopProduct.objects.filter(
        business=business,
        is_active=True
    ).order_by("brand", "model_name")
    
    # Get stock counts per product
    for product in products:
        product.stock_count = LaptopSerial.objects.filter(
            product=product,
            status="IN_STOCK",
            is_active=True
        ).count()
    
    context = {
        "business": business,
        "products": products,
        "page_title": "Laptop Products",
    }
    
    return render(request, "inventory/laptops/products_list.html", context)

