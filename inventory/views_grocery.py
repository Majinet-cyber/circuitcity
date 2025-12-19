# inventory/views_grocery.py
"""
Views for Grocery vertical - simple, no agents/wallets/timelogs.
Focus on: Costs, Stock In, Sell, Dashboard, Analytics.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import timedelta, date
from typing import Dict, Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Count, Q, F
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from tenants.models import Business
from core.verticals import require_vertical, get_vertical_context
from .models_grocery import (
    GroceryProduct,
    GroceryStockIn,
    GrocerySale,
    GroceryCost,
    GroceryCategory,
    GroceryUnitType,
    GrocerySaleType,
)


# ==============================================================================
# FAST SELL (BARCODE SCAN)
# ==============================================================================

@login_required
@require_vertical('grocery')
@require_http_methods(["GET", "POST"])
def grocery_fast_sell(request: HttpRequest) -> HttpResponse:
    """
    Fast sell page with barcode scanning support.
    ONLY uses Unique Products (barcode/SKU-based inventory).
    """
    from .models_unique_products import UniqueProduct, UniqueSale
    
    business: Business = request.business
    
    if request.method == "POST":
        # Handle sale submission for UNIQUE PRODUCTS ONLY
        product_id = request.POST.get("product_id")
        quantity = request.POST.get("quantity", "0")
        unit_price = request.POST.get("unit_price", "0")
        payment_method = request.POST.get("payment_method", "CASH")
        customer_name = request.POST.get("customer_name", "").strip()
        customer_phone = request.POST.get("customer_phone", "").strip()
        
        try:
            # ONLY lookup from UniqueProduct table
            product = UniqueProduct.objects.get(
                id=product_id,
                business=business,
                vertical="groceries",
                is_active=True
            )
            qty = Decimal(quantity)
            price = Decimal(unit_price)
            
            if qty <= 0:
                messages.error(request, "Quantity must be greater than 0.")
            elif qty > product.quantity:
                messages.error(request, f"Insufficient stock. Available: {product.quantity} {product.unit}")
            else:
                with transaction.atomic():
                    # Create unique sale
                    sale = UniqueSale.objects.create(
                        business=business,
                        product=product,
                        quantity=qty,
                        unit_price=price,
                        unit_cost=product.cost_price,
                        payment_method=payment_method,
                        customer_name=customer_name,
                        customer_phone=customer_phone,
                        sold_by=request.user,
                    )
                    
                    # Deduct stock
                    product.quantity -= qty
                    product.save(update_fields=["quantity", "updated_at"])
                    
                    messages.success(
                        request,
                        f"✅ Sale completed: {qty} {product.unit} of {product.name}"
                    )
                    return redirect("grocery:fast_sell")
        except UniqueProduct.DoesNotExist:
            messages.error(request, "Product not found in Unique Products.")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    # GET: show fast sell page
    # Show recent unique sales (not regular grocery sales)
    recent_sales = UniqueSale.objects.filter(
        business=business,
        product__vertical="groceries",
        is_deleted=False
    ).select_related("product").order_by("-sold_at")[:5]
    
    return render(request, "verticals/grocery/fast_sell.html", {
        "business": business,
        "recent_sales": recent_sales,
    })


@login_required
@require_vertical('grocery')
@require_http_methods(["GET"])
def grocery_fast_sell_lookup(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to lookup product by barcode or name.
    ONLY searches in Unique Products (barcode/SKU-based).
    Returns product details for fast sell.
    """
    from .models_unique_products import UniqueProduct
    
    business: Business = request.business
    query = request.GET.get("q", "").strip().upper()
    
    if not query:
        return JsonResponse({"success": False, "error": "Query is required"})
    
    # ONLY lookup from UniqueProduct table (groceries vertical)
    # Try to find by barcode first (exact match)
    product = None
    try:
        product = UniqueProduct.objects.filter(
            business=business,
            vertical="groceries",
            is_active=True,
            barcode=query
        ).first()
    except Exception:
        pass
    
    # If not found by barcode, try by name (case-insensitive contains)
    if not product:
        try:
            product = UniqueProduct.objects.filter(
                business=business,
                vertical="groceries",
                is_active=True,
                name__icontains=query
            ).first()
        except Exception:
            pass
    
    if not product:
        return JsonResponse({
            "success": False,
            "error": "Not found in Unique Products",
            "barcode": query,
        })
    
    return JsonResponse({
        "success": True,
        "product": {
            "id": product.id,
            "name": product.name,
            "barcode": product.barcode,
            "unit": product.unit,
            "quantity": float(product.quantity),
            "cost_price": float(product.cost_price),
            "selling_price": float(product.selling_price),
            "is_in_stock": product.is_in_stock,
        }
    })


# ==============================================================================
# GROCERY DASHBOARD
# ==============================================================================

@login_required
@require_vertical('grocery')
@require_http_methods(["GET"])
def grocery_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard for grocery vertical.
    Shows: Universal KPIs, recent sales, low stock alerts, motivational quote.
    """
    from .services_kpis import get_kpi_context
    
    business: Business = request.business
    
    # Get KPI context with date range support
    kpi_context = get_kpi_context(
        business=business,
        vertical="groceries",
        date_range_param=request.GET.get("date_range"),
        start_date_param=request.GET.get("start_date"),
        end_date_param=request.GET.get("end_date"),
    )
    
    # Active products (bundled + unique)
    products = GroceryProduct.objects.filter(business=business, is_active=True)
    total_products = products.count()
    
    from .models_unique_products import UniqueProduct
    unique_products = UniqueProduct.objects.filter(
        business=business,
        vertical="groceries",
        is_active=True
    )
    total_products += unique_products.count()
    
    # Low stock alerts
    low_stock_products = products.filter(quantity__lte=F("reorder_level"))
    low_stock_count = low_stock_products.count()
    
    # Recent sales (from both bundled and unique)
    today = timezone.now().date()
    days = int(request.GET.get("days", 7))
    start_date = today - timedelta(days=days)
    
    regular_sales = GrocerySale.objects.filter(
        business=business,
        is_deleted=False,
        sold_at__date__gte=start_date
    ).order_by("-sold_at")[:5]
    
    from .models_unique_products import UniqueSale
    unique_sales_list = UniqueSale.objects.filter(
        business=business,
        product__vertical="groceries",
        is_deleted=False,
        sold_at__date__gte=start_date
    ).select_related("product").order_by("-sold_at")[:5]
    
    # Motivational quote (rotating)
    quotes = [
        "Every sale is a step towards success! 🎯",
        "Keep your stock fresh, keep your customers happy! 🌟",
        "Consistency is the key to profitability. 📈",
        "Quality products, quality service, quality results! ✨",
        "Your dedication makes the difference! 💪",
    ]
    daily_quote = quotes[hash(str(today)) % len(quotes)]
    
    context = {
        **kpi_context,  # Include KPI data
        "total_products": total_products,
        "low_stock_count": low_stock_count,
        "low_stock_products": low_stock_products[:10],
        "recent_regular_sales": regular_sales,
        "recent_unique_sales": unique_sales_list,
        "days": days,
        "daily_quote": daily_quote,
    }
    
    return render(request, "verticals/grocery/dashboard.html", context)


# ==============================================================================
# GROCERY STOCK IN
# ==============================================================================

@login_required
@require_vertical('grocery')
@require_http_methods(["GET", "POST"])
def grocery_stock_in(request: HttpRequest) -> HttpResponse:
    """
    Add stock for grocery products.
    """
    business: Business = request.business
    
    if request.method == "POST":
        # Extract form data
        product_id = request.POST.get("product_id")
        product_name = request.POST.get("product_name", "").strip()
        category = request.POST.get("category", "").strip()
        unit_type = request.POST.get("unit_type", "").strip()
        quantity = request.POST.get("quantity", "0")
        cost_price = request.POST.get("cost_price", "0")
        selling_price = request.POST.get("selling_price", "0")
        supplier = request.POST.get("supplier", "").strip()
        notes = request.POST.get("notes", "").strip()
        
        # Validation
        errors = []
        
        if product_id:
            # Existing product
            try:
                product = GroceryProduct.objects.get(id=product_id, business=business)
            except GroceryProduct.DoesNotExist:
                errors.append("Product not found.")
                product = None
        else:
            # New product
            if not product_name:
                errors.append("Product name is required.")
            if not category or category not in dict(GroceryCategory.choices):
                errors.append("Valid category is required.")
            if not unit_type or unit_type not in dict(GroceryUnitType.choices):
                errors.append("Valid unit type is required.")
            product = None
        
        try:
            qty = Decimal(quantity)
            if qty <= 0:
                errors.append("Quantity must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Invalid quantity.")
            qty = Decimal("0")
        
        try:
            cost = Decimal(cost_price)
            if cost < 0:
                errors.append("Cost price cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Invalid cost price.")
            cost = Decimal("0")
        
        try:
            selling = Decimal(selling_price)
            if selling < 0:
                errors.append("Selling price cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Invalid selling price.")
            selling = Decimal("0")
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                with transaction.atomic():
                    # Create or get product
                    if not product:
                        product = GroceryProduct.objects.create(
                            business=business,
                            name=product_name,
                            category=category,
                            unit_type=unit_type,
                            quantity=Decimal("0"),
                            cost_price=cost,
                            selling_price=selling,
                        )
                    
                    # Create stock in record
                    stock_in = GroceryStockIn.objects.create(
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
                    product.cost_price = cost
                    product.selling_price = selling
                    product.save(update_fields=["quantity", "cost_price", "selling_price"])
                    
                    messages.success(
                        request,
                        f"✅ Added {qty} {product.get_unit_type_display()} of {product.name}"
                    )
                    return redirect("grocery:stock_in")
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
    
    # GET: show form
    products = GroceryProduct.objects.filter(business=business, is_active=True).order_by("name")
    
    context = {
        "products": products,
        "categories": GroceryCategory.choices,
        "unit_types": GroceryUnitType.choices,
    }
    
    return render(request, "verticals/grocery/stock_in.html", context)


# ==============================================================================
# GROCERY SELL
# ==============================================================================

@login_required
@require_vertical('grocery')
@require_http_methods(["GET", "POST"])
def grocery_sell(request: HttpRequest) -> HttpResponse:
    """
    Record grocery sales (retail or wholesale).
    """
    business: Business = request.business
    
    if request.method == "POST":
        product_id = request.POST.get("product_id")
        sale_type = request.POST.get("sale_type", "retail")
        quantity = request.POST.get("quantity", "0")
        unit_price = request.POST.get("unit_price", "0")
        payment_method = request.POST.get("payment_method", "CASH")
        customer_name = request.POST.get("customer_name", "").strip()
        customer_phone = request.POST.get("customer_phone", "").strip()
        notes = request.POST.get("notes", "").strip()
        
        # Validation
        errors = []
        
        try:
            product = GroceryProduct.objects.get(id=product_id, business=business)
        except GroceryProduct.DoesNotExist:
            errors.append("Product not found.")
            product = None
        
        try:
            qty = Decimal(quantity)
            if qty <= 0:
                errors.append("Quantity must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Invalid quantity.")
            qty = Decimal("0")
        
        try:
            price = Decimal(unit_price)
            if price < 0:
                errors.append("Unit price cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Invalid unit price.")
            price = Decimal("0")
        
        # Check stock availability
        if product and qty > product.quantity:
            errors.append(f"Insufficient stock. Available: {product.quantity} {product.get_unit_type_display()}")
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                with transaction.atomic():
                    # Create sale
                    sale = GrocerySale.objects.create(
                        business=business,
                        product=product,
                        sale_type=sale_type,
                        quantity=qty,
                        unit_price=price,
                        unit_cost=product.cost_price,
                        payment_method=payment_method,
                        customer_name=customer_name,
                        customer_phone=customer_phone,
                        notes=notes,
                        sold_by=request.user,
                    )
                    
                    # Deduct stock
                    product.quantity -= qty
                    product.save(update_fields=["quantity"])
                    
                    messages.success(
                        request,
                        f"✅ Sold {qty} {product.get_unit_type_display()} of {product.name} for {sale.total_amount}"
                    )
                    return redirect("grocery:sell")
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
    
    # GET: show form
    products = GroceryProduct.objects.filter(
        business=business,
        is_active=True,
        quantity__gt=0
    ).order_by("name")
    
    context = {
        "products": products,
        "sale_types": GrocerySaleType.choices,
    }
    
    return render(request, "verticals/grocery/sell.html", context)


# ==============================================================================
# GROCERY COSTS
# ==============================================================================

@login_required
@require_vertical('grocery')
@require_http_methods(["GET", "POST"])
def grocery_costs(request: HttpRequest) -> HttpResponse:
    """
    Record and view operational costs.
    """
    business: Business = request.business
    
    if request.method == "POST":
        cost_type = request.POST.get("cost_type")
        amount = request.POST.get("amount", "0")
        description = request.POST.get("description", "").strip()
        cost_date_str = request.POST.get("cost_date", "")
        
        # Validation
        errors = []
        
        try:
            amt = Decimal(amount)
            if amt <= 0:
                errors.append("Amount must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Invalid amount.")
            amt = Decimal("0")
        
        try:
            cost_date = date.fromisoformat(cost_date_str) if cost_date_str else date.today()
        except ValueError:
            errors.append("Invalid date format.")
            cost_date = date.today()
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                GroceryCost.objects.create(
                    business=business,
                    cost_type=cost_type,
                    amount=amt,
                    description=description,
                    cost_date=cost_date,
                    recorded_by=request.user,
                )
                messages.success(request, f"✅ Recorded {cost_type} cost: {amt}")
                return redirect("grocery:costs")
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
    
    # GET: show costs
    days = int(request.GET.get("days", 30))
    start_date = date.today() - timedelta(days=days)
    
    costs = GroceryCost.objects.filter(
        business=business,
        cost_date__gte=start_date
    ).order_by("-cost_date")
    
    total_costs = costs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    
    # Group by cost type
    costs_by_type = costs.values("cost_type").annotate(
        total=Sum("amount")
    ).order_by("-total")
    
    context = {
        "costs": costs,
        "total_costs": total_costs,
        "costs_by_type": costs_by_type,
        "days": days,
        "cost_types": GroceryCost.COST_TYPE_CHOICES,
    }
    
    return render(request, "verticals/grocery/costs.html", context)


# ==============================================================================
# GROCERY ANALYTICS
# ==============================================================================

@login_required
@require_vertical('grocery')
@require_http_methods(["GET"])
def grocery_analytics(request: HttpRequest) -> HttpResponse:
    """
    Analytics dashboard for grocery business.
    """
    business: Business = request.business
    
    # Date range
    days = int(request.GET.get("days", 30))
    today = date.today()
    start_date = today - timedelta(days=days)
    
    # Sales data
    sales = GrocerySale.objects.filter(
        business=business,
        is_deleted=False,
        sold_at__date__gte=start_date
    )
    
    # Daily sales trend
    daily_sales = sales.extra(
        select={"day": "DATE(sold_at)"}
    ).values("day").annotate(
        revenue=Sum("total_amount"),
        count=Count("id")
    ).order_by("day")
    
    # Sales by category
    sales_by_category = sales.values(
        "product__category"
    ).annotate(
        revenue=Sum("total_amount"),
        count=Count("id")
    ).order_by("-revenue")
    
    # Sales by type (retail vs wholesale)
    sales_by_type = sales.values("sale_type").annotate(
        revenue=Sum("total_amount"),
        count=Count("id")
    )
    
    # Total metrics
    total_revenue = sales.aggregate(Sum("total_amount"))["total_amount__sum"] or Decimal("0")
    total_profit = sum(sale.profit for sale in sales)
    
    costs = GroceryCost.objects.filter(business=business, cost_date__gte=start_date)
    total_costs = costs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0")
    
    net_profit = total_profit - total_costs
    
    context = {
        "days": days,
        "daily_sales": list(daily_sales),
        "sales_by_category": sales_by_category,
        "sales_by_type": sales_by_type,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "total_costs": total_costs,
        "net_profit": net_profit,
    }
    
    return render(request, "verticals/grocery/analytics.html", context)


# ==============================================================================
# GROCERY PRODUCT LIST
# ==============================================================================

@login_required
@require_vertical('grocery')
@require_http_methods(["GET"])
def grocery_products(request: HttpRequest) -> HttpResponse:
    """
    List all grocery products with stock levels.
    """
    business: Business = request.business
    
    products = GroceryProduct.objects.filter(
        business=business,
        is_active=True
    ).order_by("name")
    
    # Filter by category if requested
    category = request.GET.get("category")
    if category:
        products = products.filter(category=category)
    
    context = {
        "products": products,
        "categories": GroceryCategory.choices,
        "selected_category": category,
    }
    
    return render(request, "verticals/grocery/products.html", context)

