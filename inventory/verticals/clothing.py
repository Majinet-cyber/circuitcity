from __future__ import annotations

from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F, Q
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingSale

from . import base


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def dashboard(request):
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    # Get product metrics (unchanged)
    metrics = base.merch_metrics(business, BusinessKind.CLOTHING)
    
    # ===== DATE FILTER PARAMS =====
    # Use shared date range parser
    date_range_ctx = base.parse_date_range_from_request(request)
    range_param = date_range_ctx['active_range']
    selected_date = date_range_ctx['selected_date']
    date_param = date_range_ctx['date_param']
    
    # ===== SALES METRICS WITH DATE FILTERING =====
    sales_data = base.clothing_sales_metrics(
        business,
        location=location,
        period=range_param,
        date_str=date_param if range_param == 'date' else None
    )
    
    # ===== INVENTORY VALUE METRICS (Current Stock) =====
    inventory_data = base.clothing_inventory_metrics(
        business,
        location=location
    )
    
    # Extract metrics from sales_data
    revenue_mtd = sales_data['revenue']
    cost_mtd = sales_data['cost_of_goods']
    overhead_costs = sales_data['overhead_costs']
    profit_mtd = sales_data['profit']
    total_sales_mtd = sales_data['total_sales']
    payment_mix_data = sales_data['payment_mix_data']
    top_models = sales_data['top_models']
    top_model = sales_data['top_model']
    sales_trend = sales_data['sales_trend']
    
    # Extract inventory metrics
    inventory_value = inventory_data['inventory_value']
    retail_value = inventory_data['retail_value']
    expected_margin = inventory_data['expected_margin']

    ctx.update(
        {
            "hero_title": "Clothing & Fashion",
            "hero_blurb": "Track outfits, sizes, and curated drops for each location.",
            "product_count": metrics["total"],
            "active_product_count": metrics["active"],
            "scan_required_count": metrics["scan_required"],
            "inventory_tracked_count": metrics["inventory_tracked"],
            "recent_products": metrics["recent"],
            
            # KPI Panels (Sales Metrics)
            "revenue_mtd": revenue_mtd,
            "cost_mtd": cost_mtd,
            "overhead_costs": overhead_costs,
            "profit_mtd": profit_mtd,
            "total_sales_mtd": total_sales_mtd,
            
            # Inventory Value KPIs (Current Stock)
            "inventory_value": inventory_value,
            "retail_value": retail_value,
            "expected_margin": expected_margin,
            
            # Payment Mix
            "payment_mix_data": payment_mix_data,
            
            # Top Model & Trends
            "top_model": top_model,
            "top_models": top_models,
            "sales_trend": sales_trend,
            
            # Date Filter State
            "active_range": range_param,
            "selected_date": selected_date,
            "date_param": date_param,
        }
    )
    
    # ===== NEW: Personalized dashboard enhancements =====
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_yesterday import get_yesterday_summary, should_show_yesterday_summary, mark_yesterday_summary_shown
        from dashboard.helpers_payments import get_payment_mix_for_dashboard
        from dashboard.helpers_quotes import get_todays_quotes
        
        # Personalized greeting
        greeting_ctx = get_personalized_greeting(request.user, business)
        
        # Brand header context
        brand_logo_url = None
        if business and hasattr(business, 'logo') and business.logo:
            brand_logo_url = business.logo.url
        
        # Yesterday summary (show once per day)
        yesterday_summary = None
        if should_show_yesterday_summary(request):
            yesterday_summary = get_yesterday_summary(request.user, business)
            if yesterday_summary:
                mark_yesterday_summary_shown(request)
        
        # Daily quotes
        daily_quotes = get_todays_quotes(request.user, count=10)
        
        # Add to context
        ctx.update({
            "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
            "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
            "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
            "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
            "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
            "DASHBOARD_BRAND_TITLE": business.name if business else "Clothing Dashboard",
            "YESTERDAY_SUMMARY": yesterday_summary,
            "DASHBOARD_QUOTES": daily_quotes,
        })
    except Exception:
        pass  # Gracefully degrade if helpers not available
    
    return render(request, "verticals/clothing/dashboard.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def hub(request):
    """
    Clothing Hub - Stock Overview Page with gamified battery display.
    Shows each product with stock levels, sales, and status indicators.
    """
    from inventory.models_verticals import ClothingProductLog, ClothingProductAction
    
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    # Get all active clothing products
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.CLOTHING,
        is_active=True,
        is_archived=False
    ).order_by('-id')
    
    # Build product panel data
    product_panels = []
    for product in products:
        # Calculate stock IN quantities from logs
        stock_in_logs = ClothingProductLog.objects.filter(
            product=product,
            action=ClothingProductAction.STOCK_IN
        )
        
        stock_in_qty = 0
        total_stock_in_cost = Decimal('0.00')
        for log in stock_in_logs:
            qty_added = log.changes.get('quantity_added', 0)
            cost_price_str = log.changes.get('cost_price', '0')
            try:
                cost_price = Decimal(str(cost_price_str))
            except:
                cost_price = Decimal('0.00')
            
            stock_in_qty += qty_added
            total_stock_in_cost += Decimal(qty_added) * cost_price
        
        # Calculate sales stats
        sales = ClothingSale.objects.filter(
            business=business,
            product=product
        ).aggregate(
            total_sold=Sum('quantity'),
            total_revenue=Sum('total_price'),
            total_cost=Sum('total_cost')
        )
        
        stock_sold_qty = sales['total_sold'] or 0
        revenue_total = sales['total_revenue'] or Decimal('0.00')
        cost_of_goods_sold = sales['total_cost'] or Decimal('0.00')
        
        # Calculate available stock
        available_qty = product.quantity_in_stock or 0
        
        # Calculate inventory cost (cost of remaining stock)
        # Use current product cost_price or calculate average cost
        unit_cost = product.cost_price or Decimal('0.00')
        if unit_cost == 0 and stock_in_qty > 0 and total_stock_in_cost > 0:
            # Calculate average cost from stock-in logs
            unit_cost = total_stock_in_cost / Decimal(stock_in_qty)
        
        inventory_cost_total = Decimal(available_qty) * unit_cost
        
        # Calculate profit
        profit_total = revenue_total - cost_of_goods_sold
        
        # Stock battery calculation
        initial_capacity = stock_in_qty or (available_qty + stock_sold_qty)
        battery_percentage = 0
        if initial_capacity > 0:
            battery_percentage = int((available_qty / initial_capacity) * 100)
        
        # Status heuristics
        status = "Normal"
        status_class = "normal"
        
        if stock_sold_qty > 10:
            status = "🔥 Hot Selling"
            status_class = "hot"
        elif available_qty < 3 and available_qty > 0:
            status = "⚠️ Low Stock"
            status_class = "low"
        elif available_qty == 0:
            status = "❌ Out of Stock"
            status_class = "out"
        elif stock_sold_qty == 0 and stock_in_qty > 0:
            status = "✨ New Drop"
            status_class = "new"
        
        product_panels.append({
            'product': product,
            'available_stock': available_qty,
            'stock_in_qty': stock_in_qty,
            'total_sold': stock_sold_qty,
            'revenue': revenue_total,
            'inventory_cost': inventory_cost_total,
            'cost_of_goods_sold': cost_of_goods_sold,
            'profit': profit_total,
            'battery_percentage': battery_percentage,
            'status': status,
            'status_class': status_class,
        })
    
    ctx.update({
        'product_panels': product_panels,
        'page_title': 'Clothing Hub',
    })
    
    return render(request, "verticals/clothing/hub.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def scan_in(request):
    """
    Gamified clothing stock-in flow.
    Step-by-step process: Category → Size → Color → Quantity/Cost
    """
    from django import forms
    from django.db import transaction
    from django.contrib import messages
    from django.shortcuts import redirect
    
    business = base.base_context(request).get("business")
    
    # Define clothing categories
    CLOTHING_CATEGORIES = [
        ('suit', 'Suit', '🤵'),
        ('dress', 'Dress', '👗'),
        ('shirt', 'Shirt', '👔'),
        ('trousers', 'Trousers', '👖'),
        ('shoes', 'Shoes', '👞'),
        ('jacket', 'Jacket', '🧥'),
        ('skirt', 'Skirt', '🩱'),
        ('other', 'Other', '👕'),
    ]
    
    # Define sizes
    SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '28', '30', '32', '34', '36', '38', '40', '42', '44']
    
    # Define colors
    COLORS = ['Black', 'Navy', 'Grey', 'White', 'Beige', 'Brown', 'Blue', 'Red', 'Green', 'Other']
    
    class ClothingStockInForm(forms.Form):
        category = forms.ChoiceField(
            choices=[(cat[0], cat[1]) for cat in CLOTHING_CATEGORIES],
            widget=forms.Select(attrs={'class': 'form-control form-select'})
        )
        size = forms.ChoiceField(
            choices=[(s, s) for s in SIZES],
            widget=forms.Select(attrs={'class': 'form-control form-select'})
        )
        color = forms.ChoiceField(
            choices=[(c, c) for c in COLORS],
            widget=forms.Select(attrs={'class': 'form-control form-select'})
        )
        quantity = forms.IntegerField(
            min_value=1,
            initial=1,
            widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity'})
        )
        cost_price = forms.DecimalField(
            max_digits=10,
            decimal_places=2,
            min_value=0,
            widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Cost per unit'})
        )
        selling_price = forms.DecimalField(
            max_digits=10,
            decimal_places=2,
            min_value=0,
            required=False,
            widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Selling price (optional)'})
        )
    
    if request.method == 'POST':
        form = ClothingStockInForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            
            # Create product name from category, size, and color
            product_name = f"{data['category'].title()} - {data['size']} - {data['color']}"
            
            with transaction.atomic():
                # Check if product exists
                product, created = MerchProduct.objects.get_or_create(
                    business=business,
                    name=product_name,
                    defaults={
                        'kind': BusinessKind.CLOTHING,
                        'category': data['category'],
                        'size': data['size'],
                        'color': data['color'],
                        'cost_price': data['cost_price'],
                        'selling_price': data.get('selling_price'),
                        'quantity_in_stock': data['quantity'],
                        'is_active': True,
                        'track_inventory': True,
                    }
                )
                
                if not created:
                    # Update existing product stock
                    product.quantity_in_stock += data['quantity']
                    product.cost_price = data['cost_price']
                    if data.get('selling_price'):
                        product.selling_price = data['selling_price']
                    product.save(update_fields=['quantity_in_stock', 'cost_price', 'selling_price'])
                
                # Log the stock-in action
                from inventory.models_verticals import ClothingProductLog, ClothingProductAction
                ClothingProductLog.objects.create(
                    product=product,
                    action=ClothingProductAction.STOCK_IN,
                    changes={
                        'quantity_added': data['quantity'],
                        'cost_price': str(data['cost_price']),
                        'new_stock': product.quantity_in_stock
                    },
                    performed_by=request.user
                )
            
            messages.success(
                request,
                f"✅ Stock added: {data['quantity']} × {product_name} (K {data['cost_price']} each)"
            )
            return redirect('verticals:clothing_scan_in')
    else:
        form = ClothingStockInForm()
    
    # Recent stock-ins
    recent_logs = []
    try:
        from inventory.models_verticals import ClothingProductLog, ClothingProductAction
        recent_logs = ClothingProductLog.objects.filter(
            product__business=business,
            action=ClothingProductAction.STOCK_IN
        ).select_related('product', 'performed_by').order_by('-created_at')[:10]
    except:
        pass
    
    ctx = {
        'business': business,
        'form': form,
        'categories': CLOTHING_CATEGORIES,
        'recent_logs': recent_logs,
    }
    
    return render(request, "verticals/clothing/scan_in.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def sell(request):
    """
    Gamified clothing sell flow.
    Pick product → size → color → confirm sale
    """
    from django import forms
    from django.db import transaction
    from django.contrib import messages
    from django.shortcuts import redirect
    from inventory.models_verticals import PaymentMethod
    
    business = base.base_context(request).get("business")
    
    class ClothingSellForm(forms.Form):
        product = forms.ModelChoiceField(
            queryset=MerchProduct.objects.none(),
            widget=forms.Select(attrs={'class': 'form-control form-select'}),
            label="Product/Model"
        )
        quantity = forms.IntegerField(
            min_value=1,
            initial=1,
            widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity'}),
            label="Quantity"
        )
        selling_price = forms.DecimalField(
            max_digits=10,
            decimal_places=2,
            min_value=0,
            widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Selling price per unit'}),
            label="Selling Price (per unit)"
        )
        payment_method = forms.ChoiceField(
            choices=PaymentMethod.choices,
            initial=PaymentMethod.CASH,
            widget=forms.Select(attrs={'class': 'form-control form-select'}),
            label="Payment Method"
        )
        notes = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional notes'}),
            label="Notes"
        )
        
        def __init__(self, business=None, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if business:
                # Only show clothing products with stock
                self.fields['product'].queryset = MerchProduct.objects.filter(
                    business=business,
                    kind=BusinessKind.CLOTHING,
                    is_active=True,
                    is_archived=False,
                    quantity_in_stock__gt=0
                ).order_by('name')
    
    if request.method == 'POST':
        form = ClothingSellForm(business, request.POST)
        if form.is_valid():
            data = form.cleaned_data
            product = data['product']
            quantity = data['quantity']
            
            # Check stock availability
            if product.quantity_in_stock < quantity:
                messages.error(
                    request,
                    f"❌ Insufficient stock! Only {product.quantity_in_stock} available."
                )
            else:
                with transaction.atomic():
                    # Reduce stock
                    product.quantity_in_stock -= quantity
                    product.save(update_fields=['quantity_in_stock'])
                    
                    # Create sale
                    unit_price = data['selling_price']
                    total_price = Decimal(quantity) * unit_price
                    unit_cost = product.cost_price or Decimal('0.00')
                    total_cost = Decimal(quantity) * unit_cost
                    
                    sale = ClothingSale.objects.create(
                        business=business,
                        product=product,
                        quantity=quantity,
                        unit_price=unit_price,
                        total_price=total_price,
                        unit_cost=unit_cost,
                        total_cost=total_cost,
                        payment_method=data['payment_method'],
                        sold_by=request.user,
                        notes=data.get('notes', '')
                    )
                    
                    # Log the sale
                    from inventory.models_verticals import ClothingProductLog, ClothingProductAction
                    ClothingProductLog.objects.create(
                        product=product,
                        action=ClothingProductAction.SOLD,
                        changes={
                            'quantity_sold': quantity,
                            'selling_price': str(unit_price),
                            'total_revenue': str(total_price),
                            'remaining_stock': product.quantity_in_stock
                        },
                        performed_by=request.user
                    )
                    
                    profit = total_price - total_cost
                    messages.success(
                        request,
                        f"✅ Sale recorded: {quantity} × {product.name} | "
                        f"Revenue: K {total_price} | Profit: K {profit}"
                    )
                    return redirect('verticals:clothing_sell')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ClothingSellForm(business)
    
    # Recent sales
    recent_sales = ClothingSale.objects.filter(
        business=business
    ).select_related('product', 'sold_by').order_by('-sold_at')[:10]
    
    ctx = {
        'business': business,
        'form': form,
        'recent_sales': recent_sales,
    }
    
    return render(request, "verticals/clothing/sell.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def sales_history(request):
    """
    Sales History page with filters, pagination, and export.
    Shows all clothing sales with date range filtering and search.
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.db.models import Q
    
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    # Build base queryset
    sales_qs = ClothingSale.objects.filter(business=business).select_related('product', 'sold_by')
    
    if location:
        # If ClothingSale has location field, filter by it
        if hasattr(ClothingSale, 'location'):
            sales_qs = sales_qs.filter(location=location)
    
    # Parse filter parameters
    start_date = request.GET.get('start', '')
    end_date = request.GET.get('end', '')
    search_query = request.GET.get('q', '')
    sale_id = request.GET.get('sale_id', '')
    
    # Apply date filters
    if start_date:
        try:
            from datetime import datetime
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
            sales_qs = sales_qs.filter(sold_at__date__gte=start_dt)
        except ValueError:
            pass
    
    if end_date:
        try:
            from datetime import datetime
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
            sales_qs = sales_qs.filter(sold_at__date__lte=end_dt)
        except ValueError:
            pass
    
    # Apply search filter (search across product name, notes, payment method)
    if search_query:
        sales_qs = sales_qs.filter(
            Q(product__name__icontains=search_query) |
            Q(product__category__icontains=search_query) |
            Q(notes__icontains=search_query) |
            Q(sold_by__username__icontains=search_query)
        )
    
    # Highlight specific sale if sale_id provided
    highlighted_sale_id = None
    if sale_id:
        try:
            highlighted_sale_id = int(sale_id)
            # Ensure the sale exists in the filtered queryset
            if not sales_qs.filter(id=highlighted_sale_id).exists():
                highlighted_sale_id = None
        except ValueError:
            pass
    
    # Order by most recent first
    sales_qs = sales_qs.order_by('-sold_at')
    
    # Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(sales_qs, 50)  # 50 sales per page
    
    try:
        sales_page = paginator.page(page)
    except PageNotAnInteger:
        sales_page = paginator.page(1)
    except EmptyPage:
        sales_page = paginator.page(paginator.num_pages)
    
    # Summary stats for filtered results
    summary = sales_qs.aggregate(
        total_revenue=Sum('total_price'),
        total_cost=Sum('total_cost'),
        total_sales=Count('id'),
        total_items=Sum('quantity')
    )
    
    ctx.update({
        'sales': sales_page,
        'start_date': start_date,
        'end_date': end_date,
        'search_query': search_query,
        'highlighted_sale_id': highlighted_sale_id,
        'summary': summary,
        'page_title': 'Sales History',
    })
    
    return render(request, "verticals/clothing/sales_history.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def sales_export_csv(request):
    """
    Export filtered sales to CSV.
    Respects all the same filters as sales_history view.
    """
    import csv
    from django.http import HttpResponse
    from django.db.models import Q
    
    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")
    
    # Build queryset with same filters as sales_history
    sales_qs = ClothingSale.objects.filter(business=business).select_related('product', 'sold_by')
    
    if location:
        if hasattr(ClothingSale, 'location'):
            sales_qs = sales_qs.filter(location=location)
    
    # Apply filters
    start_date = request.GET.get('start', '')
    end_date = request.GET.get('end', '')
    search_query = request.GET.get('q', '')
    
    if start_date:
        try:
            from datetime import datetime
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
            sales_qs = sales_qs.filter(sold_at__date__gte=start_dt)
        except ValueError:
            pass
    
    if end_date:
        try:
            from datetime import datetime
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
            sales_qs = sales_qs.filter(sold_at__date__lte=end_dt)
        except ValueError:
            pass
    
    if search_query:
        sales_qs = sales_qs.filter(
            Q(product__name__icontains=search_query) |
            Q(product__category__icontains=search_query) |
            Q(notes__icontains=search_query) |
            Q(sold_by__username__icontains=search_query)
        )
    
    sales_qs = sales_qs.order_by('-sold_at')
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="clothing_sales_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'Timestamp',
        'Date',
        'Time',
        'Item',
        'Category',
        'Size',
        'Color',
        'Qty',
        'Unit Price',
        'Total',
        'Payment Method',
        'Cashier',
        'Notes'
    ])
    
    # Write data rows
    for sale in sales_qs:
        product = sale.product
        timestamp = timezone.localtime(sale.sold_at)
        
        writer.writerow([
            timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            timestamp.strftime('%Y-%m-%d'),
            timestamp.strftime('%H:%M:%S'),
            product.name or '',
            getattr(product, 'category', '') or '',
            getattr(product, 'size', '') or '',
            getattr(product, 'color', '') or '',
            sale.quantity,
            f'{sale.unit_price:.2f}',
            f'{sale.total_price:.2f}',
            sale.get_payment_method_display() if hasattr(sale, 'get_payment_method_display') else sale.payment_method,
            sale.sold_by.username if sale.sold_by else 'System',
            sale.notes or ''
        ])
    
    return response


@login_required
@require_business
@require_business_kind(BusinessKind.CLOTHING)
def sales_trend_json(request):
    """
    JSON endpoint for sales trend data.
    Respects dashboard date filters if provided.
    Returns data suitable for Chart.js or similar libraries.
    
    Uses the same queryset logic as clothing_sales_metrics to ensure consistency.
    """
    from django.http import JsonResponse
    from django.db.models.functions import TruncDate
    from django.db.models import Count, Sum
    
    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")
    
    # Parse date range from request
    date_range_ctx = base.parse_date_range_from_request(request)
    start_date = date_range_ctx['start_date']
    end_date = date_range_ctx['end_date']
    range_param = date_range_ctx['active_range']
    
    # Build sales queryset using unified helper (same as clothing_sales_metrics)
    sales_qs = base.clothing_sales_queryset(
        business=business,
        location=location,
        start_date=start_date,
        end_date=end_date,
    )
    
    # DB-grouped-by-day using TruncDate (same logic as clothing_sales_metrics)
    from django.db.models.functions import TruncDate
    from django.db.models.functions import Coalesce
    
    daily_sales = sales_qs.annotate(
        sale_date=TruncDate('sold_at')
    ).values('sale_date').annotate(
        revenue=Coalesce(Sum('total_price'), base.DECIMAL_ZERO, output_field=base.DECIMAL_FIELD),
        count=Count('id')
    ).order_by('sale_date')
    
    # Build dictionary for quick lookup
    sales_by_date = {}
    for day_data in daily_sales:
        sale_date = day_data['sale_date']
        if sale_date:
            # Convert Decimal to float for JSON serialization
            revenue_value = float(day_data['revenue'] or Decimal('0.00'))
            sales_by_date[sale_date.isoformat()] = {
                'revenue': revenue_value,
                'count': day_data['count'] or 0
            }
    
    # Fill missing days in Python
    labels = []
    revenue_values = []
    count_values = []
    
    current_date = start_date
    while current_date < end_date:
        date_key = current_date.isoformat()
        day_data = sales_by_date.get(date_key, {'revenue': 0.0, 'count': 0})
        
        labels.append(current_date.strftime('%b %d'))
        revenue_values.append(day_data['revenue'])
        count_values.append(day_data['count'])
        
        current_date += timedelta(days=1)
    
    # Check if there's actual data (non-zero revenue or count)
    has_data = any(r > 0 for r in revenue_values) or any(c > 0 for c in count_values)
    
    # Return response with cache-busting metadata
    return JsonResponse({
        'labels': labels,
        'revenue': revenue_values,
        'count': count_values,
        'has_data': has_data,
        'period': range_param,
        'start_date': start_date.isoformat(),
        'end_date': (end_date - timedelta(days=1)).isoformat(),
        'timestamp': timezone.now().isoformat(),
    })
