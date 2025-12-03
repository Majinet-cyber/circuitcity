# inventory/dashboard_services.py
"""
Shared dashboard metrics and helpers for inventory dashboards.

These functions extract inventory-specific calculations so they can be
reused across:
- Main dashboard (dashboard/views.py)
- Inventory dashboard (inventory/views_dashboard.py)
- Vertical dashboards (inventory/verticals/*.py)

All functions accept business + location and return serializable dicts/lists.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional

from django.db.models import Sum, Count, Q, Avg, F, DecimalField, Value
from django.db.models.functions import Coalesce
from django.utils import timezone


def get_stock_alerts(business, location=None, threshold: int = 5) -> List[Dict[str, Any]]:
    """
    Get low-stock/stockout alerts for inventory items.
    
    Args:
        business: Business instance
        location: Optional Location instance to filter by
        threshold: Low-stock threshold (default: 5 units)
    
    Returns:
        List of alert dicts with keys:
            - product_name: str
            - on_hand: int
            - threshold: int
            - severity: "critical" | "warning"
            - message: str
    """
    from inventory.models import InventoryItem, Product
    
    if not business:
        return []
    
    alerts = []
    
    try:
        # Get in-stock items grouped by product
        stock_qs = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK",
            is_active=True
        ).select_related('product')
        
        if location:
            stock_qs = stock_qs.filter(current_location=location)
        
        # Group by product and count
        product_counts = (
            stock_qs.values('product_id', 'product__brand', 'product__model', 'product__variant', 'product__low_stock_threshold')
            .annotate(on_hand=Count('id'))
            .order_by('on_hand')
        )
        
        for item in product_counts:
            product_name = f"{item['product__brand']} {item['product__model']}"
            if item['product__variant']:
                product_name += f" {item['product__variant']}"
            
            on_hand = item['on_hand']
            # Use per-product threshold if available, else global threshold
            item_threshold = item.get('product__low_stock_threshold') or threshold
            
            if on_hand == 0:
                alerts.append({
                    "product_name": product_name,
                    "on_hand": on_hand,
                    "threshold": item_threshold,
                    "severity": "critical",
                    "message": f"{product_name} is OUT OF STOCK!",
                })
            elif on_hand <= item_threshold:
                alerts.append({
                    "product_name": product_name,
                    "on_hand": on_hand,
                    "threshold": item_threshold,
                    "severity": "warning",
                    "message": f"{product_name} is low ({on_hand} units left)",
                })
        
    except Exception as e:
        # Gracefully handle errors
        import logging
        log = logging.getLogger(__name__)
        log.exception("Failed to get stock alerts: %s", e)
        
    return alerts[:10]  # Limit to top 10 most urgent


def get_cfo_alerts(business, location=None) -> List[Dict[str, Any]]:
    """
    Get CFO-level alerts (stockout predictions, financial warnings, etc.)
    
    Args:
        business: Business instance
        location: Optional Location instance
    
    Returns:
        List of alert dicts with keys:
            - severity: "high" | "medium" | "low"
            - category: "stock" | "finance" | "operations"
            - title: str
            - message: str
            - suggested_action: str (optional)
    """
    from inventory.models import InventoryItem
    from datetime import timedelta
    
    if not business:
        return []
    
    alerts = []
    
    try:
        # Calculate run-rate predictions (last 30 days)
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        
        # Get sales in last 30 days
        sold_items = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__gte=thirty_days_ago
        )
        
        if location:
            sold_items = sold_items.filter(current_location=location)
        
        # Group by product and calculate daily run-rate
        sales_by_product = (
            sold_items.values('product_id', 'product__brand', 'product__model')
            .annotate(sold_count=Count('id'))
        )
        
        # Get current stock
        stock_qs = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK",
            is_active=True
        )
        
        if location:
            stock_qs = stock_qs.filter(current_location=location)
        
        stock_by_product = {
            item['product_id']: item['on_hand']
            for item in stock_qs.values('product_id').annotate(on_hand=Count('id'))
        }
        
        # Predict stockouts
        for sale_data in sales_by_product:
            product_id = sale_data['product_id']
            sold_count = sale_data['sold_count']
            daily_rate = sold_count / 30.0  # Average daily sales
            
            on_hand = stock_by_product.get(product_id, 0)
            
            if daily_rate > 0:
                days_until_stockout = on_hand / daily_rate
                
                product_name = f"{sale_data['product__brand']} {sale_data['product__model']}"
                
                if days_until_stockout <= 7:
                    alerts.append({
                        "severity": "high",
                        "category": "stock",
                        "title": "Stockout Imminent",
                        "message": f"{product_name} will stock out in ~{int(days_until_stockout)} days",
                        "suggested_action": f"Reorder {int(daily_rate * 14)} units (2-week supply)",
                    })
                elif days_until_stockout <= 14:
                    alerts.append({
                        "severity": "medium",
                        "category": "stock",
                        "title": "Low Stock Warning",
                        "message": f"{product_name} has ~{int(days_until_stockout)} days of stock left",
                        "suggested_action": f"Consider reordering soon",
                    })
        
        # If no alerts, add a positive message
        if not alerts:
            alerts.append({
                "severity": "low",
                "category": "stock",
                "title": "All Systems Green",
                "message": "No stockout predictions for the next 14 days",
            })
    
    except Exception as e:
        import logging
        log = logging.getLogger(__name__)
        log.exception("Failed to get CFO alerts: %s", e)
        
    return alerts[:5]  # Limit to top 5


def get_ai_insights(business, location=None) -> Dict[str, Any]:
    """
    Get AI-driven insights for the dashboard.
    
    Args:
        business: Business instance
        location: Optional Location instance
    
    Returns:
        dict with keys:
            - fast_movers: List of top-selling products
            - slow_movers: List of slow-moving products
            - recommendations: List of actionable insights
    """
    from inventory.models import InventoryItem
    
    if not business:
        return {"fast_movers": [], "slow_movers": [], "recommendations": []}
    
    try:
        # Last 30 days window
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        
        # Fast movers (top 5 by units sold in last 30 days)
        sold_qs = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__gte=thirty_days_ago
        )
        
        if location:
            sold_qs = sold_qs.filter(current_location=location)
        
        fast_movers_data = (
            sold_qs.values('product_id', 'product__brand', 'product__model', 'product__variant')
            .annotate(
                units_sold=Count('id'),
                revenue=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField())
            )
            .order_by('-units_sold')[:5]
        )
        
        fast_movers = [
            {
                "product_name": f"{item['product__brand']} {item['product__model']} {item['product__variant'] or ''}".strip(),
                "units_sold": item['units_sold'],
                "revenue": float(item['revenue']),
            }
            for item in fast_movers_data
        ]
        
        # Slow movers (products with stock but no sales in last 30 days)
        stock_qs = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK",
            is_active=True
        )
        
        if location:
            stock_qs = stock_qs.filter(current_location=location)
        
        # Products with stock
        products_with_stock = set(
            stock_qs.values_list('product_id', flat=True).distinct()
        )
        
        # Products that sold recently
        products_sold_recently = set(
            sold_qs.values_list('product_id', flat=True).distinct()
        )
        
        # Slow movers = products with stock but no recent sales
        slow_product_ids = products_with_stock - products_sold_recently
        
        slow_movers_data = (
            stock_qs.filter(product_id__in=list(slow_product_ids))
            .values('product_id', 'product__brand', 'product__model', 'product__variant')
            .annotate(on_hand=Count('id'))
            .order_by('-on_hand')[:5]
        )
        
        slow_movers = [
            {
                "product_name": f"{item['product__brand']} {item['product__model']} {item['product__variant'] or ''}".strip(),
                "on_hand": item['on_hand'],
            }
            for item in slow_movers_data
        ]
        
        # Generate recommendations
        recommendations = []
        
        if fast_movers:
            top_seller = fast_movers[0]
            recommendations.append(
                f"🔥 {top_seller['product_name']} is your top seller with {top_seller['units_sold']} units sold. Keep it well-stocked!"
            )
        
        if slow_movers:
            recommendations.append(
                f"💡 {len(slow_movers)} products haven't sold in 30 days. Consider promotions or markdowns."
            )
        
        if not fast_movers and not slow_movers:
            recommendations.append("📊 Not enough data yet. Keep selling to unlock insights!")
        
        return {
            "fast_movers": fast_movers,
            "slow_movers": slow_movers,
            "recommendations": recommendations,
        }
    
    except Exception as e:
        import logging
        log = logging.getLogger(__name__)
        log.exception("Failed to get AI insights: %s", e)
        return {"fast_movers": [], "slow_movers": [], "recommendations": []}


def get_revenue_profit_summary(business, location=None, period="this_month") -> Dict[str, Any]:
    """
    Get revenue and profit summary for a given period.
    
    Args:
        business: Business instance
        location: Optional Location instance
        period: "today" | "this_week" | "this_month" | "last_30_days"
    
    Returns:
        dict with keys:
            - revenue: Decimal
            - cost: Decimal
            - profit: Decimal
            - profit_margin: int (percentage)
            - units_sold: int
            - period_label: str
    """
    from inventory.models import InventoryItem
    
    if not business:
        return {
            "revenue": Decimal("0.00"),
            "cost": Decimal("0.00"),
            "profit": Decimal("0.00"),
            "profit_margin": 0,
            "units_sold": 0,
            "period_label": period,
        }
    
    try:
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Determine date range
        if period == "today":
            start_dt = today_start
            end_dt = start_dt + timedelta(days=1)
            period_label = "Today"
        elif period == "this_week":
            # Start of week (Monday)
            start_dt = today_start - timedelta(days=today_start.weekday())
            end_dt = now
            period_label = "This Week"
        elif period == "this_month":
            start_dt = today_start.replace(day=1)
            end_dt = now
            period_label = "This Month"
        elif period == "last_30_days":
            start_dt = today_start - timedelta(days=30)
            end_dt = now
            period_label = "Last 30 Days"
        else:
            start_dt = today_start.replace(day=1)
            end_dt = now
            period_label = "This Month"
        
        # Query sold items in period
        sold_qs = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__gte=start_dt,
            sold_at__lt=end_dt
        )
        
        if location:
            sold_qs = sold_qs.filter(current_location=location)
        
        # Calculate aggregates
        totals = sold_qs.aggregate(
            revenue=Coalesce(Sum('selling_price'), Decimal('0.00'), output_field=DecimalField()),
            cost=Coalesce(Sum('order_price'), Decimal('0.00'), output_field=DecimalField()),
            units=Count('id')
        )
        
        revenue = totals['revenue'] or Decimal('0.00')
        cost = totals['cost'] or Decimal('0.00')
        profit = revenue - cost
        units_sold = totals['units'] or 0
        
        # Calculate profit margin
        profit_margin = 0
        if revenue > 0:
            profit_margin = int((profit / revenue) * 100)
        
        return {
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "profit_margin": profit_margin,
            "units_sold": units_sold,
            "period_label": period_label,
        }
    
    except Exception as e:
        import logging
        log = logging.getLogger(__name__)
        log.exception("Failed to get revenue/profit summary: %s", e)
        return {
            "revenue": Decimal("0.00"),
            "cost": Decimal("0.00"),
            "profit": Decimal("0.00"),
            "profit_margin": 0,
            "units_sold": 0,
            "period_label": period,
        }


def get_stock_battery(business, location=None) -> Dict[str, Any]:
    """
    Get stock "battery" health indicator.
    
    Args:
        business: Business instance
        location: Optional Location instance
    
    Returns:
        dict with keys:
            - level: int (0-100, percentage of healthy stock)
            - color: "red" | "yellow" | "green"
            - label: str (descriptive label)
            - units_on_hand: int
            - target_level: int (optional, if target is configured)
    """
    from inventory.models import InventoryItem
    
    if not business:
        return {
            "level": 0,
            "color": "red",
            "label": "No data",
            "units_on_hand": 0,
        }
    
    try:
        stock_qs = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK",
            is_active=True
        )
        
        if location:
            stock_qs = stock_qs.filter(current_location=location)
        
        units_on_hand = stock_qs.count()
        
        # Simple heuristic: stock battery based on absolute count
        # (Can be enhanced with target levels per product)
        if units_on_hand >= 100:
            level = 100
            color = "green"
            label = "Excellent"
        elif units_on_hand >= 50:
            level = min(100, int((units_on_hand / 100) * 100))
            color = "green"
            label = "Good"
        elif units_on_hand >= 20:
            level = int((units_on_hand / 100) * 100)
            color = "yellow"
            label = "Fair"
        else:
            level = int((units_on_hand / 100) * 100)
            color = "red"
            label = "Critical"
        
        return {
            "level": level,
            "color": color,
            "label": label,
            "units_on_hand": units_on_hand,
        }
    
    except Exception as e:
        import logging
        log = logging.getLogger(__name__)
        log.exception("Failed to get stock battery: %s", e)
        return {
            "level": 0,
            "color": "red",
            "label": "Error",
            "units_on_hand": 0,
        }


__all__ = [
    "get_stock_alerts",
    "get_cfo_alerts",
    "get_ai_insights",
    "get_revenue_profit_summary",
    "get_stock_battery",
]

