# inventory/verticals/cement.py
"""
Cement / Hardware Vertical - Building materials and hardware store
"""
from __future__ import annotations

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from tenants.utils import require_business


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def dashboard(request):
    """Cement/Hardware dashboard with KPIs"""
    business = get_active_business(request)
    
    # Get all cement/hardware products
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CEMENT,
        is_active=True
    )
    
    # Calculate KPIs
    total_products = products.count()
    total_stock_value = sum(
        (p.quantity_in_stock or 0) * (p.cost_price or Decimal('0'))
        for p in products
    )
    items_in_stock = sum(p.quantity_in_stock or 0 for p in products)
    
    # Sales data
    total_revenue = Decimal('0')
    total_profit = Decimal('0')
    total_costs = total_stock_value
    sold_today_count = 0
    
    # Low stock items (less than 5 bags/units)
    low_stock_items = products.filter(quantity_in_stock__lt=5, quantity_in_stock__gt=0).order_by('quantity_in_stock')[:10]
    
    # Recent stock-ins
    recent_products = products.order_by('-id')[:10]
    
    context = {
        'business': business,
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'total_costs': total_costs,
        'stock_value': total_stock_value,
        'sold_today': sold_today_count,
        'items_in_stock': items_in_stock,
        'total_products': total_products,
        'low_stock_items': low_stock_items,
        'recent_products': recent_products,
        'active_tab': 'dashboard',
    }
    
    return render(request, 'verticals/cement/dashboard.html', context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def stock_list(request):
    """List all cement/hardware products"""
    business = get_active_business(request)
    
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CEMENT,
        is_active=True
    ).order_by('name')
    
    context = {
        'business': business,
        'products': products,
        'active_tab': 'stock',
    }
    
    return render(request, 'verticals/cement/stock_list.html', context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def stock_in(request):
    """Add stock for cement/hardware products"""
    business = get_active_business(request)
    
    if request.method == 'POST':
        try:
            product_name = request.POST.get('product_name', '').strip()
            category = request.POST.get('category', 'cement').strip()
            quantity = int(request.POST.get('quantity', 0))
            cost_price = Decimal(request.POST.get('cost_price', '0'))
            selling_price = Decimal(request.POST.get('selling_price', '0'))
            unit = request.POST.get('unit', 'bag').strip()
            
            if not product_name:
                messages.error(request, "Product name is required")
                return redirect('cement:stock_in')
            
            if quantity <= 0:
                messages.error(request, "Quantity must be greater than 0")
                return redirect('cement:stock_in')
            
            with transaction.atomic():
                # Get or create product
                product, created = MerchProduct.objects.get_or_create(
                    business=business,
                    name=product_name,
                    kind=BusinessKind.CEMENT,
                    defaults={
                        'category': category,
                        'cost_price': cost_price,
                        'selling_price': selling_price,
                        'quantity_in_stock': quantity,
                        'base_unit': unit,
                        'is_active': True,
                        'track_inventory': True,
                    }
                )
                
                if not created:
                    # Update existing product
                    product.quantity_in_stock += quantity
                    product.cost_price = cost_price
                    product.selling_price = selling_price
                    product.save(update_fields=['quantity_in_stock', 'cost_price', 'selling_price'])
                
                messages.success(request, f"✅ Added {quantity} {unit} of {product_name} to stock")
                return redirect('cement:stock_in')
        
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect('cement:stock_in')
        except Exception as e:
            messages.error(request, f"Error adding stock: {e}")
            return redirect('cement:stock_in')
    
    # GET: Show form
    categories = [
        ('cement', 'Cement'),
        ('sand', 'Sand & Aggregates'),
        ('bricks', 'Bricks & Blocks'),
        ('steel', 'Steel & Iron'),
        ('timber', 'Timber & Wood'),
        ('paint', 'Paint & Coatings'),
        ('tools', 'Tools'),
        ('plumbing', 'Plumbing Supplies'),
        ('electrical', 'Electrical Supplies'),
        ('other', 'Other'),
    ]
    
    units = [
        ('bag', 'Bag'),
        ('ton', 'Ton'),
        ('kg', 'Kilograms'),
        ('pcs', 'Pieces'),
        ('bundle', 'Bundle'),
        ('roll', 'Roll'),
        ('meter', 'Meter'),
        ('liter', 'Liter'),
    ]
    
    context = {
        'business': business,
        'categories': categories,
        'units': units,
        'active_tab': 'stock_in',
    }
    
    return render(request, 'verticals/cement/stock_in.html', context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def sell(request):
    """Sell cement/hardware products"""
    business = get_active_business(request)
    
    if request.method == 'POST':
        try:
            product_id = int(request.POST.get('product_id', 0))
            quantity = int(request.POST.get('quantity', 0))
            
            product = MerchProduct.objects.select_for_update().get(
                pk=product_id,
                business=business,
                kind=BusinessKind.CEMENT,
                is_active=True
            )
            
            if quantity <= 0:
                messages.error(request, "Quantity must be greater than 0")
                return redirect('cement:sell')
            
            if product.quantity_in_stock < quantity:
                messages.error(
                    request,
                    f"Insufficient stock. Available: {product.quantity_in_stock}, Requested: {quantity}"
                )
                return redirect('cement:sell')
            
            with transaction.atomic():
                # Calculate totals
                total_cost = (product.cost_price or Decimal('0')) * quantity
                total_revenue = (product.selling_price or Decimal('0')) * quantity
                profit = total_revenue - total_cost
                
                # Decrease stock
                product.quantity_in_stock -= quantity
                product.save(update_fields=['quantity_in_stock'])
                
                # TODO: Create sale record for proper tracking
                # For now, just update stock
                
                messages.success(
                    request,
                    f"✅ Sold {quantity} {product.base_unit} of {product.name}. "
                    f"Revenue: MK {total_revenue:,.2f}, Profit: MK {profit:,.2f}"
                )
                return redirect('cement:sell')
        
        except MerchProduct.DoesNotExist:
            messages.error(request, "Product not found")
            return redirect('cement:sell')
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect('cement:sell')
        except Exception as e:
            messages.error(request, f"Error processing sale: {e}")
            return redirect('cement:sell')
    
    # GET: Show products
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CEMENT,
        is_active=True,
        quantity_in_stock__gt=0
    ).order_by('name')
    
    context = {
        'business': business,
        'products': products,
        'active_tab': 'sell',
    }
    
    return render(request, 'verticals/cement/sell.html', context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def analytics(request):
    """Basic analytics for cement/hardware"""
    business = get_active_business(request)
    
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CEMENT,
        is_active=True
    )
    
    # Basic stats
    total_products = products.count()
    total_stock_value = sum(
        (p.quantity_in_stock or 0) * (p.cost_price or Decimal('0'))
        for p in products
    )
    
    context = {
        'business': business,
        'total_products': total_products,
        'total_stock_value': total_stock_value,
        'active_tab': 'analytics',
    }
    
    return render(request, 'verticals/cement/analytics.html', context)

