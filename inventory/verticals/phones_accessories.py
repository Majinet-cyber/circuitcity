# inventory/verticals/phones_accessories.py
"""
Accessories system for Phones vertical - quantity-based stock (NOT IMEI).

Provides:
- Dashboard with KPIs (revenue, profit, stock value)
- Stock-in wizard (gamified, barcode optional)
- Fast sell (barcode lookup + manual select)
- All fully scoped to business and location

CRITICAL: Accessories are SEPARATE from IMEI phones - no conflicts.
"""
from __future__ import annotations

import json
from decimal import Decimal
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from tenants.utils import require_business
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models import Location
from inventory.models_accessories import (
    AccessoryProduct, AccessoryStock, AccessoryStockLog,
    AccessoryCategory, normalize_barcode
)
from sales.models import Sale
from . import base


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def accessories_dashboard(request):
    """
    Accessories Dashboard - comprehensive KPIs for accessories business.
    
    Shows:
    - Revenue, profit, and profit margin
    - Stock value and stock count
    - Low stock alerts
    - Top selling accessories
    - Recent stock movements
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    # Parse date range (default: month-to-date)
    from inventory.verticals.phones import _parse_date_range
    range_key, start_date, end_date, range_label = _parse_date_range(request)
    
    # ==========================================================================
    # A) SALES KPIs FOR SELECTED RANGE
    # ==========================================================================
    # Accessories sales are stored in Sale model with a reference to AccessoryProduct
    # We need to create a new sale type or track via a special field
    # For now, let's calculate from AccessoryStockLog where action='SALE'
    
    sale_logs = AccessoryStockLog.objects.filter(
        business=business,
        action='SALE',
        created_at__gte=start_date,
        created_at__lt=end_date
    ).select_related('product', 'location')
    
    if location:
        sale_logs = sale_logs.filter(location=location)
    
    # Calculate revenue and costs from sale logs
    total_revenue = Decimal('0.00')
    total_cost = Decimal('0.00')
    units_sold = 0
    
    for log in sale_logs:
        # Quantity is negative for sales, so we take absolute value
        qty = abs(log.quantity)
        units_sold += qty
        
        # Get unit cost from log or product
        unit_cost = log.unit_cost or (log.product.default_order_price if log.product else Decimal('0.00'))
        unit_price = log.product.default_selling_price if log.product else Decimal('0.00')
        
        total_cost += Decimal(qty) * unit_cost
        total_revenue += Decimal(qty) * unit_price
    
    # Calculate profit and margin
    profit = total_revenue - total_cost
    profit_margin = (profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')
    
    # ==========================================================================
    # B) STOCK KPIs (CURRENT)
    # ==========================================================================
    stock_qs = AccessoryStock.objects.filter(
        business=business,
        product__is_active=True
    ).select_related('product', 'location')
    
    if location:
        stock_qs = stock_qs.filter(location=location)
    
    # Total stock count and value
    stock_items = stock_qs.filter(qty_on_hand__gt=0)
    total_stock_units = stock_qs.aggregate(
        total=Coalesce(Sum('qty_on_hand'), 0)
    )['total'] or 0
    
    stock_value = Decimal('0.00')
    for stock in stock_items:
        stock_value += stock.stock_value
    
    # Low stock count (products with qty < 5)
    low_stock_count = stock_qs.filter(qty_on_hand__lt=5, qty_on_hand__gt=0).count()
    
    # ==========================================================================
    # C) TOP SELLING ACCESSORIES (SELECTED RANGE)
    # ==========================================================================
    top_accessories = (
        sale_logs
        .values('product__id', 'product__name', 'product__category')
        .annotate(
            total_qty=Sum('quantity'),  # Will be negative, so we'll abs it
            revenue=Sum(F('quantity') * F('product__default_selling_price'))
        )
        .order_by('total_qty')[:10]  # Most negative = most sold
    )
    
    top_accessories_list = []
    for item in top_accessories:
        top_accessories_list.append({
            'name': item['product__name'] or 'Unknown',
            'category': AccessoryCategory(item['product__category']).label if item['product__category'] else 'Other',
            'units_sold': abs(item['total_qty'] or 0),
            'revenue': abs(item['revenue'] or Decimal('0.00')),
        })
    
    # ==========================================================================
    # D) RECENT STOCK MOVEMENTS (LAST 20)
    # ==========================================================================
    recent_movements = AccessoryStockLog.objects.filter(
        business=business
    ).select_related('product', 'location', 'by_user')
    
    if location:
        recent_movements = recent_movements.filter(location=location)
    
    recent_movements = recent_movements.order_by('-created_at')[:20]
    
    # ==========================================================================
    # E) CONTEXT ASSEMBLY
    # ==========================================================================
    ctx.update({
        'hero_title': 'Accessories Dashboard',
        'hero_blurb': 'Track your phone accessories sales, stock, and profitability.',
        'page_title': 'Accessories Dashboard',
        
        # Date range
        'range_key': range_key,
        'range_label': range_label,
        'start_date': start_date.date() if hasattr(start_date, 'date') else start_date,
        'end_date': end_date.date() if hasattr(end_date, 'date') else end_date,
        
        # KPIs
        'units_sold': units_sold,
        'revenue': total_revenue,
        'cost': total_cost,
        'profit': profit,
        'profit_margin': profit_margin,
        'profit_abs': abs(profit),
        'profit_margin_abs': abs(profit_margin),
        
        # Stock metrics
        'total_stock_units': total_stock_units,
        'stock_value': stock_value,
        'low_stock_count': low_stock_count,
        
        # Lists
        'top_accessories': top_accessories_list,
        'recent_movements': recent_movements,
    })
    
    return render(request, "verticals/phones/accessories_dashboard.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def accessories_stock_in(request):
    """
    Gamified stock-in wizard for accessories.
    
    Flow:
    1. Choose category (via clickable cards)
    2. Choose product (existing or create new)
    3. Barcode option (has barcode / no barcode)
    4. Prices (order price + selling price)
    5. Quantity
    6. Save (stock increases)
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    # If no location, use default
    if not location:
        location = Location.default_for(business)
        if not location:
            location = Location.ensure_default_for_business(business)
    
    # Get all categories for step 1
    categories = [
        {'value': cat[0], 'label': cat[1], 'icon': _get_category_icon(cat[0])}
        for cat in AccessoryCategory.choices
    ]
    
    # Get existing products grouped by category for quick access
    products_by_category = {}
    for cat_value, cat_label in AccessoryCategory.choices:
        products = AccessoryProduct.objects.filter(
            business=business,
            category=cat_value,
            is_active=True
        ).order_by('name')
        products_by_category[cat_value] = list(products)
    
    ctx.update({
        'hero_title': 'Stock In Accessories',
        'hero_blurb': 'Add accessories to your inventory with our gamified wizard.',
        'page_title': 'Stock In Accessories',
        'categories': categories,
        'products_by_category': json.dumps({
            k: [{'id': p.id, 'name': p.name, 'sku': p.sku, 'barcode': p.barcode or '',
                 'default_order_price': float(p.default_order_price),
                 'default_selling_price': float(p.default_selling_price)}
                for p in v]
            for k, v in products_by_category.items()
        }),
        'location': location,
    })
    
    return render(request, "verticals/phones/accessories_stock_in.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def accessories_fast_sell(request):
    """
    Fast sell page for accessories.
    Allows quick barcode scan or manual product selection for instant sales.
    
    FIXED: Apply location filter BEFORE slicing to avoid "Cannot filter a query once a slice has been taken" error.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    # If no location, use default
    if not location:
        location = Location.default_for(business)
        if not location:
            location = Location.ensure_default_for_business(business)
    
    # Get recent sales for feedback
    # CRITICAL FIX: Filter FIRST, then slice (not the other way around)
    recent_sales = AccessoryStockLog.objects.filter(
        business=business,
        action='SALE'
    ).select_related('product', 'by_user')
    
    # Apply location filter BEFORE slicing
    if location:
        recent_sales = recent_sales.filter(location=location)
    
    # Now slice after all filtering is complete
    recent_sales = recent_sales.order_by('-created_at')[:10]
    
    ctx.update({
        'hero_title': 'Fast Sell Accessories',
        'hero_blurb': 'Scan barcode or search to sell accessories instantly.',
        'page_title': 'Fast Sell Accessories',
        'recent_sales': recent_sales,
        'location': location,
    })
    
    return render(request, "verticals/phones/accessories_fast_sell.html", ctx)


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def accessories_lookup_api(request):
    """
    API: Lookup accessory by barcode or search term.
    Returns product details and current stock.
    """
    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")
    
    barcode = request.GET.get('barcode', '').strip()
    search = request.GET.get('search', '').strip()
    
    if not barcode and not search:
        return JsonResponse({'error': 'Barcode or search term required'}, status=400)
    
    # Lookup by barcode first
    product = None
    if barcode:
        normalized = normalize_barcode(barcode)
        product = AccessoryProduct.objects.filter(
            business=business,
            barcode=normalized,
            is_active=True
        ).first()
    
    # Fallback to search by name
    if not product and search:
        product = AccessoryProduct.objects.filter(
            business=business,
            name__icontains=search,
            is_active=True
        ).first()
    
    if not product:
        return JsonResponse({'error': 'Product not found'}, status=404)
    
    # Get stock for this product at current location
    stock = AccessoryStock.objects.filter(
        business=business,
        location=location,
        product=product
    ).first()
    
    stock_qty = stock.qty_on_hand if stock else 0
    
    return JsonResponse({
        'success': True,
        'product': {
            'id': product.id,
            'name': product.name,
            'category': product.get_category_display(),
            'sku': product.sku,
            'barcode': product.barcode or '',
            'default_order_price': float(product.default_order_price),
            'default_selling_price': float(product.default_selling_price),
            'stock_qty': stock_qty,
        }
    })


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def accessories_stock_in_api(request):
    """
    API: Stock in accessories (create product if needed, add stock).
    
    POST params:
    - product_id (optional, if existing)
    - name (required if new product)
    - category (required if new product)
    - brand (optional)
    - barcode (optional)
    - order_price (required)
    - selling_price (required)
    - quantity (required)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")
    
    if not location:
        location = Location.default_for(business)
        if not location:
            location = Location.ensure_default_for_business(business)
    
    try:
        # Parse input
        product_id = request.POST.get('product_id', '').strip()
        name = request.POST.get('name', '').strip()
        category = request.POST.get('category', '').strip()
        brand = request.POST.get('brand', '').strip()
        barcode = request.POST.get('barcode', '').strip()
        order_price = Decimal(request.POST.get('order_price', '0'))
        selling_price = Decimal(request.POST.get('selling_price', '0'))
        quantity = int(request.POST.get('quantity', '0'))
        
        if quantity <= 0:
            return JsonResponse({'error': 'Quantity must be positive'}, status=400)
        
        with transaction.atomic():
            # Get or create product
            if product_id:
                product = get_object_or_404(AccessoryProduct, id=product_id, business=business)
            else:
                # Create new product
                if not name or not category:
                    return JsonResponse({'error': 'Name and category required for new product'}, status=400)
                
                product = AccessoryProduct.objects.create(
                    business=business,
                    name=name,
                    category=category,
                    brand=brand,
                    barcode=barcode,
                    default_order_price=order_price,
                    default_selling_price=selling_price,
                )
            
            # Get or create stock entry
            stock = AccessoryStock.get_or_create_stock(business, location, product)
            
            # Add stock
            stock.add_stock(quantity, order_price)
            
            # Log the stock-in
            AccessoryStockLog.objects.create(
                business=business,
                product=product,
                location=location,
                action='STOCK_IN',
                quantity=quantity,
                unit_cost=order_price,
                by_user=request.user,
                notes=f"Stock in via wizard: {quantity} units @ MK {order_price}"
            )
        
        return JsonResponse({
            'success': True,
            'message': f'Added {quantity} x {product.name} to stock',
            'product': {
                'id': product.id,
                'name': product.name,
                'stock_qty': stock.qty_on_hand,
            }
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def accessories_normal_sell(request):
    """
    Normal sell page for accessories (manual selection, NOT fast sell).
    Allows picking product from category → product list, set quantity and price.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    # If no location, use default
    if not location:
        location = Location.default_for(business)
        if not location:
            location = Location.ensure_default_for_business(business)
    
    # Get all categories for selection
    categories = [
        {'value': cat[0], 'label': cat[1], 'icon': _get_category_icon(cat[0])}
        for cat in AccessoryCategory.choices
    ]
    
    # Get all products with current stock
    products = AccessoryProduct.objects.filter(
        business=business,
        is_active=True
    ).order_by('category', 'name')
    
    # Annotate with stock quantity at current location
    products_with_stock = []
    for product in products:
        stock = AccessoryStock.objects.filter(
            business=business,
            location=location,
            product=product
        ).first()
        
        stock_qty = stock.qty_on_hand if stock else 0
        
        products_with_stock.append({
            'id': product.id,
            'name': product.name,
            'category': product.category,
            'category_label': product.get_category_display(),
            'default_selling_price': float(product.default_selling_price) if product.default_selling_price else 0.0,
            'stock_qty': stock_qty,
        })
    
    ctx.update({
        'hero_title': 'Sell Accessories',
        'hero_blurb': 'Select products and quantities to sell',
        'page_title': 'Sell Accessories',
        'categories': categories,
        'products': json.dumps(products_with_stock),
        'location': location,
    })
    
    return render(request, "verticals/phones/accessories_normal_sell.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def accessories_sell_api(request):
    """
    API: Sell accessories (both fast sell and normal sell).
    
    POST params:
    - product_id (required)
    - quantity (required, default=1)
    - selling_price (optional, uses product default if not provided)
    - payment_method (optional, default=CASH)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")
    
    if not location:
        location = Location.default_for(business)
        if not location:
            location = Location.ensure_default_for_business(business)
    
    try:
        # Parse input
        product_id = request.POST.get('product_id', '').strip()
        quantity = int(request.POST.get('quantity', '1'))
        selling_price_str = request.POST.get('selling_price', '').strip()
        payment_method = request.POST.get('payment_method', 'CASH')
        
        if not product_id:
            return JsonResponse({'error': 'Product ID required'}, status=400)
        if quantity <= 0:
            return JsonResponse({'error': 'Quantity must be positive'}, status=400)
        
        with transaction.atomic():
            # Get product
            product = get_object_or_404(AccessoryProduct, id=product_id, business=business)
            
            # Determine selling price (use custom if provided, otherwise product default)
            if selling_price_str:
                try:
                    selling_price = Decimal(selling_price_str)
                    if selling_price <= 0:
                        return JsonResponse({'error': 'Selling price must be positive'}, status=400)
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'Invalid selling price'}, status=400)
            else:
                selling_price = product.default_selling_price
            
            # Get stock entry
            stock = AccessoryStock.objects.filter(
                business=business,
                location=location,
                product=product
            ).first()
            
            if not stock or stock.qty_on_hand < quantity:
                available = stock.qty_on_hand if stock else 0
                return JsonResponse({
                    'error': f'Insufficient stock: requested {quantity}, available {available}'
                }, status=400)
            
            # Remove stock
            stock.remove_stock(quantity)
            
            # Calculate revenue
            total_revenue = Decimal(quantity) * selling_price
            
            # Log the sale
            AccessoryStockLog.objects.create(
                business=business,
                product=product,
                location=location,
                action='SALE',
                quantity=-quantity,  # Negative for sales
                unit_cost=stock.avg_cost,
                by_user=request.user,
                notes=f"Sold: {quantity} x {product.name} @ MK {selling_price} ({payment_method})"
            )
        
        return JsonResponse({
            'success': True,
            'message': f'SOLD: {quantity} x {product.name} @ MK {selling_price}',
            'product': {
                'id': product.id,
                'name': product.name,
                'stock_remaining': stock.qty_on_hand,
            },
            'sale': {
                'quantity': quantity,
                'unit_price': float(selling_price),
                'total': float(total_revenue),
                'payment_method': payment_method,
            }
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ==============================================================================
# HELPERS
# ==============================================================================

def _get_category_icon(category: str) -> str:
    """Get Bootstrap icon for category."""
    icons = {
        'powerbank': 'bi-battery-charging',
        'charger': 'bi-plug',
        'cable': 'bi-ethernet',
        'battery': 'bi-battery-half',
        'headset': 'bi-headphones',
        'speaker': 'bi-speaker',
        'other': 'bi-box',
    }
    return icons.get(category, 'bi-box')


# Export views
__all__ = [
    'accessories_dashboard',
    'accessories_stock_in',
    'accessories_fast_sell',
    'accessories_normal_sell',  # NEW: Manual sell page
    'accessories_lookup_api',
    'accessories_stock_in_api',
    'accessories_sell_api',
]

