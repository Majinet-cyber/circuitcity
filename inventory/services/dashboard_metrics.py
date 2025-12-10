# inventory/services/dashboard_metrics.py
"""
Single source of truth for all dashboard KPIs and ratios.
Computes Revenue, Costs (COGS + Admin), Profit, and all ratios.
"""
from decimal import Decimal
from typing import Optional
import logging

from django.db.models import Sum, Q, F, Value, DecimalField, ExpressionWrapper, QuerySet
from django.db.models.functions import Coalesce
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_inventory_kpis(
    *,
    business,
    location=None,
    sales_qs: QuerySet,
    start_date=None,
    end_date=None,
    model_filter: Optional[int] = None,
) -> dict:
    """
    Returns a dict with all dashboard KPIs and ratios for the inventory dashboard.
    All numbers respect tenant/business, location, and current filters.
    
    Args:
        business: Business instance (required for admin costs)
        location: Location instance (optional, for location-specific scoping)
        sales_qs: Pre-filtered QuerySet of Sale objects (already scoped by business/agent/period)
        start_date: Start date for period filter (for admin costs)
        end_date: End date for period filter (for admin costs)
        model_filter: Product ID if filtering by model (optional)
    
    Returns:
        dict with keys:
            - total_revenue (Decimal)
            - total_costs (Decimal) - includes COGS + admin costs
            - total_cogs (Decimal) - cost of goods sold only
            - total_admin_costs (Decimal) - admin wallet costs only
            - total_profit (Decimal)
            - profit_margin (float) - percentage
            
            # Revenue vs Costs ratios
            - rev_vs_costs_pct_revenue (int)
            - rev_vs_costs_pct_costs (int)
            
            # Profit vs Costs ratios
            - profit_vs_costs_pct_profit (int)
            - profit_vs_costs_pct_costs (int)
            - profit_vs_costs_warning (bool) - True if costs > 10% of revenue
            
            # Payment Mix
            - payment_mix_cash_pct (int)
            - payment_mix_bank_pct (int)
            - payment_mix_mobile_pct (int)
            - payment_mix_cash_amount (Decimal)
            - payment_mix_bank_amount (Decimal)
            - payment_mix_mobile_amount (Decimal)
            - payment_mix_total (Decimal)
    """
    dec2 = DecimalField(max_digits=14, decimal_places=2)
    
    # ================================================================
    # 1. REVENUE from sales (already filtered by period/model/agent)
    # ================================================================
    revenue_agg = sales_qs.aggregate(
        revenue=Coalesce(Sum("price"), Value(0), output_field=dec2)
    )
    total_revenue = Decimal(str(revenue_agg.get("revenue") or 0))
    
    # ================================================================
    # 2. COSTS = COGS (from items) + ADMIN COSTS (from wallet)
    # ================================================================
    
    # 2a. COGS (Cost of Goods Sold) - from item order prices
    cogs_agg = sales_qs.aggregate(
        cogs=Coalesce(
            Sum(Coalesce(F("item__order_price"), Value(0), output_field=dec2)),
            Value(0),
            output_field=dec2
        )
    )
    total_cogs = Decimal(str(cogs_agg.get("cogs") or 0))
    
    # 2b. ADMIN COSTS (from WalletTransaction)
    total_admin_costs = Decimal("0.00")
    
    try:
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        if business and start_date and end_date:
            # Convert datetime to date for comparison with DateField
            start_d = start_date.date() if hasattr(start_date, 'date') else start_date
            end_d = end_date.date() if hasattr(end_date, 'date') else end_date
            
            # Query admin costs for this business and period
            admin_costs_qs = WalletTransaction.objects.filter(
                business=business,
                ledger=Ledger.COMPANY,
                type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
            )
            
            # Filter by effective date range
            # For once-off costs: use effective_date within period
            once_off_q = Q(
                type=TxnType.COST_ONCE_OFF,
                is_recurring=False,
                effective_date__gte=start_d,
                effective_date__lte=end_d,
            )
            
            # For recurring costs: include if effective_from <= end_date
            # (assumes they continue indefinitely once started)
            recurring_q = Q(
                type=TxnType.COST_RECURRING,
                is_recurring=True,
                effective_from__lte=end_d,
            )
            
            period_costs_qs = admin_costs_qs.filter(once_off_q | recurring_q)
            
            # Sum costs (they're stored as negative, so we take absolute value)
            costs_agg = period_costs_qs.aggregate(
                total=Coalesce(Sum("amount"), Value(0), output_field=dec2)
            )
            admin_costs_sum = Decimal(str(costs_agg.get("total") or 0))
            total_admin_costs = abs(admin_costs_sum)  # Convert to positive for display
            
            logger.debug(
                "Admin costs for business=%s, period=%s to %s: %s (from %d transactions)",
                business.id if business else None,
                start_date,
                end_date,
                total_admin_costs,
                period_costs_qs.count(),
            )
    
    except ImportError:
        logger.warning("WalletTransaction not available, admin costs will be 0")
    except Exception as e:
        logger.exception("Error computing admin costs: %s", e)
    
    # Total costs = COGS + Admin Costs
    total_costs = total_cogs + total_admin_costs
    
    # ================================================================
    # 3. PROFIT = Revenue - Total Costs
    # ================================================================
    total_profit = total_revenue - total_costs
    
    # Profit margin percentage
    profit_margin = float((total_profit / total_revenue) * 100) if total_revenue > 0 else 0.0
    
    # ================================================================
    # 4. REVENUE VS COSTS RATIOS
    # ================================================================
    # Revenue% = revenue / (revenue + costs) * 100
    # Costs%   = costs   / (revenue + costs) * 100
    total_rev_cost = total_revenue + total_costs
    if total_rev_cost > 0:
        rev_vs_costs_pct_revenue = int(round((total_revenue / total_rev_cost) * 100))
        rev_vs_costs_pct_costs = 100 - rev_vs_costs_pct_revenue
    else:
        rev_vs_costs_pct_revenue = 0
        rev_vs_costs_pct_costs = 0
    
    # ================================================================
    # 5. PROFIT VS COSTS RATIOS + WARNING
    # ================================================================
    # Profit% = profit / (profit + costs) * 100 (only if profit > 0)
    # Costs%  = costs  / (profit + costs) * 100
    profit_for_ratio = max(total_profit, Decimal("0.00"))
    total_profit_cost = profit_for_ratio + total_costs
    
    if total_profit_cost > 0:
        profit_vs_costs_pct_profit = int(round((profit_for_ratio / total_profit_cost) * 100))
        profit_vs_costs_pct_costs = 100 - profit_vs_costs_pct_profit
    else:
        profit_vs_costs_pct_profit = 0
        profit_vs_costs_pct_costs = 0
    
    # Warning: costs > 10% of revenue (low margin)
    profit_vs_costs_warning = False
    if total_revenue > 0:
        cost_percentage_of_revenue = (total_costs / total_revenue) * 100
        if cost_percentage_of_revenue > 10:
            profit_vs_costs_warning = True
    
    # ================================================================
    # 6. PAYMENT MIX (Cash / Bank / Mobile Money)
    # ================================================================
    payment_agg = sales_qs.aggregate(
        cash=Coalesce(Sum("price", filter=Q(payment_method="CASH")), Value(0), output_field=dec2),
        bank=Coalesce(Sum("price", filter=Q(payment_method="BANK")), Value(0), output_field=dec2),
        mobile=Coalesce(Sum("price", filter=Q(payment_method="MOBILE_MONEY")), Value(0), output_field=dec2),
    )
    
    cash_amount = Decimal(str(payment_agg.get("cash") or 0))
    bank_amount = Decimal(str(payment_agg.get("bank") or 0))
    mobile_amount = Decimal(str(payment_agg.get("mobile") or 0))
    payment_mix_total = cash_amount + bank_amount + mobile_amount
    
    # Calculate percentages (ensure they sum to 100)
    if payment_mix_total > 0:
        cash_pct = int(round((cash_amount / payment_mix_total) * 100))
        bank_pct = int(round((bank_amount / payment_mix_total) * 100))
        # Last one takes remainder to avoid rounding drift
        mobile_pct = 100 - cash_pct - bank_pct
    else:
        cash_pct = bank_pct = mobile_pct = 0
    
    # ================================================================
    # 7. LOGGING
    # ================================================================
    logger.info(
        "Dashboard KPIs [business=%s, period=%s to %s]: revenue=%s, cogs=%s, admin_costs=%s, "
        "total_costs=%s, profit=%s, margin=%.1f%%",
        business.id if business else None,
        start_date,
        end_date,
        total_revenue,
        total_cogs,
        total_admin_costs,
        total_costs,
        total_profit,
        profit_margin,
    )
    
    logger.info(
        "Payment mix: cash=%s (%.0f%%), bank=%s (%.0f%%), mobile=%s (%.0f%%)",
        cash_amount, cash_pct,
        bank_amount, bank_pct,
        mobile_amount, mobile_pct,
    )
    
    if profit_vs_costs_warning:
        logger.warning(
            "⚠ Low margin warning: costs (%.1f%%) > 10%% of revenue",
            cost_percentage_of_revenue if total_revenue > 0 else 0
        )
    
    # ================================================================
    # 8. RETURN COMPLETE KPI DICT
    # ================================================================
    return {
        # Core metrics
        "total_revenue": total_revenue,
        "total_costs": total_costs,
        "total_cogs": total_cogs,
        "total_admin_costs": total_admin_costs,
        "total_profit": total_profit,
        "profit_margin": profit_margin,
        
        # Revenue vs Costs
        "rev_vs_costs_pct_revenue": rev_vs_costs_pct_revenue,
        "rev_vs_costs_pct_costs": rev_vs_costs_pct_costs,
        
        # Profit vs Costs
        "profit_vs_costs_pct_profit": profit_vs_costs_pct_profit,
        "profit_vs_costs_pct_costs": profit_vs_costs_pct_costs,
        "profit_vs_costs_warning": profit_vs_costs_warning,
        
        # Payment Mix
        "payment_mix_cash_pct": cash_pct,
        "payment_mix_bank_pct": bank_pct,
        "payment_mix_mobile_pct": mobile_pct,
        "payment_mix_cash_amount": cash_amount,
        "payment_mix_bank_amount": bank_amount,
        "payment_mix_mobile_amount": mobile_amount,
        "payment_mix_total": payment_mix_total,
    }

