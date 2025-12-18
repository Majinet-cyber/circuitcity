# inventory/views_analytics.py
"""
Premium analytics dashboard for all businesses - Excel-dashboard style with live updates.
Uses adapter pattern for vertical-specific analytics.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional
import json
import csv

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from inventory.helpers import business_vertical as get_business_vertical, get_active_business
from inventory.verticals.base import base_context
from inventory.analytics import get_adapter
from inventory.analytics.common import (
    parse_date_range, apply_business_scope, apply_location_filter,
    get_cache_key, cache_analytics_data, get_cached_analytics_data
)
from tenants.utils import require_business
from tenants.models import Business, Membership
from inventory.models import Location


@login_required
@require_business
def analytics_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Main analytics dashboard page for all businesses.
    Renders a single premium template that works for all verticals.
    """
    try:
        business = get_active_business(request)
        if not business:
            from django.contrib import messages
            messages.error(request, "No active business selected")
            try:
                return redirect("dashboard:home")
            except Exception:
                return redirect("/inventory/dashboard/")
        
        vertical = get_business_vertical(request)
        
        # Get base context
        try:
            ctx = base_context(request)
        except Exception:
            ctx = {}
        
        # Parse date range
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        # Get location filter
        location_id = request.GET.get('location')
        location = None
        if location_id:
            try:
                location = Location.objects.filter(pk=location_id, business=business).first()
            except Exception:
                pass
        
        # Get staff filter
        staff_id = request.GET.get('agent', request.GET.get('staff_id'))
        staff = None
        if staff_id:
            try:
                staff = Membership.objects.filter(pk=staff_id, business=business).first()
            except Exception:
                pass
        
        # Get payment method filter
        payment_method = request.GET.get('payment_method', '')
        
        # Get search query
        search_query = request.GET.get('q', '').strip()
        
        # Get selected sections (defaults based on vertical)
        sections_param = request.GET.getlist('sections')
        if sections_param:
            selected_sections = sections_param
        else:
            # Default sections based on vertical
            if vertical == 'gym':
                selected_sections = ['members', 'new_members', 'profit', 'cash_mix', 'top_products']
            else:
                selected_sections = ['sales', 'profit', 'cash_mix', 'top_products', 'top_categories']
        
        # Get available locations and staff
        try:
            locations = Location.objects.filter(business=business).order_by('name')
        except Exception:
            locations = []
        
        try:
            staff_list = Membership.objects.filter(
                business=business,
                is_active=True
            ).select_related('user').order_by('user__first_name', 'user__last_name')
        except Exception:
            staff_list = []
        
        # Get adapter and fetch analytics data
        adapter = get_adapter(vertical, business=business)
        
        # Build analytics_data with safe defaults
        analytics_data = {
            'kpis': {
                'revenue': Decimal('0'),
                'profit': Decimal('0'),
                'total_sales': 0,
                'units_sold': 0,
                'avg_order_value': Decimal('0'),
                'gross_margin': Decimal('0'),
                'costs': Decimal('0'),
                'inventory_value': Decimal('0'),
                'retail_value': Decimal('0'),
                'expected_margin': Decimal('0'),
                'active_members': 0,
                'new_members': 0,
            },
            'charts': {
                'sales_trend': [],
                'profit_trend': [],
                'payment_mix': [],
                'top_products': [],
                'top_agents': [],
                'stock_overview': {},
            },
            'top_items': [],
            'categories': [],
        }
        
        # Try to fetch real data (but don't crash if adapter fails)
        try:
            kpis = adapter.kpis(
                business=business,
                start_date=date_params['start_date'],
                end_date=date_params['end_date'],
                location=location,
                payment_method=payment_method if payment_method else None,
                search_query=search_query if search_query else None,
            )
            if kpis:
                analytics_data['kpis'].update(kpis)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to fetch KPIs: {e}")
        
        try:
            charts = adapter.charts(
                business=business,
                start_date=date_params['start_date'],
                end_date=date_params['end_date'],
                location=location,
                payment_method=payment_method if payment_method else None,
                search_query=search_query if search_query else None,
            )
            if charts:
                analytics_data['charts'].update(charts)
                # Extract top_items and categories from charts if available
                if 'top_products' in charts:
                    analytics_data['top_items'] = charts['top_products']
                if 'top_categories' in charts:
                    analytics_data['categories'] = charts['top_categories']
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to fetch charts: {e}")
        
        ctx.update({
            'analytics_ok': True,
            'vertical': vertical,
            'date_params': date_params,
            'selected_location': location,
            'locations': locations,
            'selected_staff': staff,
            'staff_list': staff_list,
            'payment_method': payment_method,
            'search_query': search_query,
            'selected_sections': selected_sections,
            'analytics_data': analytics_data,
            'business': business,
            'active_tab': 'analytics',
        })
        
        # Use single template for all verticals
        return render(request, 'analytics/dashboard.html', ctx)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Analytics dashboard error")
        
        # Return error context
        try:
            business = get_active_business(request)
            vertical = get_business_vertical(request)
        except Exception:
            business = None
            vertical = 'phones'
        
        try:
            ctx = base_context(request)
        except Exception:
            ctx = {}
        
        today = date.today()
        
        # Provide safe defaults for error case
        default_sections = ['sales', 'profit', 'cash_mix', 'top_products']
        if vertical == 'gym':
            default_sections = ['members', 'new_members', 'profit', 'cash_mix', 'top_products']
        
        ctx.update({
            'analytics_ok': False,
            'analytics_error': str(e),
            'vertical': vertical,
            'active_tab': 'analytics',
            'date_params': {
                'start_date': today - timedelta(days=30),
                'end_date': today,
                'range_label': 'Last 30 Days',
                'active_range': None,
            },
            'selected_sections': default_sections,
            'analytics_data': {
                'kpis': {
                    'revenue': Decimal('0'),
                    'profit': Decimal('0'),
                    'total_sales': 0,
                    'units_sold': 0,
                    'avg_order_value': Decimal('0'),
                    'gross_margin': Decimal('0'),
                    'costs': Decimal('0'),
                    'inventory_value': Decimal('0'),
                    'retail_value': Decimal('0'),
                    'expected_margin': Decimal('0'),
                    'active_members': 0,
                    'new_members': 0,
                },
                'charts': {
                    'sales_trend': [],
                    'profit_trend': [],
                    'payment_mix': [],
                    'top_products': [],
                    'top_agents': [],
                    'stock_overview': {},
                },
                'top_items': [],
                'categories': [],
            },
            'locations': [],
            'staff_list': [],
            'selected_location': None,
            'selected_staff': None,
            'payment_method': '',
            'search_query': '',
            'business': business,
        })
        
        return render(request, 'analytics/dashboard.html', ctx, status=200)


# ============================================================================
# JSON API ENDPOINTS
# ============================================================================

@login_required
@require_business
@require_http_methods(["GET"])
def api_kpis(request: HttpRequest) -> JsonResponse:
    """Get KPIs as JSON."""
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({'error': 'No active business'}, status=400)
        
        vertical = get_business_vertical(request)
        adapter = get_adapter(vertical, business=business)
        
        # Parse filters
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            location = Location.objects.filter(pk=location_id, business=business).first()
        
        payment_method = request.GET.get('payment_method', '')
        search_query = request.GET.get('q', '').strip()
        
        # Check cache
        cache_key = get_cache_key(
            'kpis',
            business.id,
            vertical=vertical,
            start=date_params['start_date'].isoformat(),
            end=date_params['end_date'].isoformat(),
            location=location_id or '',
            payment_method=payment_method,
            search=search_query,
        )
        
        cached = get_cached_analytics_data(cache_key)
        if cached:
            return JsonResponse(cached)
        
        # Get KPIs
        kpis = adapter.kpis(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
            payment_method=payment_method if payment_method else None,
            search_query=search_query if search_query else None,
        )
        
        # Serialize Decimal values
        result = {
            'revenue': float(kpis['revenue']),
            'profit': float(kpis['profit']),
            'total_sales': kpis['total_sales'],
            'avg_order_value': float(kpis['avg_order_value']),
            'gross_margin': float(kpis['gross_margin']),
            'costs': float(kpis['costs']),
            'last_updated': timezone.now().isoformat(),
        }
        
        # Cache for 30 seconds
        cache_analytics_data(cache_key, result, timeout=30)
        
        return JsonResponse(result)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("API KPIs error")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def api_sales_trend(request: HttpRequest) -> JsonResponse:
    """Get sales trend chart data as JSON."""
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({'error': 'No active business'}, status=400)
        
        vertical = get_business_vertical(request)
        adapter = get_adapter(vertical, business=business)
        
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            location = Location.objects.filter(pk=location_id, business=business).first()
        
        payment_method = request.GET.get('payment_method', '')
        search_query = request.GET.get('q', '').strip()
        
        cache_key = get_cache_key(
            'sales_trend',
            business.id,
            vertical=vertical,
            start=date_params['start_date'].isoformat(),
            end=date_params['end_date'].isoformat(),
            location=location_id or '',
            payment_method=payment_method,
            search=search_query,
        )
        
        cached = get_cached_analytics_data(cache_key)
        if cached:
            return JsonResponse(cached)
        
        charts = adapter.charts(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
            payment_method=payment_method if payment_method else None,
            search_query=search_query if search_query else None,
        )
        
        result = {
            'sales_trend': charts.get('sales_trend', []),
            'last_updated': timezone.now().isoformat(),
        }
        
        cache_analytics_data(cache_key, result, timeout=30)
        
        return JsonResponse(result)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("API sales trend error")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def api_profit_trend(request: HttpRequest) -> JsonResponse:
    """Get profit trend chart data as JSON."""
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({'error': 'No active business'}, status=400)
        
        vertical = get_business_vertical(request)
        adapter = get_adapter(vertical, business=business)
        
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            location = Location.objects.filter(pk=location_id, business=business).first()
        
        payment_method = request.GET.get('payment_method', '')
        search_query = request.GET.get('q', '').strip()
        
        cache_key = get_cache_key(
            'profit_trend',
            business.id,
            vertical=vertical,
            start=date_params['start_date'].isoformat(),
            end=date_params['end_date'].isoformat(),
            location=location_id or '',
            payment_method=payment_method,
            search=search_query,
        )
        
        cached = get_cached_analytics_data(cache_key)
        if cached:
            return JsonResponse(cached)
        
        charts = adapter.charts(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
            payment_method=payment_method if payment_method else None,
            search_query=search_query if search_query else None,
        )
        
        result = {
            'profit_trend': charts.get('profit_trend', []),
            'last_updated': timezone.now().isoformat(),
        }
        
        cache_analytics_data(cache_key, result, timeout=30)
        
        return JsonResponse(result)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("API profit trend error")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def api_payment_mix(request: HttpRequest) -> JsonResponse:
    """Get payment mix chart data as JSON."""
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({'error': 'No active business'}, status=400)
        
        vertical = get_business_vertical(request)
        adapter = get_adapter(vertical, business=business)
        
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            location = Location.objects.filter(pk=location_id, business=business).first()
        
        payment_method = request.GET.get('payment_method', '')
        search_query = request.GET.get('q', '').strip()
        
        cache_key = get_cache_key(
            'payment_mix',
            business.id,
            vertical=vertical,
            start=date_params['start_date'].isoformat(),
            end=date_params['end_date'].isoformat(),
            location=location_id or '',
            payment_method=payment_method,
            search=search_query,
        )
        
        cached = get_cached_analytics_data(cache_key)
        if cached:
            return JsonResponse(cached)
        
        charts = adapter.charts(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
            payment_method=payment_method if payment_method else None,
            search_query=search_query if search_query else None,
        )
        
        result = {
            'payment_mix': charts.get('payment_mix', []),
            'last_updated': timezone.now().isoformat(),
        }
        
        cache_analytics_data(cache_key, result, timeout=30)
        
        return JsonResponse(result)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("API payment mix error")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def api_top_products(request: HttpRequest) -> JsonResponse:
    """Get top products chart data as JSON."""
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({'error': 'No active business'}, status=400)
        
        vertical = get_business_vertical(request)
        adapter = get_adapter(vertical, business=business)
        
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            location = Location.objects.filter(pk=location_id, business=business).first()
        
        payment_method = request.GET.get('payment_method', '')
        search_query = request.GET.get('q', '').strip()
        
        cache_key = get_cache_key(
            'top_products',
            business.id,
            vertical=vertical,
            start=date_params['start_date'].isoformat(),
            end=date_params['end_date'].isoformat(),
            location=location_id or '',
            payment_method=payment_method,
            search=search_query,
        )
        
        cached = get_cached_analytics_data(cache_key)
        if cached:
            return JsonResponse(cached)
        
        charts = adapter.charts(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
            payment_method=payment_method if payment_method else None,
            search_query=search_query if search_query else None,
        )
        
        result = {
            'top_products': charts.get('top_products', []),
            'last_updated': timezone.now().isoformat(),
        }
        
        cache_analytics_data(cache_key, result, timeout=30)
        
        return JsonResponse(result)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("API top products error")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def api_top_agents(request: HttpRequest) -> JsonResponse:
    """Get top agents/trainers/cashiers chart data as JSON."""
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({'error': 'No active business'}, status=400)
        
        vertical = get_business_vertical(request)
        adapter = get_adapter(vertical, business=business)
        
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            location = Location.objects.filter(pk=location_id, business=business).first()
        
        payment_method = request.GET.get('payment_method', '')
        search_query = request.GET.get('q', '').strip()
        
        cache_key = get_cache_key(
            'top_agents',
            business.id,
            vertical=vertical,
            start=date_params['start_date'].isoformat(),
            end=date_params['end_date'].isoformat(),
            location=location_id or '',
            payment_method=payment_method,
            search=search_query,
        )
        
        cached = get_cached_analytics_data(cache_key)
        if cached:
            return JsonResponse(cached)
        
        charts = adapter.charts(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
            payment_method=payment_method if payment_method else None,
            search_query=search_query if search_query else None,
        )
        
        result = {
            'top_agents': charts.get('top_agents', []),
            'last_updated': timezone.now().isoformat(),
        }
        
        cache_analytics_data(cache_key, result, timeout=30)
        
        return JsonResponse(result)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("API top agents error")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def api_stock_overview(request: HttpRequest) -> JsonResponse:
    """Get stock overview data as JSON."""
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({'error': 'No active business'}, status=400)
        
        vertical = get_business_vertical(request)
        adapter = get_adapter(vertical, business=business)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            location = Location.objects.filter(pk=location_id, business=business).first()
        
        cache_key = get_cache_key(
            'stock_overview',
            business.id,
            vertical=vertical,
            location=location_id or '',
        )
        
        cached = get_cached_analytics_data(cache_key)
        if cached:
            return JsonResponse(cached)
        
        # Use current date range for stock overview
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        charts = adapter.charts(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
        )
        
        result = {
            'stock_overview': charts.get('stock_overview', {}),
            'last_updated': timezone.now().isoformat(),
        }
        
        cache_analytics_data(cache_key, result, timeout=60)
        
        return JsonResponse(result)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("API stock overview error")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def api_stock_overview_cross_vertical(request: HttpRequest) -> JsonResponse:
    """
    Get cross-vertical stock overview for unified analytics chart.
    Returns stock counts across ALL verticals (phones, liquor, pharmacy, clothing).
    """
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({'error': 'No active business'}, status=400)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            location = Location.objects.filter(pk=location_id, business=business).first()
        
        # Check cache
        cache_key = get_cache_key(
            'stock_overview_cross_vertical',
            business.id,
            location=location_id or '',
        )
        
        cached = get_cached_analytics_data(cache_key)
        if cached:
            return JsonResponse(cached)
        
        # Get cross-vertical stock data
        from inventory.services.analytics_stock_overview import get_cross_vertical_stock_overview
        
        stock_data = get_cross_vertical_stock_overview(business, location)
        
        result = {
            'ok': True,
            'labels': stock_data['labels'],
            'values': stock_data['values'],
            'total_units': stock_data['total_units'],
            'most_stocked_vertical': stock_data['most_stocked_vertical'],
            'breakdown': stock_data['breakdown'],
            'last_updated': timezone.now().isoformat(),
        }
        
        # Cache for 2 minutes (stock changes frequently)
        cache_analytics_data(cache_key, result, timeout=120)
        
        return JsonResponse(result)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("API cross-vertical stock overview error")
        return JsonResponse({
            'ok': False,
            'error': str(e),
            'labels': [],
            'values': [],
            'total_units': 0,
            'most_stocked_vertical': 'None',
            'breakdown': {},
        }, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def api_cost_breakdown(request: HttpRequest) -> JsonResponse:
    """Get cost breakdown data as JSON."""
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({'error': 'No active business'}, status=400)
        
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        from wallet.models import WalletTransaction, Ledger, TxnType
        from django.db.models import Sum, Q
        
        costs_qs = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        ).filter(
            Q(type=TxnType.COST_ONCE_OFF, effective_date__gte=date_params['start_date'], effective_date__lte=date_params['end_date']) |
            Q(type=TxnType.COST_RECURRING, effective_from__lte=date_params['end_date'])
        )
        
        # Group by type
        cost_breakdown = costs_qs.values('type').annotate(
            total=Sum('amount')
        ).order_by('-total')
        
        result = {
            'cost_breakdown': [
                {
                    'type': item['type'],
                    'type_display': dict(TxnType.choices).get(item['type'], item['type']),
                    'total': abs(float(item['total'] or 0)),
                }
                for item in cost_breakdown
            ],
            'last_updated': timezone.now().isoformat(),
        }
        
        return JsonResponse(result)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("API cost breakdown error")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def api_alerts(request: HttpRequest) -> JsonResponse:
    """Get alerts (low stock, expiry, etc.) as JSON."""
    try:
        business = get_active_business(request)
        if not business:
            return JsonResponse({'error': 'No active business'}, status=400)
        
        vertical = get_business_vertical(request)
        adapter = get_adapter(vertical, business=business)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            location = Location.objects.filter(pk=location_id, business=business).first()
        
        # Get stock overview for alerts
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        charts = adapter.charts(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
        )
        
        alerts = []
        stock_overview = charts.get('stock_overview', {})
        
        # Low stock alerts
        if stock_overview.get('low_stock_count', 0) > 0:
            alerts.append({
                'type': 'low_stock',
                'severity': 'warning',
                'message': f"{stock_overview['low_stock_count']} items are low in stock",
                'count': stock_overview['low_stock_count'],
            })
        
        # Vertical-specific alerts
        vertical_sections = adapter.vertical_sections(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
        )
        
        # Pharmacy expiry alerts
        if vertical == 'pharmacy':
            if vertical_sections.get('expired_batches', 0) > 0:
                alerts.append({
                    'type': 'expired',
                    'severity': 'error',
                    'message': f"{vertical_sections['expired_batches']} batches have expired",
                    'count': vertical_sections['expired_batches'],
                })
            if vertical_sections.get('expiring_soon', 0) > 0:
                alerts.append({
                    'type': 'expiring_soon',
                    'severity': 'warning',
                    'message': f"{vertical_sections['expiring_soon']} batches expiring soon",
                    'count': vertical_sections['expiring_soon'],
                })
        
        result = {
            'alerts': alerts,
            'last_updated': timezone.now().isoformat(),
        }
        
        return JsonResponse(result)
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("API alerts error")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_business
@require_http_methods(["GET"])
def api_export_csv(request: HttpRequest) -> HttpResponse:
    """Export analytics data as CSV."""
    try:
        business = get_active_business(request)
        if not business:
            return HttpResponse("No active business", status=400)
        
        vertical = get_business_vertical(request)
        adapter = get_adapter(vertical, business=business)
        
        range_preset = request.GET.get('range', request.GET.get('preset', ''))
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        date_params = parse_date_range(range_preset, start_str, end_str)
        
        location_id = request.GET.get('location')
        location = None
        if location_id:
            location = Location.objects.filter(pk=location_id, business=business).first()
        
        payment_method = request.GET.get('payment_method', '')
        search_query = request.GET.get('q', '').strip()
        
        # Get KPIs and charts
        kpis = adapter.kpis(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
            payment_method=payment_method if payment_method else None,
            search_query=search_query if search_query else None,
        )
        
        charts = adapter.charts(
            business=business,
            start_date=date_params['start_date'],
            end_date=date_params['end_date'],
            location=location,
            payment_method=payment_method if payment_method else None,
            search_query=search_query if search_query else None,
        )
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        filename = f"analytics_{vertical}_{date_params['start_date']}_{date_params['end_date']}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow(['Analytics Export', business.name])
        writer.writerow(['Date Range', f"{date_params['start_date']} to {date_params['end_date']}"])
        writer.writerow(['Vertical', vertical])
        writer.writerow([])
        
        # Write KPIs
        writer.writerow(['KPIs'])
        writer.writerow(['Revenue', kpis['revenue']])
        writer.writerow(['Profit', kpis['profit']])
        writer.writerow(['Total Sales', kpis['total_sales']])
        writer.writerow(['Avg Order Value', kpis['avg_order_value']])
        writer.writerow(['Gross Margin', kpis['gross_margin']])
        writer.writerow(['Costs', kpis['costs']])
        writer.writerow([])
        
        # Write top products
        top_products = charts.get('top_products', [])
        if top_products:
            writer.writerow(['Top Products'])
            writer.writerow(['Name', 'Revenue', 'Units Sold'])
            for item in top_products:
                writer.writerow([item.get('name', ''), item.get('revenue', 0), item.get('units_sold', 0)])
            writer.writerow([])
        
        return response
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("CSV export error")
        return HttpResponse(f"Error generating CSV: {str(e)}", status=500)
