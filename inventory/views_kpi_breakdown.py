"""
KPI Breakdown Views
Every KPI card must be clickable and navigate to its breakdown page.

These views show detailed breakdowns of metrics:
- Revenue breakdown
- Profit breakdown
- COGS breakdown  
- Stock value breakdown

Mobile-first, gamified, self-explanatory dashboards.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Q, Count, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict

from inventory.models_unique_products import UniqueProduct, UniqueSale
from common.utils.number_formatter import format_money


@login_required
def revenue_breakdown(request):
    """
    Revenue Breakdown Page
    Shows: Total Revenue = Sum of all sales
    Breakdown by: Day, Product, Payment Method, Vertical
    """
    business = request.user.profile.business
    if not business:
        return redirect('onboarding:create_business')
    
    # Get date range from query params
    date_range = request.GET.get('date_range', '7days')
    
    # Calculate date boundaries
    end_date = timezone.now()
    if date_range == 'today':
        start_date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == 'yesterday':
        start_date = (timezone.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)
    elif date_range == '30days':
        start_date = timezone.now() - timedelta(days=30)
    elif date_range == 'this_month':
        start_date = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif date_range == 'custom':
        start = request.GET.get('start_date')
        end = request.GET.get('end_date')
        if start and end:
            start_date = datetime.strptime(start, '%Y-%m-%d')
            end_date = datetime.strptime(end, '%Y-%m-%d')
        else:
            start_date = timezone.now() - timedelta(days=7)
    else:  # 7days default
        start_date = timezone.now() - timedelta(days=7)
    
    # Get all sales in period (across all verticals)
    # This is a simplified approach - in production you'd query each vertical's sale model
    total_revenue = Decimal('0.00')
    sales_by_day = defaultdict(Decimal)
    sales_by_payment = defaultdict(Decimal)
    sale_transactions = []
    
    # === Unique Products Sales ===
    unique_sales = UniqueSale.objects.filter(
        business=business,
        sold_at__gte=start_date,
        sold_at__lte=end_date,
        is_deleted=False
    ).select_related('product')
    
    for sale in unique_sales:
        revenue = sale.quantity * sale.unit_price
        total_revenue += revenue
        
        # By day
        day_key = sale.sold_at.strftime('%Y-%m-%d')
        sales_by_day[day_key] += revenue
        
        # By payment method
        if sale.payment_method:
            sales_by_payment[sale.payment_method] += revenue
        
        # Transaction list
        sale_transactions.append({
            'date': sale.sold_at,
            'product': sale.product.name if sale.product else 'Unknown',
            'quantity': sale.quantity,
            'unit_price': sale.unit_price,
            'revenue': revenue,
            'payment_method': sale.payment_method or 'N/A',
            'type': 'Unique Product Sale'
        })
    
    # === Top Contributing Products ===
    top_products = UniqueSale.objects.filter(
        business=business,
        sold_at__gte=start_date,
        sold_at__lte=end_date,
        is_deleted=False
    ).values('product__name').annotate(
        total_revenue=Sum(F('quantity') * F('unit_price')),
        total_quantity=Sum('quantity')
    ).order_by('-total_revenue')[:10]
    
    # === Explanation Data ===
    explanation = {
        'formula': 'Total Revenue = Sum of all sales',
        'components': [
            {
                'label': 'Sales from Unique Products',
                'value': total_revenue,
                'currency': 'MWK'
            }
        ]
    }
    
    context = {
        'page_title': 'Revenue Breakdown',
        'metric_name': 'Revenue',
        'metric_icon': '💵',
        'metric_color': 'revenue',
        'total_value': total_revenue,
        'currency': 'MWK',
        'date_range': date_range,
        'start_date': start_date,
        'end_date': end_date,
        'explanation': explanation,
        'sales_by_day': dict(sales_by_day),
        'sales_by_payment': dict(sales_by_payment),
        'top_products': top_products,
        'sale_transactions': sorted(sale_transactions, key=lambda x: x['date'], reverse=True)[:50],
    }
    
    return render(request, 'inventory/kpi_breakdown_detail.html', context)


@login_required
def profit_breakdown(request):
    """
    Profit Breakdown Page
    Shows: Profit = Revenue - COGS
    Clear breakdown with visualization
    """
    business = request.user.profile.business
    if not business:
        return redirect('onboarding:create_business')
    
    # Get date range
    date_range = request.GET.get('date_range', '7days')
    
    # Calculate boundaries (reuse same logic as revenue_breakdown)
    end_date = timezone.now()
    if date_range == 'today':
        start_date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == 'yesterday':
        start_date = (timezone.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)
    elif date_range == '30days':
        start_date = timezone.now() - timedelta(days=30)
    elif date_range == 'this_month':
        start_date = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = timezone.now() - timedelta(days=7)
    
    # Calculate profit
    total_revenue = Decimal('0.00')
    total_cogs = Decimal('0.00')
    
    unique_sales = UniqueSale.objects.filter(
        business=business,
        sold_at__gte=start_date,
        sold_at__lte=end_date,
        is_deleted=False
    )
    
    for sale in unique_sales:
        revenue = sale.quantity * sale.unit_price
        cost = sale.quantity * (sale.unit_cost or Decimal('0.00'))
        
        total_revenue += revenue
        total_cogs += cost
    
    total_profit = total_revenue - total_cogs
    
    # Profit margin
    profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # Explanation
    explanation = {
        'formula': 'Profit = Revenue - Cost of Goods Sold (COGS)',
        'components': [
            {
                'label': 'Total Revenue',
                'value': total_revenue,
                'currency': 'MWK',
                'operator': ''
            },
            {
                'label': 'Total COGS',
                'value': total_cogs,
                'currency': 'MWK',
                'operator': '-'
            },
            {
                'label': 'Profit',
                'value': total_profit,
                'currency': 'MWK',
                'operator': '='
            }
        ]
    }
    
    context = {
        'page_title': 'Profit Breakdown',
        'metric_name': 'Profit',
        'metric_icon': '📈',
        'metric_color': 'profit',
        'total_value': total_profit,
        'currency': 'MWK',
        'date_range': date_range,
        'explanation': explanation,
        'profit_margin': profit_margin,
        'total_revenue': total_revenue,
        'total_cogs': total_cogs,
    }
    
    return render(request, 'inventory/kpi_breakdown_detail.html', context)


@login_required
def cogs_breakdown(request):
    """
    COGS (Cost of Goods Sold) Breakdown
    Shows: Total cost of items sold in period
    """
    business = request.user.profile.business
    if not business:
        return redirect('onboarding:create_business')
    
    date_range = request.GET.get('date_range', '7days')
    
    end_date = timezone.now()
    if date_range == 'today':
        start_date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == 'yesterday':
        start_date = (timezone.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)
    elif date_range == '30days':
        start_date = timezone.now() - timedelta(days=30)
    elif date_range == 'this_month':
        start_date = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = timezone.now() - timedelta(days=7)
    
    total_cogs = Decimal('0.00')
    cogs_by_product = defaultdict(Decimal)
    
    unique_sales = UniqueSale.objects.filter(
        business=business,
        sold_at__gte=start_date,
        sold_at__lte=end_date,
        is_deleted=False
    ).select_related('product')
    
    for sale in unique_sales:
        cost = sale.quantity * (sale.unit_cost or Decimal('0.00'))
        total_cogs += cost
        
        if sale.product:
            cogs_by_product[sale.product.name] += cost
    
    # Top cost contributors
    top_cost_products = sorted(
        cogs_by_product.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]
    
    explanation = {
        'formula': 'COGS = Sum of (Quantity Sold × Cost Price) for all sales',
        'components': [
            {
                'label': 'Total Cost of Goods Sold',
                'value': total_cogs,
                'currency': 'MWK'
            }
        ]
    }
    
    context = {
        'page_title': 'COGS Breakdown',
        'metric_name': 'Cost of Goods Sold',
        'metric_icon': '📦',
        'metric_color': 'cost',
        'total_value': total_cogs,
        'currency': 'MWK',
        'date_range': date_range,
        'explanation': explanation,
        'top_cost_products': top_cost_products,
    }
    
    return render(request, 'inventory/kpi_breakdown_detail.html', context)


@login_required
def stock_value_breakdown(request):
    """
    Stock Value Breakdown
    Shows: Current stock value = Sum(Quantity × Cost Price)
    Not date-filtered, shows current snapshot
    """
    business = request.user.profile.business
    if not business:
        return redirect('onboarding:create_business')
    
    # Stock value is a snapshot - not date filtered
    total_stock_value = Decimal('0.00')
    items_breakdown = []
    
    # Unique Products
    unique_products = UniqueProduct.objects.filter(
        business=business,
        is_active=True,
        quantity__gt=0
    )
    
    for product in unique_products:
        value = product.quantity * (product.cost_price or Decimal('0.00'))
        total_stock_value += value
        
        items_breakdown.append({
            'name': product.name,
            'quantity': product.quantity,
            'unit': product.unit,
            'cost_price': product.cost_price,
            'value': value
        })
    
    # Sort by value
    items_breakdown = sorted(items_breakdown, key=lambda x: x['value'], reverse=True)[:50]
    
    explanation = {
        'formula': 'Stock Value = Sum of (Current Quantity × Cost Price) for all products',
        'components': [
            {
                'label': 'Total Stock Value (at cost basis)',
                'value': total_stock_value,
                'currency': 'MWK'
            }
        ]
    }
    
    context = {
        'page_title': 'Stock Value Breakdown',
        'metric_name': 'Stock Value',
        'metric_icon': '🏪',
        'metric_color': 'stock',
        'total_value': total_stock_value,
        'currency': 'MWK',
        'date_range': None,  # Not date-filtered
        'explanation': explanation,
        'items_breakdown': items_breakdown,
        'is_snapshot': True,
    }
    
    return render(request, 'inventory/kpi_breakdown_detail.html', context)

