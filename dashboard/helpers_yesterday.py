# dashboard/helpers_yesterday.py
"""
Yesterday summary helper for dashboard.
Shows business activity from the previous day on first visit of new day.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from django.db.models import Sum, Count, Q
from django.utils import timezone


def get_yesterday_summary(user, business) -> Optional[dict]:
    """
    Get a summary of yesterday's activity for the business.
    
    Args:
        user: Django User object (for potential future agent-scoped summaries)
        business: Business object
    
    Returns:
        dict or None with keys:
            - date: date object for yesterday
            - sales_count: int
            - total_revenue: Decimal
            - payment_mix: list of dicts with 'method', 'count', 'amount'
        
        Returns None if no data or business is None.
    """
    if not business:
        return None
    
    try:
        from sales.models import Sale, PaymentMethod
        from tenants.models import set_current_business_id, get_current_business_id
        
        yesterday = timezone.localdate() - timedelta(days=1)
        
        # Set business context
        prev_bid = get_current_business_id()
        set_current_business_id(business.pk)
        
        try:
            # Get sales from yesterday
            sales_qs = Sale.objects.filter(sold_at=yesterday)
            
            sales_count = sales_qs.count()
            
            # If no sales, return minimal summary
            if sales_count == 0:
                return {
                    "date": yesterday,
                    "sales_count": 0,
                    "total_revenue": 0,
                    "payment_mix": [],
                }
            
            # Total revenue
            total_revenue = sales_qs.aggregate(total=Sum("price"))["total"] or 0
            
            # Payment mix breakdown
            payment_mix = []
            for method_code, method_display in PaymentMethod.choices:
                method_qs = sales_qs.filter(payment_method=method_code)
                method_count = method_qs.count()
                if method_count > 0:
                    method_amount = method_qs.aggregate(total=Sum("price"))["total"] or 0
                    payment_mix.append({
                        "method": method_display,
                        "method_code": method_code,
                        "count": method_count,
                        "amount": float(method_amount),
                    })
            
            return {
                "date": yesterday,
                "sales_count": sales_count,
                "total_revenue": float(total_revenue),
                "payment_mix": payment_mix,
            }
        
        finally:
            set_current_business_id(prev_bid)
    
    except Exception:
        # Gracefully handle missing models or query errors
        return None


def should_show_yesterday_summary(request) -> bool:
    """
    Determine if the yesterday summary should be shown.
    
    Logic:
        - Show once per calendar day (first visit of the day)
        - Track using session: 'last_summary_date'
        - If today's date != stored date, show summary and update
    
    Args:
        request: HttpRequest object (for session access)
    
    Returns:
        bool: True if summary should be shown
    """
    if not request or not hasattr(request, 'session'):
        return False
    
    try:
        today_str = timezone.localdate().isoformat()
        last_shown = request.session.get('last_summary_date')
        
        # If never shown or shown on a different date, show it
        return last_shown != today_str
    
    except Exception:
        return False


def mark_yesterday_summary_shown(request) -> None:
    """
    Mark that the yesterday summary was shown today.
    Updates session with current date.
    
    Args:
        request: HttpRequest object
    """
    if not request or not hasattr(request, 'session'):
        return
    
    try:
        today_str = timezone.localdate().isoformat()
        request.session['last_summary_date'] = today_str
    except Exception:
        pass

