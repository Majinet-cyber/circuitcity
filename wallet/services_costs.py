# wallet/services_costs.py
"""
Cost management services for the admin wallet.
Managers can track fixed and variable costs (recurring or once-off).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Sum, Q
from django.utils import timezone

from .models import WalletTransaction, TxnType, Ledger


def get_business_costs_for_period(
    business,
    period: str = 'month',
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> dict:
    """
    Calculate total costs for a business in a given period.
    
    Args:
        business: Business instance
        period: 'month', 'week', 'year', or 'custom'
        start_date: Start date for custom period
        end_date: End date for custom period
    
    Returns:
        Dictionary with cost totals:
        {
            'fixed_costs_total': Decimal,
            'variable_costs_total': Decimal,
            'overall_costs_total': Decimal,
            'recurring_costs': Decimal,
            'once_off_costs': Decimal,
            'period_start': date,
            'period_end': date,
        }
    """
    today = timezone.localdate()
    
    # Determine period dates
    if period == 'month':
        period_start = today.replace(day=1)
        # Last day of month
        if today.month == 12:
            period_end = today.replace(month=12, day=31)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
            period_end = next_month - timedelta(days=1)
    elif period == 'week':
        # Start of week (Monday)
        period_start = today - timedelta(days=today.weekday())
        period_end = period_start + timedelta(days=6)
    elif period == 'year':
        period_start = today.replace(month=1, day=1)
        period_end = today.replace(month=12, day=31)
    elif period == 'custom' and start_date and end_date:
        period_start = start_date
        period_end = end_date
    else:
        # Default to current month
        period_start = today.replace(day=1)
        if today.month == 12:
            period_end = today.replace(month=12, day=31)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
            period_end = next_month - timedelta(days=1)
    
    # Get cost transactions for this period
    # Costs are stored as negative amounts in COMPANY ledger
    costs_qs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
        effective_date__gte=period_start,
        effective_date__lte=period_end
    )
    
    # Split by cost type (note: we need to check metadata or naming convention)
    # For now, we'll use the 'type' field to distinguish
    recurring_total = abs(
        costs_qs.filter(type=TxnType.COST_RECURRING, is_recurring=True)
        .aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    )
    
    once_off_total = abs(
        costs_qs.filter(type=TxnType.COST_ONCE_OFF, is_recurring=False)
        .aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    )
    
    # Calculate totals by category (fixed vs variable)
    # We'll use metadata or note field to distinguish fixed vs variable
    # For simplicity, we'll treat all as general costs and let the view categorize
    
    # Get all costs and categorize
    all_costs = costs_qs.values('id', 'amount', 'note', 'meta', 'is_recurring')
    
    fixed_total = Decimal('0.00')
    variable_total = Decimal('0.00')
    
    for cost in all_costs:
        cost_amount = abs(cost['amount'])
        meta = cost.get('meta', {}) or {}
        note = cost.get('note', '').lower()
        
        # Determine if fixed or variable based on metadata or note
        if meta.get('cost_category') == 'fixed' or 'fixed' in note or 'rent' in note or 'salary' in note:
            fixed_total += cost_amount
        else:
            variable_total += cost_amount
    
    overall_total = fixed_total + variable_total
    
    return {
        'fixed_costs_total': fixed_total,
        'variable_costs_total': variable_total,
        'overall_costs_total': overall_total,
        'recurring_costs': recurring_total,
        'once_off_costs': once_off_total,
        'period_start': period_start,
        'period_end': period_end,
    }


def add_business_cost(
    business,
    name: str,
    amount: Decimal,
    cost_category: str = 'variable',  # 'fixed' or 'variable'
    is_recurring: bool = False,
    effective_date: Optional[date] = None,
    created_by=None,
    note: str = '',
) -> WalletTransaction:
    """
    Add a cost entry for a business.
    
    Args:
        business: Business instance
        name: Name/description of the cost
        amount: Cost amount (positive value, will be stored as negative)
        cost_category: 'fixed' or 'variable'
        is_recurring: Whether this is a recurring cost
        effective_date: Date the cost is effective from
        created_by: User who created this cost
        note: Additional notes
    
    Returns:
        WalletTransaction instance
    """
    if effective_date is None:
        effective_date = timezone.localdate()
    
    # Costs are stored as negative amounts
    cost_amount = -abs(amount)
    
    # Determine transaction type
    txn_type = TxnType.COST_RECURRING if is_recurring else TxnType.COST_ONCE_OFF
    
    # Build note with name
    full_note = f"{name}"
    if note:
        full_note += f" - {note}"
    
    # Create transaction
    txn = WalletTransaction.objects.create(
        business=business,
        ledger=Ledger.COMPANY,
        type=txn_type,
        amount=cost_amount,
        note=full_note,
        effective_date=effective_date,
        effective_from=effective_date if is_recurring else None,
        is_recurring=is_recurring,
        created_by=created_by,
        meta={
            'cost_category': cost_category,
            'cost_name': name,
        }
    )
    try:
        from .business_memory import record_cash_bank_transaction
        from .models import CashBankTransaction

        record_cash_bank_transaction(
            business=business,
            amount=amount,
            direction=CashBankTransaction.Direction.CASH_OUT,
            category="Business expense",
            payment_method="cash",
            tx_date=effective_date,
            description=full_note,
            related_sale_reference=f"cost:{txn.pk}",
            created_by=created_by,
        )
    except Exception:
        pass
    
    return txn


def get_recurring_costs_for_month(business, year: int, month: int) -> Decimal:
    """
    Calculate total recurring costs that should be applied for a specific month.
    
    This includes:
    - Recurring costs created in or before this month
    - That are still active (no end date or end date >= month)
    
    Args:
        business: Business instance
        year: Year (e.g., 2024)
        month: Month (1-12)
    
    Returns:
        Total recurring costs for the month
    """
    from datetime import date
    
    # Get start and end of target month
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year, 12, 31)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    
    # Get all recurring costs that apply to this month
    recurring_costs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type=TxnType.COST_RECURRING,
        is_recurring=True,
        effective_from__lte=month_end  # Started on or before the month
    )
    
    total = abs(
        recurring_costs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    )
    
    return total


def get_cost_breakdown_by_category(business, start_date: date, end_date: date) -> dict:
    """
    Get a detailed breakdown of costs by category.
    
    Returns:
        {
            'fixed': [list of cost dicts],
            'variable': [list of cost dicts],
            'fixed_total': Decimal,
            'variable_total': Decimal,
        }
    """
    costs_qs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
        effective_date__gte=start_date,
        effective_date__lte=end_date
    ).order_by('-effective_date')
    
    fixed_costs = []
    variable_costs = []
    fixed_total = Decimal('0.00')
    variable_total = Decimal('0.00')
    
    for cost in costs_qs:
        cost_amount = abs(cost.amount)
        meta = cost.meta or {}
        cost_category = meta.get('cost_category', 'variable')
        
        cost_dict = {
            'id': cost.id,
            'name': meta.get('cost_name', cost.note),
            'amount': cost_amount,
            'date': cost.effective_date,
            'is_recurring': cost.is_recurring,
            'type': cost.get_type_display(),
        }
        
        if cost_category == 'fixed':
            fixed_costs.append(cost_dict)
            fixed_total += cost_amount
        else:
            variable_costs.append(cost_dict)
            variable_total += cost_amount
    
    return {
        'fixed': fixed_costs,
        'variable': variable_costs,
        'fixed_total': fixed_total,
        'variable_total': variable_total,
    }

