# inventory/views_sales_trend.py
"""
Unified sales trend API endpoints for all verticals.
"""
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page
from datetime import timedelta
from django.utils import timezone

from inventory.decorators import require_business
from inventory import base
from inventory.services.sales_trend import get_sales_trend_by_product


@login_required
@require_business
@require_http_methods(["GET"])
@cache_page(60 * 5)  # Cache for 5 minutes
def sales_trend_json(request):
    """
    Unified sales trend API for all verticals.
    Returns Products vs Quantity Sold data for bar charts.
    
    Query params:
        - range: today|7d|mtd|30d (default: 7d)
        - limit: max products to return (default: 10)
    
    Returns:
        {
            "labels": ["Product 1", "Product 2", ...],
            "quantities": [50, 30, ...],
            "revenue": [500000, 300000, ...],
            "total_qty": 100,
            "total_revenue": 1000000.00,
            "period": "2025-12-01 to 2025-12-16",
            "range": "7d"
        }
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    if not business:
        return JsonResponse({
            "error": "Business not found",
            "labels": [],
            "quantities": [],
            "revenue": [],
        }, status=400)
    
    # Parse date range
    range_param = request.GET.get('range', '7d')
    limit = int(request.GET.get('limit', 10))
    
    today = timezone.localdate()
    
    if range_param == 'today':
        start_date = today
        end_date = today
    elif range_param == 'mtd':
        start_date = today.replace(day=1)
        end_date = today
    elif range_param == '30d':
        start_date = today - timedelta(days=29)
        end_date = today
    else:  # Default to 7d
        start_date = today - timedelta(days=6)
        end_date = today
    
    # Get vertical
    vertical = getattr(business, 'business_kind', 'phones').lower()
    
    # Get sales trend data
    try:
        data = get_sales_trend_by_product(
            business=business,
            start_date=start_date,
            end_date=end_date,
            vertical=vertical,
            location=location,
            limit=limit,
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Sales trend error: {e}", exc_info=True)
        
        # Return empty data on error
        data = {
            'labels': [],
            'quantities': [],
            'revenue': [],
            'total_qty': 0,
            'total_revenue': 0.0,
            'period': f"{start_date} to {end_date}",
        }
    
    # Add metadata
    data['range'] = range_param
    data['start_date'] = start_date.isoformat()
    data['end_date'] = end_date.isoformat()
    data['timestamp'] = timezone.now().isoformat()
    
    return JsonResponse(data)


@login_required
@require_business
@require_http_methods(["GET"])
def sales_trend_test_page(request):
    """
    Test page to visualize sales trend bar chart.
    Useful for development and debugging.
    """
    from django.shortcuts import render
    
    ctx = base.base_context(request)
    
    return render(request, 'inventory/sales_trend_test.html', {
        **ctx,
        'page_title': 'Sales Trend Bar Chart Test',
    })

