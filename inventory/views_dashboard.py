# inventory/views_dashboard.py
"""
Legacy Inventory Dashboard View - Richer layout with low stock alerts, charts, and top models.

This is the general-purpose inventory dashboard that works across all verticals.
It uses the centralized dashboard_metrics service for accurate KPI calculations.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Count, Avg, F, DecimalField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from tenants.utils import require_business

logger = logging.getLogger(__name__)


def _try_import(modpath: str, attr: str | None = None):
    """Import helper that never explodes."""
    try:
        mod = __import__(modpath, fromlist=[attr] if attr else [])
        return getattr(mod, attr) if attr else mod
    except Exception:
        return None


# Import metrics service (single source of truth for KPIs)
_get_inventory_kpis = _try_import("inventory.services.dashboard_metrics", "get_inventory_kpis")

# Prefer the single-source-of-truth helpers if present
_dashboard_counts = _try_import("inventory.query", "dashboard_counts")
_sales_in_range = _try_import("inventory.query", "sales_in_range")
_compute_agent_ranking = _try_import("inventory.services.agent_ranking", "compute_agent_ranking")
_format_rank = _try_import("inventory.services.agent_ranking", "format_rank")


def _parse_date_range(request):
    """
    Parse date range from query parameters.

    Supports:
    - ?range=today
    - ?range=7d (last 7 days)
    - ?range=mtd (month to date, DEFAULT)
    - ?range=custom&start=YYYY-MM-DD&end=YYYY-MM-DD

    Returns:
        tuple: (range_key, start_datetime, end_datetime, display_label)
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    range_param = request.GET.get("range", "mtd").lower()

    if range_param == "today":
        return ("today", today_start, today_end, "Today")

    elif range_param == "7d":
        start = today_start - timedelta(days=7)
        return ("7d", start, today_end, "Last 7 Days")

    elif range_param == "custom":
        # Parse custom dates from query params
        start_str = request.GET.get("start", "")
        end_str = request.GET.get("end", "")

        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

            # Convert to timezone-aware datetimes
            start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

            label = f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')}"
            return ("custom", start_dt, end_dt, label)
        except (ValueError, TypeError):
            # Fall back to MTD if custom dates are invalid
            pass

    # Default: month-to-date
    month_start = today_start.replace(day=1)
    return ("mtd", month_start, today_end, "This Month")


@login_required
@never_cache
@require_business
def inventory_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Legacy Inventory Dashboard with rich layout:
    - Business KPIs strip (Units Sold, Revenue, Costs, Profit)
    - Low stock alerts
    - Profit vs Costs chart data
    - Top models/SKUs

    - Uses centralized dashboard_metrics service for accurate KPIs
    - Supports date range filtering: Today / Last 7 Days / MTD / Custom
    - Works across all business verticals
    - JSON if: ?format=json or Accept: application/json
    - Otherwise renders inventory/dashboard.html

    NOTE: For PHONES vertical, this now redirects to Analytics (replaces dashboard).
    """
    # Get business from request
    business = getattr(request, "business", None) or getattr(request, "active_business", None)
    if not business:
        return HttpResponse("No active business found", status=400)

    # For phones, redirect to analytics (replaces inventory dashboard)
    from inventory.helpers import business_vertical, PHONES

    vertical = business_vertical(request)
    if vertical == PHONES:
        from django.shortcuts import redirect

        # Check if JSON is requested - if so, we still need to provide data
        wants_json = (
            (request.GET.get("format") or "").lower() == "json"
            or request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or request.headers.get("accept") or "")
        )
        if not wants_json:
            # Redirect to analytics for phones - safe redirect with fallback
            try:
                from django.urls import reverse

                analytics_url = reverse("app_router:analytics")
                return redirect(analytics_url)
            except Exception:
                # Fallback to safe URL if reverse fails
                return redirect("/app/analytics/")
        # For JSON requests, continue with analytics data (analytics view handles JSON)
        from inventory.views_analytics import analytics_dashboard

        return analytics_dashboard(request)

    # Parse date range
    range_key, start_date, end_date, range_label = _parse_date_range(request)

    # Check if JSON response is requested
    wants_json = (
        (request.GET.get("format") or "").lower() == "json"
        or request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or request.headers.get("accept") or "")
    )

    # ================================================================
    # COMPUTE METRICS USING CENTRALIZED SERVICE
    # ================================================================

    # Get location (optional)
    location = getattr(request, "location", None) or getattr(request, "active_location", None)

    # Build sales queryset for the selected period
    try:
        from sales.models import Sale

        sales_qs = Sale.objects.filter(
            Q(item__business=business) | Q(location__business=business),
            created_at__gte=start_date,
            created_at__lt=end_date,
        ).select_related("item", "item__product", "agent")

        # Optional location filter
        if location:
            sales_qs = sales_qs.filter(location=location)

        # Compute KPIs using the centralized metrics service
        kpis = {}
        if callable(_get_inventory_kpis):
            try:
                kpis = _get_inventory_kpis(
                    business=business,
                    location=location,
                    sales_qs=sales_qs,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as e:
                logger.exception("Failed to compute dashboard KPIs: %s", e)

        # Extract key metrics
        total_revenue = kpis.get("total_revenue", Decimal("0.00"))
        costs_total = kpis.get("total_costs", Decimal("0.00"))
        cost_of_goods = kpis.get("total_cogs", Decimal("0.00"))
        business_costs = kpis.get("total_admin_costs", Decimal("0.00"))
        profit_total = kpis.get("total_profit", Decimal("0.00"))
        profit_margin = kpis.get("profit_margin", 0.0)

        # Profit = revenue - total costs (cost of goods + business costs)
        # Defensive check: Ensure profit is ALWAYS revenue - costs, never just -costs
        profit_total = total_revenue - costs_total
        profit_margin = float((profit_total / total_revenue) * 100) if total_revenue > 0 else 0.0

        # Units sold
        total_units = sales_qs.count()

    except ImportError:
        logger.warning("Sale model not available, metrics will be zero")
        total_revenue = costs_total = profit_total = Decimal("0.00")
        cost_of_goods = business_costs = Decimal("0.00")
        profit_margin = 0.0
        total_units = 0
        kpis = {}
    except Exception as e:
        logger.exception("Error computing dashboard metrics: %s", e)
        total_revenue = costs_total = profit_total = Decimal("0.00")
        cost_of_goods = business_costs = Decimal("0.00")
        profit_margin = 0.0
        total_units = 0
        kpis = {}

    # ================================================================
    # STOCK COUNTS
    # ================================================================
    products = items_in_stock = 0

    if callable(_dashboard_counts):
        try:
            counts = _dashboard_counts(request, products_in_stock_only=False)
            products = int(counts.get("products") or 0)
            items_in_stock = int(counts.get("items_in_stock") or 0)
        except Exception as e:
            logger.exception("dashboard_counts failed: %s", e)

    # ================================================================
    # LOW STOCK ALERTS (products with 2 or fewer items in stock)
    # ================================================================
    low_stock_items = []
    try:
        from inventory.models import Product, InventoryItem

        # Get products with their stock counts
        products_with_stock = (
            Product.objects.filter(business=business)
            .annotate(
                stock_count=Count(
                    "inventoryitem", filter=Q(inventoryitem__status="IN_STOCK", inventoryitem__is_active=True)
                )
            )
            .filter(Q(stock_count=0) | Q(stock_count__lte=2))
            .order_by("stock_count")[:10]
        )  # Top 10 low/out of stock

        for product in products_with_stock:
            low_stock_items.append(
                {
                    "id": product.id,
                    "name": f"{product.brand or ''} {product.model or ''} {product.variant or ''}".strip()
                    or "Unknown Product",
                    "stock_count": product.stock_count,
                    "status": "OUT" if product.stock_count == 0 else "LOW",
                }
            )

    except Exception as e:
        logger.exception("Failed to compute low stock alerts: %s", e)

    # ================================================================
    # TOP MODELS / TOP SKUS (top 5 by units sold in selected range)
    # ================================================================
    top_models = []
    try:
        from sales.models import Sale

        # Query top products by units sold
        top_products_query = (
            sales_qs.values(
                "item__product__id", "item__product__brand", "item__product__model", "item__product__variant"
            )
            .annotate(
                units_sold=Count("id"), revenue=Coalesce(Sum("price"), Decimal("0.00"), output_field=DecimalField())
            )
            .order_by("-units_sold")[:5]
        )

        for item in top_products_query:
            brand = item["item__product__brand"] or "Unknown"
            model = item["item__product__model"] or "Unknown"
            variant = item["item__product__variant"] or ""
            product_name = f"{brand} {model} {variant}".strip()

            top_models.append(
                {
                    "product_id": item["item__product__id"],
                    "product_name": product_name,
                    "units_sold": item["units_sold"],
                    "revenue": item["revenue"],
                }
            )

    except Exception as e:
        logger.exception("Failed to compute top models: %s", e)

    # ================================================================
    # PROFIT VS COSTS CHART DATA (last 30 days)
    # ================================================================
    profit_cost_series = []
    try:
        from sales.models import Sale

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Generate last 30 days of data
        for i in range(30):
            day_start = today_start - timedelta(days=29 - i)
            day_end = day_start + timedelta(days=1)

            # Sales for this day
            day_sales = Sale.objects.filter(
                Q(item__business=business) | Q(location__business=business),
                created_at__gte=day_start,
                created_at__lt=day_end,
            )

            if location:
                day_sales = day_sales.filter(location=location)

            # Revenue
            day_revenue = day_sales.aggregate(
                total=Coalesce(Sum("price"), Decimal("0.00"), output_field=DecimalField())
            )["total"] or Decimal("0.00")

            # COGS
            day_cogs = day_sales.aggregate(
                total=Coalesce(Sum("item__order_price"), Decimal("0.00"), output_field=DecimalField())
            )["total"] or Decimal("0.00")

            # Profit
            day_profit = day_revenue - day_cogs

            profit_cost_series.append(
                {
                    "date": day_start.strftime("%Y-%m-%d"),
                    "date_short": day_start.strftime("%b %d"),
                    "revenue": float(day_revenue),
                    "costs": float(day_cogs),
                    "profit": float(day_profit),
                }
            )

    except Exception as e:
        logger.exception("Failed to generate profit/cost chart data: %s", e)

    # Serialize for JavaScript
    profit_cost_json = json.dumps(profit_cost_series)

    # ================================================================
    # BUILD CONTEXT
    # ================================================================
    ctx = {
        # Business & location info
        "business": business,
        "location": location,
        "location_label": location.name if location else "All Locations",
        # Date range info
        "range_key": range_key,
        "range_label": range_label,
        "start_date": start_date,
        "end_date": end_date,
        "period": range_label,
        # Core KPIs (using centralized metrics service)
        "total_revenue": float(total_revenue),
        "revenue_total": float(total_revenue),  # Alias for template compatibility
        "costs_total": float(costs_total),
        "cost_of_goods": float(cost_of_goods),
        "business_costs": float(business_costs),
        "profit_total": float(profit_total),
        "profit_margin": profit_margin,
        "margin_pct": profit_margin,  # Alias
        # Units
        "total_units": total_units,
        "units_sold": total_units,  # Alias
        # Stock info
        "products": products,
        "items_in_stock": items_in_stock,
        "active_stock_count": items_in_stock,  # Alias
        # Inventory-specific features
        "low_stock_items": low_stock_items,
        "top_models": top_models,
        "profit_cost_series": profit_cost_series,
        "profit_cost_json": profit_cost_json,
        # Additional KPIs from service
        "kpis": kpis,
        # Template metadata
        "active_tab": "inventory_dashboard",
        "page_title": "Inventory Dashboard",
    }

    # ================================================================
    # JSON RESPONSE
    # ================================================================
    if wants_json:
        return JsonResponse(
            {
                "ok": True,
                "metrics": {
                    "products": products,
                    "items_in_stock": items_in_stock,
                    "total_revenue": float(total_revenue),
                    "costs_total": float(costs_total),
                    "profit_total": float(profit_total),
                    "profit_margin": profit_margin,
                    "total_units": total_units,
                },
                "low_stock_count": len(low_stock_items),
                "top_models_count": len(top_models),
                "period": range_label,
            }
        )

    # ================================================================
    # HTML RESPONSE
    # ================================================================
    try:
        return render(request, "inventory/dashboard.html", ctx)
    except Exception as e:
        logger.exception("Failed to render dashboard template: %s", e)
        # Fallback HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Inventory Dashboard</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: system-ui; background: #0b1020; color: #eef2ff; margin: 0; padding: 20px; }}
                .panel {{ background: #0e152b; border: 1px solid #1c2541; border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
                .kpi {{ display: inline-block; margin: 10px 20px; }}
                .kpi .label {{ font-size: 0.9rem; color: #8ea0b5; }}
                .kpi .value {{ font-size: 1.8rem; font-weight: 900; }}
            </style>
        </head>
        <body>
            <div class="panel">
                <h1>Inventory Dashboard</h1>
                <p>Period: {range_label}</p>
                <div class="kpi">
                    <div class="label">Revenue</div>
                    <div class="value">MK {total_revenue:,.0f}</div>
                </div>
                <div class="kpi">
                    <div class="label">Costs</div>
                    <div class="value">MK {costs_total:,.0f}</div>
                </div>
                <div class="kpi">
                    <div class="label">Profit</div>
                    <div class="value">MK {profit_total:,.0f}</div>
                </div>
                <div class="kpi">
                    <div class="label">Units Sold</div>
                    <div class="value">{total_units}</div>
                </div>
            </div>
            <div class="panel">
                <p><strong>Cost Breakdown:</strong></p>
                <p>Cost of goods: MK {cost_of_goods:,.0f}</p>
                <p>Business costs: MK {business_costs:,.0f}</p>
            </div>
            <div class="panel">
                <p><strong>Low Stock Alerts:</strong> {len(low_stock_items)} items</p>
            </div>
            <div class="panel">
                <p><strong>Top Models:</strong> {len(top_models)} products</p>
            </div>
        </body>
        </html>
        """
        return HttpResponse(html, content_type="text/html")
