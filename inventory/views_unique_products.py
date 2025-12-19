# inventory/views_unique_products.py
"""
Views for Unique Products (Barcode/SKU-based inventory for Fast Sell).

These views handle:
- Listing unique products
- Creating new unique products
- Stock-in for unique products
- Viewing unique sales history
"""
from __future__ import annotations

from decimal import Decimal
from datetime import timedelta, date
from typing import Dict, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Count, Q, F, DecimalField
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from tenants.models import Business
from .models_unique_products import UniqueProduct, UniqueProductStockIn, UniqueSale


# ==============================================================================
# UNIQUE PRODUCTS LIST
# ==============================================================================

@login_required
@require_http_methods(["GET"])
def unique_products_list(request: HttpRequest) -> HttpResponse:
    """
    List all unique products (barcode/SKU products) for the business.
    Supports filtering by vertical and search.
    """
    business: Business = request.business
    vertical = request.GET.get("vertical", "")
    search = request.GET.get("search", "").strip()
    
    products = UniqueProduct.objects.filter(
        business=business,
        is_active=True
    ).select_related("created_by").order_by("-created_at")
    
    # Filter by vertical if specified
    if vertical:
        products = products.filter(vertical=vertical)
    
    # Search by name or barcode
    if search:
        products = products.filter(
            Q(name__icontains=search) | Q(barcode__icontains=search)
        )
    
    # Calculate totals
    totals = products.aggregate(
        total_products=Count("id"),
        total_stock_value_cost=Sum(
            F("quantity") * F("cost_price"),
            output_field=DecimalField(max_digits=15, decimal_places=2)
        ),
        total_stock_value_selling=Sum(
            F("quantity") * F("selling_price"),
            output_field=DecimalField(max_digits=15, decimal_places=2)
        ),
    )
    
    context = {
        "products": products,
        "vertical": vertical,
        "search": search,
        "total_products": totals["total_products"] or 0,
        "total_stock_value_cost": totals["total_stock_value_cost"] or Decimal("0.00"),
        "total_stock_value_selling": totals["total_stock_value_selling"] or Decimal("0.00"),
        "verticals": [
            ("clothing", "Clothing"),
            ("pharmacy", "Pharmacy"),
            ("cosmetics", "Cosmetics"),
            ("groceries", "Groceries"),
        ],
    }
    
    return render(request, "inventory/unique_products/list.html", context)


# ==============================================================================
# CREATE UNIQUE PRODUCT
# ==============================================================================

@login_required
@require_http_methods(["GET", "POST"])
def unique_product_create(request: HttpRequest) -> HttpResponse:
    """
    Create a new unique product with barcode/SKU.
    Can be accessed directly or via Fast Sell "Not Found" flow.
    """
    business: Business = request.business
    
    if request.method == "POST":
        # Extract form data
        vertical = request.POST.get("vertical", "").strip()
        barcode = request.POST.get("barcode", "").strip().upper()
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        unit = request.POST.get("unit", "unit").strip()
        quantity = request.POST.get("quantity", "0")
        cost_price = request.POST.get("cost_price", "0")
        selling_price = request.POST.get("selling_price", "0")
        
        # Validation
        errors = []
        
        if not vertical or vertical not in ["clothing", "pharmacy", "cosmetics", "groceries"]:
            errors.append("Valid vertical is required.")
        
        if not barcode:
            errors.append("Barcode/SKU is required.")
        elif len(barcode) < 3:
            errors.append("Barcode/SKU must be at least 3 characters.")
        else:
            # Check for duplicate barcode in this business
            existing = UniqueProduct.objects.filter(
                business=business,
                barcode=barcode,
                is_active=True
            ).first()
            if existing:
                errors.append(
                    f"Barcode '{barcode}' is already used by product: {existing.name}. "
                    "Each barcode must be unique per business."
                )
        
        if not name:
            errors.append("Product name is required.")
        
        try:
            qty = Decimal(quantity)
            if qty < 0:
                errors.append("Quantity cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Invalid quantity.")
            qty = Decimal("0.00")
        
        try:
            cost = Decimal(cost_price)
            if cost < 0:
                errors.append("Cost price cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Invalid cost price.")
            cost = Decimal("0.00")
        
        try:
            selling = Decimal(selling_price)
            if selling <= 0:
                errors.append("Selling price must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Invalid selling price.")
            selling = Decimal("0.00")
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                with transaction.atomic():
                    # Create unique product
                    product = UniqueProduct.objects.create(
                        business=business,
                        vertical=vertical,
                        barcode=barcode,
                        name=name,
                        description=description,
                        unit=unit,
                        quantity=qty,
                        cost_price=cost,
                        selling_price=selling,
                        created_by=request.user,
                    )
                    
                    messages.success(
                        request,
                        f"✅ Unique product created: {name} (Code: {barcode})"
                    )
                    
                    # Check if this was from Fast Sell redirect
                    redirect_to_fast_sell = request.POST.get("redirect_to_fast_sell")
                    if redirect_to_fast_sell:
                        return redirect(f"inventory:{vertical}:fast_sell")
                    else:
                        return redirect("inventory:unique_products:list")
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
    
    # GET: show form
    # Pre-fill barcode if provided (from Fast Sell not-found flow)
    prefill_barcode = request.GET.get("barcode", "").strip()
    prefill_vertical = request.GET.get("vertical", "")
    redirect_to_fast_sell = request.GET.get("from_fast_sell", "")
    
    context = {
        "prefill_barcode": prefill_barcode,
        "prefill_vertical": prefill_vertical,
        "redirect_to_fast_sell": redirect_to_fast_sell,
        "verticals": [
            ("clothing", "Clothing"),
            ("pharmacy", "Pharmacy"),
            ("cosmetics", "Cosmetics"),
            ("groceries", "Groceries"),
        ],
    }
    
    return render(request, "inventory/unique_products/create.html", context)


# ==============================================================================
# STOCK IN UNIQUE PRODUCT
# ==============================================================================

@login_required
@require_http_methods(["GET", "POST"])
def unique_product_stock_in(request: HttpRequest) -> HttpResponse:
    """
    Add stock to an existing unique product or create a new one.
    """
    business: Business = request.business
    
    if request.method == "POST":
        # Two modes: existing product or new product
        mode = request.POST.get("mode", "existing")
        
        if mode == "existing":
            product_id = request.POST.get("product_id")
            try:
                product = UniqueProduct.objects.get(
                    id=product_id,
                    business=business,
                    is_active=True
                )
            except UniqueProduct.DoesNotExist:
                messages.error(request, "Product not found.")
                return redirect("inventory:unique_products:stock_in")
        else:
            # Create new product (similar to create view)
            vertical = request.POST.get("vertical", "").strip()
            barcode = request.POST.get("barcode", "").strip().upper()
            name = request.POST.get("name", "").strip()
            unit = request.POST.get("unit", "unit").strip()
            
            # Validate new product data
            if not all([vertical, barcode, name]):
                messages.error(request, "Vertical, barcode, and name are required for new products.")
                return redirect("inventory:unique_products:stock_in")
            
            # Check for duplicate
            existing = UniqueProduct.objects.filter(
                business=business,
                barcode=barcode,
                is_active=True
            ).first()
            if existing:
                messages.error(
                    request,
                    f"Barcode '{barcode}' already exists. Use 'Existing Product' mode instead."
                )
                return redirect("inventory:unique_products:stock_in")
            
            # Create the product
            product = UniqueProduct.objects.create(
                business=business,
                vertical=vertical,
                barcode=barcode,
                name=name,
                unit=unit,
                quantity=Decimal("0.00"),
                cost_price=Decimal("0.00"),
                selling_price=Decimal("0.00"),
                created_by=request.user,
            )
        
        # Now add stock
        quantity = request.POST.get("quantity", "0")
        cost_price = request.POST.get("cost_price", "0")
        selling_price = request.POST.get("selling_price", "0")
        supplier = request.POST.get("supplier", "").strip()
        notes = request.POST.get("notes", "").strip()
        
        # Validation
        errors = []
        
        try:
            qty = Decimal(quantity)
            if qty <= 0:
                errors.append("Quantity must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Invalid quantity.")
            qty = Decimal("0.00")
        
        try:
            cost = Decimal(cost_price)
            if cost < 0:
                errors.append("Cost price cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Invalid cost price.")
            cost = Decimal("0.00")
        
        try:
            selling = Decimal(selling_price)
            if selling < 0:
                errors.append("Selling price cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Invalid selling price.")
            selling = Decimal("0.00")
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                with transaction.atomic():
                    # Create stock-in record
                    stock_in = UniqueProductStockIn.objects.create(
                        business=business,
                        product=product,
                        quantity=qty,
                        cost_price=cost,
                        selling_price=selling,
                        supplier=supplier,
                        notes=notes,
                        added_by=request.user,
                    )
                    
                    # Update product stock and prices
                    product.quantity += qty
                    if cost > 0:
                        product.cost_price = cost
                    if selling > 0:
                        product.selling_price = selling
                    product.save(update_fields=["quantity", "cost_price", "selling_price", "updated_at"])
                    
                    messages.success(
                        request,
                        f"✅ Added {qty} {product.unit} to {product.name} (Code: {product.barcode})"
                    )
                    return redirect("inventory:unique_products:stock_in")
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
    
    # GET: show form
    products = UniqueProduct.objects.filter(
        business=business,
        is_active=True
    ).order_by("name")
    
    context = {
        "products": products,
        "verticals": [
            ("clothing", "Clothing"),
            ("pharmacy", "Pharmacy"),
            ("cosmetics", "Cosmetics"),
            ("groceries", "Groceries"),
        ],
    }
    
    return render(request, "inventory/unique_products/stock_in.html", context)


# ==============================================================================
# UNIQUE SALES HISTORY
# ==============================================================================

@login_required
@require_http_methods(["GET"])
def unique_sales_history(request: HttpRequest) -> HttpResponse:
    """
    View sales history for unique products.
    Shows detailed sales with profit/cost tracking.
    """
    business: Business = request.business
    
    # Date range (default: last 30 days)
    days = int(request.GET.get("days", 30))
    today = timezone.now().date()
    start_date = today - timedelta(days=days)
    
    # Optional filters
    vertical = request.GET.get("vertical", "")
    product_id = request.GET.get("product_id", "")
    
    # Base queryset
    sales = UniqueSale.objects.filter(
        business=business,
        is_deleted=False,
        sold_at__date__gte=start_date
    ).select_related("product", "sold_by").order_by("-sold_at")
    
    # Apply filters
    if vertical:
        sales = sales.filter(product__vertical=vertical)
    if product_id:
        sales = sales.filter(product_id=product_id)
    
    # Calculate totals
    total_revenue = sum(sale.total_amount for sale in sales)
    total_cost = sum(sale.total_cost for sale in sales)
    total_profit = total_revenue - total_cost
    total_count = sales.count()
    
    # Get product list for filter dropdown
    products = UniqueProduct.objects.filter(
        business=business,
        is_active=True
    ).order_by("name")
    
    context = {
        "sales": sales[:100],  # Limit to 100 most recent
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "total_count": total_count,
        "days": days,
        "vertical": vertical,
        "product_id": product_id,
        "products": products,
        "verticals": [
            ("clothing", "Clothing"),
            ("pharmacy", "Pharmacy"),
            ("cosmetics", "Cosmetics"),
            ("groceries", "Groceries"),
        ],
    }
    
    return render(request, "inventory/unique_products/sales_history.html", context)


# ==============================================================================
# API: LOOKUP UNIQUE PRODUCT BY BARCODE (for Fast Sell)
# ==============================================================================

@login_required
@require_http_methods(["GET"])
def api_lookup_unique_product(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to lookup unique product by barcode.
    Used by Fast Sell flows.
    
    GET /inventory/unique-products/api/lookup/?barcode=<code>&vertical=<vertical>
    """
    business: Business = request.business
    barcode = request.GET.get("barcode", "").strip().upper()
    vertical = request.GET.get("vertical", "").strip()
    
    if not barcode:
        return JsonResponse({"success": False, "error": "Barcode is required"})
    
    # Find product
    query = UniqueProduct.objects.filter(
        business=business,
        barcode=barcode,
        is_active=True
    )
    
    if vertical:
        query = query.filter(vertical=vertical)
    
    product = query.first()
    
    if not product:
        return JsonResponse({
            "success": False,
            "error": "Not found in Unique Products",
            "barcode": barcode,
            "vertical": vertical,
        })
    
    return JsonResponse({
        "success": True,
        "product": {
            "id": product.id,
            "name": product.name,
            "barcode": product.barcode,
            "vertical": product.vertical,
            "quantity": float(product.quantity),
            "unit": product.unit,
            "cost_price": float(product.cost_price),
            "selling_price": float(product.selling_price),
            "is_in_stock": product.is_in_stock,
            "stock_value_cost": float(product.stock_value_cost),
            "stock_value_selling": float(product.stock_value_selling),
        }
    })

