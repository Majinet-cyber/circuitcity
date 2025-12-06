# wallet/services_commission.py
"""
Commission wallet integration - creates wallet transactions for phone sales commissions.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .models import WalletTransaction, TxnType, Ledger
from tenants.utils_commission import get_phone_commission_pct


def record_sale_commission_to_wallet(
    sale,
    *,
    created_by=None,
    business=None
) -> Optional[WalletTransaction]:
    """
    Create a wallet transaction for a phone sale commission.
    
    This is the SINGLE SOURCE OF TRUTH for recording sale commissions to agent wallets.
    Call this after a Sale is created/finalized.
    
    Args:
        sale: Sale instance
        created_by: User who triggered the commission (optional)
        business: Business instance (optional, will be inferred from sale)
        
    Returns:
        WalletTransaction instance or None if no commission
    """
    # Get business from sale
    if not business:
        business = getattr(sale.location, "business", None) if sale.location else None
        if not business:
            # Try to get from item
            business = getattr(sale.item, "business", None)
    
    if not business:
        return None
    
    # Get commission percentage from config
    commission_pct_fraction = get_phone_commission_pct(business)
    
    # Calculate commission amount
    commission_amount = sale.price * commission_pct_fraction
    
    if commission_amount <= 0:
        return None
    
    # Create wallet transaction
    txn = WalletTransaction.objects.create(
        ledger=Ledger.AGENT,
        agent=sale.agent,
        type=TxnType.COMMISSION,
        amount=commission_amount,
        note=f"Commission for Sale #{sale.id}",
        reference=f"SALE-{sale.id}",
        effective_date=sale.sold_at,
        created_by=created_by,
        business=business,
        meta={
            "sale_id": sale.id,
            "item_id": sale.item_id,
            "sale_price": str(sale.price),
            "commission_pct": str(commission_pct_fraction * 100),  # Store as percentage for clarity
        },
    )
    
    return txn


def get_agent_commission_summary(agent, business, *, start_date=None, end_date=None):
    """
    Get commission summary for an agent in a business over a date range.
    
    Args:
        agent: User instance
        business: Business instance
        start_date: Start date (optional, defaults to first of current month)
        end_date: End date (optional, defaults to today)
        
    Returns:
        dict with commission stats
    """
    from django.db.models import Sum
    
    if not start_date:
        start_date = timezone.localdate().replace(day=1)
    if not end_date:
        end_date = timezone.localdate()
    
    commission_qs = WalletTransaction.objects.filter(
        ledger=Ledger.AGENT,
        agent=agent,
        business=business,
        type=TxnType.COMMISSION,
        effective_date__gte=start_date,
        effective_date__lte=end_date,
    )
    
    total = commission_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    count = commission_qs.count()
    
    # Get today's commissions
    today_qs = commission_qs.filter(effective_date=end_date)
    today_total = today_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    today_count = today_qs.count()
    
    # Get MTD (month-to-date)
    month_start = end_date.replace(day=1)
    mtd_qs = WalletTransaction.objects.filter(
        ledger=Ledger.AGENT,
        agent=agent,
        business=business,
        type=TxnType.COMMISSION,
        effective_date__gte=month_start,
        effective_date__lte=end_date,
    )
    mtd_total = mtd_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    mtd_count = mtd_qs.count()
    
    # Get all-time
    all_time_qs = WalletTransaction.objects.filter(
        ledger=Ledger.AGENT,
        agent=agent,
        business=business,
        type=TxnType.COMMISSION,
    )
    all_time_total = all_time_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    all_time_count = all_time_qs.count()
    
    return {
        "period_total": total,
        "period_count": count,
        "today_total": today_total,
        "today_count": today_count,
        "mtd_total": mtd_total,
        "mtd_count": mtd_count,
        "all_time_total": all_time_total,
        "all_time_count": all_time_count,
    }


def get_recent_commissions(agent, business, *, limit=10):
    """
    Get recent commission transactions for an agent.
    
    Args:
        agent: User instance
        business: Business instance
        limit: Max number of transactions to return
        
    Returns:
        QuerySet of WalletTransaction instances
    """
    return WalletTransaction.objects.filter(
        ledger=Ledger.AGENT,
        agent=agent,
        business=business,
        type=TxnType.COMMISSION,
    ).select_related("agent", "created_by").order_by("-created_at")[:limit]

