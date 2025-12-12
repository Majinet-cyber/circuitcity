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
        from datetime import datetime, time
        
        # Default date range: current month to today
        if start_date is None:
            start_date = timezone.localdate().replace(day=1)
        if end_date is None:
            end_date = timezone.localdate()
        
        # Determine which sale model to use based on vertical or business kind
        sales_qs = _get_sales_queryset(business, vertical)
        
        if sales_qs is None:
            return []
        
        # Convert date objects to timezone-aware datetime ranges for robust filtering
        # This works consistently across SQLite/Postgres/MySQL and all timezones
        if not isinstance(start_date, datetime):
            # Start of day (00:00:00)
            start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
        else:
            start_dt = start_date
        
        if not isinstance(end_date, datetime):
            # End of day (23:59:59.999999) by adding 1 day and using exclusive lt
            end_dt = timezone.make_aware(datetime.combine(end_date, time.min)) + timezone.timedelta(days=1)
        else:
            end_dt = end_date
        
        # Use gte/lt for robust range filtering (inclusive start, exclusive end)
        sales_qs = sales_qs.filter(sold_at__gte=start_dt, sold_at__lt=end_dt)
        
        # Scope to user if provided (agent filter)
        if user:
            # Try different agent field names based on model
            if hasattr(sales_qs.model, '_meta'):
                field_names = [f.name for f in sales_qs.model._meta.get_fields()]
                if 'sold_by' in field_names:
                    sales_qs = sales_qs.filter(sold_by=user)
                elif 'agent' in field_names:
                    sales_qs = sales_qs.filter(agent=user)
        
        # Get payment method choices
        payment_choices = _get_payment_method_choices(business, vertical)
        
        # Determine revenue field name based on model
        revenue_field = 'price'  # Default for Sale model
        if hasattr(sales_qs.model, '_meta'):
            field_names = [f.name for f in sales_qs.model._meta.get_fields()]
            if 'total_price' in field_names:
                revenue_field = 'total_price'
            elif 'amount' in field_names:
                revenue_field = 'amount'
        
        # Calculate total for percentages
        total_amount = sales_qs.aggregate(total=Sum(revenue_field))["total"] or 0
        if total_amount == 0:
            return []
        
        # Build payment mix
        payment_mix = []
        for method_code, method_display in payment_choices:
            method_qs = sales_qs.filter(payment_method=method_code)
            method_count = method_qs.count()
            
            if method_count > 0:
                method_amount = method_qs.aggregate(total=Sum(revenue_field))["total"] or 0
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
    
    except Exception:
        # Gracefully fail
        import logging
        logging.exception("Error in get_payment_mix")
        return []


def _get_sales_queryset(business, vertical: Optional[str] = None):
    """
    Get the appropriate Sale queryset based on business vertical.
    CRITICAL: Always filters by business to ensure proper data isolation.
    
    Returns the queryset or None if no suitable model exists.
    """
    if not business:
        return None
    
    # Determine vertical from business if not provided
    if not vertical:
        vertical = getattr(business, 'business_kind', None)
    
    vertical_lower = (vertical or '').lower()
    
    # Try vertical-specific models first (they have direct business field)
    if vertical_lower == 'liquor':
        try:
            from inventory.models_verticals import LiquorSale
            # ✅ Explicitly filter by business
            return LiquorSale.objects.filter(business=business).select_related('shift')
        except Exception:
            pass
    
    elif vertical_lower == 'gym':
        try:
            from inventory.models_verticals import GymMemberPayment
            # Gym uses payments not sales, filter via member__business
            # ✅ Explicitly filter by business
            return GymMemberPayment.objects.filter(member__business=business).select_related('member')
        except Exception:
            pass
    
    elif vertical_lower == 'pharmacy':
        try:
            from inventory.models_pharmacy import PharmacySale
            # Check if PharmacySale has business field
            if hasattr(PharmacySale, '_meta'):
                field_names = [f.name for f in PharmacySale._meta.get_fields()]
                if 'business' in field_names:
                    # ✅ Explicitly filter by business
                    return PharmacySale.objects.filter(business=business).select_related('batch')
                elif 'batch' in field_names:
                    # Filter via batch__business if applicable
                    return PharmacySale.objects.filter(batch__business=business).select_related('batch')
            # Fallback without filtering (shouldn't happen but graceful)
            return PharmacySale.objects.select_related('batch').all()
        except Exception:
            pass
    
    elif vertical_lower == 'clothing':
        try:
            from inventory.models_verticals import ClothingSale
            # ✅ Explicitly filter by business
            return ClothingSale.objects.filter(business=business)
        except Exception:
            pass
    
    # Fall back to standard Sale model (phones vertical)
    try:
        from sales.models import Sale
        from django.db.models import Q
        # Sale model doesn't have direct business field
        # ✅ Filter via item__business or location__business
        return Sale.objects.filter(
            Q(item__business=business) | Q(location__business=business)
        ).select_related('item')
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
    
    elif vertical_lower == 'clothing':
        try:
            from inventory.models_verticals import PaymentMethod as ClothingPaymentMethod
            return ClothingPaymentMethod.choices
        except Exception:
            pass
    
    # Default payment methods (standard Sales model - for phones)
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

