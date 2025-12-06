# inventory/verticals/phones.py
"""
Premium PHONES dashboard - the crown jewel of CircuitCity verticals.

Mirrors the premium Liquor dashboard patterns:
- Comprehensive KPIs (today, 7-day, MTD, stock on hand)
- Fast-moving models and top agents tracking  
- Sales trend visualization over 30 days
- Business panel with average metrics and sell-through rate
- Scoped to business + location + agents (same as Liquor)

PHONES uses the InventoryItem model where each phone is tracked with IMEI.
Sales are recorded by setting status="SOLD" and sold_at timestamp.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, Avg, F, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from tenants.utils import require_business
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models import InventoryItem, Product, Location
from . import base


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def dashboard(request):
    """
    Premium PHONES Dashboard - Crown Jewel Edition
    
    Provides comprehensive business metrics for phone retailers:
    - Today, Last 7 Days, Month-to-Date KPIs
    - Stock on hand with cost/selling value and potential profit
    - 30-day sales trend for visualization
    - Fast-moving models (top 5 by units sold)
    - Top agents leaderboard (top 5 by revenue)
    - Best sales day in last 30 days
    - Business panel with average metrics and sell-through rate
    
    Follows the Liquor dashboard pattern for consistency and premium feel.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    if location is None:
        location = getattr(request, "location", None)
    
    # Current datetime for date range calculations
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    # Last 7 days range
    last_7_days_start = today_start - timedelta(days=7)
    
    # Month-to-date range
    month_start = today_start.replace(day=1)
    
    # Last 30 days range (for trends and fast-moving analysis)
    last_30_days_start = today_start - timedelta(days=30)
    
    # Base queryset for sold items (scoped to business)
    sold_items = InventoryItem.objects.filter(
        business=business,
        status="SOLD",
        sold_at__isnull=False
    ).select_related('product', 'assigned_agent')
    
    # If location is set, optionally filter by location
    # (Following Liquor pattern where location filtering is optional)
    if location:
        sold_items = sold_items.filter(current_location=location)
    
    # ==========================================================================
    # A) FAST-MOVING KPIs (BUSINESS PANEL FOR PHONES)
    # ==========================================================================
    
    # --- TODAY ---
    today_sales = sold_items.filter(sold_at__gte=today_start, sold_at__lt=today_end)
    phones_sold_today = today_sales.count()
    revenue_today = today_sales.aggregate(
        total=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField())
    )['total'] or Decimal('0.00')
    cost_today = today_sales.aggregate(
        total=Coalesce(Sum('order_price'), Decimal('0.00'), output_field=DecimalField())
    )['total'] or Decimal('0.00')
    gross_profit_today = revenue_today - cost_today
    
    # --- LAST 7 DAYS ---
    last_7_days_sales = sold_items.filter(sold_at__gte=last_7_days_start)
    phones_sold_7d = last_7_days_sales.count()
    revenue_7d = last_7_days_sales.aggregate(
        total=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField())
    )['total'] or Decimal('0.00')
    cost_7d = last_7_days_sales.aggregate(
        total=Coalesce(Sum('order_price'), Decimal('0.00'), output_field=DecimalField())
    )['total'] or Decimal('0.00')
    gross_profit_7d = revenue_7d - cost_7d
    
    # --- MONTH-TO-DATE ---
    mtd_sales = sold_items.filter(sold_at__gte=month_start)
    phones_sold_mtd = mtd_sales.count()
    revenue_mtd = mtd_sales.aggregate(
        total=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField())
    )['total'] or Decimal('0.00')
    cost_mtd = mtd_sales.aggregate(
        total=Coalesce(Sum('order_price'), Decimal('0.00'), output_field=DecimalField())
    )['total'] or Decimal('0.00')
    gross_profit_mtd = revenue_mtd - cost_mtd
    
    # --- STOCK ON HAND ---
    stock_items = InventoryItem.objects.filter(
        business=business,
        status="IN_STOCK",
        is_active=True
    ).select_related('product')
    
    if location:
        stock_items = stock_items.filter(current_location=location)
    
    stock_units_on_hand = stock_items.count()
    stock_cost_value = stock_items.aggregate(
        total=Coalesce(Sum('order_price'), Decimal('0.00'), output_field=DecimalField())
    )['total'] or Decimal('0.00')
    
    # Compute estimated selling value and potential profit using margin-based estimation
    # This replaces the old (selling_value - cost_value) which could go negative
    from inventory.utils_metrics import estimate_margin_for_business_and_sku
    
    margin_pct = estimate_margin_for_business_and_sku(business)
    stock_selling_value = stock_cost_value * (Decimal('1') + margin_pct)
    potential_profit_on_hand = max(Decimal('0'), stock_cost_value * margin_pct)
    
    # Group into organized dict
    phones_kpis = {
        "today": {
            "units": phones_sold_today,
            "revenue": revenue_today,
            "gross_profit": gross_profit_today,
        },
        "last_7_days": {
            "units": phones_sold_7d,
            "revenue": revenue_7d,
            "gross_profit": gross_profit_7d,
        },
        "mtd": {
            "units": phones_sold_mtd,
            "revenue": revenue_mtd,
            "gross_profit": gross_profit_mtd,
        },
        "stock": {
            "units": stock_units_on_hand,
            "cost_value": stock_cost_value,
            "selling_value": stock_selling_value,
            "potential_profit": potential_profit_on_hand,
        },
    }
    
    # ==========================================================================
    # B) FAST MOVING GRAPHS + HIGHLIGHTS
    # ==========================================================================
    
    # --- SALES TREND - LAST 30 DAYS ---
    # Group sales by date for the last 30 days
    sales_trend_data = []
    for i in range(30):
        day_start = today_start - timedelta(days=29-i)
        day_end = day_start + timedelta(days=1)
        day_sales = sold_items.filter(sold_at__gte=day_start, sold_at__lt=day_end)
        day_units = day_sales.count()
        day_revenue = day_sales.aggregate(
            total=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField())
        )['total'] or Decimal('0.00')
        
        sales_trend_data.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "units": day_units,
            "revenue": float(day_revenue),
        })
    
    sales_trend_30d = sales_trend_data
    
    # --- FAST MOVING MODELS - TOP 5 BY UNITS SOLD (LAST 30 DAYS) ---
    fast_models_query = (
        sold_items.filter(sold_at__gte=last_30_days_start)
        .values('product__brand', 'product__model', 'product__variant')
        .annotate(
            units=Count('id'),
            revenue=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField())
        )
        .order_by('-units')[:5]
    )
    
    fast_models_30d = []
    for item in fast_models_query:
        brand = item['product__brand'] or "Unknown"
        model = item['product__model'] or "Unknown"
        variant = item['product__variant'] or ""
        ram_rom = variant if variant else "N/A"
        
        fast_models_30d.append({
            "brand": brand,
            "model": model,
            "ram_rom": ram_rom,
            "units": item['units'],
            "revenue": item['revenue'],
        })
    
    # --- FAST AGENTS - TOP 5 BY REVENUE (LAST 30 DAYS) ---
    fast_agents_query = (
        sold_items.filter(
            sold_at__gte=last_30_days_start,
            assigned_agent__isnull=False
        )
        .values('assigned_agent__id', 'assigned_agent__first_name', 'assigned_agent__last_name', 'assigned_agent__username')
        .annotate(
            units=Count('id'),
            revenue=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField())
        )
        .order_by('-revenue')[:5]
    )
    
    fast_agents_30d = []
    for item in fast_agents_query:
        first_name = item['assigned_agent__first_name'] or ""
        last_name = item['assigned_agent__last_name'] or ""
        username = item['assigned_agent__username'] or "Unknown"
        agent_name = f"{first_name} {last_name}".strip() or username
        
        # Find best day for this agent (day with highest revenue in last 30 days)
        agent_id = item['assigned_agent__id']
        best_day = None
        if agent_id:
            # Group by day and find the day with max revenue
            agent_daily_sales = (
                sold_items.filter(
                    assigned_agent__id=agent_id,
                    sold_at__gte=last_30_days_start
                )
                .extra(select={'day': 'DATE(sold_at)'})
                .values('day')
                .annotate(
                    day_revenue=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField())
                )
                .order_by('-day_revenue')
                .first()
            )
            if agent_daily_sales:
                best_day = agent_daily_sales['day']
        
        fast_agents_30d.append({
            "agent_name": agent_name,
            "units": item['units'],
            "revenue": item['revenue'],
            "best_day": best_day,
        })
    
    # --- BEST SALES DAY - LAST 30 DAYS ---
    # Find the single day with the highest revenue
    best_day_query = (
        sold_items.filter(sold_at__gte=last_30_days_start)
        .extra(select={'day': 'DATE(sold_at)'})
        .values('day')
        .annotate(
            day_units=Count('id'),
            day_revenue=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField())
        )
        .order_by('-day_revenue')
        .first()
    )
    
    best_sales_day_30d = None
    if best_day_query:
        best_sales_day_30d = {
            "date": best_day_query['day'],
            "units": best_day_query['day_units'],
            "revenue": best_day_query['day_revenue'],
        }
    
    # ==========================================================================
    # C) BUSINESS PANEL METRICS (PHONES-SPECIFIC)
    # ==========================================================================
    
    # Average selling price per unit this month
    avg_selling_price_mtd = Decimal('0.00')
    if phones_sold_mtd > 0:
        avg_selling_price_mtd = revenue_mtd / phones_sold_mtd
    
    # Average gross profit per unit this month
    avg_gross_profit_mtd = Decimal('0.00')
    if phones_sold_mtd > 0:
        avg_gross_profit_mtd = gross_profit_mtd / phones_sold_mtd
    
    # Sell-through rate: units_sold_mtd / (units_on_hand + units_sold_mtd)
    sell_through_rate = 0
    total_inventory = stock_units_on_hand + phones_sold_mtd
    if total_inventory > 0:
        sell_through_rate = int((phones_sold_mtd / total_inventory) * 100)
    
    # Traffic light hints
    sell_through_hint = "Needs attention"
    sell_through_color = "red"
    if sell_through_rate >= 70:
        sell_through_hint = "Great"
        sell_through_color = "green"
    elif sell_through_rate >= 40:
        sell_through_hint = "Okay"
        sell_through_color = "yellow"
    
    profit_margin_mtd = 0
    if revenue_mtd > 0:
        profit_margin_mtd = int((gross_profit_mtd / revenue_mtd) * 100)
    
    business_panel = {
        "avg_selling_price_mtd": avg_selling_price_mtd,
        "avg_gross_profit_mtd": avg_gross_profit_mtd,
        "sell_through_rate": sell_through_rate,
        "sell_through_hint": sell_through_hint,
        "sell_through_color": sell_through_color,
        "profit_margin_mtd": profit_margin_mtd,
    }
    
    # ==========================================================================
    # D) CONTEXT ASSEMBLY
    # ==========================================================================
    
    # Serialize data for JavaScript charts (following Liquor pattern)
    sales_trend_json = json.dumps(sales_trend_30d)
    fast_models_json = json.dumps([
        {"label": f"{m['brand']} {m['model']} {m['ram_rom']}", "value": m['units']}
        for m in fast_models_30d
    ])
    fast_agents_json = json.dumps([
        {"label": a['agent_name'], "value": float(a['revenue'])}
        for a in fast_agents_30d
    ])
    
    # Dashboard enhancements (greeting, quotes, etc.) - same as Liquor
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_yesterday import get_yesterday_summary, should_show_yesterday_summary, mark_yesterday_summary_shown
        from dashboard.helpers_quotes import get_todays_quotes
        
        greeting_ctx = get_personalized_greeting(request.user, business)
        
        brand_logo_url = None
        if business and hasattr(business, 'logo') and business.logo:
            brand_logo_url = business.logo.url
        
        yesterday_summary = None
        if should_show_yesterday_summary(request):
            yesterday_summary = get_yesterday_summary(request.user, business)
            if yesterday_summary:
                mark_yesterday_summary_shown(request)
        
        daily_quotes = get_todays_quotes(request.user, count=10)
        
        # Extract just the quote text for JavaScript rotation
        quote_texts = [q.get("quote", "") for q in daily_quotes if q.get("quote")]
        quotes_json = json.dumps(quote_texts)
        
        ctx_enhancements = {
            "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
            "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
            "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
            "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
            "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
            "DASHBOARD_BRAND_TITLE": business.name if business else "Phones Dashboard",
            "YESTERDAY_SUMMARY": yesterday_summary,
            "DASHBOARD_QUOTES": daily_quotes,
            "quotes_json": quotes_json,  # For JS rotation
        }
    except Exception:
        ctx_enhancements = {}
    
    # Update context
    ctx.update({
        "hero_title": "Phones & Electronics",
        "hero_blurb": "Track your phone sales, stock, and agents in one premium dashboard.",
        
        # KPIs
        "phones_kpis": phones_kpis,
        "business_panel": business_panel,
        
        # Charts and trends
        "sales_trend_30d": sales_trend_30d,
        "sales_trend_json": sales_trend_json,
        "fast_models_30d": fast_models_30d,
        "fast_models_json": fast_models_json,
        "fast_agents_30d": fast_agents_30d,
        "fast_agents_json": fast_agents_json,
        "best_sales_day_30d": best_sales_day_30d,
        
        # UI flags
        "show_search": False,
        "active_tab": "home",
        
        **ctx_enhancements,
    })
    
    return render(request, "verticals/phones/dashboard.html", ctx)

