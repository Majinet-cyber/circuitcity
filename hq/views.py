# circuitcity/hq/views.py
from __future__ import annotations

import datetime
import json
from collections import deque
from datetime import datetime as dt
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldError
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Cast, Coalesce, TruncDate, TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import TemplateDoesNotExist, loader
from django.template.loader import select_template
from django.urls import reverse
from django.utils import timezone

from billing.models import Invoice, Subscription  # BusinessSubscription alias
from hq.permissions import hq_admin_required
from hq.services.hq_analytics import get_hq_analytics_data
from hq.utils_dates import get_month_range, get_period_from_request, get_year_from_request
from hq.utils_gamification import get_agent_rankings
from inventory.models import InventoryItem, Location
from sales.models import Sale
from tenants.models import Business, Membership

# Try to import Plan model if you have one
try:
    from billing.models import Plan  # type: ignore
except Exception:  # pragma: no cover
    Plan = None  # type: ignore

# Check if contracts module is available
try:
    from hq import views_contracts

    CONTRACTS_ENABLED = True
except ImportError:
    CONTRACTS_ENABLED = False


# -------------------------------------------------------------------
# Plan catalog - IMPORT FROM BILLING.PRICING (SINGLE SOURCE OF TRUTH)
# -------------------------------------------------------------------
from billing.pricing import PLAN_CATALOG


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _esc(s) -> str:
    s = "" if s is None else str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_safe(request, template_name: str, ctx: dict, inline_html_builder=None):
    """Render template if present; otherwise serve a minimal inline page."""
    try:
        loader.get_template(template_name)
        return render(request, template_name, ctx)
    except TemplateDoesNotExist:
        if inline_html_builder:
            return HttpResponse(inline_html_builder(ctx))
        return HttpResponse("<h1 style='font-family:system-ui'>Page</h1>")


def _date_range_from_request(request):
    rng = (request.GET.get("range") or "all").lower()
    today = timezone.now().date()
    if rng == "7d":
        return today - timedelta(days=7), today, rng
    if rng == "custom":

        def _p(x):
            try:
                return dt.strptime(x, "%Y-%m-%d").date()
            except Exception:
                return None

        s = _p(request.GET.get("start") or "")
        e = _p(request.GET.get("end") or "")
        if not s or not e or s > e:
            s, e = today - timedelta(days=30), today
        return s, e, rng
    return None, None, "all"


def _paginate(request, qs, per_page=25):
    if not qs.query.order_by:
        qs = qs.order_by("-id")
    p = Paginator(qs, per_page)
    return p.get_page(request.GET.get("page") or 1)


def _field(model, name: str):
    try:
        return model._meta.get_field(name)
    except Exception:
        return None


def _range_filter(qs, model, field_name: str, start, end):
    f = _field(model, field_name)
    if not f or start is None or end is None:
        return qs
    lookup = f"{field_name}__date__range" if isinstance(f, models.DateTimeField) else f"{field_name}__range"
    return qs.filter(**{lookup: (start, end)})


def _json_body(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


def _plan_info_from_subscription(sub: Subscription) -> dict:
    """
    Return dict describing the subscription's current plan (code, name, amount, limits).
    Works whether you store amount on Subscription or via a related Plan.
    """
    code = getattr(sub, "plan_code", None)
    name = None
    amount = None

    if _field(Subscription, "plan") and getattr(sub, "plan_id", None):
        plan_obj = getattr(sub, "plan")
        code = getattr(plan_obj, "code", None) or (getattr(plan_obj, "name", "") or "").lower().replace(" ", "")
        name = getattr(plan_obj, "name", None)
        amount = getattr(plan_obj, "amount", None)

    if amount is None:
        amount = getattr(sub, "amount", None)

    selected = None
    if code and code in PLAN_CATALOG:
        selected = PLAN_CATALOG[code]
    else:
        for p in PLAN_CATALOG.values():
            if amount is not None and Decimal(str(amount)) == Decimal(str(p["amount"])):  # price match
                selected = p
                break

    if not selected:
        return {
            "code": code or "custom",
            "name": name or "Custom",
            "amount": Decimal(str(amount or 0)),
            "max_agents": None,
            "max_stores": None,
        }
    return selected


def _limits_for_business(biz: Business) -> dict:
    """Return effective limits for the business (agents/stores) based on its active subscription."""
    sub = Subscription.objects.filter(business=biz).order_by("-id").first()
    if not sub:
        return PLAN_CATALOG["starter"]
    return _plan_info_from_subscription(sub)


def _back_to(request, fallback_name: str = "hq:subscriptions") -> HttpResponse:
    """Redirect back to the referring page or to a named URL."""
    to = request.META.get("HTTP_REFERER")
    try:
        return redirect(to) if to else redirect(reverse(fallback_name))
    except Exception:
        return redirect(reverse(fallback_name))


# -------------------------------------------------------------------
# Dashboard
# -------------------------------------------------------------------
def _dashboard_inline(ctx: dict) -> str:
    cards = [
        ("Total Businesses", ctx.get("total_biz", 0)),
        ("New (7d)", ctx.get("new_biz_7d", 0)),
        ("Active Subs", ctx.get("active_subs", 0)),
        ("MRR (plan amount sum)", ctx.get("mrr_sum", 0)),
        ("Open Invoices", ctx.get("open_invoices", 0)),
        ("Open Total", ctx.get("open_total", 0)),
        ("Agents Total", ctx.get("agents_total", 0)),
        ("Agents New (30d)", ctx.get("agents_new_30d", 0)),
        ("Stock In (7d)", ctx.get("stock_in_7d", 0)),
        ("Stock Out (7d)", ctx.get("stock_out_7d", 0)),
    ]

    def fmt_num(v):
        try:
            if isinstance(v, int):
                return f"{v}"
            return f"{float(v):,.2f}"
        except Exception:
            return _esc(v)

    card_html = "".join(
        f"""
        <div class="card">
          <div class="label">{_esc(label)}</div>
          <div class="value">{fmt_num(val)}</div>
        </div>
        """
        for label, val in cards
    )

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>HQ Â· Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {{ --bg:#0b1220; --fg:#e5e7eb; --muted:#94a3b8; --card:#111827; --border:#1f2937; --accent:#22d3ee; }}
    body {{ margin:24px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;background:var(--bg);color:var(--fg); }}
    .title {{ font-size:22px;font-weight:800;margin:0 0 6px }}
    .muted {{ color:var(--muted); margin-bottom:18px }}
    .notice {{ margin:0 0 18px; padding:10px 14px; background:#0f172a; border:1px solid var(--border); border-radius:10px; color:var(--muted); }}
    .grid {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fill, minmax(180px,1fr)); }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px; }}
    .label {{ font-size:12px; color:var(--muted); margin-bottom:6px }}
    .value {{ font-size:22px; font-weight:800; color:#e2e8f0 }}
  </style>
</head>
<body>
  <div class="title">HQ Â· Dashboard</div>
  <div class="muted">Template <code>hq/dashboard.html</code> not found; showing a safe inline version.</div>
  <div class="notice">Create <code>templates/hq/dashboard.html</code> later to fully brand this page.</div>
  <div class="grid">{card_html}</div>
</body>
</html>
""".strip()


@hq_admin_required
def dashboard(request):
    # Log HQ dashboard access
    from audit.utils import log_hq_action

    log_hq_action(request, action="VIEW_PAGE", entity_type="HQ_DASHBOARD", message="Accessed HQ dashboard")

    now = timezone.now()
    seven = now - timedelta(days=7)
    thirty = now - timedelta(days=30)

    # Get date filtering parameters
    start_date, end_date, period_type = get_period_from_request(request, default_to_current_month=True)
    year = get_year_from_request(request)

    ctx = {}
    ctx["total_biz"] = Business.objects.count()
    ctx["new_biz_7d"] = Business.objects.filter(created_at__gte=seven).count() if _field(Business, "created_at") else 0

    zero_dec = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))
    ctx["active_subs"] = Subscription.objects.filter(status__in=["TRIAL", "ACTIVE", "trial", "active"]).count()
    if _field(Subscription, "plan"):
        ctx["mrr_sum"] = Subscription.objects.filter(status__in=["ACTIVE", "active"]).aggregate(
            v=Coalesce(Sum("plan__amount"), zero_dec)
        )["v"]
    else:
        ctx["mrr_sum"] = Subscription.objects.filter(status__in=["ACTIVE", "active"]).aggregate(
            v=Coalesce(Sum("amount"), zero_dec)
        )["v"]

    open_inv = Invoice.objects.filter(status__in=["OPEN", "PAST_DUE", "UNPAID", "DUE", "open", "past_due"])
    ctx["open_invoices"] = open_inv.count()
    ctx["open_total"] = open_inv.aggregate(
        v=Coalesce(Sum("total"), Value(0, output_field=DecimalField(max_digits=18, decimal_places=2)))
    )["v"]

    ctx["agents_total"] = Membership.objects.filter(role="AGENT").count()
    ctx["agents_new_30d"] = (
        Membership.objects.filter(role="AGENT", created_at__gte=thirty).count()
        if _field(Membership, "created_at")
        else 0
    )

    # Use whichever InventoryItem manager exists
    inv_mgr = getattr(InventoryItem, "all_objects", InventoryItem.objects)
    ctx["stock_in_7d"] = inv_mgr.filter(received_at__gte=seven).count()
    ctx["stock_out_7d"] = inv_mgr.filter(sold_at__isnull=False, sold_at__gte=seven).count()

    ctx["any_trials"] = Subscription.objects.filter(status__in=["TRIAL", "trial"]).exists()

    # === NEW: Sales metrics for the selected period ===
    sales_qs = Sale.objects.all()
    if start_date and end_date:
        sales_qs = sales_qs.filter(sold_at__gte=start_date, sold_at__lt=end_date)

    ctx["sales_count"] = sales_qs.count()
    ctx["sales_revenue"] = sales_qs.aggregate(total=Coalesce(Sum("price"), zero_dec))["total"]

    # === Monthly aggregates for the selected year ===
    year_start = timezone.make_aware(dt(year, 1, 1))
    year_end = timezone.make_aware(dt(year + 1, 1, 1))

    # SQLite-safe monthly aggregation
    from django.db import connection

    if connection.vendor == "sqlite":
        # SQLite fallback: fetch raw data and group in Python
        sales_raw = (
            Sale.objects.filter(sold_at__isnull=False, sold_at__gte=year_start, sold_at__lt=year_end)
            .values("sold_at", "price")
            .order_by("sold_at")
        )

        # Group by month in Python
        from collections import defaultdict

        monthly_data = defaultdict(lambda: {"count": 0, "revenue": 0})

        for sale in sales_raw:
            if sale["sold_at"]:
                # Get year-month tuple
                sold_dt = sale["sold_at"]
                month_key = (sold_dt.year, sold_dt.month)
                monthly_data[month_key]["count"] += 1
                monthly_data[month_key]["revenue"] += float(sale["price"] or 0)

        # Sort and prepare chart data
        sorted_months = sorted(monthly_data.keys())
        monthly_sales_labels = [dt(y, m, 1).strftime("%B") for y, m in sorted_months]
        monthly_sales_data = [monthly_data[k]["count"] for k in sorted_months]
        monthly_revenue_data = [monthly_data[k]["revenue"] for k in sorted_months]
    else:
        # PostgreSQL/MySQL: use DB-level aggregation
        sales_by_month = (
            Sale.objects.filter(sold_at__isnull=False, sold_at__gte=year_start, sold_at__lt=year_end)
            .annotate(month=TruncMonth("sold_at"))
            .values("month")
            .annotate(count=Count("id"), revenue=Coalesce(Sum("price"), zero_dec))
            .order_by("month")
        )

        # Prepare chart data (monthly sales)
        monthly_sales_labels = []
        monthly_sales_data = []
        monthly_revenue_data = []

        for item in sales_by_month:
            month_date = item["month"]
            if month_date:
                monthly_sales_labels.append(month_date.strftime("%B"))
                monthly_sales_data.append(item["count"])
                monthly_revenue_data.append(float(item["revenue"]))

    ctx["monthly_sales_labels"] = json.dumps(monthly_sales_labels)
    ctx["monthly_sales_data"] = json.dumps(monthly_sales_data)
    ctx["monthly_revenue_data"] = json.dumps(monthly_revenue_data)

    # === Chart context: totals, peak month, table data ===
    sales_ytd_count = sum(monthly_sales_data) if monthly_sales_data else 0
    sales_ytd_revenue = sum(monthly_revenue_data) if monthly_revenue_data else 0

    # Find peak month
    sales_peak_month_label = ""
    sales_peak_month_count = 0
    sales_peak_month_revenue = 0
    if monthly_sales_data and monthly_sales_labels:
        peak_idx = monthly_sales_data.index(max(monthly_sales_data)) if monthly_sales_data else 0
        sales_peak_month_label = monthly_sales_labels[peak_idx] if peak_idx < len(monthly_sales_labels) else ""
        sales_peak_month_count = monthly_sales_data[peak_idx] if peak_idx < len(monthly_sales_data) else 0
        sales_peak_month_revenue = monthly_revenue_data[peak_idx] if peak_idx < len(monthly_revenue_data) else 0

    # Build table data
    sales_month_table = []
    for i, label in enumerate(monthly_sales_labels):
        sales_month_table.append(
            {
                "month": label,
                "count": monthly_sales_data[i] if i < len(monthly_sales_data) else 0,
                "revenue": monthly_revenue_data[i] if i < len(monthly_revenue_data) else 0,
            }
        )

    ctx["sales_ytd_count"] = sales_ytd_count
    ctx["sales_ytd_revenue"] = sales_ytd_revenue
    ctx["sales_peak_month_label"] = sales_peak_month_label
    ctx["sales_peak_month_count"] = sales_peak_month_count
    ctx["sales_peak_month_revenue"] = sales_peak_month_revenue
    ctx["sales_month_table"] = sales_month_table

    # === New agent onboardings by month ===
    if _field(Membership, "created_at"):
        from django.db import connection

        if connection.vendor == "sqlite":
            # SQLite fallback: fetch raw data and group in Python
            onboardings_raw = (
                Membership.objects.filter(
                    role="AGENT", created_at__isnull=False, created_at__gte=year_start, created_at__lt=year_end
                )
                .values("created_at")
                .order_by("created_at")
            )

            # Group by month in Python
            from collections import defaultdict

            monthly_counts = defaultdict(int)

            for item in onboardings_raw:
                if item["created_at"]:
                    created_dt = item["created_at"]
                    month_key = (created_dt.year, created_dt.month)
                    monthly_counts[month_key] += 1

            # Sort and prepare chart data
            sorted_months = sorted(monthly_counts.keys())
            monthly_onboardings_labels = [dt(y, m, 1).strftime("%B") for y, m in sorted_months]
            monthly_onboardings_data = [monthly_counts[k] for k in sorted_months]
        else:
            # PostgreSQL/MySQL: use DB-level aggregation
            onboardings_by_month = (
                Membership.objects.filter(
                    role="AGENT", created_at__isnull=False, created_at__gte=year_start, created_at__lt=year_end
                )
                .annotate(month=TruncMonth("created_at"))
                .values("month")
                .annotate(count=Count("id"))
                .order_by("month")
            )

            monthly_onboardings_labels = []
            monthly_onboardings_data = []

            for item in onboardings_by_month:
                month_date = item["month"]
                if month_date:
                    monthly_onboardings_labels.append(month_date.strftime("%B"))
                    monthly_onboardings_data.append(item["count"])

        ctx["monthly_onboardings_labels"] = json.dumps(monthly_onboardings_labels)
        ctx["monthly_onboardings_data"] = json.dumps(monthly_onboardings_data)

        # === Chart context for onboardings ===
        onb_ytd_count = sum(monthly_onboardings_data) if monthly_onboardings_data else 0
        onb_peak_month_label = ""
        onb_peak_month_count = 0
        if monthly_onboardings_data and monthly_onboardings_labels:
            peak_idx = monthly_onboardings_data.index(max(monthly_onboardings_data)) if monthly_onboardings_data else 0
            onb_peak_month_label = (
                monthly_onboardings_labels[peak_idx] if peak_idx < len(monthly_onboardings_labels) else ""
            )
            onb_peak_month_count = monthly_onboardings_data[peak_idx] if peak_idx < len(monthly_onboardings_data) else 0

        onb_month_table = []
        for i, label in enumerate(monthly_onboardings_labels):
            onb_month_table.append(
                {"month": label, "count": monthly_onboardings_data[i] if i < len(monthly_onboardings_data) else 0}
            )

        ctx["onb_ytd_count"] = onb_ytd_count
        ctx["onb_peak_month_label"] = onb_peak_month_label
        ctx["onb_peak_month_count"] = onb_peak_month_count
        ctx["onb_month_table"] = onb_month_table
    else:
        ctx["monthly_onboardings_labels"] = json.dumps([])
        ctx["monthly_onboardings_data"] = json.dumps([])
        ctx["onb_ytd_count"] = 0
        ctx["onb_peak_month_label"] = ""
        ctx["onb_peak_month_count"] = 0
        ctx["onb_month_table"] = []

    # === Daily drill-down if month is selected ===
    if period_type == "month" and start_date and end_date:
        # SQLite-safe: filter out null sold_at, then group in Python if needed
        from django.db import connection

        if connection.vendor == "sqlite":
            # SQLite fallback: fetch raw data and group in Python
            sales_raw = (
                Sale.objects.filter(sold_at__isnull=False, sold_at__gte=start_date, sold_at__lt=end_date)
                .values("sold_at", "price")
                .order_by("sold_at")
            )

            # Group by date in Python
            from collections import defaultdict

            daily_data = defaultdict(lambda: {"count": 0, "revenue": 0})

            for sale in sales_raw:
                if sale["sold_at"]:
                    # Convert to date
                    day = sale["sold_at"].date() if hasattr(sale["sold_at"], "date") else sale["sold_at"]
                    daily_data[day]["count"] += 1
                    daily_data[day]["revenue"] += float(sale["price"] or 0)

            # Sort and prepare chart data
            sorted_days = sorted(daily_data.keys())
            daily_sales_labels = [d.strftime("%d") for d in sorted_days]
            daily_sales_data = [daily_data[d]["count"] for d in sorted_days]
            daily_revenue_data = [daily_data[d]["revenue"] for d in sorted_days]
        else:
            # PostgreSQL/MySQL: use DB-level aggregation
            sales_by_day = (
                Sale.objects.filter(sold_at__isnull=False, sold_at__gte=start_date, sold_at__lt=end_date)
                .annotate(day=TruncDate("sold_at"))
                .values("day")
                .annotate(count=Count("id"), revenue=Coalesce(Sum("price"), zero_dec))
                .order_by("day")
            )

            daily_sales_labels = []
            daily_sales_data = []
            daily_revenue_data = []

            for item in sales_by_day:
                day_date = item["day"]
                if day_date:
                    daily_sales_labels.append(day_date.strftime("%d"))
                    daily_sales_data.append(item["count"])
                    daily_revenue_data.append(float(item["revenue"]))

        ctx["daily_sales_labels"] = json.dumps(daily_sales_labels)
        ctx["daily_sales_data"] = json.dumps(daily_sales_data)
        ctx["daily_revenue_data"] = json.dumps(daily_revenue_data)

    # === Top 10 agents (global) ===
    # For simplicity, we'll aggregate across all businesses
    # In a real multi-tenant setup, you might want to scope this differently
    top_agents = (
        get_agent_rankings(
            business=None, start_date=start_date, end_date=end_date, limit=10  # We'll handle this in the utility
        )
        if start_date and end_date
        else []
    )

    # For now, let's do a simple global aggregate instead
    from django.contrib.auth import get_user_model

    User = get_user_model()

    # Include both agents and managers for HQ reporting
    agent_memberships = Membership.objects.filter(Q(role="AGENT") | Q(role="MANAGER"))
    agent_users = [m.user_id for m in agent_memberships if m.user_id]

    # Get sales attributed to agents/managers, handling missing agent gracefully
    top_agents_data = Sale.objects.filter(agent_id__in=agent_users) if agent_users else Sale.objects.none()

    if start_date and end_date:
        top_agents_data = top_agents_data.filter(sold_at__gte=start_date, sold_at__lt=end_date)

    top_agents_data = (
        top_agents_data.values("agent")
        .annotate(sales_count=Count("id"), revenue=Coalesce(Sum("price"), zero_dec))
        .order_by("-sales_count")[:10]
    )

    top_agents_list = []
    for item in top_agents_data:
        if not item.get("agent"):
            continue
        try:
            agent = User.objects.get(id=item["agent"])
            top_agents_list.append(
                {
                    "name": agent.get_full_name() or agent.username,
                    "sales_count": item["sales_count"],
                    "revenue": item["revenue"],
                }
            )
        except User.DoesNotExist:
            # Handle case where user was deleted
            top_agents_list.append(
                {"name": "Unknown Agent", "sales_count": item["sales_count"], "revenue": item["revenue"]}
            )

    ctx["top_agents"] = top_agents_list

    # Context for filters
    ctx["selected_year"] = year
    ctx["selected_period"] = period_type
    ctx["start_date"] = start_date
    ctx["end_date"] = end_date

    # Year range for selector
    current_year = timezone.now().year
    ctx["year_range"] = range(current_year - 5, current_year + 2)

    # active_tab for base.html mobile nav
    ctx["active_tab"] = "home"

    # Add contracts_enabled flag for sidebar
    ctx["contracts_enabled"] = CONTRACTS_ENABLED

    # Add filter options for analytics
    ctx["all_businesses"] = Business.objects.all().order_by("name")[:100]  # Limit for performance
    # Include both agents and managers in filter dropdowns
    ctx["all_agents"] = (
        Membership.objects.filter(Q(role="AGENT") | Q(role="MANAGER"))
        .select_related("user", "business")
        .order_by("user__username")[:100]
    )
    # Build base queryset first, then optionally filter by is_active if field exists
    locations_qs = Location.objects.select_related("business").order_by("business__name", "name")
    try:
        ctx["all_locations"] = locations_qs.filter(is_active=True)[:100]
    except FieldError:
        # Location model doesn't have is_active field, return all locations
        ctx["all_locations"] = locations_qs[:100]

    # Vertical options
    ctx["vertical_options"] = [
        ("", "All Verticals"),
        ("phones", "Phones"),
        ("clothing", "Clothing"),
        ("liquor", "Liquor"),
        ("pharmacy", "Pharmacy"),
        ("gym", "Gym"),
    ]

    # Payment mode options
    from sales.models import PaymentMethod

    ctx["payment_mode_options"] = [("", "All")] + list(PaymentMethod.choices)

    # Wallet balance (default to 0 if wallet feature not configured)
    ctx["wallet_balance"] = Decimal("0")
    ctx["wallet_currency"] = "MWK"

    return _render_safe(request, "hq/dashboard.html", ctx, _dashboard_inline)


# -------------------------------------------------------------------
# API: Monthly Drill-Down
# -------------------------------------------------------------------
@hq_admin_required
def monthly_drill_down_api(request):
    """
    JSON API endpoint for monthly drill-down data.
    Returns daily sales data for a specific month.

    Query params:
    - year (int): Year to query
    - month (int): Month to query (1-12)
    """
    try:
        year = int(request.GET.get("year", timezone.now().year))
        month = int(request.GET.get("month", timezone.now().month))

        if not (1 <= month <= 12 and 1900 <= year <= 2100):
            return JsonResponse({"error": "Invalid year or month"}, status=400)

        # Get date range for the month
        start_date, end_date = get_month_range(year, month)

        # Aggregate sales by day - SQLite-safe
        zero_dec = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))
        from django.db import connection

        if connection.vendor == "sqlite":
            # SQLite fallback: fetch raw data and group in Python
            sales_raw = (
                Sale.objects.filter(sold_at__isnull=False, sold_at__gte=start_date, sold_at__lt=end_date)
                .values("sold_at", "price")
                .order_by("sold_at")
            )

            from collections import defaultdict

            daily_sales = defaultdict(lambda: {"count": 0, "revenue": 0})

            for sale in sales_raw:
                if sale["sold_at"]:
                    day = sale["sold_at"].date() if hasattr(sale["sold_at"], "date") else sale["sold_at"]
                    daily_sales[day]["count"] += 1
                    daily_sales[day]["revenue"] += float(sale["price"] or 0)

            daily_data = [
                {
                    "date": day.isoformat(),
                    "day": day.day,
                    "sales_count": daily_sales[day]["count"],
                    "revenue": daily_sales[day]["revenue"],
                }
                for day in sorted(daily_sales.keys())
            ]
        else:
            # PostgreSQL/MySQL: use DB-level aggregation
            sales_by_day = (
                Sale.objects.filter(sold_at__isnull=False, sold_at__gte=start_date, sold_at__lt=end_date)
                .annotate(day=TruncDate("sold_at"))
                .values("day")
                .annotate(count=Count("id"), revenue=Coalesce(Sum("price"), zero_dec))
                .order_by("day")
            )

            daily_data = [
                {
                    "date": item["day"].isoformat(),
                    "day": item["day"].day,
                    "sales_count": item["count"],
                    "revenue": float(item["revenue"]),
                }
                for item in sales_by_day
                if item["day"]
            ]

        # Aggregate new onboardings by day (if available) - SQLite-safe
        if _field(Membership, "created_at"):
            if connection.vendor == "sqlite":
                # SQLite fallback
                onboardings_raw = (
                    Membership.objects.filter(
                        role="AGENT", created_at__isnull=False, created_at__gte=start_date, created_at__lt=end_date
                    )
                    .values("created_at")
                    .order_by("created_at")
                )

                from collections import defaultdict

                daily_onboardings = defaultdict(int)

                for item in onboardings_raw:
                    if item["created_at"]:
                        day = item["created_at"].date() if hasattr(item["created_at"], "date") else item["created_at"]
                        daily_onboardings[day] += 1

                onboarding_data = [
                    {"date": day.isoformat(), "day": day.day, "count": daily_onboardings[day]}
                    for day in sorted(daily_onboardings.keys())
                ]
            else:
                # PostgreSQL/MySQL
                onboardings_by_day = (
                    Membership.objects.filter(
                        role="AGENT", created_at__isnull=False, created_at__gte=start_date, created_at__lt=end_date
                    )
                    .annotate(day=TruncDate("created_at"))
                    .values("day")
                    .annotate(count=Count("id"))
                    .order_by("day")
                )

                onboarding_data = [
                    {"date": item["day"].isoformat(), "day": item["day"].day, "count": item["count"]}
                    for item in onboardings_by_day
                    if item["day"]
                ]
        else:
            onboarding_data = []

        return JsonResponse(
            {
                "year": year,
                "month": month,
                "daily_sales": daily_data,
                "daily_onboardings": onboarding_data,
            }
        )

    except (ValueError, TypeError) as e:
        return JsonResponse({"error": f"Invalid parameters: {str(e)}"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)


# -------------------------------------------------------------------
# Businesses
# -------------------------------------------------------------------
@hq_admin_required
def businesses(request):
    # Log HQ access to businesses list
    from audit.utils import log_hq_action

    log_hq_action(request, action="VIEW_PAGE", entity_type="BUSINESS_LIST", message="Accessed businesses list")

    start, end, rng = _date_range_from_request(request)
    q = (request.GET.get("q") or "").strip()

    rows = Business.objects.all()
    rows = rows.order_by("-created_at") if _field(Business, "created_at") else rows.order_by("name")

    if q:
        rows = rows.filter(Q(name__icontains=q) | Q(slug__icontains=q))

    page_obj = _paginate(request, rows, per_page=25)
    ctx = {
        "rows": rows,
        "page_obj": page_obj,
        "q": q,
        "range": rng,
        "start": start,
        "end": end,
        "active_tab": "businesses",
        "contracts_enabled": CONTRACTS_ENABLED,
    }
    return _render_safe(
        request, "hq/businesses.html", ctx, lambda c: "<h1 style='font-family:system-ui'>Businesses</h1>"
    )


@hq_admin_required
def business_detail(request, pk: int):
    biz = get_object_or_404(Business, pk=pk)

    # Log HQ access to business detail
    from audit.utils import log_hq_action

    log_hq_action(
        request,
        action="VIEW_PAGE",
        entity_type="Business",
        entity_id=pk,
        message=f"Viewed business detail: {biz.name}",
        business=biz,
    )

    start, end, rng = _date_range_from_request(request)

    inv = Invoice.objects.filter(business=biz)
    date_field = (
        "issue_date" if _field(Invoice, "issue_date") else ("created_at" if _field(Invoice, "created_at") else None)
    )
    if date_field and start and end:
        inv = _range_filter(inv, Invoice, date_field, start, end)

    paid_total = inv.filter(status__in=["PAID", "SETTLED", "paid"]).aggregate(
        v=Coalesce(Sum("total"), Value(0, output_field=DecimalField(max_digits=18, decimal_places=2)))
    )["v"]
    open_total = inv.exclude(status__in=["PAID", "SETTLED", "paid"]).aggregate(
        v=Coalesce(Sum("total"), Value(0, output_field=DecimalField(max_digits=18, decimal_places=2)))
    )["v"]

    subs_qs = Subscription.objects.filter(business=biz)
    active_subs = subs_qs.filter(status__in=["ACTIVE", "active"]).count()
    if _field(Subscription, "plan"):
        mrr = subs_qs.filter(status__in=["ACTIVE", "active"]).aggregate(
            v=Coalesce(Sum("plan__amount"), Value(0, output_field=DecimalField(max_digits=18, decimal_places=2)))
        )["v"]
    else:
        mrr = subs_qs.filter(status__in=["ACTIVE", "active"]).aggregate(
            v=Coalesce(Sum("amount"), Value(0, output_field=DecimalField(max_digits=18, decimal_places=2)))
        )["v"]

    trunc_base = (
        "issue_date" if _field(Invoice, "issue_date") else ("created_at" if _field(Invoice, "created_at") else None)
    )
    if trunc_base:
        paid_series_qs = (
            inv.filter(status__in=["PAID", "SETTLED", "paid"])
            .annotate(m=TruncMonth(trunc_base))
            .values("m")
            .order_by("m")
            .annotate(
                amount=Coalesce(Sum("total"), Value(0, output_field=DecimalField(max_digits=18, decimal_places=2)))
            )
        )
    else:
        paid_series_qs = []

    agents_qs = Membership.objects.filter(role="AGENT", business=biz).select_related("user")
    limits = _limits_for_business(biz)

    # Get subscription for membership controls - handle missing subscription safely
    subscription = None
    try:
        subscription = biz.subscription
    except Subscription.DoesNotExist:
        subscription = None
    except AttributeError:
        subscription = None

    total_invoices = inv.count()

    ctx = {
        "biz": biz,
        "range": rng,
        "start": start,
        "end": end,
        "paid_total": paid_total,
        "open_total": open_total,
        "total_invoices": total_invoices,
        "active_subs": active_subs,
        "mrr": mrr,
        "agents_qs": agents_qs,
        "subscription": subscription,
        "series_paid": [
            {"label": (r["m"].strftime("%Y-%m") if r["m"] else ""), "amount": float(r["amount"] or 0)}
            for r in paid_series_qs
        ],
        "limits": limits,
        "active_tab": "businesses",
        "contracts_enabled": CONTRACTS_ENABLED,
    }
    return _render_safe(
        request, "hq/business_detail.html", ctx, lambda c: f"<h1 style='font-family:system-ui'>{_esc(biz.name)}</h1>"
    )


# -------------------------------------------------------------------
# Subscriptions
# -------------------------------------------------------------------
@hq_admin_required
def subscriptions(request):
    # Log HQ access to subscriptions list
    from audit.utils import log_hq_action

    log_hq_action(request, action="VIEW_PAGE", entity_type="SUBSCRIPTION_LIST", message="Accessed subscriptions list")

    start, end, rng = _date_range_from_request(request)
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Subscription.objects.select_related("business", "plan")

    if q:
        qs = qs.filter(
            Q(business__name__icontains=q)
            | Q(business__slug__icontains=q)
            | Q(plan__name__icontains=q)
            | Q(plan__code__icontains=q)
        )
    if status:
        qs = qs.filter(status__iexact=status)

    if start and end and _field(Subscription, "created_at"):
        qs = _range_filter(qs, Subscription, "created_at", start, end)

    order_field = "-created_at" if _field(Subscription, "created_at") else "-id"
    qs = qs.order_by(order_field)

    page = _paginate(request, qs, per_page=25)

    ctx = {
        "subscriptions": page,
        "subscriptions_qs": qs,
        "subs": page,
        "rows": page.object_list,
        "object_list": page.object_list,
        "items": page.object_list,
        "page_obj": page,
        "count": qs.count(),
        "total": qs.count(),
        "q": q,
        "status": status,
        "range": rng,
        "start": start,
        "end": end,
        "plan_catalog": PLAN_CATALOG,
        "active_tab": "subscriptions",
        "contracts_enabled": CONTRACTS_ENABLED,
    }

    tpl = select_template(["hq/subscriptions.html", "billing/hq_subscriptions.html"])
    # Render the selected template directly to avoid name confusion
    return HttpResponse(tpl.render(ctx, request))


# -------------------------------------------------------------------
# Invoices
# -------------------------------------------------------------------
@hq_admin_required
def invoices(request):
    # Log HQ access to invoices list
    from audit.utils import log_hq_action

    log_hq_action(request, action="VIEW_PAGE", entity_type="INVOICE_LIST", message="Accessed invoices list")

    qs = Invoice.objects.select_related("business", "created_by")

    status = (request.GET.get("status") or "").strip()
    if status:
        qs = qs.filter(status__iexact=status)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(business__name__icontains=q))

    # Business filter
    business_id = request.GET.get("business_id")
    if business_id:
        try:
            qs = qs.filter(business_id=int(business_id))
        except (ValueError, TypeError):
            pass

    order_field = "-created_at" if _field(Invoice, "created_at") else "-id"
    qs = qs.order_by(order_field)

    page_obj = Paginator(qs, 25).get_page(request.GET.get("page"))

    # Get all businesses for dropdown (with subscription info)
    businesses = Business.objects.select_related("subscription").order_by("name")[:100]

    ctx = {
        "page_obj": page_obj,
        "invoices": page_obj,
        "active_tab": "invoices",
        "contracts_enabled": CONTRACTS_ENABLED,
        "all_businesses": businesses,
        "selected_business_id": business_id,
        "status": status,
        "q": q,
    }
    return render(request, "hq/invoices.html", ctx)


# -------------------------------------------------------------------
# Agents
# -------------------------------------------------------------------
@hq_admin_required
def agents(request):
    """HQ Agents list page - shows all agents and managers across all businesses"""
    # Log HQ access to agents list (optional, don't fail if audit not available)
    try:
        from audit.utils import log_hq_action

        log_hq_action(request, action="VIEW_PAGE", entity_type="AGENT_LIST", message="Accessed agents list")
    except Exception:
        pass  # Audit logging is optional

    q = (request.GET.get("q") or "").strip()
    # Include both AGENT and MANAGER roles for HQ reporting
    # Use safe select_related - location is nullable
    try:
        rows = Membership.objects.filter(Q(role="AGENT") | Q(role="MANAGER")).select_related("business", "user")
        # Location might be nullable, so prefetch it separately to avoid issues
        rows = rows.prefetch_related("location")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error querying memberships: {e}", exc_info=True)
        rows = Membership.objects.none()

    # Apply search filter if provided
    if q:
        try:
            rows = rows.filter(Q(user__username__icontains=q) | Q(business__name__icontains=q))
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Error applying search filter: {e}")

    # Safe ordering - created_at exists on Membership model
    try:
        rows = rows.order_by("-created_at")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Error ordering rows: {e}")
        rows = rows.order_by("-id")

    # Limits per business to enable UI nudges (e.g., â€œUpgrade to add more agentsâ€)
    biz_limits = {}
    for b_id in rows.values_list("business_id", flat=True).distinct():
        if not b_id:
            continue
        try:
            biz = Business.objects.get(pk=b_id)
            lim = _limits_for_business(biz)
            if lim:
                agent_count = Membership.objects.filter(role="AGENT", business_id=b_id).count()
                lim = {**lim, "agent_count": agent_count}
            biz_limits[b_id] = lim
        except Business.DoesNotExist:
            biz_limits[b_id] = None
        except Exception as e:
            # Don't crash on subscription or other errors
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Error getting limits for business {b_id}: {e}")
            biz_limits[b_id] = None

    ctx = {
        "rows": rows,
        "page_obj": _paginate(request, rows, per_page=30),
        "q": q,
        "biz_limits": biz_limits,
        "active_tab": "agents",
        "contracts_enabled": CONTRACTS_ENABLED,
    }
    return _render_safe(request, "hq/agents.html", ctx, lambda c: "<h1 style='font-family:system-ui'>Agents</h1>")


# -------------------------------------------------------------------
# Stock trends (SQLite-safe with filters)
# -------------------------------------------------------------------
@hq_admin_required
def stock_trends(request):
    """
    HQ Stock Trends (SQLite-safe)
    """
    # Log HQ access to stock trends
    from audit.utils import log_hq_action

    log_hq_action(request, action="VIEW_PAGE", entity_type="STOCK_TRENDS", message="Accessed stock trends")

    # dates
    def _parse(dtxt, fallback):
        try:
            return timezone.datetime.fromisoformat(dtxt).date()
        except Exception:
            return fallback

    today = timezone.localdate()
    default_start = today - timedelta(days=29)
    start = _parse(request.GET.get("start") or "", default_start)
    end = _parse(request.GET.get("end") or "", today)
    if start > end:
        start, end = end, start

    # Use whichever manager exists
    base = getattr(InventoryItem, "all_objects", InventoryItem.objects).all()

    biz_id = request.GET.get("business")
    loc_id = request.GET.get("location")
    agent_id = request.GET.get("agent")
    city = (request.GET.get("city") or "").strip()

    if biz_id:
        base = base.filter(business_id=biz_id)
    if loc_id:
        base = base.filter(current_location_id=loc_id)
    if agent_id:
        base = base.filter(assigned_agent_id=agent_id)
    if city:
        base = base.filter(current_location__city__icontains=city)

    # KPIs all-time
    total_in = base.count()
    total_out = base.filter(status="SOLD").count()
    sell_through_pct = round((total_out / total_in * 100.0), 2) if total_in else 0.0

    # Daily IN
    daily_in = (
        base.filter(received_at__gte=start, received_at__lte=end)
        .values("received_at")
        .order_by("received_at")
        .annotate(v=Count("id"))
    )
    m_in = {row["received_at"]: int(row["v"]) for row in daily_in}

    # Daily OUT
    sold_qs = base.filter(sold_at__isnull=False, sold_at__date__gte=start, sold_at__date__lte=end)
    daily_out = (
        sold_qs.annotate(d=Cast("sold_at", output_field=models.DateField()))
        .values("d")
        .order_by("d")
        .annotate(v=Count("id"))
    )
    m_out = {row["d"]: int(row["v"]) for row in daily_out}

    # date axis
    dates = []
    cur = start
    while cur <= end:
        dates.append(cur)
        cur += timedelta(days=1)

    d_labels = [d.isoformat() for d in dates]
    series_in = [m_in.get(d, 0) for d in dates]
    series_out = [m_out.get(d, 0) for d in dates]

    # ma7
    ma7, s, window = [], 0, deque()
    for x in series_out:
        window.append(x)
        s += x
        if len(window) > 7:
            s -= window.popleft()
        ma7.append(round(s / len(window), 2))

    # cumulative
    cum_in, cum_out = [], []
    acc_i = acc_o = 0
    for i, o in zip(series_in, series_out):
        acc_i += i
        acc_o += o
        cum_in.append(acc_i)
        cum_out.append(acc_o)

    # trend (simple linear regression over index)
    n = len(series_out)
    if n > 1:
        sx = n * (n - 1) / 2
        sx2 = (n - 1) * n * (2 * n - 1) / 6
        sy = sum(series_out)
        sxy = sum(i * y for i, y in enumerate(series_out))
        denom = (n * sx2 - sx * sx) or 1
        a = (n * sxy - sx * sy) / denom
        b = (sy - a * sx) / n
        out_trend = [round(a * i + b, 2) for i in range(n)]
    else:
        out_trend = series_out[:]

    # period KPIs
    days_count = max(1, (end - start).days + 1)
    total_out_period = sum(series_out)
    avg_daily_out = round(total_out_period / days_count, 2)
    projected_monthly_run_rate = round(avg_daily_out * 30, 2)

    ctx = {
        "start": start,
        "end": end,
        "d_labels": d_labels,
        "series_in": series_in,
        "series_out": series_out,
        "ma7": ma7,
        "cum_in": cum_in,
        "cum_out": cum_out,
        "out_trend": out_trend,
        "total_in": total_in,
        "total_out": total_out,
        "sell_through_pct": sell_through_pct,
        "avg_daily_out": avg_daily_out,
        "projected_monthly_run_rate": projected_monthly_run_rate,
        "active_tab": "stock",
        "contracts_enabled": CONTRACTS_ENABLED,
    }
    return _render_safe(
        request,
        "hq/stock_trends.html",
        ctx,
        lambda c: "<h1 style='font-family:system-ui'>Stock Trends</h1>",
    )


# -------------------------------------------------------------------
# Wallet
# -------------------------------------------------------------------
@hq_admin_required
def wallet_home(request):
    """
    Rebuilt HQ Wallet: Business table with payment tracking, filters, and graphs.
    """
    from audit.utils import log_hq_action

    log_hq_action(request, action="VIEW_PAGE", entity_type="HQ_WALLET", message="Accessed HQ wallet")

    # Parse filters
    start, end, rng = _date_range_from_request(request)
    plan_filter = request.GET.get("plan", "").strip()
    status_filter = request.GET.get("status", "").strip()  # paid/unpaid
    search_query = request.GET.get("q", "").strip()

    # Build business queryset with subscription details
    businesses = Business.objects.select_related("subscription").all()

    if search_query:
        businesses = businesses.filter(Q(name__icontains=search_query) | Q(slug__icontains=search_query))

    # Plan filter
    if plan_filter:
        businesses = businesses.filter(subscription__plan__code=plan_filter)

    # Enrich businesses with payment status
    business_rows = []
    for biz in businesses:
        try:
            sub = biz.subscription
            plan_name = sub.plan.name if sub and hasattr(sub, "plan") and sub.plan else "No Plan"
            plan_code = sub.plan.code if sub and hasattr(sub, "plan") and sub.plan else ""
            amount = sub.plan.amount if sub and hasattr(sub, "plan") and sub.plan else Decimal("0.00")
            sub_status = sub.status if sub else "none"

            # Check last payment mark
            from hq.models import HQPaymentMark

            last_mark = HQPaymentMark.objects.filter(business=biz).order_by("-period_start").first()
            paid_status = "paid" if last_mark and last_mark.period_end >= timezone.now().date() else "unpaid"
            last_payment_date = last_mark.marked_at if last_mark else None

            # Apply status filter
            if status_filter and status_filter != paid_status:
                continue

            business_rows.append(
                {
                    "id": biz.id,
                    "name": biz.name,
                    "plan": plan_name,
                    "plan_code": plan_code,
                    "amount": amount,
                    "sub_status": sub_status,
                    "paid_status": paid_status,
                    "last_payment_date": last_payment_date,
                    "next_due": sub.next_billing_date if sub and hasattr(sub, "next_billing_date") else None,
                }
            )
        except Exception:
            # Handle businesses without subscriptions gracefully
            business_rows.append(
                {
                    "id": biz.id,
                    "name": biz.name,
                    "plan": "No Plan",
                    "plan_code": "",
                    "amount": Decimal("0.00"),
                    "sub_status": "none",
                    "paid_status": "unpaid",
                    "last_payment_date": None,
                    "next_due": None,
                }
            )

    # Pagination
    paginator = Paginator(business_rows, 25)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    # Graph data: Revenue over time (paid invoices)
    zero = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))
    inv = Invoice.objects.filter(status__in=["PAID", "SETTLED", "paid"])
    date_field = (
        "issue_date" if _field(Invoice, "issue_date") else ("created_at" if _field(Invoice, "created_at") else None)
    )

    if date_field and start and end:
        inv = _range_filter(inv, Invoice, date_field, start, end)

    # Monthly revenue aggregation
    if date_field:
        from django.db import connection

        if connection.vendor == "sqlite":
            # SQLite fallback
            revenue_raw = inv.values(date_field, "total").order_by(date_field)
            from collections import defaultdict

            monthly_revenue = defaultdict(float)
            for item in revenue_raw:
                if item[date_field]:
                    month_key = (
                        item[date_field].strftime("%Y-%m")
                        if hasattr(item[date_field], "strftime")
                        else str(item[date_field])[:7]
                    )
                    monthly_revenue[month_key] += float(item["total"] or 0)
            revenue_labels = sorted(monthly_revenue.keys())
            revenue_data = [monthly_revenue[k] for k in revenue_labels]
        else:
            revenue_by_month = (
                inv.annotate(month=TruncMonth(date_field))
                .values("month")
                .annotate(revenue=Coalesce(Sum("total"), zero))
                .order_by("month")
            )
            revenue_labels = [r["month"].strftime("%Y-%m") if r["month"] else "" for r in revenue_by_month]
            revenue_data = [float(r["revenue"]) for r in revenue_by_month]
    else:
        revenue_labels = []
        revenue_data = []

    # Paid vs unpaid counts
    paid_count = len([r for r in business_rows if r["paid_status"] == "paid"])
    unpaid_count = len([r for r in business_rows if r["paid_status"] == "unpaid"])

    # Plan distribution
    from collections import Counter

    plan_distribution = Counter([r["plan"] for r in business_rows if r["plan"] != "No Plan"])

    # Total income
    income = inv.aggregate(v=Coalesce(Sum("total"), zero))["v"]

    ctx = {
        "businesses": page_obj,
        "page_obj": page_obj,
        "income": income,
        "balance": income,  # Simplified
        "range": rng,
        "start": start,
        "end": end,
        "plan_filter": plan_filter,
        "status_filter": status_filter,
        "search_query": search_query,
        "revenue_labels": json.dumps(revenue_labels),
        "revenue_data": json.dumps(revenue_data),
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "plan_distribution": json.dumps(dict(plan_distribution)),
        "active_tab": "wallet",
        "contracts_enabled": CONTRACTS_ENABLED,
    }
    return render(request, "hq/wallet.html", ctx)


@hq_admin_required
def wallet_mark_paid(request):
    """
    Mark a business as paid for a specific period (idempotent).
    POST: business_id, period_start, period_end, amount
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    from audit.utils import log_hq_action
    from hq.models import HQPaymentMark

    try:
        business_id = int(request.POST.get("business_id"))
        period_start = request.POST.get("period_start")
        period_end = request.POST.get("period_end")
        amount = Decimal(request.POST.get("amount", "0"))
        notes = request.POST.get("notes", "")

        biz = get_object_or_404(Business, id=business_id)

        # Parse dates
        from datetime import datetime as dt

        p_start = dt.strptime(period_start, "%Y-%m-%d").date()
        p_end = dt.strptime(period_end, "%Y-%m-%d").date()

        # Get plan code
        plan_code = ""
        try:
            sub = biz.subscription
            if sub and hasattr(sub, "plan") and sub.plan:
                plan_code = sub.plan.code
        except Exception:
            pass

        # Create or update mark (idempotent)
        mark, created = HQPaymentMark.objects.update_or_create(
            business=biz,
            period_start=p_start,
            period_end=p_end,
            defaults={
                "plan_code": plan_code,
                "amount": amount,
                "marked_by": request.user,
                "marked_at": timezone.now(),
                "notes": notes,
            },
        )

        # Log action
        log_hq_action(
            request,
            action="MARK_PAID",
            entity_type="Business",
            entity_id=business_id,
            message=f"Marked {biz.name} as paid for {period_start} to {period_end}: {amount}",
            business=biz,
        )

        return JsonResponse(
            {
                "ok": True,
                "created": created,
                "mark": {
                    "period_start": mark.period_start.isoformat(),
                    "period_end": mark.period_end.isoformat(),
                    "amount": str(mark.amount),
                    "marked_at": mark.marked_at.isoformat(),
                },
            }
        )

    except (ValueError, TypeError) as e:
        return JsonResponse({"ok": False, "error": f"Invalid data: {str(e)}"}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


# -------------------------------------------------------------------
# APIs (dashboard/widgets)
# -------------------------------------------------------------------
@login_required
def api_wallet_income(request):
    """
    JSON API endpoint for wallet income data.
    Returns daily income breakdown for a date range.

    Query params:
    - start (YYYY-MM-DD, required): Start date
    - end (YYYY-MM-DD, required): End date
    - currency (default "MWK"): Currency filter
    """
    # Permission check: HQ admin only
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({"error": "Forbidden"}, status=403)

    # Parse query parameters
    start_raw = request.GET.get("start", "").strip()
    end_raw = request.GET.get("end", "").strip()
    currency = request.GET.get("currency", "MWK").strip().upper()

    # Validate required parameters
    if not start_raw or not end_raw:
        return JsonResponse({"error": "start and end parameters are required (YYYY-MM-DD)"}, status=400)

    # Parse dates
    try:
        start_d = datetime.date.fromisoformat(start_raw)
        end_d = datetime.date.fromisoformat(end_raw)
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": f"Invalid date format: {str(e)}. Use YYYY-MM-DD"}, status=400)

    # Validate date range
    if start_d > end_d:
        return JsonResponse({"error": "start date must be before or equal to end date"}, status=400)

    # Query paid invoices
    qs = Invoice.objects.filter(status__in=["PAID", "SETTLED", "paid"])

    # Filter by currency if Invoice model has currency field
    if _field(Invoice, "currency"):
        qs = qs.filter(currency=currency)

    # Determine date field to use
    df_name = (
        "paid_at"
        if _field(Invoice, "paid_at")
        else (
            "issue_date" if _field(Invoice, "issue_date") else ("created_at" if _field(Invoice, "created_at") else None)
        )
    )
    if not df_name:
        return JsonResponse([], safe=False)

    # Filter by date range
    qs = _range_filter(qs, Invoice, df_name, start_d, end_d)

    # Determine amount field
    amount_field = "total" if _field(Invoice, "total") else ("amount" if _field(Invoice, "amount") else None)
    if not amount_field:
        return JsonResponse([], safe=False)

    # Aggregate by day
    f = _field(Invoice, df_name)
    if isinstance(f, models.DateTimeField):
        agg = qs.annotate(day=TruncDate(df_name)).values("day").order_by("day").annotate(amount=Sum(amount_field))
        data = [{"date": (row["day"] or start_d).isoformat(), "amount": float(row["amount"] or 0)} for row in agg]
    else:
        agg = qs.values(df_name).order_by(df_name).annotate(amount=Sum(amount_field))
        data = [{"date": (row[df_name] or start_d).isoformat(), "amount": float(row["amount"] or 0)} for row in agg]

    return JsonResponse(data, safe=False)


@hq_admin_required
def api_mrr_timeseries(request):
    zero = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))
    has_plan = _field(Subscription, "plan")
    amount_field = "plan__amount" if has_plan else "amount"
    created_field = "created_at" if _field(Subscription, "created_at") else None

    qs = Subscription.objects.all()
    if created_field:
        qs = (
            qs.annotate(m=TruncMonth(created_field))
            .values("m")
            .order_by("m")
            .annotate(mrr=Coalesce(Sum(amount_field), zero))
        )
        data = [{"date": (r["m"].strftime("%Y-%m") if r["m"] else ""), "mrr": float(r["mrr"] or 0)} for r in qs]
    else:
        total = Subscription.objects.aggregate(v=Coalesce(Sum(amount_field), zero))["v"]
        data = [{"date": timezone.now().date().strftime("%Y-%m"), "mrr": float(total or 0)}]
    return JsonResponse(data, safe=False)


@hq_admin_required
def api_search_suggest(request):
    term = (request.GET.get("q") or "").strip()
    out = []
    if not term:
        return JsonResponse(out, safe=False)

    try:
        out.append(
            {
                "label": f"Businesses matching â€œ{term}â€",
                "type": "Businesses",
                "url": f"{reverse('hq:businesses')}?q={term}",
            }
        )
    except Exception:
        pass
    try:
        out.append(
            {"label": f"Invoices for â€œ{term}â€", "type": "Invoices", "url": f"{reverse('hq:invoices')}?q={term}"}
        )
    except Exception:
        pass
    try:
        out.append(
            {
                "label": f"Subscriptions with â€œ{term}â€",
                "type": "Subscriptions",
                "url": f"{reverse('hq:subscriptions')}?q={term}",
            }
        )
    except Exception:
        pass
    try:
        out.append({"label": f"Agents named â€œ{term}â€", "type": "Agents", "url": f"{reverse('hq:agents')}?q={term}"})
    except Exception:
        pass
    return JsonResponse(out, safe=False)


@hq_admin_required
def hq_notifications_api(request):
    """
    HQ Notifications API endpoint.
    Returns JSON with notification data. Supports 'since' query parameter.

    Returns:
    {
        "items": [
            {
                "id": "...",
                "level": "info|warning|danger",
                "title": "...",
                "body": "...",
                "url": "...",
                "ts": "ISO"
            }
        ],
        "unread_count": N
    }

    Must never 404 - always returns 200 with at least empty list.
    """
    try:
        since = request.GET.get("since", "").strip()
        items = []
        unread_count = 0

        # Check for expiring subscriptions within 7 days
        try:
            from datetime import timedelta

            from django.utils import timezone

            from billing.models import Subscription

            seven_days_from_now = timezone.now().date() + timedelta(days=7)
            expiring_subs = Subscription.objects.filter(
                status="ACTIVE", expires_at__lte=seven_days_from_now, expires_at__gt=timezone.now().date()
            ).order_by("expires_at")[:10]

            for sub in expiring_subs:
                items.append(
                    {
                        "id": f"sub-expiring-{sub.id}",
                        "level": "warning",
                        "title": f"Subscription Expiring: {sub.business.name if hasattr(sub, 'business') else 'Unknown'}",
                        "body": f"Expires on {sub.expires_at.strftime('%Y-%m-%d')}",
                        "url": f"/hq/subscriptions/{sub.id}/",
                        "ts": sub.expires_at.isoformat()
                        if hasattr(sub.expires_at, "isoformat")
                        else str(sub.expires_at),
                    }
                )
        except Exception:
            # Subscription model may not exist - skip
            pass

        # Check for failed invoices last 7 days
        try:
            from datetime import timedelta

            from django.utils import timezone

            from billing.models import Invoice

            seven_days_ago = timezone.now() - timedelta(days=7)
            failed_invoices = Invoice.objects.filter(
                status__in=["FAILED", "OVERDUE", "UNPAID"], created_at__gte=seven_days_ago
            ).order_by("-created_at")[:10]

            for inv in failed_invoices:
                items.append(
                    {
                        "id": f"inv-failed-{inv.id}",
                        "level": "danger",
                        "title": f"Failed Invoice: {inv.business.name if hasattr(inv, 'business') else 'Unknown'}",
                        "body": f"Amount: {inv.amount if hasattr(inv, 'amount') else 'N/A'}",
                        "url": f"/hq/invoices/{inv.id}/",
                        "ts": inv.created_at.isoformat()
                        if hasattr(inv.created_at, "isoformat")
                        else str(inv.created_at),
                    }
                )
        except Exception:
            # Invoice model may not exist - skip
            pass

        # Check for new businesses last 7 days
        try:
            from datetime import timedelta

            from django.utils import timezone

            seven_days_ago = timezone.now() - timedelta(days=7)
            new_businesses = Business.objects.filter(created_at__gte=seven_days_ago).order_by("-created_at")[:10]

            for biz in new_businesses:
                items.append(
                    {
                        "id": f"biz-new-{biz.id}",
                        "level": "info",
                        "title": f"New Business: {biz.name}",
                        "body": f"Created on {biz.created_at.strftime('%Y-%m-%d') if hasattr(biz.created_at, 'strftime') else str(biz.created_at)}",
                        "url": f"/hq/businesses/{biz.id}/",
                        "ts": biz.created_at.isoformat()
                        if hasattr(biz.created_at, "isoformat")
                        else str(biz.created_at),
                    }
                )
        except Exception:
            # Business model may not exist - skip
            pass

        unread_count = len(items)

        return JsonResponse(
            {
                "items": items,
                "unread_count": unread_count,
            }
        )

    except Exception as e:
        # Never crash - return empty list
        logger.error(f"hq_notifications_api error: {e}", exc_info=True)
        return JsonResponse(
            {
                "items": [],
                "unread_count": 0,
            }
        )


# -------------------------------------------------------------------
# HQ Analytics API Endpoint
# -------------------------------------------------------------------
@hq_admin_required
def api_analytics_data(request):
    """
    JSON API endpoint for HQ analytics data.
    Returns KPIs, chart series, breakdowns, and top lists based on filters.

    Query params:
    - start_date (YYYY-MM-DD): Start date (default: 30 days ago)
    - end_date (YYYY-MM-DD): End date (default: today)
    - business_id (int): Filter by business
    - agent_id (int): Filter by agent
    - vertical (str): Filter by vertical (phones, clothing, liquor, pharmacy, gym)
    - payment_mode (str): Filter by payment method (CASH, BANK, MOBILE_MONEY)
    - location_id (int): Filter by location
    - sale_type (str): Filter by sale type (credit/cash) - if supported
    """
    try:
        # Parse date range
        start_date = None
        end_date = None
        start_str = request.GET.get("start_date", "").strip()
        end_str = request.GET.get("end_date", "").strip()

        if start_str:
            try:
                start_date = dt.strptime(start_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        if end_str:
            try:
                end_date = dt.strptime(end_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        # Parse other filters
        business_id = None
        if request.GET.get("business_id"):
            try:
                business_id = int(request.GET.get("business_id"))
            except (ValueError, TypeError):
                pass

        agent_id = None
        if request.GET.get("agent_id"):
            try:
                agent_id = int(request.GET.get("agent_id"))
            except (ValueError, TypeError):
                pass

        vertical = request.GET.get("vertical", "").strip() or None
        payment_mode = request.GET.get("payment_mode", "").strip() or None
        location_id = None
        if request.GET.get("location_id"):
            try:
                location_id = int(request.GET.get("location_id"))
            except (ValueError, TypeError):
                pass

        sale_type = request.GET.get("sale_type", "").strip() or None

        # Get analytics data
        data = get_hq_analytics_data(
            start_date=start_date,
            end_date=end_date,
            business_id=business_id,
            agent_id=agent_id,
            vertical=vertical,
            payment_mode=payment_mode,
            location_id=location_id,
            sale_type=sale_type,
        )

        return JsonResponse(data, safe=False)

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.exception("Error in api_analytics_data")
        return JsonResponse({"error": str(e)}, status=500)


@hq_admin_required
def hq_analytics(request):
    """
    HQ Analytics page with filters across businesses/verticals.
    Hardened to never 500: safe filter parsing, defaults for all edge cases.
    """
    try:
        # Parse date range with safe defaults
        start_date = None
        end_date = None
        start_str = request.GET.get("start", "").strip()
        end_str = request.GET.get("end", "").strip()
        preset = request.GET.get("preset", "").strip()

        today = timezone.now().date()

        # Handle preset (safe: unknown presets fall through to defaults)
        if preset == "today":
            start_date = today
            end_date = today
        elif preset == "yesterday":
            start_date = today - timedelta(days=1)
            end_date = start_date
        elif preset == "last_7d":
            start_date = today - timedelta(days=6)
            end_date = today
        elif preset == "last_30d":
            start_date = today - timedelta(days=29)
            end_date = today
        elif preset == "this_month":
            start_date = today.replace(day=1)
            end_date = today
        elif preset == "last_month":
            first_day_this_month = today.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            start_date = last_day_last_month.replace(day=1)
            end_date = last_day_last_month
        elif preset == "all_time":
            start_date = today.replace(month=1, day=1, year=today.year - 2)
            end_date = today
        elif start_str or end_str:
            # Custom date range (safe parsing: invalid dates ignored)
            if start_str:
                try:
                    start_date = dt.strptime(start_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    pass
            if end_str:
                try:
                    end_date = dt.strptime(end_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    pass

        # Default: last 30 days if no valid dates parsed
        if not start_date:
            start_date = today - timedelta(days=30)
        if not end_date:
            end_date = today

        # Ensure start <= end
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        # Parse filters (safe: invalid values become None)
        business_id = None
        if request.GET.get("business_id"):
            try:
                business_id = int(request.GET.get("business_id"))
            except (ValueError, TypeError):
                pass

        vertical = request.GET.get("vertical", "").strip() or None
        # Validate vertical against known options
        valid_verticals = ["phones", "clothing", "liquor", "pharmacy", "gym"]
        if vertical and vertical not in valid_verticals:
            vertical = None

        location_id = None
        if request.GET.get("location_id"):
            try:
                location_id = int(request.GET.get("location_id"))
            except (ValueError, TypeError):
                pass

        # Get analytics data (wrapped in try/except to prevent 500s)
        try:
            analytics_data = get_hq_analytics_data(
                start_date=start_date,
                end_date=end_date,
                business_id=business_id,
                vertical=vertical,
                location_id=location_id,
            )
        except Exception:
            # On any error, return empty analytics data structure
            analytics_data = {
                "kpis": {
                    "total_revenue": 0,
                    "total_sales": 0,
                    "total_profit": 0,
                    "active_businesses": 0,
                },
                "series": [],
                "breakdowns": {},
            }

        # Get filter options (safe: handle missing models gracefully)
        try:
            all_businesses = Business.objects.filter(is_active=True).order_by("name")[:100]
        except Exception:
            all_businesses = []

        all_locations = []
        if business_id:
            try:
                all_locations = Location.objects.filter(business_id=business_id).order_by("name")[:100]
            except Exception:
                all_locations = []

        vertical_options = [
            ("phones", "Phones"),
            ("clothing", "Clothing"),
            ("liquor", "Liquor"),
            ("pharmacy", "Pharmacy"),
            ("gym", "Gym"),
        ]

        # Billing KPIs (safe: all wrapped in try/except)
        billing_kpis = {}
        try:
            active_subs = Subscription.objects.filter(status="active").count()
            trialing_subs = Subscription.objects.filter(status__in=["trial", "trialing"]).count()
            churn_risk = Subscription.objects.filter(status__in=["past_due", "grace", "suspended"]).count()
            canceled_subs = Subscription.objects.filter(status__in=["canceled", "cancelled", "expired"]).count()
            # MRR: sum of plan amounts for active subscriptions
            from django.db.models import Sum as _Sum
            mrr_result = Subscription.objects.filter(status="active").aggregate(
                mrr=Coalesce(_Sum("plan__amount"), Value(0, output_field=DecimalField()))
            )
            mrr = float(mrr_result["mrr"] or 0)
            # Open invoices
            open_invoices = Invoice.objects.filter(status__in=["issued", "sent", "overdue"]).count()
            outstanding_result = Invoice.objects.filter(status__in=["issued", "sent", "overdue"]).aggregate(
                total=Coalesce(_Sum("total"), Value(0, output_field=DecimalField()))
            )
            outstanding_amount = float(outstanding_result["total"] or 0)
            # Collections rate
            paid_result = Invoice.objects.filter(status="paid").aggregate(
                total=Coalesce(_Sum("total"), Value(0, output_field=DecimalField()))
            )
            paid_amount = float(paid_result["total"] or 0)
            total_invoiced = paid_amount + outstanding_amount
            collections_rate = round((paid_amount / total_invoiced * 100) if total_invoiced > 0 else 0, 1)

            billing_kpis = {
                "active_subscriptions": active_subs,
                "trialing_subscriptions": trialing_subs,
                "churn_risk": churn_risk,
                "canceled_subscriptions": canceled_subs,
                "mrr": mrr,
                "open_invoices": open_invoices,
                "outstanding_amount": outstanding_amount,
                "paid_amount": paid_amount,
                "collections_rate": collections_rate,
            }
        except Exception:
            billing_kpis = {
                "active_subscriptions": 0,
                "trialing_subscriptions": 0,
                "churn_risk": 0,
                "canceled_subscriptions": 0,
                "mrr": 0,
                "open_invoices": 0,
                "outstanding_amount": 0,
                "paid_amount": 0,
                "collections_rate": 0,
            }

        ctx = {
            "analytics_data": analytics_data,
            "billing_kpis": billing_kpis,
            "start_date": start_date,
            "end_date": end_date,
            "preset": preset,
            "all_businesses": all_businesses,
            "selected_business_id": business_id,
            "all_locations": all_locations,
            "selected_location_id": location_id,
            "vertical_options": vertical_options,
            "selected_vertical": vertical,
        }

        return render(request, "hq/analytics.html", ctx)
    except Exception:
        # Ultimate fallback: return minimal page with error message
        from django.contrib import messages

        messages.error(request, "An error occurred loading analytics. Please try again.")
        return redirect("hq:dashboard")


# -------------------------------------------------------------------
# Admin actions (Trials / Cancel / Refund / Plan change)
# NOTE: These accept GET or POST.
#   - GET: perform action, flash message, redirect back
#   - POST: perform action, return JSON for AJAX
# -------------------------------------------------------------------
@hq_admin_required
def sub_adjust_trial(request, pk: int):
    sub = get_object_or_404(Subscription, pk=pk)
    # Allow GET with ?days=... or ?trial_end=YYYY-MM-DD
    data = _json_body(request) if request.method == "POST" else request.GET

    if Invoice.objects.filter(business=sub.business, status__in=["PAID", "SETTLED", "paid"]).exists():
        if request.method == "GET":
            messages.error(request, "Cannot adjust: subscription is locked by payment activity.")
            return _back_to(request)
        return JsonResponse({"ok": False, "error": "locked_by_payment"}, status=409)

    # +/- days
    days = data.get("days")
    if days is not None:
        try:
            days = int(days)
        except Exception:
            days = None
    if isinstance(days, int) and days != 0:
        if hasattr(sub, "extend_trial"):
            sub.extend_trial(days, save=True)
        else:
            if not getattr(sub, "trial_end", None):
                if request.method == "GET":
                    messages.error(request, "No trial_end field on subscription.")
                    return _back_to(request)
                return JsonResponse({"ok": False, "error": "no_trial_field"}, status=409)
            sub.trial_end = (sub.trial_end or timezone.now()) + timedelta(days=days)
            sub.current_period_end = sub.trial_end
            sub.save(update_fields=["trial_end", "current_period_end"])
        if request.method == "GET":
            messages.success(request, f"Trial adjusted by {days} day(s).")
            return _back_to(request)
        return JsonResponse({"ok": True, "trial_end": sub.trial_end.isoformat()})

    # Set to specific date
    new_date = data.get("trial_end")
    if new_date:
        try:
            d = dt.strptime(new_date, "%Y-%m-%d").date()
            new_dt = timezone.make_aware(dt(d.year, d.month, d.day, 23, 59, 59))
            sub.trial_end = new_dt
            if _field(Subscription, "current_period_end"):
                sub.current_period_end = new_dt
                sub.save(update_fields=["trial_end", "current_period_end"])
            else:
                sub.save(update_fields=["trial_end"])
            if request.method == "GET":
                messages.success(request, f"Trial end set to {d.isoformat()}.")
                return _back_to(request)
            return JsonResponse({"ok": True, "trial_end": sub.trial_end.isoformat()})
        except Exception:
            if request.method == "GET":
                messages.error(request, "Invalid date format.")
                return _back_to(request)
            return JsonResponse({"ok": False, "error": "bad_date"}, status=400)

    if request.method == "GET":
        messages.info(request, "No trial change requested.")
        return _back_to(request)
    return JsonResponse({"ok": False, "error": "no_action"}, status=400)


@hq_admin_required
def sub_cancel(request, pk: int):
    sub = get_object_or_404(Subscription, pk=pk)
    try:
        if _field(Subscription, "cancel_at_period_end"):
            sub.cancel_at_period_end = True
            sub.save(update_fields=["cancel_at_period_end"])
        else:
            sub.status = "CANCELED"
            sub.save(update_fields=["status"])
        if request.method == "GET":
            messages.success(request, "Subscription marked to cancel at period end.")
            return _back_to(request)
        return JsonResponse({"ok": True})
    except Exception:
        if request.method == "GET":
            messages.error(request, "Could not cancel subscription.")
            return _back_to(request)
        return JsonResponse({"ok": False}, status=400)


@hq_admin_required
def invoice_refund(request, pk: int):
    inv = get_object_or_404(Invoice, pk=pk)
    try:
        if _field(Invoice, "related_to"):
            Invoice.objects.create(
                business=inv.business,
                total=-(inv.total or Decimal("0.00")),
                status="REFUND",
                related_to=inv,
                number=f"{getattr(inv, 'number', 'INV')}-R",
                notes=f"Refund for {getattr(inv, 'number', '')}",
                currency=getattr(inv, "currency", "MWK"),
                issue_date=timezone.localdate(),
            )
        else:
            Invoice.objects.create(
                business=inv.business,
                total=-(inv.total or Decimal("0.00")),
                status="REFUND",
                number=f"{getattr(inv, 'number', 'INV')}-CR",
                notes=f"Credit note for {getattr(inv, 'number', '')}",
                currency=getattr(inv, "currency", "MWK"),
                issue_date=timezone.localdate(),
            )
        if request.method == "GET":
            messages.success(request, "Refund/credit note issued.")
            return _back_to(request, "hq:invoices")
        return JsonResponse({"ok": True})
    except Exception:
        if request.method == "GET":
            messages.error(request, "Could not create refund/credit note.")
            return _back_to(request, "hq:invoices")
        return JsonResponse({"ok": False}, status=400)


@hq_admin_required
def invoice_create(request):
    """
    Create a new invoice for a business (manual generation from HQ).
    POST: business_id, amount, description, issue_date
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    from audit.utils import log_hq_action

    try:
        business_id = int(request.POST.get("business_id"))
        amount = Decimal(request.POST.get("amount", "0"))
        description = request.POST.get("description", "")
        issue_date_str = request.POST.get("issue_date", "")

        biz = get_object_or_404(Business, id=business_id)

        # Parse issue date
        from datetime import datetime as dt

        if issue_date_str:
            issue_date = dt.strptime(issue_date_str, "%Y-%m-%d").date()
        else:
            issue_date = timezone.localdate()

        # Get subscription/plan info
        plan_name = "Manual Invoice"
        try:
            sub = biz.subscription
            if sub and hasattr(sub, "plan") and sub.plan:
                plan_name = sub.plan.name
        except Exception:
            pass

        # Generate invoice number
        last_inv = Invoice.objects.order_by("-id").first()
        next_num = (last_inv.id + 1) if last_inv else 1
        number = f"INV-{next_num:06d}"

        # Create invoice
        invoice = Invoice.objects.create(
            business=biz,
            number=number,
            total=amount,
            status="OPEN",
            notes=description or f"Invoice for {plan_name}",
            currency=getattr(settings, "REPORTS_DEFAULT_CURRENCY", "MWK"),
            issue_date=issue_date,
            created_by=request.user if hasattr(Invoice, "created_by") else None,
        )

        # Log action
        log_hq_action(
            request,
            action="CREATE_INVOICE",
            entity_type="Invoice",
            entity_id=invoice.id,
            message=f"Created invoice {number} for {biz.name}: {amount}",
            business=biz,
        )

        return JsonResponse(
            {
                "ok": True,
                "invoice": {
                    "id": invoice.id,
                    "number": number,
                    "amount": str(amount),
                    "business": biz.name,
                    "issue_date": issue_date.isoformat(),
                },
            }
        )

    except (ValueError, TypeError) as e:
        return JsonResponse({"ok": False, "error": f"Invalid data: {str(e)}"}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


# --- Extend trial by +/- days OR set specific date
@hq_admin_required
def sub_extend(request, pk: int):
    sub = get_object_or_404(Subscription, pk=pk)
    data = _json_body(request) if request.method == "POST" else request.GET

    if Invoice.objects.filter(business=sub.business, status__in=["PAID", "SETTLED", "paid"]).exists():
        if request.method == "GET":
            messages.error(request, "Cannot extend: subscription is locked by payment activity.")
            return _back_to(request)
        return JsonResponse({"ok": False, "error": "locked_by_payment"}, status=409)

    if "trial_end" in data and data["trial_end"]:
        try:
            d = dt.strptime(data["trial_end"], "%Y-%m-%d").date()
            new_dt = timezone.make_aware(dt(d.year, d.month, d.day, 23, 59, 59))
            sub.trial_end = new_dt
            sub.status = getattr(sub, "Status", sub).TRIAL if hasattr(sub, "Status") else "trial"
            if _field(Subscription, "current_period_end"):
                sub.current_period_end = new_dt
            if _field(Subscription, "next_billing_date"):
                sub.next_billing_date = new_dt
            sub.save(update_fields=["trial_end", "status", "current_period_end", "next_billing_date", "updated_at"])
            if request.method == "GET":
                messages.success(request, f"Trial extended to {d.isoformat()}.")
                return _back_to(request)
            return JsonResponse({"ok": True, "trial_end": sub.trial_end.isoformat()})
        except Exception:
            if request.method == "GET":
                messages.error(request, "Invalid date format.")
                return _back_to(request)
            return JsonResponse({"ok": False, "error": "bad_date"}, status=400)

    days = data.get("days", None)
    try:
        days = int(days) if days is not None else None
    except Exception:
        days = None

    if isinstance(days, int) and days != 0:
        if hasattr(sub, "extend_trial"):
            sub.extend_trial(days, save=True)
        else:
            sub.trial_end = (sub.trial_end or timezone.now()) + timedelta(days=days)
            sub.current_period_end = (
                sub.trial_end
                if _field(Subscription, "current_period_end")
                else getattr(sub, "current_period_end", None)
            )
            sub.status = "trial"
            sub.save(update_fields=["trial_end", "current_period_end", "status"])
        if request.method == "GET":
            messages.success(request, f"Trial adjusted by {days} day(s).")
            return _back_to(request)
        return JsonResponse({"ok": True, "trial_end": sub.trial_end.isoformat()})

    if request.method == "GET":
        messages.info(request, "No change requested.")
        return _back_to(request)
    return JsonResponse({"ok": False}, status=400)


# --- Revoke trial now (moves to GRACE by default)
@hq_admin_required
def sub_revoke_trial(request, pk: int):
    sub = get_object_or_404(Subscription, pk=pk)
    try:
        if hasattr(sub, "end_trial_now"):
            sub.end_trial_now(to_grace=True, save=True)
        else:
            sub.trial_end = timezone.now()
            if hasattr(sub, "enter_grace"):
                sub.enter_grace(save=True)
            else:
                sub.status = "canceled"
                sub.save(update_fields=["trial_end", "status", "updated_at"])
        if request.method == "GET":
            messages.success(request, "Trial revoked.")
            return _back_to(request)
        return JsonResponse({"ok": True})
    except Exception:
        if request.method == "GET":
            messages.error(request, "Could not revoke trial.")
            return _back_to(request)
        return JsonResponse({"ok": False}, status=400)


# --- Activate immediately (start paid 30-day period)
@hq_admin_required
def sub_activate_now(request, pk: int):
    sub = get_object_or_404(Subscription, pk=pk)
    try:
        sub.activate_now(period_days=30)
        if request.method == "GET":
            messages.success(request, "Subscription activated.")
            return _back_to(request)
        return JsonResponse({"ok": True})
    except Exception:
        if request.method == "GET":
            messages.error(request, "Could not activate subscription.")
            return _back_to(request)
        return JsonResponse({"ok": False}, status=400)


# --- Set plan (Starter / Pro / Pro Max)
@hq_admin_required
def sub_set_plan(request, pk: int):
    """
    Body/Query: { "plan_code": "starter" | "pro" | "promax" }
    Superusers can change any; staff according to your hq_admin_required policy.
    """
    sub = get_object_or_404(Subscription, pk=pk)
    data = _json_body(request) if request.method == "POST" else request.GET
    code = (data.get("plan_code") or "").lower().strip()
    if code not in PLAN_CATALOG:
        if request.method == "GET":
            messages.error(request, "Unknown plan.")
            return _back_to(request)
        return JsonResponse({"ok": False, "error": "unknown_plan"}, status=400)

    catalog = PLAN_CATALOG[code]
    try:
        # a) If you have a Plan model, attach it
        if _field(Subscription, "plan") and Plan:
            # build kwargs only for existing fields
            kwargs = {}
            if _field(Plan, "code"):
                kwargs["code"] = catalog["code"]
            if _field(Plan, "name"):
                kwargs["name"] = catalog["name"]
            if _field(Plan, "amount"):
                kwargs["amount"] = catalog["amount"]
            if _field(Plan, "interval"):
                kwargs["interval"] = "month"

            plan_obj = (
                Plan.objects.filter(Q(code=kwargs.get("code", None)) | Q(name__iexact=catalog["name"]))
                .order_by("-id")
                .first()
            )
            if not plan_obj:
                plan_obj = Plan.objects.create(**kwargs)

            sub.plan = plan_obj
            if _field(Subscription, "plan_code"):
                sub.plan_code = catalog["code"]
            if _field(Subscription, "amount"):
                sub.amount = catalog["amount"]
            sub.save(
                update_fields=[fn for fn in ["plan", "plan_code", "amount", "updated_at"] if _field(Subscription, fn)]
            )
        else:
            # b) No Plan model â†’ store amount & optional plan_code on subscription
            update_fields = []
            if _field(Subscription, "amount"):
                sub.amount = catalog["amount"]
                update_fields.append("amount")
            if _field(Subscription, "plan_code"):
                sub.plan_code = catalog["code"]
                update_fields.append("plan_code")
            if _field(Subscription, "updated_at"):
                update_fields.append("updated_at")
            sub.save(update_fields=update_fields)

        if request.method == "GET":
            messages.success(request, f"Plan set to {catalog['name']}.")
            return _back_to(request)
        return JsonResponse({"ok": True, "plan": catalog["name"], "amount": str(catalog["amount"])})
    except Exception:
        if request.method == "GET":
            messages.error(request, "Could not change plan.")
            return _back_to(request)
        return JsonResponse({"ok": False}, status=400)
