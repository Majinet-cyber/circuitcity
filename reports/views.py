# reports/views.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Optional, Any, Dict

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.serializers.json import DjangoJSONEncoder
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
            return Business.objects.filter(pk=bid).first()
    except Exception:
        pass
    
    return None


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
@user_passes_test(_is_staff_or_auditor)
def reports_home(request: HttpRequest) -> HttpResponse:
    """
    Main reports dashboard with monthly business overview.
    Shows revenue, costs, profit, trends, and downloadable reports.
    """
    filters = ReportFilters.from_request(request)
    business = _get_active_business(request)
    
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
@user_passes_test(_is_staff_or_auditor)
def sales_report(request: HttpRequest) -> HttpResponse:
    """
    Dedicated sales report view (placeholder for now).
    """
    context: Dict[str, Any] = {
        "title": "Sales Report",
        "subtitle": "Top movers, revenue, agents",
    }
    
    # Apply SSOT defaults to prevent KeyError failures
    context = apply_default_report_context(context)
    
    # Try to render a dedicated sales template, fall back to generic
    tpl_name, origin = _resolve_template(["reports/sales_report.html", "ccreports/sales.html", "reports/home.html"])
    resp = render(request, tpl_name, context)
    resp["X-Template-Origin"] = origin
    resp["X-Template-Name"] = tpl_name
    return resp


@login_required
@user_passes_test(_is_staff_or_auditor)
def inventory_report(request: HttpRequest) -> HttpResponse:
    """
    Dedicated inventory report view (placeholder for now).
    """
    context: Dict[str, Any] = {
        "title": "Inventory Report",
        "subtitle": "Stock ageing, low stock, turnover",
    }
    
    # Apply SSOT defaults to prevent KeyError failures
    context = apply_default_report_context(context)
    
    # Try to render a dedicated inventory template, fall back to generic
    tpl_name, origin = _resolve_template(["reports/inventory_report.html", "ccreports/inventory.html", "reports/home.html"])
    resp = render(request, tpl_name, context)
    resp["X-Template-Origin"] = origin
    resp["X-Template-Name"] = tpl_name
    return resp


