# core/utils_payment_mix.py
"""
PAYMENT MIX - SINGLE SOURCE OF TRUTH

Provides standardized payment mix calculation for ALL verticals.
Returns data in format compatible with partials/payment_mix_bar_standard.html

Usage:
    from core.utils_payment_mix import build_payment_mix
    
    # In any dashboard view
    payment_mix = build_payment_mix(
        business=request.business,
        sales_qs=Sale.objects.filter(business=request.business, ...),
    )
    
    # In template
    {% include "partials/payment_mix_bar_standard.html" with payment_mix=payment_mix range_label="Today" %}
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models import QuerySet


# Payment method display mapping
PAYMENT_METHOD_DISPLAY = {
    "CASH": "Cash",
    "cash": "Cash",
    "BANK": "Bank",
    "bank": "Bank",
    "MOBILE_MONEY": "Mobile Money",
    "mobile_money": "Mobile Money",
    "MOBILE": "Mobile Money",
    "mobile": "Mobile Money",
    "CARD": "Card",
    "card": "Card",
    "MIXED": "Mixed",
    "mixed": "Mixed",
    "OTHER": "Other",
    "other": "Other",
}


def normalize_payment_method(raw_method: str) -> str:
    """
    Normalize payment method to canonical form.

    Args:
        raw_method: Raw payment method string

    Returns:
        str: Normalized method code (CASH, BANK, MOBILE_MONEY, etc.)
    """
    if not raw_method:
        return "CASH"

    method = str(raw_method).strip().upper()

    # Normalize variants
    if method in ("MOBILE", "MPAMBA", "AIRTEL_MONEY", "TNM_MPAMBA"):
        return "MOBILE_MONEY"

    if method in ("CARD", "DEBIT", "CREDIT"):
        return "BANK"

    return method


def get_display_name(method_code: str) -> str:
    """
    Get human-readable display name for payment method.

    Args:
        method_code: Payment method code

    Returns:
        str: Display name
    """
    return PAYMENT_METHOD_DISPLAY.get(method_code, method_code.replace("_", " ").title())


def build_payment_mix(
    business,
    sales_qs: "QuerySet",
    payment_field: str = "payment_method",
    amount_field: str = "total_amount",
) -> List[Dict]:
    """
    Build standardized payment mix data structure.

    Args:
        business: Business instance (for context, not used currently)
        sales_qs: QuerySet of sales to analyze
        payment_field: Name of payment method field (default: "payment_method")
        amount_field: Name of amount field (default: "total_amount")

    Returns:
        List of dicts with keys:
            - method: str (display name)
            - method_code: str (internal code)
            - amount: Decimal (total for this method)
            - count: int (number of transactions)
            - percentage: float (0-100)

    Example return:
        [
            {
                "method": "Cash",
                "method_code": "CASH",
                "amount": Decimal("150000.00"),
                "count": 45,
                "percentage": 62.5
            },
            ...
        ]
    """
    from django.db.models import Sum, Count, Q
    from collections import defaultdict

    # Initialize result structure
    payment_data = defaultdict(lambda: {"amount": Decimal("0.00"), "count": 0})

    # Group by payment method
    try:
        # Get aggregated data per payment method
        aggregates = sales_qs.values(payment_field).annotate(total=Sum(amount_field), count=Count("id"))

        for agg in aggregates:
            method_raw = agg.get(payment_field, "CASH")
            method_code = normalize_payment_method(method_raw)

            payment_data[method_code]["amount"] += Decimal(str(agg.get("total") or 0))
            payment_data[method_code]["count"] += int(agg.get("count") or 0)
    except Exception as e:
        # Fallback: iterate manually if aggregation fails
        try:
            for sale in sales_qs:
                method_raw = getattr(sale, payment_field, "CASH")
                method_code = normalize_payment_method(method_raw)
                amount = getattr(sale, amount_field, Decimal("0.00"))

                payment_data[method_code]["amount"] += Decimal(str(amount or 0))
                payment_data[method_code]["count"] += 1
        except Exception:
            pass

    # Calculate total revenue
    total_revenue = sum(data["amount"] for data in payment_data.values())

    # Build result list
    result = []
    for method_code, data in payment_data.items():
        percentage = 0.0
        if total_revenue > 0:
            percentage = float((data["amount"] / total_revenue) * 100)

        result.append(
            {
                "method": get_display_name(method_code),
                "method_code": method_code,
                "amount": float(data["amount"]),  # Convert to float for JSON/template compatibility
                "count": data["count"],
                "percentage": round(percentage, 1),
            }
        )

    # Sort by amount descending
    result.sort(key=lambda x: x["amount"], reverse=True)

    return result


def build_payment_mix_for_pharmacy(business, start_date=None, end_date=None) -> List[Dict]:
    """
    Build payment mix specifically for pharmacy sales.

    Args:
        business: Business instance
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of payment mix dicts
    """
    try:
        from inventory.models_pharmacy import PharmacySale
    except Exception:
        return []

    qs = PharmacySale.objects.filter(business=business)

    if start_date:
        qs = qs.filter(sold_at__date__gte=start_date)

    if end_date:
        qs = qs.filter(sold_at__date__lte=end_date)

    return build_payment_mix(
        business=business,
        sales_qs=qs,
        payment_field="payment_method",
        amount_field="total_amount",
    )


def build_payment_mix_for_phones(business, start_date=None, end_date=None) -> List[Dict]:
    """
    Build payment mix specifically for phones sales.

    Args:
        business: Business instance
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of payment mix dicts
    """
    try:
        from sales.models import Sale
    except Exception:
        return []

    qs = Sale.objects.filter(business=business)

    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)

    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)

    return build_payment_mix(
        business=business,
        sales_qs=qs,
        payment_field="payment_method",
        amount_field="selling_price",
    )


def build_payment_mix_for_clothing(business, start_date=None, end_date=None) -> List[Dict]:
    """
    Build payment mix specifically for clothing sales.

    Args:
        business: Business instance
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of payment mix dicts
    """
    # Clothing uses same Sale model as phones
    return build_payment_mix_for_phones(business, start_date, end_date)


def build_payment_mix_for_gym(business, start_date=None, end_date=None) -> List[Dict]:
    """
    Build payment mix specifically for gym payments.

    Args:
        business: Business instance
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of payment mix dicts
    """
    try:
        from inventory.models_verticals import GymPayment
    except Exception:
        return []

    qs = GymPayment.objects.filter(member__business=business)

    if start_date:
        qs = qs.filter(payment_date__gte=start_date)

    if end_date:
        qs = qs.filter(payment_date__lte=end_date)

    return build_payment_mix(
        business=business,
        sales_qs=qs,
        payment_field="payment_method",
        amount_field="amount",
    )


def build_payment_mix_for_liquor(business, start_date=None, end_date=None) -> List[Dict]:
    """
    Build payment mix specifically for liquor sales.

    Args:
        business: Business instance
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of payment mix dicts
    """
    # Liquor likely uses Sale model or a custom model
    try:
        from sales.models import Sale
    except Exception:
        return []

    qs = Sale.objects.filter(business=business)

    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)

    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)

    return build_payment_mix(
        business=business,
        sales_qs=qs,
        payment_field="payment_method",
        amount_field="selling_price",
    )


__all__ = [
    "build_payment_mix",
    "build_payment_mix_for_pharmacy",
    "build_payment_mix_for_phones",
    "build_payment_mix_for_clothing",
    "build_payment_mix_for_gym",
    "build_payment_mix_for_liquor",
    "normalize_payment_method",
    "get_display_name",
]
