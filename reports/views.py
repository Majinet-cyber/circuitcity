# reports/views.py
from __future__ import annotations

import io
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional, Any, Dict
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.serializers.json import DjangoJSONEncoder
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.loader import get_template
from django.utils import timezone

# These imports are fine to keep; we won't assume field names that could break.
from sales.models import Sale  # noqa
from inventory.models import InventoryItem  # noqa
from wallet.models import WalletTransaction, TxnType, Ledger  # noqa

# SSOT: Import context defaults to prevent KeyError failures
from reports.services.context_defaults import apply_default_report_context


# -------------------------------
# Auth helpers
# -------------------------------
def _is_staff_or_auditor(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    return user.groups.filter(name__in=["Admin", "Manager", "Auditor", "Auditors"]).exists()


def _can_view_business_reports(user, business) -> bool:
    if not user.is_authenticated:
        return False
    if _is_staff_or_auditor(user):
        return True
    if not business:
        return False
    try:
        from tenants.models import Membership
        return Membership.objects.filter(
            business=business,
            user=user,
            status="ACTIVE",
            role__in=["MANAGER", "BAR_MANAGER"],
        ).exists()
    except Exception:
        return False


# -------------------------------
# Filters
# -------------------------------
@dataclass
class ReportFilters:
    date_from: Optional[datetime]
    date_to: Optional[datetime]
    agent_id: Optional[int]
    model_q: Optional[str]
    channel: Optional[str]
    ads: Optional[str]  # "with", "without", or None

    @classmethod
    def from_request(cls, request: HttpRequest) -> "ReportFilters":
        g = request.GET

        def _make_aware(dt: Optional[datetime]) -> Optional[datetime]:
            if not dt:
                return None
            tz = timezone.get_current_timezone()
            return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt.astimezone(tz)

        def parse_iso_date_or_datetime(val: str, *, end_of_day: bool = False) -> Optional[datetime]:
            """
            Accepts 'YYYY-MM-DD' or full ISO 'YYYY-MM-DDTHH:MM[:SS[.ffffff]]'.
            Returns timezone-aware datetime (local tz). For date-only:
            - start_of_day at 00:00:00
            - end_of_day at 23:59:59.999999 if end_of_day=True
            """
            val = (val or "").strip()
            if not val:
                return None
            try:
                # If only a date was provided, add a time component.
                if "T" not in val and " " not in val and len(val) == 10:
                    if end_of_day:
                        dt = datetime.fromisoformat(val)  # naive date -> midnight
                        dt = datetime.combine(dt.date(), time(23, 59, 59, 999999))
                    else:
                        dt = datetime.fromisoformat(val)  # naive date -> midnight
                        dt = datetime.combine(dt.date(), time(0, 0, 0, 0))
                else:
                    dt = datetime.fromisoformat(val)
            except Exception:
                return None
            return _make_aware(dt)

        date_from = parse_iso_date_or_datetime(g.get("date_from", ""), end_of_day=False)
        date_to = parse_iso_date_or_datetime(g.get("date_to", ""), end_of_day=True)

        # Normalize ordering if user swapped them
        if date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from

        return cls(
            date_from=date_from,
            date_to=date_to,
            agent_id=int(g.get("agent") or 0) or None,
            model_q=(g.get("model") or "").strip() or None,
            channel=(g.get("channel") or "").strip() or None,
            ads=(g.get("ads") or "").strip() or None,
        )


# -------------------------------
# Template resolving / rendering
# -------------------------------
def _resolve_template(candidates: list[str]) -> tuple[str, str]:
    """
    Returns (template_name, origin_path). Tries candidates in order.
    """
    last_error: Optional[Exception] = None
    for tpl in candidates:
        try:
            t = get_template(tpl)
            origin = getattr(getattr(t, "origin", None), "name", "(unknown origin)")
            # Print to console for fast feedback
            print(f">> REPORTS USING TEMPLATE {tpl}: {origin}")
            return tpl, origin
        except Exception as e:
            last_error = e
            continue
    # Nothing resolved; raise the last error to surface the issue.
    raise last_error or RuntimeError("No reports template could be resolved.")


def _render(request: HttpRequest, context: Dict[str, Any]) -> HttpResponse:
    """
    Renders the best-guess Reports template and attaches X-Template-Origin.
    Prefers 'ccreports/home.html' (new module), falls back to 'reports/home.html' (legacy).
    """
    tpl_name, origin = _resolve_template(["ccreports/home.html", "reports/home.html"])
    resp = render(request, tpl_name, context)
    resp["X-Template-Origin"] = origin
    resp["X-Template-Name"] = tpl_name
    return resp


# -------------------------------
# Business Metrics Helpers
# -------------------------------
def _get_active_business(request: HttpRequest):
    """Get active business from request (multi-tenant aware)."""
    # Try multiple approaches to get business
    biz = getattr(request, "business", None) or getattr(request, "active_business", None)
    if biz:
        return biz
    
    # Try session
    try:
        bid = request.session.get("active_business_id") or request.session.get("biz_id")
        if bid:
            from tenants.models import Business
            business = Business.objects.filter(pk=bid).first()
            if business and _can_view_business_reports(request.user, business):
                return business
    except Exception:
        pass
    
    return None


def _require_report_access(request: HttpRequest):
    business = _get_active_business(request)
    if business and _can_view_business_reports(request.user, business):
        return business
    if _is_staff_or_auditor(request.user):
        return business
    raise PermissionDenied("You do not have permission to view business reports.")


def _compute_monthly_metrics(business, start_date, end_date):
    """
    Compute comprehensive monthly business metrics.
    Returns dict with revenue, costs, commissions, profit, trends, etc.
    """
    if not business:
        return _empty_metrics()
    
    # --- Sales / Revenue ---
    sales_qs = Sale.objects.filter(
        item__business=business,
        sold_at__gte=start_date,
        sold_at__lte=end_date
    ).select_related("item__product", "agent")
    
    sales_agg = sales_qs.aggregate(
        total_revenue=Coalesce(Sum("price"), Decimal("0.00")),
        total_sales_count=Count("id"),
        total_commissions=Coalesce(
            Sum(F("price") * F("commission_pct") / 100, output_field=DecimalField()),
            Decimal("0.00")
        ),
    )
    
    total_revenue = sales_agg["total_revenue"]
    total_commissions = sales_agg["total_commissions"]
    
    # --- COGS (Cost of Goods Sold) ---
    # Sum up cost_price of sold items
    cogs_agg = sales_qs.aggregate(
        total_cogs=Coalesce(Sum("item__product__cost_price"), Decimal("0.00"))
    )
    total_cogs = cogs_agg["total_cogs"]
    
    # --- Admin Costs (from wallet) ---
    costs_qs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
        effective_date__gte=start_date,
        effective_date__lte=end_date
    )
    costs_agg = costs_qs.aggregate(
        total_costs=Coalesce(Sum("amount"), Decimal("0.00"))
    )
    # Costs are stored as negative, so negate to get positive expense amount
    total_costs = abs(costs_agg["total_costs"])
    
    # --- Profit Calculations ---
    gross_profit = total_revenue - total_cogs
    net_profit = gross_profit - total_costs - total_commissions
    
    # --- Payment Mix ---
    payment_mix = list(
        sales_qs.values("payment_method")
        .annotate(
            count=Count("id"),
            amount=Coalesce(Sum("price"), Decimal("0.00"))
        )
        .order_by("-amount")
    )
    
    # --- Daily Trend ---
    daily_trend = list(
        sales_qs.annotate(date=TruncDate("sold_at"))
        .values("date")
        .annotate(
            revenue=Coalesce(Sum("price"), Decimal("0.00")),
            count=Count("id")
        )
        .order_by("date")
    )
    
    # Add costs and commissions to daily trend
    daily_costs = {
        item["effective_date"]: abs(item["amount"])
        for item in costs_qs.values("effective_date").annotate(
            amount=Coalesce(Sum("amount"), Decimal("0.00"))
        )
    }
    
    for day in daily_trend:
        day_date = day["date"]
        day["costs"] = daily_costs.get(day_date, Decimal("0.00"))
        # Estimate daily commissions (proportional to revenue)
        if total_revenue > 0:
            day["commissions"] = (day["revenue"] / total_revenue) * total_commissions
        else:
            day["commissions"] = Decimal("0.00")
        # Estimate daily COGS
        day["cogs"] = Decimal("0.00")  # Would need per-item cost tracking
        day["net_profit"] = day["revenue"] - day["costs"] - day["commissions"] - day["cogs"]
    
    # --- Top Products ---
    top_products = list(
        sales_qs.values(
            "item__product__name",
            "item__product__brand",
            "item__product__model"
        )
        .annotate(
            revenue=Coalesce(Sum("price"), Decimal("0.00")),
            count=Count("id")
        )
        .order_by("-revenue")[:5]
    )
    
    # --- Top Agents ---
    top_agents = list(
        sales_qs.values("agent__id", "agent__username", "agent__first_name", "agent__last_name")
        .annotate(
            revenue=Coalesce(Sum("price"), Decimal("0.00")),
            count=Count("id"),
            commission=Coalesce(
                Sum(F("price") * F("commission_pct") / 100, output_field=DecimalField()),
                Decimal("0.00")
            )
        )
        .order_by("-revenue")[:5]
    )
    
    return {
        "total_revenue": total_revenue,
        "total_cogs": total_cogs,
        "total_costs": total_costs,
        "total_commissions": total_commissions,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "sales_count": sales_agg["total_sales_count"],
        "payment_mix": payment_mix,
        "daily_trend": daily_trend,
        "top_products": top_products,
        "top_agents": top_agents,
    }


def _empty_metrics():
    """Return empty metrics structure when no business is active."""
    return {
        "total_revenue": Decimal("0.00"),
        "total_cogs": Decimal("0.00"),
        "total_costs": Decimal("0.00"),
        "total_commissions": Decimal("0.00"),
        "gross_profit": Decimal("0.00"),
        "net_profit": Decimal("0.00"),
        "sales_count": 0,
        "payment_mix": [],
        "daily_trend": [],
        "top_products": [],
        "top_agents": [],
    }


def _period_query(request: HttpRequest, start_date: date, end_date: date) -> str:
    params = request.GET.copy()
    params["start"] = start_date.isoformat()
    params["end"] = end_date.isoformat()
    return urlencode(params, doseq=True)


def _product_label(product) -> str:
    if not product:
        return "Unknown product"
    return str(product) or getattr(product, "name", "") or "Unknown product"


def _business_kind(business) -> str:
    return (getattr(business, "business_kind", None) or getattr(business, "kind", None) or "").lower()


def _exclusive_end(end_date: date) -> date:
    return end_date + timedelta(days=1)


def _sale_cost(sale) -> Decimal:
    item = getattr(sale, "item", None)
    if not item:
        return Decimal("0")
    cost = getattr(item, "order_price", None)
    if cost is not None:
        return cost or Decimal("0")
    product = getattr(item, "product", None)
    return getattr(product, "cost_price", Decimal("0")) or Decimal("0")


def _sales_queryset(business, start_date: date, end_date: date):
    if not business:
        return Sale.objects.none()
    return (
        Sale.objects.filter(
            Q(location__business=business) | Q(item__business=business),
            sold_at__gte=start_date,
            sold_at__lte=end_date,
            is_rolled_back=False,
        )
        .select_related("item", "item__product", "agent", "location")
        .distinct()
    )


def _clothing_sales_report_data(business, start_date: date, end_date: date) -> Dict[str, Any]:
    from inventory.verticals import base as vertical_base

    metrics = vertical_base.clothing_sales_metrics(
        business,
        start_date=start_date,
        end_date=_exclusive_end(end_date),
    )
    sales_qs = vertical_base.clothing_sales_queryset(
        business,
        start_date=start_date,
        end_date=_exclusive_end(end_date),
    ).select_related("product", "sold_by")

    total_sales = metrics.get("revenue") or Decimal("0")
    total_cogs = metrics.get("cost_of_goods") or Decimal("0")
    overhead = metrics.get("overhead_costs") or Decimal("0")
    profit = metrics.get("profit") or Decimal("0")
    transaction_count = metrics.get("total_sales") or 0
    avg_sale = (total_sales / transaction_count) if transaction_count else Decimal("0")

    top_rows = (
        sales_qs.values("product__name")
        .annotate(
            units=Coalesce(Sum("quantity"), 0),
            revenue=Coalesce(Sum("total_price"), Decimal("0.00"), output_field=DecimalField()),
            cost=Coalesce(Sum("total_cost"), Decimal("0.00"), output_field=DecimalField()),
        )
        .order_by("-revenue")[:10]
    )
    top_products = [
        {
            "name": row.get("product__name") or "Unknown product",
            "units": row.get("units") or 0,
            "revenue": row.get("revenue") or Decimal("0"),
            "profit": (row.get("revenue") or Decimal("0")) - (row.get("cost") or Decimal("0")),
        }
        for row in top_rows
    ]

    payment_breakdown = [
        {
            "method": row.get("method_display") or row.get("method") or "Unspecified",
            "count": row.get("count") or 0,
            "amount": row.get("total") or Decimal("0"),
        }
        for row in metrics.get("payment_mix_data", [])
    ]

    trend = [
        {
            "date": date.fromisoformat(row["date"]),
            "revenue": Decimal(str(row.get("revenue") or 0)),
            "profit": Decimal(str(row.get("profit") or 0)),
            "count": row.get("count") or 0,
        }
        for row in metrics.get("sales_trend", [])
        if row.get("revenue") or row.get("profit") or row.get("count")
    ]

    recent_sales = [
        {
            "sold_at": sale.sold_at,
            "product": getattr(sale.product, "name", None) or "Unknown product",
            "agent": (sale.sold_by.get_full_name() or sale.sold_by.username) if sale.sold_by else "Unassigned",
            "payment_method": sale.get_payment_method_display() if hasattr(sale, "get_payment_method_display") else sale.payment_method,
            "amount": sale.total_price or Decimal("0"),
            "profit": sale.profit,
        }
        for sale in sales_qs[:30]
    ]

    return {
        "summary": {
            "total_sales": total_sales,
            "gross_profit": profit,
            "transaction_count": transaction_count,
            "avg_sale": avg_sale,
            "gross_margin": (profit / total_sales * 100) if total_sales else Decimal("0"),
            "costs": overhead,
            "cogs": total_cogs,
        },
        "top_products": top_products,
        "payment_breakdown": payment_breakdown,
        "trend": trend,
        "recent_sales": recent_sales,
        "trend_json": json.dumps(
            [{"date": r["date"].isoformat(), "revenue": float(r["revenue"]), "profit": float(r["profit"]), "count": r["count"]} for r in trend],
            cls=DjangoJSONEncoder,
        ),
        "payment_json": json.dumps(
            [{"method": r["method"], "amount": float(r["amount"]), "count": r["count"]} for r in payment_breakdown],
            cls=DjangoJSONEncoder,
        ),
        "top_products_json": json.dumps(
            [{"name": r["name"], "revenue": float(r["revenue"]), "units": r["units"]} for r in top_products[:6]],
            cls=DjangoJSONEncoder,
        ),
    }


def _sales_report_data(business, start_date: date, end_date: date) -> Dict[str, Any]:
    if _business_kind(business) == "clothing":
        return _clothing_sales_report_data(business, start_date, end_date)

    sales_qs = _sales_queryset(business, start_date, end_date)
    sales = list(sales_qs)

    total_sales = sum((s.price or Decimal("0")) for s in sales)
    total_cogs = sum(_sale_cost(s) for s in sales)
    gross_profit = total_sales - total_cogs
    transaction_count = len(sales)
    avg_sale = (total_sales / transaction_count) if transaction_count else Decimal("0")

    top_map: dict[str, dict[str, Any]] = {}
    pay_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"method": "", "count": 0, "amount": Decimal("0")})
    trend_map: dict[date, dict[str, Any]] = {}
    for sale in sales:
        product = getattr(getattr(sale, "item", None), "product", None)
        label = _product_label(product)
        row = top_map.setdefault(label, {"name": label, "units": 0, "revenue": Decimal("0"), "profit": Decimal("0")})
        row["units"] += 1
        row["revenue"] += sale.price or Decimal("0")
        row["profit"] += (sale.price or Decimal("0")) - _sale_cost(sale)

        method = sale.get_payment_method_display() if hasattr(sale, "get_payment_method_display") else sale.payment_method
        pay = pay_map[method or "Unspecified"]
        pay["method"] = method or "Unspecified"
        pay["count"] += 1
        pay["amount"] += sale.price or Decimal("0")

        day = sale.sold_at
        trend = trend_map.setdefault(day, {"date": day, "revenue": Decimal("0"), "profit": Decimal("0"), "count": 0})
        trend["revenue"] += sale.price or Decimal("0")
        trend["profit"] += (sale.price or Decimal("0")) - _sale_cost(sale)
        trend["count"] += 1

    top_products = sorted(top_map.values(), key=lambda r: r["revenue"], reverse=True)[:10]
    payment_breakdown = sorted(pay_map.values(), key=lambda r: r["amount"], reverse=True)
    trend = [trend_map[d] for d in sorted(trend_map)]
    recent_sales = [
        {
            "sold_at": sale.sold_at,
            "product": _product_label(getattr(getattr(sale, "item", None), "product", None)),
            "agent": (sale.agent.get_full_name() or sale.agent.username) if sale.agent else "Unassigned",
            "payment_method": sale.get_payment_method_display() if hasattr(sale, "get_payment_method_display") else sale.payment_method,
            "amount": sale.price or Decimal("0"),
            "profit": (sale.price or Decimal("0")) - _sale_cost(sale),
        }
        for sale in sales[:30]
    ]

    return {
        "summary": {
            "total_sales": total_sales,
            "gross_profit": gross_profit,
            "transaction_count": transaction_count,
            "avg_sale": avg_sale,
            "gross_margin": (gross_profit / total_sales * 100) if total_sales else Decimal("0"),
        },
        "top_products": top_products,
        "payment_breakdown": payment_breakdown,
        "trend": trend,
        "recent_sales": recent_sales,
        "trend_json": json.dumps(
            [{"date": r["date"].isoformat(), "revenue": float(r["revenue"]), "profit": float(r["profit"]), "count": r["count"]} for r in trend],
            cls=DjangoJSONEncoder,
        ),
        "payment_json": json.dumps(
            [{"method": r["method"], "amount": float(r["amount"]), "count": r["count"]} for r in payment_breakdown],
            cls=DjangoJSONEncoder,
        ),
        "top_products_json": json.dumps(
            [{"name": r["name"], "revenue": float(r["revenue"]), "units": r["units"]} for r in top_products[:6]],
            cls=DjangoJSONEncoder,
        ),
    }


def _stock_report_data(business, start_date: date, end_date: date) -> Dict[str, Any]:
    if _business_kind(business) == "clothing":
        return _clothing_stock_report_data(business, start_date, end_date)

    if not business:
        items_qs = InventoryItem.objects.none()
    else:
        manager = getattr(InventoryItem, "all_objects", InventoryItem.objects)
        items_qs = manager.filter(business=business, is_active=True).select_related("product", "current_location")

    in_stock = list(items_qs.filter(status="IN_STOCK", sold_at__isnull=True))
    sold_period = list(items_qs.filter(status="SOLD", sold_at__date__gte=start_date, sold_at__date__lte=end_date))
    received_period = list(items_qs.filter(received_at__gte=start_date, received_at__lte=end_date))
    today = timezone.localdate()

    total_stock_value = sum((item.order_price or Decimal("0")) for item in in_stock)
    retail_value = sum((item.selling_price or item.order_price or Decimal("0")) for item in in_stock)

    product_counts: dict[str, dict[str, Any]] = {}
    for item in in_stock:
        product = item.product
        label = _product_label(product)
        row = product_counts.setdefault(
            label,
            {
                "sku": getattr(product, "code", ""),
                "name": label,
                "qty": 0,
                "threshold": getattr(product, "low_stock_threshold", 0) or 0,
                "value": Decimal("0"),
            },
        )
        row["qty"] += 1
        row["value"] += item.order_price or Decimal("0")
    low_stock = [row for row in product_counts.values() if row["qty"] <= row["threshold"]]
    low_stock = sorted(low_stock, key=lambda r: (r["qty"], r["name"]))[:20]

    movement_map: dict[str, dict[str, Any]] = {}
    for item in sold_period:
        product = item.product
        label = _product_label(product)
        row = movement_map.setdefault(label, {"name": label, "units": 0, "revenue": Decimal("0")})
        row["units"] += 1
        row["revenue"] += item.selling_price or item.order_price or Decimal("0")
    fast_moving = sorted(movement_map.values(), key=lambda r: (r["units"], r["revenue"]), reverse=True)[:10]

    sold_labels = set(movement_map.keys())
    slow_moving = []
    for item in in_stock:
        label = _product_label(item.product)
        age_days = (today - item.received_at).days if item.received_at else 0
        if label not in sold_labels and age_days >= 45:
            slow_moving.append(
                {
                    "name": label,
                    "imei": item.imei,
                    "age_days": age_days,
                    "value": item.order_price or Decimal("0"),
                }
            )
    slow_moving = sorted(slow_moving, key=lambda r: r["age_days"], reverse=True)[:20]

    category_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"name": "", "count": 0, "value": Decimal("0")})
    age_buckets = {
        "0-30 days": {"bucket": "0-30 days", "count": 0, "value": Decimal("0")},
        "31-60 days": {"bucket": "31-60 days", "count": 0, "value": Decimal("0")},
        "61-90 days": {"bucket": "61-90 days", "count": 0, "value": Decimal("0")},
        "90+ days": {"bucket": "90+ days", "count": 0, "value": Decimal("0")},
    }

    for item in in_stock:
        category = getattr(item.product, "brand", "") or "Unbranded"
        row = category_map[category]
        row["name"] = category
        row["count"] += 1
        row["value"] += item.order_price or Decimal("0")

        age_days = (today - item.received_at).days if item.received_at else 0
        if age_days <= 30:
            bucket = age_buckets["0-30 days"]
        elif age_days <= 60:
            bucket = age_buckets["31-60 days"]
        elif age_days <= 90:
            bucket = age_buckets["61-90 days"]
        else:
            bucket = age_buckets["90+ days"]
        bucket["count"] += 1
        bucket["value"] += item.order_price or Decimal("0")

    category_breakdown = sorted(category_map.values(), key=lambda r: r["value"], reverse=True)
    movement_summary = {
        "stock_in_count": len(received_period),
        "stock_out_count": len(sold_period),
        "stock_in_value": sum((item.order_price or Decimal("0")) for item in received_period),
        "stock_out_value": sum((item.order_price or Decimal("0")) for item in sold_period),
    }

    return {
        "summary": {
            "total_stock_value": total_stock_value,
            "retail_value": retail_value,
            "stock_units": len(in_stock),
            "low_stock_count": len(low_stock),
            "stock_in_count": movement_summary["stock_in_count"],
            "stock_out_count": movement_summary["stock_out_count"],
        },
        "low_stock": low_stock,
        "fast_moving": fast_moving,
        "slow_moving": slow_moving,
        "movement_summary": movement_summary,
        "category_breakdown": category_breakdown,
        "ageing": list(age_buckets.values()),
        "category_json": json.dumps(
            [{"name": r["name"], "count": r["count"], "value": float(r["value"])} for r in category_breakdown[:8]],
            cls=DjangoJSONEncoder,
        ),
        "movement_json": json.dumps(
            [
                {"name": "Stock In", "count": movement_summary["stock_in_count"], "value": float(movement_summary["stock_in_value"])},
                {"name": "Stock Out", "count": movement_summary["stock_out_count"], "value": float(movement_summary["stock_out_value"])},
            ],
            cls=DjangoJSONEncoder,
        ),
        "ageing_json": json.dumps(
            [{"bucket": r["bucket"], "count": r["count"], "value": float(r["value"])} for r in age_buckets.values()],
            cls=DjangoJSONEncoder,
        ),
    }


def _clothing_stock_report_data(business, start_date: date, end_date: date) -> Dict[str, Any]:
    from inventory.models import MerchProduct
    from inventory.models_clothing_barcode import ClothingBarcodeUnit
    from inventory.models_verticals import ClothingProductAction, ClothingProductLog, ClothingSale
    from inventory.verticals import base as vertical_base

    inventory = vertical_base.clothing_inventory_metrics(business)
    sales_qs = vertical_base.clothing_sales_queryset(
        business,
        start_date=start_date,
        end_date=_exclusive_end(end_date),
    )

    common_qs = MerchProduct.objects.filter(
        business=business,
        kind="clothing",
        is_active=True,
        is_archived=False,
        quantity_in_stock__gt=0,
    )
    tracked_qs = ClothingBarcodeUnit.objects.filter(
        business=business,
        status="IN_STOCK",
        is_active=True,
    ).select_related("product")

    products_with_tracked = tracked_qs.values_list("product_id", flat=True).distinct()
    common_only_qs = common_qs.exclude(id__in=products_with_tracked)

    common_units = common_only_qs.aggregate(total=Sum("quantity_in_stock")).get("total") or 0
    tracked_units = tracked_qs.count()

    low_stock = [
        {
            "sku": product.sku or product.internal_sku or "",
            "name": product.name,
            "qty": product.quantity_in_stock,
            "threshold": 5,
            "value": (product.cost_price or Decimal("0")) * product.quantity_in_stock,
        }
        for product in common_only_qs.filter(quantity_in_stock__lte=5).order_by("quantity_in_stock", "name")[:20]
    ]

    fast_moving = [
        {
            "name": row.get("product__name") or "Unknown product",
            "units": row.get("units") or 0,
            "revenue": row.get("revenue") or Decimal("0"),
        }
        for row in (
            sales_qs.values("product__name")
            .annotate(
                units=Coalesce(Sum("quantity"), 0),
                revenue=Coalesce(Sum("total_price"), Decimal("0.00"), output_field=DecimalField()),
            )
            .order_by("-units", "-revenue")[:10]
        )
    ]

    sold_product_ids = set(sales_qs.values_list("product_id", flat=True).distinct())
    today = timezone.localdate()
    slow_moving = []
    for product in common_only_qs.exclude(id__in=sold_product_ids).order_by("name")[:20]:
        age_days = (today - product.created_at.date()).days if getattr(product, "created_at", None) else 0
        slow_moving.append(
            {
                "name": product.name,
                "imei": product.sku or product.internal_sku or "",
                "age_days": age_days,
                "value": (product.cost_price or Decimal("0")) * product.quantity_in_stock,
            }
        )

    category_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"name": "", "count": 0, "value": Decimal("0")})
    for product in common_only_qs:
        category = product.category or "Uncategorised"
        row = category_map[category]
        row["name"] = category.title()
        row["count"] += product.quantity_in_stock
        row["value"] += (product.cost_price or Decimal("0")) * product.quantity_in_stock

    for unit in tracked_qs:
        category = unit.category or getattr(unit.product, "category", "") or "Uncategorised"
        row = category_map[category]
        row["name"] = category.title()
        row["count"] += 1
        row["value"] += unit.cost_price or Decimal("0")

    stock_in_count = ClothingProductLog.objects.filter(
        product__business=business,
        action=ClothingProductAction.STOCK_IN,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    ).count()
    movement_summary = {
        "stock_in_count": stock_in_count,
        "stock_out_count": sales_qs.aggregate(total=Coalesce(Sum("quantity"), 0)).get("total") or 0,
        "stock_in_value": Decimal("0"),
        "stock_out_value": sales_qs.aggregate(
            total=Coalesce(Sum("total_cost"), Decimal("0.00"), output_field=DecimalField())
        ).get("total") or Decimal("0"),
    }

    category_breakdown = sorted(category_map.values(), key=lambda r: r["value"], reverse=True)
    ageing = [
        {"bucket": "Current stock", "count": int(common_units or 0) + tracked_units, "value": inventory.get("inventory_value") or Decimal("0")},
        {"bucket": "Sold units", "count": movement_summary["stock_out_count"], "value": movement_summary["stock_out_value"]},
    ]

    return {
        "summary": {
            "total_stock_value": inventory.get("inventory_value") or Decimal("0"),
            "retail_value": inventory.get("retail_value") or Decimal("0"),
            "stock_units": int(common_units or 0) + tracked_units,
            "low_stock_count": len(low_stock),
            "stock_in_count": movement_summary["stock_in_count"],
            "stock_out_count": movement_summary["stock_out_count"],
        },
        "low_stock": low_stock,
        "fast_moving": fast_moving,
        "slow_moving": slow_moving,
        "movement_summary": movement_summary,
        "category_breakdown": category_breakdown,
        "ageing": ageing,
        "category_json": json.dumps(
            [{"name": r["name"], "count": r["count"], "value": float(r["value"])} for r in category_breakdown[:8]],
            cls=DjangoJSONEncoder,
        ),
        "movement_json": json.dumps(
            [
                {"name": "Stock In", "count": movement_summary["stock_in_count"], "value": 0.0},
                {"name": "Stock Out", "count": movement_summary["stock_out_count"], "value": float(movement_summary["stock_out_value"])},
            ],
            cls=DjangoJSONEncoder,
        ),
        "ageing_json": json.dumps(
            [{"bucket": r["bucket"], "count": r["count"], "value": float(r["value"])} for r in ageing],
            cls=DjangoJSONEncoder,
        ),
    }


def _get_period_dates(request: HttpRequest):
    """
    Parse period from query params or default to current month.
    Returns (start_date, end_date) as timezone-aware datetimes.
    """
    tz = timezone.get_current_timezone()
    now = timezone.now().astimezone(tz)
    
    # Check for custom date range
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")
    
    if start_str and end_str:
        try:
            start_date = datetime.fromisoformat(start_str)
            end_date = datetime.fromisoformat(end_str)
            if timezone.is_naive(start_date):
                start_date = timezone.make_aware(start_date, tz)
            if timezone.is_naive(end_date):
                end_date = timezone.make_aware(end_date, tz)
            # Set end to end of day
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            return start_date.date(), end_date.date()
        except (ValueError, TypeError):
            pass
    
    # Check for period type
    period = request.GET.get("period", "month")
    today = now.date()
    
    if period == "today":
        return today, today
    elif period == "week":
        # Last 7 days
        start_date = today - timedelta(days=6)
        return start_date, today
    else:  # default to month
        # Current month
        start_date = today.replace(day=1)
        # Last day of month
        if today.month == 12:
            end_date = today.replace(month=12, day=31)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
            end_date = (next_month - timedelta(days=1))
        # If we're in the middle of the month, use today as end
        if today < end_date:
            end_date = today
        return start_date, end_date


# -------------------------------
# Views
# -------------------------------
@login_required
def reports_home(request: HttpRequest) -> HttpResponse:
    """
    Main reports dashboard with monthly business overview.
    Shows revenue, costs, profit, trends, and downloadable reports.
    """
    filters = ReportFilters.from_request(request)
    business = _require_report_access(request)
    
    # Get reporting period
    start_date, end_date = _get_period_dates(request)
    
    # Compute metrics
    metrics = _compute_monthly_metrics(business, start_date, end_date)
    
    # Prepare context
    context: Dict[str, Any] = {
        "title": "Reports",
        "subtitle": "Monthly Business Overview",
        "filters": filters,
        "business": business,
        "period_start": start_date,
        "period_end": end_date,
        
        # Summary metrics
        "report_summary": {
            "total_revenue": float(metrics["total_revenue"]),
            "total_cogs": float(metrics["total_cogs"]),
            "total_costs": float(metrics["total_costs"]),
            "total_commissions": float(metrics["total_commissions"]),
            "gross_profit": float(metrics["gross_profit"]),
            "net_profit": float(metrics["net_profit"]),
            "sales_count": metrics["sales_count"],
        },
        
        # JSON-serialized data for charts
        "report_trend_json": json.dumps([
            {
                "date": str(day["date"]),
                "revenue": float(day["revenue"]),
                "costs": float(day["costs"]),
                "commissions": float(day["commissions"]),
                "net_profit": float(day["net_profit"]),
            }
            for day in metrics["daily_trend"]
        ], cls=DjangoJSONEncoder),
        
        "payment_mix_json": json.dumps([
            {
                "method": item["payment_method"],
                "count": item["count"],
                "amount": float(item["amount"]),
            }
            for item in metrics["payment_mix"]
        ], cls=DjangoJSONEncoder),
        
        # Top performers
        "top_products": [
            {
                "name": p.get("item__product__name") or f"{p.get('item__product__brand')} {p.get('item__product__model')}",
                "revenue": float(p["revenue"]),
                "count": p["count"],
            }
            for p in metrics["top_products"]
        ],
        
        "top_agents": [
            {
                "name": (
                    f"{a.get('agent__first_name', '')} {a.get('agent__last_name', '')}".strip()
                    or a.get("agent__username", f"Agent #{a.get('agent__id')}")
                ),
                "revenue": float(a["revenue"]),
                "count": a["count"],
                "commission": float(a["commission"]),
            }
            for a in metrics["top_agents"]
        ],
    }
    
    # Apply SSOT defaults to prevent KeyError failures
    context = apply_default_report_context(context)
    
    return _render(request, context)


@login_required
def sales_report(request: HttpRequest) -> HttpResponse:
    """
    Dedicated business-scoped sales report view.
    """
    business = _require_report_access(request)
    start_date, end_date = _get_period_dates(request)
    data = _sales_report_data(business, start_date, end_date)
    query = _period_query(request, start_date, end_date)
    context: Dict[str, Any] = {
        "title": "Sales Report",
        "subtitle": "Revenue, gross profit, product movement, and payment mix",
        "business": business,
        "period_start": start_date,
        "period_end": end_date,
        "period_query": query,
        "pdf_url": f"?{query}" if query else "",
        "active_tab": "reports",
        "show_search": False,
        **data,
    }
    
    # Apply SSOT defaults to prevent KeyError failures
    context = apply_default_report_context(context)
    
    # Try to render a dedicated sales template, fall back to generic
    tpl_name, origin = _resolve_template(["ccreports/sales_report.html", "reports/sales_report.html", "ccreports/sales.html", "reports/home.html"])
    resp = render(request, tpl_name, context)
    resp["X-Template-Origin"] = origin
    resp["X-Template-Name"] = tpl_name
    return resp


@login_required
def inventory_report(request: HttpRequest) -> HttpResponse:
    """
    Dedicated business-scoped stock report view.
    """
    business = _require_report_access(request)
    start_date, end_date = _get_period_dates(request)
    data = _stock_report_data(business, start_date, end_date) or {}
    query = _period_query(request, start_date, end_date)
    context: Dict[str, Any] = {
        "title": "Stock Report",
        "subtitle": "Stock value, movement, low stock, and turnover",
        "business": business,
        "period_start": start_date,
        "period_end": end_date,
        "period_query": query,
        "pdf_url": f"?{query}" if query else "",
        "active_tab": "reports",
        "show_search": False,
        **data,
    }
    
    # Apply SSOT defaults to prevent KeyError failures
    context = apply_default_report_context(context)
    
    # Try to render a dedicated inventory template, fall back to generic
    tpl_name, origin = _resolve_template(["ccreports/inventory_report.html", "reports/inventory_report.html", "ccreports/inventory.html", "reports/home.html"])
    resp = render(request, tpl_name, context)
    resp["X-Template-Origin"] = origin
    resp["X-Template-Name"] = tpl_name
    return resp


def _pdf_response(filename: str, title: str, business, start_date: date, end_date: date, rows: list[list[Any]], summary: list[tuple[str, Any]]) -> HttpResponse:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except Exception:
        return HttpResponse("PDF generation requires reportlab.", status=503, content_type="text/plain")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=30)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Heading1"], fontSize=18, textColor=colors.HexColor("#065f46"), spaceAfter=8)
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#64748b"), spaceAfter=12)
    elements = [
        Paragraph(title, title_style),
        Paragraph(f"{getattr(business, 'name', 'Business')} | {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}", meta_style),
    ]
    summary_data = [["Metric", "Value"]] + [[label, value] for label, value in summary]
    summary_table = Table(summary_data, colWidths=[2.4 * inch, 2.2 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcfce7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#064e3b")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1fae5")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.extend([summary_table, Spacer(1, 0.2 * inch)])
    if rows:
        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#065f46")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dbeafe")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(table)
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def sales_report_pdf(request: HttpRequest) -> HttpResponse:
    business = _require_report_access(request)
    start_date, end_date = _get_period_dates(request)
    data = _sales_report_data(business, start_date, end_date)
    summary = data["summary"]
    rows = [["Product", "Units", "Revenue", "Gross Profit"]] + [
        [r["name"], r["units"], f"MWK {r['revenue']:,.0f}", f"MWK {r['profit']:,.0f}"]
        for r in data["top_products"][:20]
    ]
    return _pdf_response(
        f"{getattr(business, 'slug', 'business')}_sales_report_{start_date:%Y%m%d}_{end_date:%Y%m%d}.pdf",
        "Emajinet Sales Report",
        business,
        start_date,
        end_date,
        rows,
        [
            ("Total sales", f"MWK {summary['total_sales']:,.0f}"),
            ("Gross profit", f"MWK {summary['gross_profit']:,.0f}"),
            ("Transactions", f"{summary['transaction_count']:,}"),
            ("Average sale", f"MWK {summary['avg_sale']:,.0f}"),
        ],
    )


@login_required
def inventory_report_pdf(request: HttpRequest) -> HttpResponse:
    business = _require_report_access(request)
    start_date, end_date = _get_period_dates(request)
    data = _stock_report_data(business, start_date, end_date) or {}
    data = apply_default_report_context(data)
    summary = data["summary"]
    rows = [["Low-stock product", "Qty", "Threshold", "Stock Value"]] + [
        [r["name"], r["qty"], r["threshold"], f"MWK {r['value']:,.0f}"]
        for r in data["low_stock"][:30]
    ]
    if len(rows) == 1:
        rows.append(["No low-stock items", "", "", ""])
    return _pdf_response(
        f"{getattr(business, 'slug', 'business')}_stock_report_{start_date:%Y%m%d}_{end_date:%Y%m%d}.pdf",
        "Emajinet Stock Report",
        business,
        start_date,
        end_date,
        rows,
        [
            ("Total stock value", f"MWK {summary['total_stock_value']:,.0f}"),
            ("Retail value", f"MWK {summary['retail_value']:,.0f}"),
            ("Units in stock", f"{summary['stock_units']:,}"),
            ("Stock in / out", f"{summary['stock_in_count']:,} / {summary['stock_out_count']:,}"),
        ],
    )


