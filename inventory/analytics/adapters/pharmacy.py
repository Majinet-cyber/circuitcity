# inventory/analytics/adapters/pharmacy.py
"""
Analytics adapter for pharmacy vertical.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import QuerySet, Sum, Count, Q, F, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from inventory.models_pharmacy import PharmacySale, PharmacyBatch
from inventory.analytics.adapters.base import AnalyticsAdapter
from inventory.analytics.common import (
    apply_business_scope,
    apply_location_filter,
    apply_payment_method_filter,
    apply_search_filter,
)
from wallet.models import WalletTransaction, Ledger, TxnType


class PharmacyAdapter(AnalyticsAdapter):
    """Analytics adapter for pharmacy vertical."""

    def get_sales_queryset(self, business, location=None) -> QuerySet:
        """Get base sales queryset."""
        qs = PharmacySale.objects.filter(business=business, is_deleted=False, is_reversed=False).select_related(
            "batch", "batch__merch_product", "sold_by"
        )
        # PharmacySale doesn't have location, so location filter is ignored
        return qs

    def get_stock_queryset(self, business, location=None) -> QuerySet:
        """Get base stock queryset."""
        qs = PharmacyBatch.objects.filter(business=business, is_archived=False).select_related("merch_product")
        return qs

    def get_costs_queryset(self, business, location=None) -> QuerySet:
        """Get costs queryset."""
        qs = WalletTransaction.objects.filter(
            business=business, ledger=Ledger.COMPANY, type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        return qs

    def get_search_fields(self) -> List[str]:
        """Return search fields for pharmacy."""
        return ["batch__merch_product__name", "customer_name", "customer_phone", "prescription_number"]

    def kpis(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
        payment_method: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculate KPIs for pharmacy."""
        sales_qs = self.get_sales_queryset(business, location)
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(
            timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time())
        )
        sales_qs = sales_qs.filter(sold_at__gte=start_dt, sold_at__lt=end_dt)

        sales_qs = apply_payment_method_filter(sales_qs, payment_method)
        if search_query:
            sales_qs = apply_search_filter(sales_qs, search_query, self.get_search_fields())

        revenue = sales_qs.aggregate(total=Coalesce(Sum("total_amount"), Decimal("0.00")))["total"] or Decimal("0.00")

        # Calculate cost: unit_cost * quantity for each sale
        costs_annotation = ExpressionWrapper(
            F("unit_cost") * F("quantity"), output_field=DecimalField(max_digits=12, decimal_places=2)
        )
        cost_of_goods = sales_qs.annotate(sale_cost=costs_annotation).aggregate(
            total=Coalesce(Sum("sale_cost"), Decimal("0.00"))
        )["total"] or Decimal("0.00")

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
        """Generate chart data for pharmacy."""
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
            .annotate(revenue=Coalesce(Sum("total_amount"), Decimal("0.00")), count=Count("id"))
            .order_by("day")
        )

        # Calculate cost for profit trend
        costs_annotation = ExpressionWrapper(
            F("unit_cost") * F("quantity"), output_field=DecimalField(max_digits=12, decimal_places=2)
        )
        daily_sales_with_cost = (
            sales_qs.annotate(day=TruncDate("sold_at"), sale_cost=costs_annotation)
            .values("day")
            .annotate(
                revenue=Coalesce(Sum("total_amount"), Decimal("0.00")),
                cost=Coalesce(Sum("sale_cost"), Decimal("0.00")),
                count=Count("id"),
            )
            .order_by("day")
        )

        sales_trend = [
            {
                "date": str(item["day"]),
                "date_short": item["day"].strftime("%m/%d") if item["day"] else "",
                "revenue": float(item["revenue"]),
                "count": item["count"],
            }
            for item in daily_sales
        ]

        profit_trend = [
            {
                "date": str(item["day"]),
                "date_short": item["day"].strftime("%m/%d") if item["day"] else "",
                "revenue": float(item["revenue"]),
                "profit": float(item["revenue"] - item["cost"]),
                "count": item["count"],
            }
            for item in daily_sales_with_cost
        ]

        # Payment mix
        payment_mix = (
            sales_qs.values("payment_method")
            .annotate(total=Coalesce(Sum("total_amount"), Decimal("0.00")), count=Count("id"))
            .order_by("-total")
        )

        total_amount = sum(float(pm["total"]) for pm in payment_mix)
        payment_mix_data = []
        for pm in payment_mix:
            amount = float(pm["total"])
            method = pm["payment_method"] or "CASH"
            method_display = dict(PharmacySale.PAYMENT_METHOD_CHOICES).get(method, method.replace("_", " ").title())
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
            sales_qs.values("batch__merch_product__name", "batch__merch_product_id")
            .annotate(revenue=Coalesce(Sum("total_amount"), Decimal("0.00")), units_sold=Sum("quantity"))
            .order_by("-revenue")[:10]
        )

        top_products_data = [
            {
                "name": item["batch__merch_product__name"] or "Unknown",
                "revenue": float(item["revenue"]),
                "units_sold": item["units_sold"] or 0,
            }
            for item in top_products
        ]

        # Top cashiers
        top_agents = (
            sales_qs.filter(sold_by__isnull=False)
            .values("sold_by__id", "sold_by__first_name", "sold_by__last_name", "sold_by__username")
            .annotate(revenue=Coalesce(Sum("total_amount"), Decimal("0.00")), units_sold=Sum("quantity"))
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

        # Stock overview
        stock_qs = self.get_stock_queryset(business, location)
        stock_value = stock_qs.aggregate(total=Coalesce(Sum("unit_cost") * F("quantity_remaining"), Decimal("0.00")))[
            "total"
        ] or Decimal("0.00")

        # Low stock (quantity_remaining < threshold)
        low_stock = stock_qs.filter(quantity_remaining__lt=10).values(
            "merch_product__name", "quantity_remaining", "expiry_date"
        )[:20]

        stock_overview = {
            "stock_value": float(stock_value),
            "stock_retail_value": 0.0,  # Would need to calculate from selling prices
            "low_stock_count": len(low_stock),
            "low_stock": [
                {
                    "name": item["merch_product__name"] or "Unknown",
                    "quantity": item["quantity_remaining"],
                    "expiry_date": str(item["expiry_date"]) if item["expiry_date"] else None,
                }
                for item in low_stock
            ],
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
        """Vertical-specific sections for pharmacy."""
        today = timezone.now().date()
        batches_qs = self.get_stock_queryset(business, location)

        expired_count = batches_qs.filter(expiry_date__lt=today).count()
        expiring_soon = batches_qs.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=30)).count()

        # Stock aging (group by days until expiry)
        aging_batches = (
            batches_qs.filter(expiry_date__isnull=False)
            .values("expiry_date")
            .annotate(count=Count("id"))
            .order_by("expiry_date")[:10]
        )

        return {
            "expired_batches": expired_count,
            "expiring_soon": expiring_soon,
            "stock_aging": [
                {
                    "expiry_date": str(item["expiry_date"]),
                    "count": item["count"],
                }
                for item in aging_batches
            ],
        }
