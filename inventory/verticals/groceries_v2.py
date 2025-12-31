# inventory/verticals/groceries_v2.py
"""
GROCERIES V2 - Stupid Simple Retail + Wholesale Flow for Malawi
=================================================================

Design Goals:
- Faster than writing in a notebook
- Mobile-first, one-tap actions
- Search + Top Items + Modals
- Barcode optional always
- Retail + Wholesale in one flow

Architecture:
- Service layer enforcement (atomic + select_for_update)
- Multi-tenant security (business + location scoping)
- Vertical gating (GROCERIES only)
- Zero regressions (old routes preserved)
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, F, Count
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.groceries_config import (
    CATEGORY_GROUPS,
    SALE_MODE_RETAIL,
    SALE_MODE_WHOLESALE,
    PAYMENT_METHODS,
    to_base_units,
    get_unit_price,
    get_category_by_key,
    get_default_units_for_category,
)
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.models_verticals import GrocerySale
from inventory.services.groceries_service import (
    stock_in_groceries,
    sell_groceries,
    adjust_groceries_stock,
    lookup_product_by_barcode,
    get_groceries_product,
)
from tenants.models import Location
from tenants.utils import require_business


# ==============================================================================
# DASHBOARD (Wow but not clutter)
# ==============================================================================

@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def dashboard_v2(request):
    """
    Groceries V2 Dashboard - Clean, fast, actionable
    
    Top 3 big cards: Add Product, Stock In, Sell
    KPIs: Today sales, revenue, profit, items sold
    Quick views: Low stock, Top sellers, Dead stock
    """
    business = get_active_business(request)
    location = Location.default_for(business)
    
    # Get today's date
    today = timezone.now().date()
    
    # Products query (active groceries only)
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.GROCERY,
        is_active=True,
    )
    
    # Today's sales
    today_sales = GrocerySale.objects.filter(
        business=business,
        sold_at__date=today,
    )
    
    # KPIs
    total_products = products.count()
    items_in_stock = products.aggregate(total=Sum('quantity_in_stock'))['total'] or 0
    
    sales_count = today_sales.count()
    revenue_today = today_sales.aggregate(total=Sum('total_price'))['total'] or Decimal('0')
    cost_today = today_sales.aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
    profit_today = revenue_today - cost_today
    items_sold_today = today_sales.aggregate(total=Sum('quantity'))['total'] or 0
    
    # Stock value
    stock_value = sum(
        (p.quantity_in_stock or 0) * (p.cost_price or Decimal('0'))
        for p in products
    )
    
    # Low stock (< 10 units)
    low_stock_count = products.filter(quantity_in_stock__lt=10, quantity_in_stock__gt=0).count()
    low_stock_items = products.filter(
        quantity_in_stock__lt=10,
        quantity_in_stock__gt=0
    ).order_by('quantity_in_stock')[:5]
    
    # Top sellers (last 7 days)
    seven_days_ago = timezone.now() - timezone.timedelta(days=7)
    top_sellers = GrocerySale.objects.filter(
        business=business,
        sold_at__gte=seven_days_ago,
    ).values('product__name').annotate(
        total_qty=Sum('quantity'),
        total_revenue=Sum('total_price'),
    ).order_by('-total_qty')[:5]
    
    # Dead stock (no sales in 30 days)
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    sold_product_ids = GrocerySale.objects.filter(
        business=business,
        sold_at__gte=thirty_days_ago,
    ).values_list('product_id', flat=True).distinct()
    
    dead_stock_count = products.filter(
        quantity_in_stock__gt=0
    ).exclude(id__in=sold_product_ids).count()
    
    # Gamification: Sales streak (days with sales)
    streak_days = 0
    check_date = today
    for _ in range(30):  # Check last 30 days
        if GrocerySale.objects.filter(
            business=business,
            sold_at__date=check_date,
        ).exists():
            streak_days += 1
            check_date -= timezone.timedelta(days=1)
        else:
            break
    
    context = {
        'business': business,
        'location': location,
        # KPIs
        'total_products': total_products,
        'items_in_stock': items_in_stock,
        'stock_value': stock_value,
        'sales_count': sales_count,
        'revenue_today': revenue_today,
        'profit_today': profit_today,
        'items_sold_today': items_sold_today,
        # Alerts
        'low_stock_count': low_stock_count,
        'low_stock_items': low_stock_items,
        'dead_stock_count': dead_stock_count,
        # Top performers
        'top_sellers': top_sellers,
        # Gamification
        'streak_days': streak_days,
        'active_tab': 'dashboard',
    }
    
    return render(request, 'verticals/groceries_v2/dashboard.html', context)


# ==============================================================================
# ADD PRODUCT (2-step quick add, 30 seconds)
# ==============================================================================

@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def product_add_v2(request):
    """
    Add Product - 2-step wizard:
    1. Choose category tile
    2. Fill minimal form (name, cost, price, optional wholesale)
    
    After save: Add another / Stock in now / Sell now
    """
    business = get_active_business(request)
    step = request.GET.get('step', '1')
    
    # POST: Save product
    if request.method == 'POST':
        try:
            category_key = request.POST.get('category_key', '').strip()
            name = request.POST.get('name', '').strip()
            brand = request.POST.get('brand', '').strip()
            cost_price_str = request.POST.get('cost_price', '').strip()
            selling_price_str = request.POST.get('selling_price', '').strip()
            
            # Validate required fields
            if not name:
                messages.error(request, "Product name is required")
                return redirect(f'groceries_v2:product_add?step=2&category={category_key}')
            
            if not cost_price_str or not selling_price_str:
                messages.error(request, "Cost price and selling price are required")
                return redirect(f'groceries_v2:product_add?step=2&category={category_key}')
            
            try:
                cost_price = Decimal(cost_price_str)
                selling_price = Decimal(selling_price_str)
                if cost_price < 0 or selling_price < 0:
                    raise ValueError("Prices cannot be negative")
            except (ValueError, Exception) as e:
                messages.error(request, f"Invalid price: {e}")
                return redirect(f'groceries_v2:product_add?step=2&category={category_key}')
            
            # Get default units for category
            defaults = get_default_units_for_category(category_key)
            base_unit = defaults['base_unit']
            
            # Optional: Wholesale packaging
            enable_wholesale = request.POST.get('enable_wholesale') == 'on'
            pack_label = None
            pack_size = None
            wholesale_price = None
            
            if enable_wholesale:
                pack_label = request.POST.get('pack_label', '').strip() or defaults['pack_label']
                pack_size_str = request.POST.get('pack_size', '').strip()
                wholesale_price_str = request.POST.get('wholesale_price', '').strip()
                
                if pack_size_str:
                    try:
                        pack_size = int(pack_size_str)
                        if pack_size <= 0:
                            raise ValueError("Pack size must be positive")
                    except ValueError:
                        pack_size = defaults['pack_size']
                else:
                    pack_size = defaults['pack_size']
                
                if wholesale_price_str:
                    try:
                        wholesale_price = Decimal(wholesale_price_str)
                        if wholesale_price < 0:
                            raise ValueError("Wholesale price cannot be negative")
                    except (ValueError, Exception):
                        wholesale_price = None
            
            # Optional: Barcode
            barcode = request.POST.get('barcode', '').strip() or None
            
            # Optional: Initial stock
            initial_stock_str = request.POST.get('initial_stock', '0').strip()
            try:
                initial_stock = int(initial_stock_str)
                if initial_stock < 0:
                    initial_stock = 0
            except ValueError:
                initial_stock = 0
            
            # Create product
            with transaction.atomic():
                # Build full name with brand if provided
                full_name = f"{brand} {name}" if brand else name
                
                product, created = MerchProduct.objects.get_or_create(
                    business=business,
                    name=full_name,
                    kind=BusinessKind.GROCERY,
                    defaults={
                        'category_group': category_key,
                        'base_unit': base_unit,
                        'cost_price': cost_price,
                        'selling_price': selling_price,
                        'pack_label': pack_label,
                        'bottles_per_crate': pack_size,  # pack_size alias
                        'wholesale_price_per_pack': wholesale_price,
                        'barcode': barcode,
                        'quantity_in_stock': initial_stock,
                        'is_active': True,
                        'track_inventory': True,
                        'spec_label': '',
                    }
                )
                
                if not created:
                    # Product exists - update prices and add stock
                    product.cost_price = cost_price
                    product.selling_price = selling_price
                    if enable_wholesale:
                        product.pack_label = pack_label
                        product.bottles_per_crate = pack_size
                        product.wholesale_price_per_pack = wholesale_price
                    product.quantity_in_stock += initial_stock
                    product.save()
                    
                    messages.info(
                        request,
                        f"Product '{full_name}' already exists. Updated prices and added {initial_stock} units to stock."
                    )
                else:
                    messages.success(
                        request,
                        f"✅ Product '{full_name}' created successfully!"
                    )
            
            # Next action
            next_action = request.POST.get('next_action', 'list')
            if next_action == 'add_another':
                return redirect('groceries_v2:product_add')
            elif next_action == 'stock_in':
                return redirect('groceries_v2:stock_in')
            elif next_action == 'sell':
                return redirect('groceries_v2:sell')
            else:
                return redirect('groceries_v2:dashboard')
        
        except Exception as e:
            messages.error(request, f"Error creating product: {e}")
            return redirect('groceries_v2:product_add')
    
    # GET: Show wizard
    if step == '1':
        # Step 1: Choose category tile
        context = {
            'business': business,
            'categories': CATEGORY_GROUPS,
            'step': 1,
            'active_tab': 'products',
        }
        return render(request, 'verticals/groceries_v2/product_add.html', context)
    
    elif step == '2':
        # Step 2: Fill product form
        category_key = request.GET.get('category', '')
        category = get_category_by_key(category_key)
        
        if not category:
            messages.error(request, "Invalid category")
            return redirect('groceries_v2:product_add')
        
        defaults = get_default_units_for_category(category_key)
        
        context = {
            'business': business,
            'category': category,
            'category_key': category_key,
            'defaults': defaults,
            'step': 2,
            'active_tab': 'products',
        }
        return render(request, 'verticals/groceries_v2/product_add.html', context)
    
    else:
        return redirect('groceries_v2:product_add?step=1')


# ==============================================================================
# STOCK IN (Search + Top Items + Qty Modal)
# ==============================================================================

@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def stock_in_v2(request):
    """
    Stock In - Fast flow:
    - Search box autofocus
    - Top items grid (most stocked) for one-tap
    - Tap product -> Qty modal (with unit selector)
    - Optional price update
    """
    business = get_active_business(request)
    location = Location.default_for(business)
    
    # Search query
    q = request.GET.get('q', '').strip()
    
    # Get products
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.GROCERY,
        is_active=True,
    )
    
    if q:
        products = products.filter(
            Q(name__icontains=q) |
            Q(barcode__iexact=q) |
            Q(sku__icontains=q)
        )
    
    products = products.order_by('name')
    
    # Top items (most stocked in last 7 days)
    # For simplicity, show recently updated products
    top_items = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.GROCERY,
        is_active=True,
    ).order_by('-id')[:12]
    
    context = {
        'business': business,
        'location': location,
        'products': products[:50],  # Limit to 50 for performance
        'top_items': top_items,
        'query': q,
        'active_tab': 'stock_in',
    }
    
    return render(request, 'verticals/groceries_v2/stock_in.html', context)


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
@require_POST
def stock_in_submit_v2(request):
    """
    AJAX endpoint for stock-in submission.
    Uses service layer for atomicity and validation.
    """
    business = get_active_business(request)
    location = Location.default_for(business)
    
    try:
        product_id = int(request.POST.get('product_id', 0))
        qty = float(request.POST.get('qty', 0))
        unit_label = request.POST.get('unit_label', 'base').strip()
        
        # Optional price updates
        cost_price_str = request.POST.get('cost_price', '').strip()
        selling_price_str = request.POST.get('selling_price', '').strip()
        
        cost_price = Decimal(cost_price_str) if cost_price_str else None
        selling_price = Decimal(selling_price_str) if selling_price_str else None
        
        # Get product
        product = get_groceries_product(business=business, product_id=product_id)
        
        # Stock in via service layer
        result = stock_in_groceries(
            business=business,
            location=location,
            product=product,
            qty=qty,
            unit_label=unit_label,
            cost_price_per_base_unit=cost_price,
            selling_price_per_base_unit=selling_price,
            user=request.user,
        )
        
        return JsonResponse({
            'success': True,
            'message': f"✅ Added {result['qty_added_display']} to stock",
            'new_stock': result['new_stock_level'],
        })
    
    except ValidationError as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=400)
    
    except PermissionDenied as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=403)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f"Error: {e}",
        }, status=500)


# ==============================================================================
# SELL (Search + Top Items + Cart + Checkout)
# ==============================================================================

@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def sell_v2(request):
    """
    Sell - Fast sell flow:
    - Sale mode toggle (Retail / Wholesale)
    - Search autofocus
    - Top items grid (one-tap add to cart)
    - Cart sticky bar with item count + total
    - Checkout modal (2 taps: payment method + confirm)
    """
    business = get_active_business(request)
    location = Location.default_for(business)
    
    # Get/set sale mode from session
    sale_mode = request.GET.get('mode', request.session.get('groceries_sale_mode', SALE_MODE_RETAIL))
    if sale_mode not in [SALE_MODE_RETAIL, SALE_MODE_WHOLESALE]:
        sale_mode = SALE_MODE_RETAIL
    request.session['groceries_sale_mode'] = sale_mode
    
    # Search query
    q = request.GET.get('q', '').strip()
    
    # Get products (in stock only)
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.GROCERY,
        is_active=True,
        quantity_in_stock__gt=0,
    )
    
    if q:
        products = products.filter(
            Q(name__icontains=q) |
            Q(barcode__iexact=q) |
            Q(sku__icontains=q)
        )
    
    products = products.order_by('name')
    
    # Top items (best sellers last 7 days)
    seven_days_ago = timezone.now() - timezone.timedelta(days=7)
    top_product_ids = GrocerySale.objects.filter(
        business=business,
        sold_at__gte=seven_days_ago,
    ).values('product_id').annotate(
        total_qty=Sum('quantity')
    ).order_by('-total_qty').values_list('product_id', flat=True)[:12]
    
    top_items = MerchProduct.objects.filter(
        id__in=top_product_ids,
        is_active=True,
        quantity_in_stock__gt=0,
    )
    
    # If no sales history, show recently added products
    if not top_items.exists():
        top_items = MerchProduct.objects.filter(
            business=business,
            kind=BusinessKind.GROCERY,
            is_active=True,
            quantity_in_stock__gt=0,
        ).order_by('-id')[:12]
    
    context = {
        'business': business,
        'location': location,
        'products': products[:50],
        'top_items': top_items,
        'query': q,
        'sale_mode': sale_mode,
        'payment_methods': PAYMENT_METHODS,
        'active_tab': 'sell',
    }
    
    return render(request, 'verticals/groceries_v2/sell.html', context)


@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
@require_POST
def sell_submit_v2(request):
    """
    AJAX endpoint for checkout submission.
    Processes cart and creates sale via service layer.
    """
    business = get_active_business(request)
    location = Location.default_for(business)
    
    try:
        # Parse cart from JSON
        cart_json = request.POST.get('cart', '[]')
        cart = json.loads(cart_json)
        
        if not cart:
            return JsonResponse({
                'success': False,
                'error': 'Cart is empty',
            }, status=400)
        
        # Parse cart lines
        cart_lines = []
        for item in cart:
            cart_lines.append({
                'product_id': int(item['product_id']),
                'qty': float(item['qty']),
                'unit_label': item.get('unit_label', 'base'),
                'price_override': Decimal(str(item['price_override'])) if item.get('price_override') else None,
            })
        
        # Get sale parameters
        sale_mode = request.POST.get('sale_mode', SALE_MODE_RETAIL)
        payment_method = request.POST.get('payment_method', 'CASH')
        customer_name = request.POST.get('customer_name', '').strip()
        notes = request.POST.get('notes', '').strip()
        
        # Sell via service layer
        result = sell_groceries(
            business=business,
            location=location,
            cart_lines=cart_lines,
            sale_mode=sale_mode,
            payment_method=payment_method,
            user=request.user,
            customer_name=customer_name,
            notes=notes,
            allow_price_override=True,
        )
        
        return JsonResponse({
            'success': True,
            'message': f"✅ Sale completed! Revenue: MK {result['total_revenue']:,.2f}, Profit: MK {result['total_profit']:,.2f}",
            'total_revenue': float(result['total_revenue']),
            'total_profit': float(result['total_profit']),
            'items_sold': result['items_sold'],
        })
    
    except ValidationError as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=400)
    
    except PermissionDenied as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=403)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f"Error: {e}",
        }, status=500)


# ==============================================================================
# BARCODE FAST SCAN (Optional secondary flow)
# ==============================================================================

@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def scan_v2(request, scan_value):
    """
    Optional barcode fast scan.
    If barcode found -> add to cart instantly
    If not found -> show "Quick Add Product" modal
    """
    business = get_active_business(request)
    
    # Lookup product by barcode
    product = lookup_product_by_barcode(business=business, barcode=scan_value)
    
    if product:
        # Product found - redirect to sell page with product added to cart
        # (Cart is managed client-side, so just redirect)
        messages.success(request, f"Found: {product.name}")
        return redirect(f'/verticals/groceries/v2/sell/?q={product.name}')
    else:
        # Product not found - redirect to add product
        messages.info(request, f"Barcode {scan_value} not found. Add a new product?")
        return redirect(f'/verticals/groceries/v2/products/add/?step=2&barcode={scan_value}')


# ==============================================================================
# PRODUCT LIST (View all products)
# ==============================================================================

@login_required
@require_business
@require_business_kind(BusinessKind.GROCERY)
def product_list_v2(request):
    """
    View all products with filtering and pagination.
    """
    business = get_active_business(request)
    
    # Filters
    q = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '').strip()
    
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.GROCERY,
        is_active=True,
    )
    
    if q:
        products = products.filter(
            Q(name__icontains=q) |
            Q(barcode__iexact=q) |
            Q(sku__icontains=q)
        )
    
    if category_filter:
        products = products.filter(category_group=category_filter)
    
    products = products.order_by('name')
    
    # Pagination
    paginator = Paginator(products, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'business': business,
        'page_obj': page_obj,
        'products': page_obj,
        'query': q,
        'category_filter': category_filter,
        'categories': CATEGORY_GROUPS,
        'active_tab': 'products',
    }
    
    return render(request, 'verticals/groceries_v2/product_list.html', context)

