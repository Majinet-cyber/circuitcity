# dashboard/dashboard_metrics.py
"""
Unified dashboard metrics helper for all verticals.
Provides consistent Revenue/Costs/Profit and Payment Mix calculations.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any
from datetime import date

from django.db.models import Sum, Q, Case, When, Value, DecimalField
from django.utils import timezone


def get_payment_mix(sales_queryset, payment_method_field='payment_method') -> Dict[str, Decimal]:
    """
    Calculate payment mix breakdown from a sales queryset.
    
    Args:
        sales_queryset: Queryset of sale objects
        payment_method_field: Name of the payment_method field
    
    Returns:
        dict with keys: CASH, BANK, MOBILE_MONEY, total
    """
    # Aggregate by payment method
    try:
        mix = sales_queryset.values(payment_method_field).annotate(
            total=Sum('price' if hasattr(sales_queryset.model, 'price') else 'total_price')
        )
        
        cash = Decimal("0.00")
        bank = Decimal("0.00")
        mobile_money = Decimal("0.00")
        
        for item in mix:
            method = (item.get(payment_method_field) or "CASH").upper()
            amount = Decimal(str(item.get('total') or "0.00"))
            
            if method == "CASH":
                cash += amount
            elif method == "BANK":
                bank += amount
            elif method in ("MOBILE_MONEY", "MOBILEMONEY", "MOBILE"):
                mobile_money += amount
        
        total = cash + bank + mobile_money
        
        return {
            "CASH": cash,
            "BANK": bank,
            "MOBILE_MONEY": mobile_money,
            "total": total,
        }
    except Exception:
        return {
            "CASH": Decimal("0.00"),
            "BANK": Decimal("0.00"),
            "MOBILE_MONEY": Decimal("0.00"),
            "total": Decimal("0.00"),
        }


def add_profit_context(
    context: Dict[str, Any],
    business,
    revenue: Decimal,
    start_date: date,
    end_date: date,
    period_label: str = "MTD",
) -> Dict[str, Any]:
    """
    Add Revenue/Costs/Profit metrics to dashboard context.
    
    Args:
        context: Existing dashboard context dict
        business: Business instance
        revenue: Calculated revenue for the period
        start_date: Period start date
        end_date: Period end date
        period_label: Label for display (e.g., "MTD", "Today", "Last 7 Days")
    
    Returns:
        Updated context dict
    """
    try:
        from wallet.utils import compute_revenue_costs_profit
        
        metrics = compute_revenue_costs_profit(business, revenue, start_date, end_date)
        
        context['revenue'] = metrics['revenue']
        context['costs'] = metrics['costs']
        context['profit'] = metrics['profit']
        context['profit_margin'] = metrics['profit_margin']
        context['costs_breakdown'] = metrics['costs_breakdown']
        context['period'] = period_label
        
    except Exception as e:
        # Graceful fallback if wallet app is not available
        context['revenue'] = revenue
        context['costs'] = Decimal("0.00")
        context['profit'] = revenue
        context['profit_margin'] = Decimal("100.00") if revenue > 0 else Decimal("0.00")
        context['period'] = period_label
        
    return context


def add_payment_mix_context(
    context: Dict[str, Any],
    sales_queryset,
    period_label: str = "MTD",
) -> Dict[str, Any]:
    """
    Add payment mix breakdown to dashboard context.
    
    Args:
        context: Existing dashboard context dict
        sales_queryset: Queryset of sales for the period
        period_label: Label for display
    
    Returns:
        Updated context dict
    """
    try:
        payment_mix = get_payment_mix(sales_queryset)
        context['payment_mix'] = payment_mix
        context['period'] = period_label
    except Exception:
        context['payment_mix'] = {
            "CASH": Decimal("0.00"),
            "BANK": Decimal("0.00"),
            "MOBILE_MONEY": Decimal("0.00"),
            "total": Decimal("0.00"),
        }
    
    return context


def get_mtd_dates():
    """
    Get month-to-date start and end dates.
    
    Returns:
        tuple: (start_date, end_date)
    """
    today = timezone.localdate()
    month_start = today.replace(day=1)
    return month_start, today


def get_today_dates():
    """
    Get today's date as both start and end.
    
    Returns:
        tuple: (today, today)
    """
    today = timezone.localdate()
    return today, today


# Example integration for inventory dashboard:
"""
from dashboard.dashboard_metrics import add_profit_context, add_payment_mix_context, get_mtd_dates

# In your dashboard view:
start_date, end_date = get_mtd_dates()

# Calculate revenue (existing logic)
sales_qs = Sale.objects.filter(business=business, sold_at__gte=start_date, sold_at__lte=end_date)
revenue = sales_qs.aggregate(total=Sum('price'))['total'] or Decimal("0.00")

# Add profit metrics
context = add_profit_context(context, business, revenue, start_date, end_date, "MTD")

# Add payment mix
context = add_payment_mix_context(context, sales_qs, "MTD")

# In template:
{% include "partials/profit_panel.html" %}
{% include "partials/payment_mix_panel.html" %}
"""

