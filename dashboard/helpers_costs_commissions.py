# dashboard/helpers_costs_commissions.py
"""
Dashboard helpers for costs and commissions calculations.
Provides a consolidated view of revenue, costs, commissions, and profit for managers.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, Any

from django.db.models import Sum
from django.utils import timezone


def get_costs_and_commissions_panel(business, start_date: date, end_date: date, revenue: Decimal = None) -> Dict[str, Any]:
    """
    Calculate costs, commissions, and net profit for the manager dashboard panel.
    
    This consolidates:
    - Revenue (from sales)
    - Costs (fixed + variable, from admin wallet)
    - Commissions (paid to agents)
    - Net Profit (revenue - costs - commissions)
    
    Args:
        business: Business instance
        start_date: Period start date
        end_date: Period end date
        revenue: Pre-calculated revenue (optional, will calculate if not provided)
    
    Returns:
        Dictionary with:
        {
            'revenue_this_period': Decimal,
            'gross_profit_this_period': Decimal,
            'commissions_this_period': Decimal,
            'costs_this_period': Decimal,
            'fixed_costs': Decimal,
            'variable_costs': Decimal,
            'net_profit_this_period': Decimal,
            'profit_margin': Decimal,  # Percentage
            'period_start': date,
            'period_end': date,
        }
    """
    from django.db.models import Q
    
    # Initialize return dict
    result = {
        'revenue_this_period': Decimal('0.00'),
        'gross_profit_this_period': Decimal('0.00'),
        'commissions_this_period': Decimal('0.00'),
        'costs_this_period': Decimal('0.00'),
        'fixed_costs': Decimal('0.00'),
        'variable_costs': Decimal('0.00'),
        'net_profit_this_period': Decimal('0.00'),
        'profit_margin': Decimal('0.00'),
        'period_start': start_date,
        'period_end': end_date,
    }
    
    # ===== 1. Calculate Revenue =====
    if revenue is not None:
        result['revenue_this_period'] = revenue
    else:
        # Try to calculate from sales
        try:
            from sales.models import Sale
            sales_qs = Sale.objects.filter(
                sold_at__gte=start_date,
                sold_at__lte=end_date
            )
            
            # Scope to business if Sale model has business field
            if hasattr(Sale, 'business'):
                sales_qs = sales_qs.filter(business=business)
            elif hasattr(Sale, 'location'):
                # Scope by location.business
                sales_qs = sales_qs.filter(location__business=business)
            
            revenue_sum = sales_qs.aggregate(total=Sum('price'))['total'] or Decimal('0.00')
            result['revenue_this_period'] = revenue_sum
        except Exception:
            # Fallback: calculate from InventoryItem sold in period
            try:
                from inventory.models import InventoryItem
                sold_items = InventoryItem.objects.filter(
                    business=business,
                    status='SOLD',
                    sold_at__gte=start_date,
                    sold_at__lte=end_date
                )
                revenue_sum = sold_items.aggregate(total=Sum('selling_price'))['total'] or Decimal('0.00')
                result['revenue_this_period'] = revenue_sum
            except Exception:
                pass
    
    # ===== 2. Calculate Gross Profit =====
    # Gross Profit = Revenue - Cost of Goods Sold (order_price/cost_price)
    try:
        from inventory.models import InventoryItem
        sold_items = InventoryItem.objects.filter(
            business=business,
            status='SOLD',
            sold_at__gte=start_date,
            sold_at__lte=end_date
        )
        
        # Calculate profit: sum(selling_price - order_price)
        from django.db.models import F, Sum, ExpressionWrapper, DecimalField
        profit_expr = ExpressionWrapper(
            F('selling_price') - F('order_price'),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
        gross_profit = sold_items.aggregate(profit=Sum(profit_expr))['profit'] or Decimal('0.00')
        result['gross_profit_this_period'] = gross_profit
    except Exception:
        # Fallback: gross profit = revenue (assume 100% margin if we can't calculate COGS)
        result['gross_profit_this_period'] = result['revenue_this_period']
    
    # ===== 3. Calculate Commissions =====
    try:
        from wallet.models import WalletTransaction, TxnType, Ledger
        
        # Commissions are stored in AGENT ledger with type=COMMISSION
        commissions_qs = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.AGENT,
            type=TxnType.COMMISSION,
            effective_date__gte=start_date,
            effective_date__lte=end_date
        )
        
        commissions_total = commissions_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        # Commissions are positive amounts in agent wallet
        result['commissions_this_period'] = abs(commissions_total)
        
    except Exception:
        # Fallback: try old wallet model
        try:
            from inventory.models import WalletTxn
            wallet_txns = WalletTxn.objects.filter(
                reason='COMMISSION',
                created_at__gte=start_date,
                created_at__lte=end_date
            )
            
            # Filter by business through user memberships if possible
            try:
                from tenants.models import Membership
                agent_ids = Membership.objects.filter(
                    business=business,
                    role='AGENT'
                ).values_list('user_id', flat=True)
                wallet_txns = wallet_txns.filter(user_id__in=agent_ids)
            except Exception:
                pass
            
            commissions_total = wallet_txns.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            result['commissions_this_period'] = abs(commissions_total)
        except Exception:
            pass
    
    # ===== 4. Calculate Costs =====
    try:
        from wallet.services_costs import get_business_costs_for_period, get_cost_breakdown_by_category
        
        # Get cost breakdown
        breakdown = get_cost_breakdown_by_category(business, start_date, end_date)
        
        result['fixed_costs'] = breakdown['fixed_total']
        result['variable_costs'] = breakdown['variable_total']
        result['costs_this_period'] = breakdown['fixed_total'] + breakdown['variable_total']
        
    except Exception:
        # Try direct calculation from WalletTransaction
        try:
            from wallet.models import WalletTransaction, TxnType, Ledger
            
            costs_qs = WalletTransaction.objects.filter(
                business=business,
                ledger=Ledger.COMPANY,
                type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
                effective_date__gte=start_date,
                effective_date__lte=end_date
            )
            
            # Costs are stored as negative amounts
            costs_total = abs(costs_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'))
            result['costs_this_period'] = costs_total
            
            # Try to split by category
            fixed_costs_qs = costs_qs.filter(
                Q(meta__cost_category='fixed') | Q(note__icontains='fixed') | Q(note__icontains='rent')
            )
            fixed_total = abs(fixed_costs_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'))
            result['fixed_costs'] = fixed_total
            result['variable_costs'] = costs_total - fixed_total
            
        except Exception:
            pass
    
    # ===== 5. Calculate Net Profit =====
    # Net Profit = Gross Profit - Commissions - Costs
    result['net_profit_this_period'] = (
        result['gross_profit_this_period'] 
        - result['commissions_this_period'] 
        - result['costs_this_period']
    )
    
    # ===== 6. Calculate Profit Margin =====
    if result['revenue_this_period'] > 0:
        result['profit_margin'] = (
            (result['net_profit_this_period'] / result['revenue_this_period']) * 100
        ).quantize(Decimal('0.01'))
    else:
        result['profit_margin'] = Decimal('0.00')
    
    return result


def get_month_to_date_costs_commissions(business) -> Dict[str, Any]:
    """
    Get costs and commissions panel data for month-to-date.
    Convenience wrapper around get_costs_and_commissions_panel.
    """
    today = timezone.localdate()
    month_start = today.replace(day=1)
    
    return get_costs_and_commissions_panel(business, month_start, today)


def get_today_costs_commissions(business) -> Dict[str, Any]:
    """
    Get costs and commissions panel data for today.
    Convenience wrapper around get_costs_and_commissions_panel.
    """
    today = timezone.localdate()
    
    return get_costs_and_commissions_panel(business, today, today)

