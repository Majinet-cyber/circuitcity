# notifications/daily_summary/retail.py
"""
Daily summary provider for Retail / Shop businesses.

Metrics (vertical: phones, grocery, pharmacy, clothing, hardware, liquor, etc.):
  - Total Sales Today
  - Total Revenue
  - Total Profit
  - Total COGS
  - Top Product
  - Top Category
  - Biggest Sale (amount + reference)
  - Low Stock Alerts (count of items with qty == 0 or nearly out)
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.template.loader import render_to_string

from notifications.daily_summary.base import DailySummaryProvider

logger = logging.getLogger(__name__)

# Maps business_kind → (import path for sale model, extra filter kwargs)
# Each tuple: (module, class_name, revenue_field, cogs_field, extra_filters)
_MERCH_KIND_MAP: dict[str, tuple[str, str, str, str, dict]] = {
    "liquor": (
        "inventory.models_verticals", "LiquorSale",
        "total_price", "total_cost",
        {"is_free": False},
    ),
    "clothing": (
        "inventory.models_verticals", "ClothingSale",
        "total_price", "total_cost",
        {},
    ),
    "cement": (
        "inventory.models_verticals", "CementSale",
        "total_price", "total_cost",
        {"is_void": False},
    ),
    "hardware": (
        "inventory.models_verticals", "CementSale",
        "total_price", "total_cost",
        {"is_void": False},
    ),
    "grocery": (
        "inventory.models_verticals", "GrocerySale",
        "total_price", "total_cost",
        {},
    ),
    "pharmacy": (
        "inventory.models_verticals", "GrocerySale",
        "total_price", "total_cost",
        {},
    ),
    "farm": (
        "inventory.models_verticals", "GrocerySale",
        "total_price", "total_cost",
        {},
    ),
    "welding": (
        "inventory.models_verticals", "GrocerySale",
        "total_price", "total_cost",
        {},
    ),
}


class RetailDailySummaryProvider(DailySummaryProvider):
    vertical_label = "retail"

    def get_metrics(self, business: Any, report_date: date) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "total_sales": 0,
            "total_revenue": Decimal("0.00"),
            "total_profit": Decimal("0.00"),
            "total_cogs": Decimal("0.00"),
            "top_product": None,
            "top_category": None,
            "biggest_sale_amount": Decimal("0.00"),
            "biggest_sale_ref": None,
            "low_stock_alerts": 0,
            "currency": getattr(business, "currency", "MWK"),
        }

        kind = getattr(business, "business_kind", "") or ""

        if kind == "phones":
            try:
                self._populate_phone_sales(business, report_date, metrics)
            except Exception:
                logger.exception(
                    "[RetailProvider] Error fetching phone sales for %s", business.name
                )
        elif kind in _MERCH_KIND_MAP:
            try:
                self._populate_merch_sales(business, report_date, metrics, kind)
            except Exception:
                logger.exception(
                    "[RetailProvider] Error fetching merch sales (%s) for %s",
                    kind,
                    business.name,
                )
        else:
            # Unknown vertical — attempt phone sales as a safe fallback
            try:
                self._populate_phone_sales(business, report_date, metrics)
            except Exception:
                logger.exception(
                    "[RetailProvider] Error fetching fallback phone sales for %s", business.name
                )

        try:
            self._populate_low_stock(business, metrics)
        except Exception:
            logger.exception("[RetailProvider] Error computing low stock for %s", business.name)

        return metrics

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _populate_phone_sales(
        self, business: Any, report_date: date, metrics: dict[str, Any]
    ) -> None:
        """
        Pull sales from InventoryItem (phones/electronics) with status=SOLD
        for the given date.
        """
        from django.db.models import Count, Sum

        from inventory.models import InventoryItem

        qs = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date=report_date,
        ).select_related("product")

        agg = qs.aggregate(
            cnt=Count("id"),
            rev=Sum("selling_price"),
            cogs=Sum("order_price"),
        )

        cnt = agg["cnt"] or 0
        rev = agg["rev"] or Decimal("0.00")
        cogs = agg["cogs"] or Decimal("0.00")
        profit = rev - cogs

        metrics["total_sales"] += cnt
        metrics["total_revenue"] += rev
        metrics["total_profit"] += profit
        metrics["total_cogs"] += cogs

        if cnt > 0:
            top_prod = (
                qs.values("product__name")
                .annotate(qty=Count("id"))
                .order_by("-qty")
                .first()
            )
            if top_prod and top_prod.get("product__name"):
                metrics["top_product"] = top_prod["product__name"]

            try:
                top_cat = (
                    qs.exclude(product__category="")
                    .values("product__category")
                    .annotate(qty=Count("id"))
                    .order_by("-qty")
                    .first()
                )
                if top_cat and top_cat.get("product__category"):
                    metrics["top_category"] = top_cat["product__category"]
            except Exception:
                pass

        biggest = qs.order_by("-selling_price").first()
        if biggest and (biggest.selling_price or 0) > metrics["biggest_sale_amount"]:
            metrics["biggest_sale_amount"] = biggest.selling_price or Decimal("0.00")
            metrics["biggest_sale_ref"] = f"Item #{biggest.pk}"

    def _populate_merch_sales(
        self,
        business: Any,
        report_date: date,
        metrics: dict[str, Any],
        kind: str,
    ) -> None:
        """
        Pull sales from the vertical-specific merch sale model
        (LiquorSale, ClothingSale, CementSale, or GrocerySale).

        All four models share the same key field names:
          total_price  → revenue
          total_cost   → COGS
          sold_at      → date filter
          product__name / product__category → top product / category
        """
        import importlib

        from django.db.models import Count, Sum

        module_path, class_name, rev_field, cogs_field, extra_filters = _MERCH_KIND_MAP[kind]
        module = importlib.import_module(module_path)
        SaleModel = getattr(module, class_name)

        qs = SaleModel.objects.filter(
            business=business,
            sold_at__date=report_date,
            **extra_filters,
        )

        agg = qs.aggregate(
            cnt=Count("id"),
            rev=Sum(rev_field),
            cogs=Sum(cogs_field),
        )

        cnt = agg["cnt"] or 0
        rev = agg["rev"] or Decimal("0.00")
        cogs = agg["cogs"] or Decimal("0.00")
        profit = rev - cogs

        metrics["total_sales"] += cnt
        metrics["total_revenue"] += rev
        metrics["total_profit"] += profit
        metrics["total_cogs"] += cogs

        if cnt > 0:
            try:
                top_prod = (
                    qs.exclude(product__isnull=True)
                    .values("product__name")
                    .annotate(qty=Count("id"))
                    .order_by("-qty")
                    .first()
                )
                if top_prod and top_prod.get("product__name"):
                    metrics["top_product"] = top_prod["product__name"]
            except Exception:
                pass

            try:
                top_cat = (
                    qs.exclude(product__isnull=True)
                    .exclude(product__category="")
                    .values("product__category")
                    .annotate(qty=Count("id"))
                    .order_by("-qty")
                    .first()
                )
                if top_cat and top_cat.get("product__category"):
                    metrics["top_category"] = top_cat["product__category"]
            except Exception:
                pass

        try:
            biggest = qs.order_by(f"-{rev_field}").first()
            if biggest:
                biggest_amount = getattr(biggest, rev_field) or Decimal("0.00")
                if biggest_amount > metrics["biggest_sale_amount"]:
                    metrics["biggest_sale_amount"] = biggest_amount
                    metrics["biggest_sale_ref"] = f"Sale #{biggest.pk}"
        except Exception:
            pass

    def _populate_low_stock(self, business: Any, metrics: dict[str, Any]) -> None:
        """Count MerchProducts with zero quantity_in_stock."""
        from inventory.models import MerchProduct

        low = MerchProduct.objects.filter(
            business=business,
            is_archived=False,
            is_active=True,
            quantity_in_stock=0,
        ).count()
        metrics["low_stock_alerts"] = low

    def render_email(
        self,
        business: Any,
        metrics: dict[str, Any],
        report_date: date,
    ) -> tuple[str, str]:
        context = {
            "business": business,
            "report_date": report_date,
            **metrics,
        }
        html = render_to_string("emails/daily_summary/retail.html", context)
        text = render_to_string("emails/daily_summary/retail.txt", context)
        return html, text
