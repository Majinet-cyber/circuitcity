# inventory/views_analytics_async.py
"""
Async JSON endpoints for analytics widgets.
Fast, cacheable, non-blocking endpoints that can be loaded independently.
"""
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page
from datetime import timedelta
from django.utils import timezone
from decimal import Decimal

from inventory.decorators import require_business
from inventory.helpers import get_active_business, business_vertical as get_business_vertical
from inventory.analytics import get_adapter
from inventory.analytics.common import (
    parse_date_range, get_cache_key, cache_or_compute
)
from inventory.models import Location
from tenants.models import Membership


def _decimal_to_float(obj):
    """Recursively convert Decimal to float for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_decimal_to_float(item) for item in obj]
    return obj


@login_required
@require_business
@require_http_methods(["GET"])
@cache_page(60 * 5)  # Cache for 5 minutes
def analytics_kpis_json(request):
    """
    Async JSON endpoint for analytics KPIs.
    Returns key metrics: revenue, profit, sales count, units sold, etc.
    """
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({"error": "No business selected"}, status=400)
        
        vertical = get_business_vertical(request)
        
        # Parse filters
        range_preset = request.GET.get('range', '')
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            try:
                location = Location.objects.filter(pk=location_id, business=business).first()
            except Exception:
                pass
        
        # Build cache key
        cache_key = get_cache_key(
            'kpis',
            business.id,
            vertical=vertical,
            start=date_params['start_date'].isoformat(),
            end=date_params['end_date'].isoformat(),
            location=location.id if location else None,
        )
        
        # Cache-or-compute pattern
        def compute_kpis():
            adapter = get_adapter(vertical, business=business)
            kpis = adapter.kpis(
                business=business,
                start_date=date_params['start_date'],
                end_date=date_params['end_date'],
                location=location,
            )
            return kpis or {}
        
        kpis = cache_or_compute(cache_key, compute_kpis, timeout=300)
        
        # Convert Decimals to floats for JSON
        kpis_json = _decimal_to_float(kpis)
        
        return JsonResponse({
            'ok': True,
            'kpis': kpis_json,
            'period': date_params['range_label'],
            'timestamp': timezone.now().isoformat(),
        })
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Analytics KPIs error: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
@cache_page(60 * 5)
def analytics_charts_json(request):
    """
    Async JSON endpoint for analytics charts data.
    Returns: sales trend, profit trend, payment mix, top products, etc.
    """
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({"error": "No business selected"}, status=400)
        
        vertical = get_business_vertical(request)
        
        # Parse filters
        range_preset = request.GET.get('range', '')
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            try:
                location = Location.objects.filter(pk=location_id, business=business).first()
            except Exception:
                pass
        
        # Build cache key
        cache_key = get_cache_key(
            'charts',
            business.id,
            vertical=vertical,
            start=date_params['start_date'].isoformat(),
            end=date_params['end_date'].isoformat(),
            location=location.id if location else None,
        )
        
        # Cache-or-compute pattern
        def compute_charts():
            adapter = get_adapter(vertical, business=business)
            charts = adapter.charts(
                business=business,
                start_date=date_params['start_date'],
                end_date=date_params['end_date'],
                location=location,
            )
            return charts or {}
        
        charts = cache_or_compute(cache_key, compute_charts, timeout=300)
        
        # Convert Decimals to floats for JSON
        charts_json = _decimal_to_float(charts)
        
        return JsonResponse({
            'ok': True,
            'charts': charts_json,
            'period': date_params['range_label'],
            'timestamp': timezone.now().isoformat(),
        })
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Analytics charts error: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
@cache_page(60 * 10)  # Cache for 10 minutes (more stable data)
def analytics_stock_overview_json(request):
    """
    Async JSON endpoint for stock overview across all verticals.
    Returns: total items, total cost value, total retail value, low stock, out of stock.
    """
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({"error": "No business selected"}, status=400)
        
        vertical = get_business_vertical(request)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            try:
                location = Location.objects.filter(pk=location_id, business=business).first()
            except Exception:
                pass
        
        # Build cache key
        cache_key = get_cache_key(
            'stock_overview',
            business.id,
            vertical=vertical,
            location=location.id if location else None,
        )
        
        # Cache-or-compute pattern
        def compute_stock():
            # Use shared stock overview service
            from inventory.services.stock_overview_common import get_stock_overview
            stock = get_stock_overview(business=business, vertical=vertical, location=location)
            return stock or {}
        
        stock = cache_or_compute(cache_key, compute_stock, timeout=600)  # 10 min cache
        
        # Convert Decimals to floats for JSON
        stock_json = _decimal_to_float(stock)
        
        return JsonResponse({
            'ok': True,
            'stock': stock_json,
            'timestamp': timezone.now().isoformat(),
        })
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Stock overview error: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def analytics_health_check(request):
    """
    Quick health check for analytics system.
    Returns cache status, adapter info, etc.
    """
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({"error": "No business selected"}, status=400)
        
        vertical = get_business_vertical(request)
        adapter = get_adapter(vertical, business=business)
        
        return JsonResponse({
            'ok': True,
            'business_id': business.id,
            'business_name': business.name,
            'vertical': vertical,
            'adapter': adapter.__class__.__name__,
            'timestamp': timezone.now().isoformat(),
        })
    
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

