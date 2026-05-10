# wallet/utils.py
"""
Utility functions for wallet operations and financial calculations.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional
from datetime import date

from django.db.models import Sum, Q
from django.utils import timezone

from .models import WalletTransaction, Ledger, TxnType
from .money import q2


def compute_business_costs(
    business,
    start_date: date,
    end_date: date,
) -> Dict[str, Decimal]:
    """
    Compute total costs for a business within a date range.
    
    Includes:
    - Once-off costs within the period
    - Recurring costs that are active during the period
    
    Args:
        business: Business instance
        start_date: Start of period (inclusive)
        end_date: End of period (inclusive)
    
    Returns:
        dict with keys:
            - once_off_total: Sum of one-time costs
            - recurring_total: Sum of recurring monthly costs (pro-rated if needed)
            - total: Combined total
    """
    # Once-off costs within the period
    once_off_qs = WalletTransaction.objects.filter(
        ledger=Ledger.COMPANY,
        type=TxnType.COST_ONCE_OFF,
        is_recurring=False,
        effective_date__gte=start_date,
        effective_date__lte=end_date,
    )
    if business:
        once_off_qs = once_off_qs.filter(business=business)
    
    once_off_total = once_off_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    once_off_total = abs(once_off_total)  # Costs are stored as negative, convert to positive
    
    # Recurring costs that are active during this period
    # Include costs where effective_from <= end_date
    recurring_qs = WalletTransaction.objects.filter(
        ledger=Ledger.COMPANY,
        type=TxnType.COST_RECURRING,
        is_recurring=True,
        effective_from__lte=end_date,
    )
    if business:
        recurring_qs = recurring_qs.filter(business=business)
    
    # For simplicity, sum all active recurring costs
    # In a more sophisticated system, you'd calculate how many months overlap
    recurring_total = Decimal("0.00")
    for cost in recurring_qs:
        # Check if this cost is active in our period
        if cost.effective_from <= end_date:
            # Simple approach: include full monthly cost if active anytime during period
            # More sophisticated: pro-rate based on days in period
            recurring_total += abs(cost.amount)
    
    return {
        "once_off_total": q2(once_off_total),
        "recurring_total": q2(recurring_total),
        "total": q2(once_off_total + recurring_total),
    }


def compute_revenue_costs_profit(
    business,
    revenue: Decimal,
    start_date: date,
    end_date: date,
) -> Dict[str, Decimal]:
    """
    Compute Revenue, Costs, and Profit for a business within a period.
    
    Args:
        business: Business instance
        revenue: Total revenue for the period (computed externally)
        start_date: Start of period
        end_date: End of period
    
    Returns:
        dict with keys:
            - revenue: Total revenue
            - costs: Total costs (once-off + recurring)
            - profit: Revenue minus costs
            - profit_margin: Profit as percentage of revenue
    """
    costs = compute_business_costs(business, start_date, end_date)
    total_costs = costs["total"]
    profit = q2(revenue - total_costs)
    
    # Calculate profit margin
    profit_margin = Decimal("0.00")
    if revenue > Decimal("0.00"):
        profit_margin = q2((profit / revenue) * Decimal("100.00"))
    
    return {
        "revenue": q2(revenue),
        "costs": total_costs,
        "profit": profit,
        "profit_margin": profit_margin,
        "costs_breakdown": costs,  # Include detailed breakdown
    }


def get_mtd_financial_summary(business) -> Dict[str, Decimal]:
    """
    Get month-to-date (MTD) financial summary for a business.
    
    Note: Revenue must be calculated externally based on sales data.
    This function computes costs only.
    
    Args:
        business: Business instance
    
    Returns:
        dict with keys for costs
    """
    today = timezone.localdate()
    month_start = today.replace(day=1)
    
    return compute_business_costs(business, month_start, today)


def get_agent_wallet_balance(user) -> Decimal:
    """
    Get the wallet balance for an agent (sum of all agent ledger transactions).
    
    Args:
        user: User instance
    
    Returns:
        Decimal balance
    """
    balance = WalletTransaction.objects.filter(
        ledger=Ledger.AGENT,
        agent=user,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    
    return q2(balance)
