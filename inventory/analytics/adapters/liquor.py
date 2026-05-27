# inventory/analytics/adapters/liquor.py
"""
Analytics adapter for liquor vertical.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import QuerySet, Sum, Count, Q
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from inventory.models_verticals import LiquorSale
from inventory.models import MerchProduct
from inventory.analytics.adapters.base import AnalyticsAdapter
from inventory.analytics.common import (
    apply_business_scope,
    apply_location_filter,
    apply_payment_method_filter,
    apply_search_filter,
)
from wallet.models import WalletTransaction, Ledger, TxnType


class LiquorAdapter(AnalyticsAdapter):
    """Analytics adapter for liquor vertical."""

    def get_sales_queryset(self, business, location=None) -> QuerySet:
        """Get base sales queryset."""
        qs = LiquorSale.objects.filter(business=business, is_free=False).select_related(
            "product", "shift", "shift__location", "sold_by"
        )

        if location:
            qs = qs.filter(shift__location=location)

        return qs

    def get_stock_queryset(self, business, location=None) -> QuerySet:
        """Get base stock queryset."""
        qs = MerchProduct.objects.filter(business=business, kind="liquor", is_active=True)
        # MerchProduct doesn't have location, so location filter is ignored
        return qs

    def get_costs_queryset(self, business, location=None) -> QuerySet:
        """Get costs queryset."""
        qs = WalletTransaction.objects.filter(
            business=business, ledger=Ledger.COMPANY, type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        return qs

    def get_search_fields(self) -> List[str]:
        """Return search fields for liquor."""
        return ["product__name", "product__category", "notes", "sold_by__username"]

    def kpis(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
        payment_method: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculate KPIs for liquor."""
        sales_qs = self.get_sales_queryset(business, location)
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(
            timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time())
        )
        sales_qs = sales_qs.filter(sold_at__gte=start_dt, sold_at__lt=end_dt)

        sales_qs = apply_payment_method_filter(sales_qs, payment_method)
        if search_query:
            sales_qs = apply_search_filter(sales_qs, search_query, self.get_search_fields())

        revenue = sales_qs.aggregate(total=Coalesce(Sum("total_price"), Decimal("0.00")))["total"] or Decimal("0.00")
        cost_of_goods = sales_qs.aggregate(total=Coalesce(Sum("total_cost"), Decimal("0.00")))["total"] or Decimal(
            "0.00"
        )
        total_sales = sales_qs.count()
        avg_order_value = revenue / total_sales if total_sales > 0 else Decimal("0.00")

        costs_qs = self.get_costs_queryset(business, location)
        costs_qs = costs_qs.filter(
            Q(type=TxnType.COST_ONCE_OFF, effective_date__gte=start_date, effective_date__lte=end_date)
            | Q(type=TxnType.COST_RECURRING, effective_from__lte=end_date)
        )
        costs = abs(costs_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"))

        profit = revenue - cost_of_goods - costs
        gross_margin = ((revenue - cost_of_goods) / revenue * 100) if revenue > 0 else Decimal("0.00")

        return {
            "revenue": revenue,
            "profit": profit,
            "total_sales": total_sales,
            "avg_order_value": avg_order_value,
            "gross_margin": gross_margin,
            "costs": costs,
        }

    def charts(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
        payment_method: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate chart data for liquor."""
        sales_qs = self.get_sales_queryset(business, location)
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(
            timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time())
        )
        sales_qs = sales_qs.filter(sold_at__gte=start_dt, sold_at__lt=end_dt)

        sales_qs = apply_payment_method_filter(sales_qs, payment_method)
        if search_query:
            sales_qs = apply_search_filter(sales_qs, search_query, self.get_search_fields())

        # Sales trend
        daily_sales = (
            sales_qs.annotate(day=TruncDate("sold_at"))
            .values("day")
            .annotate(
                revenue=Coalesce(Sum("total_price"), Decimal("0.00")),
                cost=Coalesce(Sum("total_cost"), Decimal("0.00")),
                count=Count("id"),
            )
            .order_by("day")
        )

        sales_trend = [
            {
                "date": str(item["day"]),
                "date_short": item["day"].strftime("%m/%d") if item["day"] else "",
                "revenue": float(item["revenue"]),
                "profit": float(item["revenue"] - item["cost"]),
                "count": item["count"],
            }
            for item in daily_sales
        ]

        profit_trend = sales_trend

        # Payment mix
        payment_mix = (
            sales_qs.values("payment_method")
            .annotate(total=Coalesce(Sum("total_price"), Decimal("0.00")), count=Count("id"))
            .order_by("-total")
        )

        total_amount = sum(float(pm["total"]) for pm in payment_mix)
        payment_mix_data = []
        for pm in payment_mix:
            amount = float(pm["total"])
            method = pm["payment_method"] or "cash"
            method_display = dict(LiquorSale._meta.get_field("payment_method").choices).get(
                method, method.replace("_", " ").title()
            )
            payment_mix_data.append(
                {
                    "method": method,
                    "method_display": method_display,
                    "amount": amount,
                    "percentage": (amount / total_amount * 100) if total_amount > 0 else 0,
                }
            )

        # Top products
        top_products = (
            sales_qs.values("product__name", "product_id")
            .annotate(revenue=Coalesce(Sum("total_price"), Decimal("0.00")), units_sold=Sum("quantity"))
            .order_by("-revenue")[:10]
        )

        top_products_data = [
            {
                "name": item["product__name"] or "Unknown",
                "revenue": float(item["revenue"]),
                "units_sold": item["units_sold"] or 0,
            }
            for item in top_products
        ]

        # Top bartenders/cashiers
        top_agents = (
            sales_qs.filter(sold_by__isnull=False)
            .values("sold_by__id", "sold_by__first_name", "sold_by__last_name", "sold_by__username")
            .annotate(revenue=Coalesce(Sum("total_price"), Decimal("0.00")), units_sold=Sum("quantity"))
            .order_by("-revenue")[:10]
        )

        top_agents_data = [
            {
                "name": f"{item['sold_by__first_name'] or ''} {item['sold_by__last_name'] or ''}".strip()
                or item["sold_by__username"]
                or "Unknown",
                "revenue": float(item["revenue"]),
                "units_sold": item["units_sold"] or 0,
            }
            for item in top_agents
        ]

        # Stock overview (simplified - would need actual stock tracking)
        stock_qs = self.get_stock_queryset(business, location)
        stock_count = stock_qs.count()

        stock_overview = {
            "stock_value": 0.0,
            "stock_retail_value": 0.0,
            "low_stock_count": 0,
            "low_stock": [],
        }

        return {
            "sales_trend": sales_trend,
            "profit_trend": profit_trend,
            "payment_mix": payment_mix_data,
            "top_products": top_products_data,
            "top_agents": top_agents_data,
            "stock_overview": stock_overview,
        }

    def vertical_sections(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
    ) -> Dict[str, Any]:
        """Vertical-specific sections for liquor."""
        sales_qs = self.get_sales_queryset(business, location)
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(
            timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time())
        )
        sales_qs = sales_qs.filter(sold_at__gte=start_dt, sold_at__lt=end_dt)

        # Category mix
        category_mix = (
            sales_qs.values("product__category")
            .annotate(count=Count("id"), revenue=Coalesce(Sum("total_price"), Decimal("0.00")))
            .order_by("-revenue")[:5]
        )

        # Credit vs cash mix
        credit_sales = sales_qs.filter(is_credit=True).aggregate(total=Coalesce(Sum("total_price"), Decimal("0.00")))[
            "total"
        ] or Decimal("0.00")

        cash_sales = sales_qs.filter(is_credit=False).aggregate(total=Coalesce(Sum("total_price"), Decimal("0.00")))[
            "total"
        ] or Decimal("0.00")

        return {
            "category_mix": [
                {
                    "category": item["product__category"] or "Uncategorized",
                    "count": item["count"],
                    "revenue": float(item["revenue"]),
                }
                for item in category_mix
            ],
            "credit_vs_cash": {
                "credit": float(credit_sales),
                "cash": float(cash_sales),
            },
        }
