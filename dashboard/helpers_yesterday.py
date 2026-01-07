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
        yesterday = timezone.localdate() - timedelta(days=1)

        # Determine which sale model to use based on business vertical
        sales_qs = None
        PaymentMethodChoices = None

        # Get business kind
        vertical = getattr(business, "business_kind", None) or ""
        vertical_lower = vertical.lower()

        # Try vertical-specific models first (they have direct business field)
        if vertical_lower == "clothing":
            try:
                from inventory.models_verticals import ClothingSale, PaymentMethod

                sales_qs = ClothingSale.objects.filter(business=business, sold_at__date=yesterday)
                PaymentMethodChoices = PaymentMethod.choices
            except Exception:
                pass

        elif vertical_lower == "liquor":
            try:
                from inventory.models_verticals import LiquorSale, PaymentMethod

                sales_qs = LiquorSale.objects.filter(
                    business=business, sold_at__date=yesterday, is_free=False  # Exclude free/complimentary drinks
                )
                PaymentMethodChoices = PaymentMethod.choices
            except Exception:
                pass

        elif vertical_lower == "gym":
            try:
                from inventory.models_verticals import GymMemberPayment

                # Gym uses payments, not sales - different structure
                sales_qs = GymMemberPayment.objects.filter(member__business=business, created_at__date=yesterday)
                # GymMemberPayment doesn't have standard payment methods
                PaymentMethodChoices = [("CASH", "Cash"), ("BANK", "Bank"), ("MOBILE_MONEY", "Mobile Money")]
            except Exception:
                pass

        elif vertical_lower == "pharmacy":
            try:
                from inventory.models_pharmacy import PharmacySale

                sales_qs = PharmacySale.objects.filter(business=business, created_at__date=yesterday)
                # PharmacySale may have payment_method field
                if hasattr(PharmacySale, "_meta"):
                    field_names = [f.name for f in PharmacySale._meta.get_fields()]
                    if "payment_method" in field_names:
                        PaymentMethodChoices = PharmacySale._meta.get_field("payment_method").choices or []
                if not PaymentMethodChoices:
                    PaymentMethodChoices = [("CASH", "Cash"), ("BANK", "Bank"), ("MOBILE_MONEY", "Mobile Money")]
            except Exception:
                pass

        # Fallback to standard Sale model (phones vertical)
        if sales_qs is None:
            try:
                from sales.models import Sale, PaymentMethod

                # Sale model doesn't have direct business field
                # Filter via item__business or location__business
                sales_qs = Sale.objects.filter(
                    Q(item__business=business) | Q(location__business=business), sold_at=yesterday
                )
                PaymentMethodChoices = PaymentMethod.choices
            except Exception:
                return None

        if sales_qs is None:
            return None

        sales_count = sales_qs.count()

        # If no sales, return minimal summary
        if sales_count == 0:
            return {
                "date": yesterday,
                "sales_count": 0,
                "total_revenue": 0,
                "payment_mix": [],
            }

        # Determine revenue field name based on model
        # ClothingSale, LiquorSale: total_price
        # Sale: price
        # GymMemberPayment: amount
        revenue_field = "price"  # Default for Sale model
        if hasattr(sales_qs.model, "_meta"):
            field_names = [f.name for f in sales_qs.model._meta.get_fields()]
            if "total_price" in field_names:
                revenue_field = "total_price"
            elif "amount" in field_names:
                revenue_field = "amount"

        # Total revenue
        total_revenue = sales_qs.aggregate(total=Sum(revenue_field))["total"] or 0

        # Payment mix breakdown
        payment_mix = []
        if PaymentMethodChoices:
            for method_code, method_display in PaymentMethodChoices:
                method_qs = sales_qs.filter(payment_method=method_code)
                method_count = method_qs.count()
                if method_count > 0:
                    method_amount = method_qs.aggregate(total=Sum(revenue_field))["total"] or 0
                    payment_mix.append(
                        {
                            "method": method_display,
                            "method_code": method_code,
                            "count": method_count,
                            "amount": float(method_amount),
                        }
                    )

        return {
            "date": yesterday,
            "sales_count": sales_count,
            "total_revenue": float(total_revenue),
            "payment_mix": payment_mix,
        }

    except Exception:
        # Gracefully handle missing models or query errors
        import logging

        logging.exception("Error in get_yesterday_summary")
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
    if not request or not hasattr(request, "session"):
        return False

    try:
        today_str = timezone.localdate().isoformat()
        last_shown = request.session.get("last_summary_date")

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
    if not request or not hasattr(request, "session"):
        return

    try:
        today_str = timezone.localdate().isoformat()
        request.session["last_summary_date"] = today_str
    except Exception:
        pass
