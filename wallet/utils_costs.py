# wallet/utils_costs.py
"""Utilities for handling recurring costs and cost calculations."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from django.db.models import Sum, Q
from django.utils import timezone

from wallet.models import WalletTransaction, Ledger, TxnType


def ensure_monthly_recurring_costs(business, month_start: Optional[date] = None):
    """
    Ensure all recurring costs have instances created for the target month.
    
    This function is idempotent - it will not create duplicates if costs
    already exist for the month.
    
    Args:
        business: Business instance
        month_start: First day of the month to ensure costs for (defaults to current month)
    
    Returns:
        int: Number of recurring costs created
    """
    if not business:
        return 0
    
    # Default to current month
    if month_start is None:
        today = timezone.now().date()
        month_start = date(today.year, today.month, 1)
    
    # Ensure month_start is actually the first day of a month
    if isinstance(month_start, datetime):
        month_start = month_start.date()
    
    month_start = date(month_start.year, month_start.month, 1)
    
    # Get all recurring cost templates (original recurring costs)
    recurring_templates = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type=TxnType.COST_RECURRING,
        is_recurring=True,
        # Only costs that started on or before this month
        effective_from__lte=month_start,
    ).distinct()
    
    created_count = 0
    
    for template in recurring_templates:
        # Check if we already created a cost for this month from this template
        # We identify duplicates by:
        # - Same business
        # - Same note (cost name)
        # - Same amount
        # - effective_date is within the target month
        
        # Get last day of target month
        if month_start.month == 12:
            month_end = date(month_start.year, 12, 31)
        else:
            next_month = date(month_start.year, month_start.month + 1, 1)
            from datetime import timedelta
            month_end = next_month - timedelta(days=1)
        
        existing = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            note=template.note,
            amount=template.amount,
            effective_date__gte=month_start,
            effective_date__lte=month_end,
        ).exists()
        
        if not existing:
            # Create a new instance for this month
            WalletTransaction.objects.create(
                business=business,
                ledger=Ledger.COMPANY,
                type=TxnType.COST_RECURRING,
                amount=template.amount,  # Already negative
                note=template.note,
                is_recurring=False,  # The instance is not recurring, only the template is
                effective_date=month_start,
                created_by=template.created_by,
                meta={
                    'auto_created': True,
                    'recurring_template_id': template.id,
                    'month': month_start.isoformat(),
                }
            )
            created_count += 1
    
    return created_count


def get_business_costs_for_period(
    business,
    start_date: date,
    end_date: date,
) -> dict:
    """
    Calculate total costs for a business within a date range.
    
    Args:
        business: Business instance
        start_date: Start of period (inclusive)
        end_date: End of period (inclusive)
    
    Returns:
        dict with keys:
            - once_off_total: Sum of one-time costs
            - recurring_total: Sum of recurring costs (actual instances, not templates)
            - total: Combined total
            - period_start: start_date
            - period_end: end_date
    """
    if not business:
        return {
            'once_off_total': Decimal('0.00'),
            'recurring_total': Decimal('0.00'),
            'total': Decimal('0.00'),
            'period_start': start_date,
            'period_end': end_date,
        }
    
    # Once-off costs within the period
    once_off_qs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type=TxnType.COST_ONCE_OFF,
        effective_date__gte=start_date,
        effective_date__lte=end_date,
    )
    
    once_off_total = once_off_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    once_off_total = abs(once_off_total)  # Costs are stored as negative, convert to positive
    
    # Recurring costs (instances) within the period
    # These are the auto-created monthly instances, not the templates
    recurring_qs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type=TxnType.COST_RECURRING,
        is_recurring=False,  # Instances, not templates
        effective_date__gte=start_date,
        effective_date__lte=end_date,
    )
    
    recurring_total = recurring_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    recurring_total = abs(recurring_total)
    
    total = once_off_total + recurring_total
    
    return {
        'once_off_total': once_off_total,
        'recurring_total': recurring_total,
        'total': total,
        'period_start': start_date,
        'period_end': end_date,
    }


def get_cost_breakdown_by_category(
    business,
    start_date: date,
    end_date: date
) -> dict:
    """
    Get cost breakdown by category for a business in a period.
    
    Returns:
        dict with category names as keys and Decimal amounts as values
    """
    if not business:
        return {}
    
    costs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
        effective_date__gte=start_date,
        effective_date__lte=end_date,
    )
    
    # Group by note (cost name) for now
    # In future, could add a category field to WalletTransaction
    breakdown = {}
    for cost in costs:
        category = cost.note or 'Uncategorized'
        amount = abs(cost.amount)
        breakdown[category] = breakdown.get(category, Decimal('0.00')) + amount
    
    return breakdown

