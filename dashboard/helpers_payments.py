# dashboard/helpers_payments.py
"""
Payment mix helper for dashboard and sales views.
Provides breakdown of sales by payment method.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, List, Dict, Any

from django.db.models import Sum, Count
from django.utils import timezone


def get_payment_mix(
    business,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    user=None,
    vertical: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get payment method breakdown for sales.
    
    Supports multiple verticals (phones, liquor, gym, pharmacy, etc.).
    
    Args:
        business: Business object (required)
        start_date: Start date for filtering (default: start of current month)
        end_date: End date for filtering (default: today)
        user: Optional user to scope to agent-level (for POS views)
        vertical: Optional vertical hint ('liquor', 'gym', 'pharmacy', etc.)
    
    Returns:
        List of dicts with keys:
            - method: str (display name)
            - method_code: str (internal code)
            - amount: float
            - count: int
            - percentage: float (0-100)
    """
    if not business:
        return []
    
    try:
        from tenants.models import set_current_business_id, get_current_business_id
        
        # Default date range: current month to today
        if start_date is None:
            start_date = timezone.localdate().replace(day=1)
        if end_date is None:
            end_date = timezone.localdate()
        
        # Set business context
        prev_bid = get_current_business_id()
        set_current_business_id(business.pk)
        
        try:
            # Determine which sale model to use based on vertical or business kind
            sales_qs = _get_sales_queryset(business, vertical)
            
            if sales_qs is None:
                return []
            
            # Filter by date range
            sales_qs = sales_qs.filter(sold_at__gte=start_date, sold_at__lte=end_date)
            
            # Scope to user if provided
            if user:
                sales_qs = sales_qs.filter(agent=user)
            
            # Get payment method choices
            payment_choices = _get_payment_method_choices(business, vertical)
            
            # Calculate total for percentages
            total_amount = sales_qs.aggregate(total=Sum("price"))["total"] or 0
            if total_amount == 0:
                return []
            
            # Build payment mix
            payment_mix = []
            for method_code, method_display in payment_choices:
                method_qs = sales_qs.filter(payment_method=method_code)
                method_count = method_qs.count()
                
                if method_count > 0:
                    method_amount = method_qs.aggregate(total=Sum("price"))["total"] or 0
                    percentage = (float(method_amount) / float(total_amount) * 100) if total_amount > 0 else 0
                    
                    payment_mix.append({
                        "method": method_display,
                        "method_code": method_code,
                        "amount": float(method_amount),
                        "count": method_count,
                        "percentage": round(percentage, 1),
                    })
            
            # Sort by amount descending
            payment_mix.sort(key=lambda x: x["amount"], reverse=True)
            
            return payment_mix
        
        finally:
            set_current_business_id(prev_bid)
    
    except Exception:
        # Gracefully fail
        return []


def _get_sales_queryset(business, vertical: Optional[str] = None):
    """
    Get the appropriate Sale queryset based on business vertical.
    
    Returns the queryset or None if no suitable model exists.
    """
    # Determine vertical from business if not provided
    if not vertical:
        vertical = getattr(business, 'business_kind', None)
    
    vertical_lower = (vertical or '').lower()
    
    # Try vertical-specific models first
    if vertical_lower == 'liquor':
        try:
            from inventory.models_verticals import LiquorSale
            return LiquorSale.objects.select_related('shift').all()
        except Exception:
            pass
    
    elif vertical_lower == 'gym':
        try:
            from inventory.models_verticals import GymMemberPayment
            # Gym uses payments not sales, map to similar structure
            return GymMemberPayment.objects.select_related('member').all()
        except Exception:
            pass
    
    elif vertical_lower == 'pharmacy':
        try:
            from inventory.models_pharmacy import PharmacySale
            return PharmacySale.objects.select_related('batch').all()
        except Exception:
            pass
    
    elif vertical_lower == 'clothing':
        try:
            from inventory.models_verticals import ClothingSale
            return ClothingSale.objects.all()
        except Exception:
            pass
    
    # Fall back to standard Sale model
    try:
        from sales.models import Sale
        return Sale.objects.select_related('item').all()
    except Exception:
        return None


def _get_payment_method_choices(business, vertical: Optional[str] = None):
    """
    Get payment method choices based on vertical.
    
    Returns list of tuples: [(code, display), ...]
    """
    # Determine vertical
    if not vertical:
        vertical = getattr(business, 'business_kind', None)
    
    vertical_lower = (vertical or '').lower()
    
    # Try to get choices from appropriate model
    if vertical_lower == 'liquor':
        try:
            from inventory.models_verticals import PaymentMethod as LiquorPaymentMethod
            return LiquorPaymentMethod.choices
        except Exception:
            pass
    
    elif vertical_lower == 'gym':
        try:
            from inventory.models_verticals import GymMemberPayment
            # Gym may have different payment method field
            if hasattr(GymMemberPayment, 'PAYMENT_METHOD_CHOICES'):
                return GymMemberPayment.PAYMENT_METHOD_CHOICES
        except Exception:
            pass
    
    elif vertical_lower == 'pharmacy':
        try:
            from inventory.models_pharmacy import PharmacySale
            if hasattr(PharmacySale, 'PAYMENT_METHOD_CHOICES'):
                return PharmacySale.PAYMENT_METHOD_CHOICES
        except Exception:
            pass
    
    # Default payment methods (standard Sales model)
    try:
        from sales.models import PaymentMethod
        return PaymentMethod.choices
    except Exception:
        # Ultimate fallback
        return [
            ("CASH", "Cash"),
            ("BANK", "Bank"),
            ("MOBILE_MONEY", "Mobile Money"),
        ]


def get_payment_mix_for_dashboard(business, period_days: int = 30, user=None) -> List[Dict[str, Any]]:
    """
    Convenience wrapper for dashboard payment mix display.
    
    Args:
        business: Business object
        period_days: Number of days to look back (default: 30)
        user: Optional user for agent-scoped view
    
    Returns:
        Payment mix list (see get_payment_mix for format)
    """
    end_date = timezone.localdate()
    start_date = end_date - timezone.timedelta(days=period_days)
    
    return get_payment_mix(
        business=business,
        start_date=start_date,
        end_date=end_date,
        user=user
    )

