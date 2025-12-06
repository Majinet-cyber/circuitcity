from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.apps import apps
from django.db.models import QuerySet, Sum, Count
from django.urls import reverse
from django.utils import timezone

from inventory.helpers import add_product_url_for_request, business_vertical, get_active_business
from inventory.models import MerchProduct
from tenants.scope import resolve_location_for_user, set_scope_in_session


def _get_location(location_id: Optional[int]):
    if not location_id:
        return None
    try:
        Location = apps.get_model("inventory", "Location")
    except Exception:
        return None
    return Location.objects.filter(pk=location_id).first()


def base_context(request) -> Dict[str, Any]:
    """
    Shared context for all vertical dashboards.
    Ensures we keep the tenant scope (business / location) in sync with session defaults.
    
    Provides vertical-aware URLs so liquor/gym/clothing contexts route correctly.
    """
    business = get_active_business(request)
    vertical = business_vertical(request)

    try:
        request.session["active_business_vertical"] = vertical
    except Exception:
        pass

    location_id = resolve_location_for_user(request)
    if business:
        set_scope_in_session(request, business_id=business.id, location_id=location_id)

    location = _get_location(location_id)
    location_label = getattr(location, "name", None) or ("All locations" if business else "No active location")

    # Vertical-aware URL overrides (Task 1A: Fix liquor stock/sell/hub URLs)
    if vertical == "liquor":
        url_home = reverse("verticals:liquor_dashboard")
        url_stock = reverse("liquor:stock_overview")
        url_sell = reverse("liquor:sell")
        url_scan_in = reverse("liquor:inventory_dashboard")  # Liquor Hub
    elif vertical == "gym":
        url_home = reverse("verticals:gym_dashboard")
        url_stock = reverse("inventory:stock_list")  # gym uses default for now
        url_sell = reverse("inventory:scan_sold")  # gym uses default for now
        url_scan_in = reverse("inventory:scan_in")
    elif vertical == "clothing":
        url_home = reverse("verticals:clothing_dashboard")
        url_stock = reverse("inventory:stock_list")  # clothing uses default for now
        url_sell = reverse("inventory:scan_sold")
        url_scan_in = reverse("inventory:scan_in")
    else:  # phones or default
        url_home = reverse("inventory:inventory_dashboard")
        url_stock = reverse("inventory:stock_list")
        url_sell = reverse("inventory:scan_sold")
        url_scan_in = reverse("inventory:scan_in")

    ctx: Dict[str, Any] = {
        "business": business,
        "location": location,
        "location_label": location_label,
        "vertical": vertical,
        # Vertical-aware URLs (for sidebar & templates)
        "url_home": url_home,
        "url_stock": url_stock,
        "url_sell": url_sell,
        "url_scan_in": url_scan_in,
        # Legacy names (backward compatibility)
        "scan_in_url": url_scan_in,
        "scan_sold_url": url_sell,
        "stock_url": url_stock,
        "add_product_url": add_product_url_for_request(request),
    }
    return ctx


def merch_queryset(business, kind: str) -> QuerySet[MerchProduct]:
    if not business:
        return MerchProduct.objects.none()
    return MerchProduct.objects.filter(business=business, kind=kind)


def merch_metrics(business, kind: str, *, recent_limit: int = 6) -> Dict[str, Any]:
    qs = merch_queryset(business, kind)
    recent = list(qs.order_by("-id")[:recent_limit])
    return {
        "total": qs.count(),
        "active": qs.filter(is_active=True).count(),
        "scan_required": qs.filter(scan_required=True).count(),
        "inventory_tracked": qs.filter(track_inventory=True).count(),
        "recent": recent,
    }


def _compute_date_range(period: str = "mtd", date_str: Optional[str] = None) -> tuple[date, date]:
    """
    Compute start and end dates for a given period.
    
    Args:
        period: One of "today", "7d", "mtd", "date"
        date_str: Specific date string (YYYY-MM-DD) when period="date"
    
    Returns:
        Tuple of (start_date, end_date) where end_date is exclusive (for range queries)
    """
    now = timezone.now()
    today = now.date()
    
    if period == "today":
        start_date = today
        end_date = today + timedelta(days=1)  # Exclusive end
    elif period == "7d":
        start_date = today - timedelta(days=6)  # Last 7 days including today
        end_date = today + timedelta(days=1)
    elif period == "date" and date_str:
        try:
            specific_date = date.fromisoformat(date_str)
            start_date = specific_date
            end_date = specific_date + timedelta(days=1)
        except (ValueError, TypeError):
            # Fallback to MTD if invalid date
            start_date = today.replace(day=1)
            end_date = today + timedelta(days=1)
    else:  # "mtd" or default
        start_date = today.replace(day=1)
        end_date = today + timedelta(days=1)
    
    return start_date, end_date


def parse_date_range_from_request(request) -> Dict[str, Any]:
    """
    Parse date range parameters from request and return normalized data.
    
    This is a reusable helper for all vertical dashboards to parse date filters
    from GET parameters in a consistent way.
    
    Args:
        request: Django HttpRequest object
    
    Returns:
        Dictionary with:
            - active_range: str ("today" | "7d" | "mtd" | "date")
            - start_date: date object (inclusive)
            - end_date: date object (exclusive for range queries)
            - selected_date: date object or None (for "date" range only)
            - date_param: str or None (ISO date string for "date" range)
    """
    # Parse filter parameters from request
    range_param = request.GET.get('range', 'mtd')  # Default to MTD
    date_param = request.GET.get('date', '')  # Specific date for "date" range
    
    # Validate range parameter
    valid_ranges = ['today', '7d', 'mtd', 'date']
    if range_param not in valid_ranges:
        range_param = 'mtd'
    
    # For "date" range, validate the date parameter
    selected_date = None
    if range_param == 'date':
        if date_param:
            try:
                selected_date = date.fromisoformat(date_param)
            except ValueError:
                # Invalid date format, fall back to MTD
                range_param = 'mtd'
                selected_date = None
                date_param = ''
        else:
            # No date provided, default to today
            selected_date = timezone.now().date()
            date_param = selected_date.isoformat()
    
    # Compute date range
    start_date, end_date = _compute_date_range(range_param, date_param)
    
    return {
        'active_range': range_param,
        'start_date': start_date,
        'end_date': end_date,
        'selected_date': selected_date,
        'date_param': date_param,
    }


def clothing_sales_metrics(
    business,
    *,
    location=None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = "mtd",
    date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate comprehensive sales metrics for clothing vertical with date filtering.
    
    Args:
        business: Business instance
        location: Optional location filter
        start_date: Optional explicit start date (inclusive)
        end_date: Optional explicit end date (exclusive)
        period: One of "today", "7d", "mtd", "date" (used if start/end not provided)
        date_str: Specific date string for period="date"
    
    Returns:
        Dictionary with KPIs, payment mix, top models, sales trend, and overhead costs
    """
    from inventory.models_verticals import ClothingSale
    
    # Determine date range
    if start_date is None or end_date is None:
        start_date, end_date = _compute_date_range(period, date_str)
    
    # Build base sales queryset
    sales_qs = ClothingSale.objects.filter(
        business=business,
        sold_at__gte=timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time())),
        sold_at__lt=timezone.make_aware(timezone.datetime.combine(end_date, timezone.datetime.min.time())),
    )
    
    if location:
        # If ClothingSale has location field, filter by it
        if hasattr(ClothingSale, 'location'):
            sales_qs = sales_qs.filter(location=location)
    
    # Revenue, Cost, Profit (Sales COGS)
    sales_aggregates = sales_qs.aggregate(
        revenue=Sum('total_price'),
        cost=Sum('total_cost'),
        total_sales=Count('id')
    )
    
    revenue = sales_aggregates['revenue'] or Decimal('0.00')
    cost_of_goods = sales_aggregates['cost'] or Decimal('0.00')
    total_sales = sales_aggregates['total_sales'] or 0
    
    # Get overhead costs for the period
    try:
        from wallet.utils import compute_business_costs
        overhead_data = compute_business_costs(business, start_date, end_date - timedelta(days=1))
        overhead_costs = overhead_data['total']
    except Exception:
        # Gracefully degrade if wallet module not available
        overhead_costs = Decimal('0.00')
    
    # Calculate profit (revenue - COGS - overhead)
    profit = revenue - cost_of_goods - overhead_costs
    
    # Payment Mix
    payment_mix = sales_qs.values('payment_method').annotate(
        total=Sum('total_price'),
        count=Count('id')
    ).order_by('-total')
    
    payment_mix_data = []
    if revenue > 0:
        for pm in payment_mix:
            pct = (pm['total'] / revenue) * 100
            from inventory.models_verticals import ClothingSale as CS
            payment_mix_data.append({
                'method': pm['payment_method'],
                'method_display': dict(CS._meta.get_field('payment_method').choices).get(
                    pm['payment_method'], pm['payment_method']
                ),
                'total': pm['total'],
                'count': pm['count'],
                'percentage': round(pct, 1)
            })
    
    # Top Models
    top_models = sales_qs.values('product__name').annotate(
        units_sold=Sum('quantity'),
        revenue=Sum('total_price')
    ).order_by('-units_sold')[:5]
    
    top_model = top_models[0] if top_models else None
    
    # Sales Trend (Last 7 Days within the period, or daily breakdown)
    # For "today" and "date" periods, this might be hourly, but we'll keep it simple
    sales_trend = []
    trend_days = 7 if period in ["mtd", "7d"] else 1
    
    for i in range(trend_days - 1, -1, -1):
        day = timezone.now().date() - timedelta(days=i)
        # Only include if within our period
        if start_date <= day < end_date:
            day_sales = ClothingSale.objects.filter(
                business=business,
                sold_at__date=day
            ).aggregate(
                revenue=Sum('total_price'),
                count=Count('id')
            )
            sales_trend.append({
                'date': day.strftime('%Y-%m-%d'),
                'date_short': day.strftime('%b %d'),
                'revenue': float(day_sales['revenue'] or 0),
                'count': day_sales['count'] or 0
            })
    
    return {
        'revenue': revenue,
        'cost_of_goods': cost_of_goods,
        'overhead_costs': overhead_costs,
        'profit': profit,
        'total_sales': total_sales,
        'payment_mix_data': payment_mix_data,
        'top_models': top_models,
        'top_model': top_model,
        'sales_trend': sales_trend,
        'period_start': start_date,
        'period_end': end_date,
    }

