# inventory/verticals/cement.py
"""
Cement / Hardware Vertical - Building materials and hardware store
"""
from __future__ import annotations

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.models_verticals import CementSale, CementCost
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
    
    # Sales data (from actual sales)
    today = timezone.now().date()
    today_sales = CementSale.objects.filter(
        business=business,
        sold_at__date=today
    )
    total_revenue = sum(sale.total_price for sale in today_sales)
    total_profit = sum(sale.profit for sale in today_sales)
    sold_today_count = today_sales.count()
    
    # Costs data
    today_costs = CementCost.objects.filter(
        business=business,
        cost_date=today
    )
    total_costs = sum(cost.amount for cost in today_costs) + total_stock_value
    
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
    """Gamified stock-in flow for cement: Brand → Product → Quantity → Pricing"""
    business = get_active_business(request)
    
    # Step tracking
    step = request.GET.get('step', '1')
    
    if request.method == 'POST':
        try:
            # Step 1: Brand selection
            if step == '1':
                brand = request.POST.get('brand', '').strip()
                if not brand:
                    messages.error(request, "Please select a brand")
                    return redirect('cement:stock_in?step=1')
                # Store brand in session for next step
                request.session['cement_stock_in_brand'] = brand
                return redirect('cement:stock_in?step=2')
            
            # Step 2: Product selection/creation
            elif step == '2':
                brand = request.session.get('cement_stock_in_brand', '')
                product_name = request.POST.get('product_name', '').strip()
                product_id = request.POST.get('product_id', '').strip()
                
                if product_id:
                    # Existing product selected
                    request.session['cement_stock_in_product_id'] = int(product_id)
                elif product_name:
                    # New product name entered
                    request.session['cement_stock_in_product_name'] = product_name
                else:
                    messages.error(request, "Please select or enter a product")
                    return redirect('cement:stock_in?step=2')
                
                request.session['cement_stock_in_brand'] = brand
                return redirect('cement:stock_in?step=3')
            
            # Step 3: Quantity and pricing
            elif step == '3':
                brand = request.session.get('cement_stock_in_brand', '')
                product_id = request.session.get('cement_stock_in_product_id')
                product_name = request.session.get('cement_stock_in_product_name', '')
                
                quantity = int(request.POST.get('quantity', 0))
                cost_price = Decimal(request.POST.get('cost_price', '0'))
                selling_price = Decimal(request.POST.get('selling_price', '0'))
                unit = request.POST.get('unit', 'bag').strip()
                
                if quantity <= 0:
                    messages.error(request, "Quantity must be greater than 0")
                    return redirect('cement:stock_in?step=3')
                
                if cost_price <= 0 or selling_price <= 0:
                    messages.error(request, "Cost and selling prices must be greater than 0")
                    return redirect('cement:stock_in?step=3')
                
                with transaction.atomic():
                    if product_id:
                        # Update existing product
                        product = MerchProduct.objects.get(
                            pk=product_id,
                            business=business,
                            kind=BusinessKind.CEMENT
                        )
                        product.quantity_in_stock += quantity
                        product.cost_price = cost_price
                        product.selling_price = selling_price
                        product.save(update_fields=['quantity_in_stock', 'cost_price', 'selling_price'])
                        final_name = product.name
                    else:
                        # Create new product
                        final_name = f"{brand} - {product_name}" if brand else product_name
                        product, created = MerchProduct.objects.get_or_create(
                            business=business,
                            name=final_name,
                            kind=BusinessKind.CEMENT,
                            defaults={
                                'category': 'cement',
                                'spec_label': "",  # CRITICAL: Always set spec_label (prevents NULL constraint)
                                'cost_price': cost_price,
                                'selling_price': selling_price,
                                'quantity_in_stock': quantity,
                                'base_unit': unit,
                                'is_active': True,
                                'track_inventory': True,
                            }
                        )
                        
                        if not created:
                            product.quantity_in_stock += quantity
                            product.cost_price = cost_price
                            product.selling_price = selling_price
                            product.save(update_fields=['quantity_in_stock', 'cost_price', 'selling_price'])
                    
                    messages.success(request, f"✅ Added {quantity} {unit} of {final_name} to stock")
                    
                    # Clear session
                    for key in ['cement_stock_in_brand', 'cement_stock_in_product_id', 'cement_stock_in_product_name']:
                        if key in request.session:
                            del request.session[key]
                    
                    return redirect('cement:stock_in')
        
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect(f'cement:stock_in?step={step}')
        except Exception as e:
            messages.error(request, f"Error adding stock: {e}")
            return redirect(f'cement:stock_in?step={step}')
    
    # GET: Show appropriate step
    # Seed brands: Akshar and Dangote
    seed_brands = [
        {'key': 'akshar', 'name': 'Akshar', 'icon': '🏗️'},
        {'key': 'dangote', 'name': 'Dangote', 'icon': '🏭'},
    ]
    
    # Get existing brands from products
    existing_brands = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CEMENT,
        is_active=True
    ).values_list('name', flat=True)
    
    # Extract unique brands (first word before dash)
    brand_set = set()
    for name in existing_brands:
        if ' - ' in name:
            brand_set.add(name.split(' - ')[0])
    
    all_brands = seed_brands + [{'key': b.lower(), 'name': b, 'icon': '📦'} for b in brand_set if b.lower() not in ['akshar', 'dangote']]
    
    context = {
        'business': business,
        'step': step,
        'brands': all_brands,
        'active_tab': 'stock_in',
    }
    
    # Step 2: Show products for selected brand
    if step == '2':
        brand = request.session.get('cement_stock_in_brand', '')
        if brand:
            # Get existing products for this brand
            products = MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.CEMENT,
                is_active=True,
                name__istartswith=brand
            ).order_by('name')
            context['selected_brand'] = brand
            context['products'] = products
    
    # Step 3: Show quantity/pricing form
    elif step == '3':
        brand = request.session.get('cement_stock_in_brand', '')
        product_id = request.session.get('cement_stock_in_product_id')
        product_name = request.session.get('cement_stock_in_product_name', '')
        
        context['selected_brand'] = brand
        if product_id:
            try:
                product = MerchProduct.objects.get(pk=product_id, business=business)
                context['selected_product'] = product
            except MerchProduct.DoesNotExist:
                messages.error(request, "Product not found")
                return redirect('cement:stock_in?step=2')
        else:
            context['new_product_name'] = product_name
        
        units = [
            ('bag', 'Bag (50kg)'),
            ('ton', 'Ton'),
            ('kg', 'Kilograms'),
        ]
        context['units'] = units
    
    return render(request, 'verticals/cement/stock_in.html', context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def sell(request):
    """Gamified sell flow for cement: Brand → Product → Quantity → Payment"""
    business = get_active_business(request)
    
    step = request.GET.get('step', '1')
    
    if request.method == 'POST':
        try:
            # Step 1: Brand selection
            if step == '1':
                brand = request.POST.get('brand', '').strip()
                if not brand:
                    messages.error(request, "Please select a brand")
                    return redirect('cement:sell?step=1')
                request.session['cement_sell_brand'] = brand
                return redirect('cement:sell?step=2')
            
            # Step 2: Product selection
            elif step == '2':
                product_id = int(request.POST.get('product_id', 0))
                if not product_id:
                    messages.error(request, "Please select a product")
                    return redirect('cement:sell?step=2')
                request.session['cement_sell_product_id'] = product_id
                return redirect('cement:sell?step=3')
            
            # Step 3: Quantity and payment
            elif step == '3':
                product_id = request.session.get('cement_sell_product_id')
                if not product_id:
                    messages.error(request, "Please start from Step 1")
                    return redirect('cement:sell')
                
                quantity = int(request.POST.get('quantity', 0))
                payment_method = request.POST.get('payment_method', 'CASH')
                
                if quantity <= 0:
                    messages.error(request, "Quantity must be greater than 0")
                    return redirect('cement:sell?step=3')
                
                product = MerchProduct.objects.select_for_update().get(
                    pk=product_id,
                    business=business,
                    kind=BusinessKind.CEMENT,
                    is_active=True
                )
                
                if product.quantity_in_stock < quantity:
                    messages.error(
                        request,
                        f"Insufficient stock. Available: {product.quantity_in_stock}, Requested: {quantity}"
                    )
                    return redirect('cement:sell?step=3')
                
                with transaction.atomic():
                    # Calculate totals
                    unit_cost = product.cost_price or Decimal('0')
                    unit_price = product.selling_price or Decimal('0')
                    total_cost = unit_cost * quantity
                    total_revenue = unit_price * quantity
                    profit = total_revenue - total_cost
                    
                    # Decrease stock
                    product.quantity_in_stock -= quantity
                    product.save(update_fields=['quantity_in_stock'])
                    
                    # Create sale record
                    CementSale.objects.create(
                        business=business,
                        product=product,
                        quantity=quantity,
                        unit_price=unit_price,
                        total_price=total_revenue,
                        unit_cost=unit_cost,
                        total_cost=total_cost,
                        payment_method=payment_method,
                        sold_by=request.user,
                        notes=request.POST.get('notes', '')
                    )
                    
                    # Clear session
                    for key in ['cement_sell_brand', 'cement_sell_product_id']:
                        if key in request.session:
                            del request.session[key]
                    
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
            return redirect(f'cement:sell?step={step}')
        except Exception as e:
            messages.error(request, f"Error processing sale: {e}")
            return redirect(f'cement:sell?step={step}')
    
    # GET: Show appropriate step
    # Seed brands
    seed_brands = [
        {'key': 'akshar', 'name': 'Akshar', 'icon': '🏗️'},
        {'key': 'dangote', 'name': 'Dangote', 'icon': '🏭'},
    ]
    
    # Get existing brands from products
    existing_brands = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CEMENT,
        is_active=True,
        quantity_in_stock__gt=0
    ).values_list('name', flat=True)
    
    brand_set = set()
    for name in existing_brands:
        if ' - ' in name:
            brand_set.add(name.split(' - ')[0])
    
    all_brands = seed_brands + [{'key': b.lower(), 'name': b, 'icon': '📦'} for b in brand_set if b.lower() not in ['akshar', 'dangote']]
    
    context = {
        'business': business,
        'step': step,
        'brands': all_brands,
        'active_tab': 'sell',
    }
    
    # Step 2: Show products for selected brand
    if step == '2':
        brand = request.session.get('cement_sell_brand', '')
        if brand:
            products = MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.CEMENT,
                is_active=True,
                quantity_in_stock__gt=0,
                name__istartswith=brand
            ).order_by('name')
            context['selected_brand'] = brand
            context['products'] = products
    
    # Step 3: Show quantity/payment form
    elif step == '3':
        product_id = request.session.get('cement_sell_product_id')
        if product_id:
            try:
                product = MerchProduct.objects.get(pk=product_id, business=business)
                context['selected_product'] = product
            except MerchProduct.DoesNotExist:
                messages.error(request, "Product not found")
                return redirect('cement:sell?step=2')
    
    return render(request, 'verticals/cement/sell.html', context)


@login_required
@require_business
@require_business_kind(BusinessKind.CEMENT)
def costs(request):
    """Manage costs for cement business (transport, labor, rent, utilities, etc.)"""
    business = get_active_business(request)
    location = getattr(request.user, 'agent_profile', None)
    if location:
        location = location.location
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0'))
            category = request.POST.get('category', 'other').strip()
            description = request.POST.get('description', '').strip()
            cost_date = request.POST.get('cost_date', '')
            notes = request.POST.get('notes', '').strip()
            
            if amount <= 0:
                messages.error(request, "Amount must be greater than 0")
                return redirect('cement:costs')
            
            if not description:
                messages.error(request, "Description is required")
                return redirect('cement:costs')
            
            from django.utils.dateparse import parse_date
            cost_date_obj = parse_date(cost_date) if cost_date else timezone.now().date()
            
            with transaction.atomic():
                CementCost.objects.create(
                    business=business,
                    location=location,
                    amount=amount,
                    category=category,
                    description=description,
                    cost_date=cost_date_obj,
                    notes=notes,
                    created_by=request.user
                )
                
                messages.success(request, f"✅ Cost entry added: {description} - MK {amount:,.2f}")
                return redirect('cement:costs')
        
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
            return redirect('cement:costs')
        except Exception as e:
            messages.error(request, f"Error adding cost: {e}")
            return redirect('cement:costs')
    
    # GET: Show costs list and form
    costs_list = CementCost.objects.filter(business=business).order_by('-cost_date', '-created_at')[:50]
    
    # Calculate totals by category
    category_totals = CementCost.objects.filter(business=business).values('category').annotate(
        total=Sum('amount')
    ).order_by('-total')
    
    # Total costs
    total_costs = CementCost.objects.filter(business=business).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    categories = [
        ('transport', 'Transport'),
        ('labor', 'Labor'),
        ('rent', 'Rent'),
        ('utilities', 'Utilities'),
        ('other', 'Other'),
    ]
    
    context = {
        'business': business,
        'costs': costs_list,
        'category_totals': category_totals,
        'total_costs': total_costs,
        'categories': categories,
        'active_tab': 'costs',
    }
    
    return render(request, 'verticals/cement/costs.html', context)


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
    
    # Sales stats
    today = timezone.now().date()
    today_sales = CementSale.objects.filter(business=business, sold_at__date=today)
    today_revenue = sum(sale.total_price for sale in today_sales)
    today_profit = sum(sale.profit for sale in today_sales)
    
    # Costs stats
    total_costs = CementCost.objects.filter(business=business).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    context = {
        'business': business,
        'total_products': total_products,
        'total_stock_value': total_stock_value,
        'today_revenue': today_revenue,
        'today_profit': today_profit,
        'total_costs': total_costs,
        'net_profit': today_profit - total_costs,
        'active_tab': 'analytics',
    }
    
    return render(request, 'verticals/cement/analytics.html', context)

