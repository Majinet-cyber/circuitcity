# circuitcity/hq/views.py
from __future__ import annotations

import datetime
import json
from datetime import datetime as dt, timedelta
from decimal import Decimal
from collections import deque

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, Sum, Value, DecimalField, Q
from django.db.models.functions import TruncDate, TruncMonth, Coalesce, Cast
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template import loader, TemplateDoesNotExist
from django.template.loader import select_template
from django.urls import reverse
from django.utils import timezone

from hq.permissions import hq_admin_required
from tenants.models import Business, Membership
from billing.models import Subscription, Invoice  # BusinessSubscription alias
from inventory.models import InventoryItem

# Try to import Plan model if you have one
try:
    from billing.models import Plan  # type: ignore
except Exception:  # pragma: no cover
    Plan = None  # type: ignore


# -------------------------------------------------------------------
# Plan catalog (single source of truth for names, prices, limits)
# -------------------------------------------------------------------
PLAN_CATALOG = {
    "starter": {
        "code": "starter",
        "name": "Starter",
        "amount": Decimal("20000.00"),
        "max_agents": 0,          # cannot add agents
        "max_stores": 1,          # one store
    },
    "pro": {
        "code": "pro",
        "name": "Pro",
        "amount": Decimal("35000.00"),
        "max_agents": 5,          # up to 5 agents
        "max_stores": None,       # unlimited
    },
    "promax": {
        "code": "promax",
        "name": "Pro Max",
        "amount": Decimal("50000.00"),
        "max_agents": None,       # unlimited
        "max_stores": None,       # unlimited
    },
}


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
    now = timezone.now()
    seven = now - timedelta(days=7)
    thirty = now - timedelta(days=30)

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
        if _field(Membership, "created_at") else 0
    )

    # Use whichever InventoryItem manager exists
    inv_mgr = getattr(InventoryItem, "all_objects", InventoryItem.objects)
    ctx["stock_in_7d"] = inv_mgr.filter(received_at__gte=seven).count()
    ctx["stock_out_7d"] = inv_mgr.filter(sold_at__isnull=False, sold_at__gte=seven).count()

    ctx["any_trials"] = Subscription.objects.filter(status__in=["TRIAL", "trial"]).exists()

    return _render_safe(request, "hq/dashboard.html", ctx, _dashboard_inline)


# -------------------------------------------------------------------
# Businesses
# -------------------------------------------------------------------
@hq_admin_required
def businesses(request):
    start, end, rng = _date_range_from_request(request)
    q = (request.GET.get("q") or "").strip()

    rows = Business.objects.all()
    rows = rows.order_by("-created_at") if _field(Business, "created_at") else rows.order_by("name")

    if q:
        rows = rows.filter(Q(name__icontains=q) | Q(slug__icontains=q))

    page_obj = _paginate(request, rows, per_page=25)
    ctx = {"rows": rows, "page_obj": page_obj, "q": q, "range": rng, "start": start, "end": end}
    return _render_safe(request, "hq/businesses.html", ctx, lambda c: "<h1 style='font-family:system-ui'>Businesses</h1>")


@hq_admin_required
def business_detail(request, pk: int):
    biz = get_object_or_404(Business, pk=pk)
    start, end, rng = _date_range_from_request(request)

    inv = Invoice.objects.filter(business=biz)
    date_field = "issue_date" if _field(Invoice, "issue_date") else ("created_at" if _field(Invoice, "created_at") else None)
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

    trunc_base = "issue_date" if _field(Invoice, "issue_date") else ("created_at" if _field(Invoice, "created_at") else None)
    if trunc_base:
        paid_series_qs = (
            inv.filter(status__in=["PAID", "SETTLED", "paid"])
            .annotate(m=TruncMonth(trunc_base))
            .values("m")
            .order_by("m")
            .annotate(amount=Coalesce(Sum("total"), Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))))
        )
    else:
        paid_series_qs = []

    agents_qs = Membership.objects.filter(role="AGENT", business=biz).select_related("user")
    limits = _limits_for_business(biz)

    ctx = {
        "biz": biz,
        "range": rng, "start": start, "end": end,
        "paid_total": paid_total, "open_total": open_total,
        "active_subs": active_subs, "mrr": mrr,
        "agents_qs": agents_qs,
        "series_paid": [{"label": (r["m"].strftime("%Y-%m") if r["m"] else ""), "amount": float(r["amount"] or 0)} for r in paid_series_qs],
        "limits": limits,
    }
    return _render_safe(request, "hq/business_detail.html", ctx, lambda c: f"<h1 style='font-family:system-ui'>{_esc(biz.name)}</h1>")


# -------------------------------------------------------------------
# Subscriptions
# -------------------------------------------------------------------
@hq_admin_required
def subscriptions(request):
    start, end, rng = _date_range_from_request(request)
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Subscription.objects.select_related("business", "plan")

    if q:
        qs = qs.filter(
            Q(business__name__icontains=q) |
            Q(business__slug__icontains=q) |
            Q(plan__name__icontains=q) |
            Q(plan__code__icontains=q)
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
        "q": q, "status": status,
        "range": rng, "start": start, "end": end,
        "plan_catalog": PLAN_CATALOG,
    }

    tpl = select_template(["hq/subscriptions.html", "billing/hq_subscriptions.html"])
    # Render the selected template directly to avoid name confusion
    return HttpResponse(tpl.render(ctx, request))


# -------------------------------------------------------------------
# Invoices
# -------------------------------------------------------------------
@hq_admin_required
def invoices(request):
    qs = Invoice.objects.select_related('business', 'created_by')

    status = (request.GET.get('status') or '').strip()
    if status:
        qs = qs.filter(status__iexact=status)

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(business__name__icontains=q))

    order_field = "-created_at" if _field(Invoice, "created_at") else "-id"
    qs = qs.order_by(order_field)

    page_obj = Paginator(qs, 25).get_page(request.GET.get('page'))
    return render(request, 'hq/invoices.html', {'page_obj': page_obj, 'invoices': page_obj})


# -------------------------------------------------------------------
# Agents
# -------------------------------------------------------------------
@hq_admin_required
def agents(request):
    q = (request.GET.get("q") or "").strip()
    rows = Membership.objects.filter(role="AGENT").select_related("business", "user")
    if q:
        rows = rows.filter(Q(user__username__icontains=q) | Q(business__name__icontains=q))
    rows = rows.order_by("-created_at") if _field(Membership, "created_at") else rows.order_by("-id")

    # Limits per business to enable UI nudges (e.g., â€œUpgrade to add more agentsâ€)
    biz_limits = {}
    for b_id in rows.values_list("business_id", flat=True).distinct():
        try:
            biz = Business.objects.get(pk=b_id)
            lim = _limits_for_business(biz)
            if lim:
                agent_count = Membership.objects.filter(role="AGENT", business_id=b_id).count()
                lim = {**lim, "agent_count": agent_count}
            biz_limits[b_id] = lim
        except Exception:
            biz_limits[b_id] = None

    ctx = {"rows": rows, "page_obj": _paginate(request, rows, per_page=30), "q": q, "biz_limits": biz_limits}
    return _render_safe(request, "hq/agents.html", ctx, lambda c: "<h1 style='font-family:system-ui'>Agents</h1>")


# -------------------------------------------------------------------
# Stock trends (SQLite-safe with filters)
# -------------------------------------------------------------------
@hq_admin_required
def stock_trends(request):
    """
    HQ Stock Trends (SQLite-safe)
    """
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
    sold_qs = base.filter(sold_at__isnull=False,
                          sold_at__date__gte=start,
                          sold_at__date__lte=end)
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
        window.append(x); s += x
        if len(window) > 7:
            s -= window.popleft()
        ma7.append(round(s / len(window), 2))

    # cumulative
    cum_in, cum_out = [], []
    acc_i = acc_o = 0
    for i, o in zip(series_in, series_out):
        acc_i += i; acc_o += o
        cum_in.append(acc_i); cum_out.append(acc_o)

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
        "start": start, "end": end,
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
    start, end, rng = _date_range_from_request(request)

    inv = Invoice.objects.all()
    date_field = "issue_date" if _field(Invoice, "issue_date") else ("created_at" if _field(Invoice, "created_at") else None)
    if date_field and start and end:
        inv = _range_filter(inv, Invoice, date_field, start, end)

    zero = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))
    income = inv.filter(status__in=["PAID", "SETTLED", "paid"]).aggregate(v=Coalesce(Sum("total"), zero))["v"]
    expense = Decimal("0.00")
    balance = (income or Decimal("0.00")) - (expense or Decimal("0.00"))

    ctx = {"income": income, "expense": expense, "balance": balance,
           "range": rng, "start": start, "end": end,
           "tx_page": None}
    return _render_safe(request, "hq/wallet.html", ctx, lambda c: "<h1 style='font-family:system-ui'>Wallet</h1>")


# -------------------------------------------------------------------
# APIs (dashboard/widgets)
# -------------------------------------------------------------------
@login_required
def api_wallet_income(request):
    start_raw = request.GET.get('start') or ''
    end_raw = request.GET.get('end') or ''

    today = timezone.now().date()
    try:
        start_d = datetime.date.fromisoformat(start_raw) if start_raw else (today - datetime.timedelta(days=29))
        end_d = datetime.date.fromisoformat(end_raw) if end_raw else today
    except Exception:
        return JsonResponse([], safe=False)

    qs = Invoice.objects.filter(status__in=["PAID", "SETTLED", "paid"])
    df_name = "paid_at" if _field(Invoice, "paid_at") else ("issue_date" if _field(Invoice, "issue_date") else ("created_at" if _field(Invoice, "created_at") else None))
    if not df_name:
        return JsonResponse([], safe=False)

    qs = _range_filter(qs, Invoice, df_name, start_d, end_d)
    amount_field = "total" if _field(Invoice, "total") else ("amount" if _field(Invoice, "amount") else None)
    if not amount_field:
        return JsonResponse([], safe=False)

    f = _field(Invoice, df_name)
    if isinstance(f, models.DateTimeField):
        agg = (qs.annotate(day=TruncDate(df_name))
                .values("day")
                .order_by("day")
                .annotate(amount=Sum(amount_field)))
        data = [{'date': (row['day'] or start_d).isoformat(), 'amount': float(row['amount'] or 0)} for row in agg]
    else:
        agg = (qs.values(df_name)
                .order_by(df_name)
                .annotate(amount=Sum(amount_field)))
        data = [{'date': (row[df_name] or start_d).isoformat(), 'amount': float(row['amount'] or 0)} for row in agg]

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
        out.append({
            "label": f'Businesses matching â€œ{term}â€',
            "type": "Businesses",
            "url": f"{reverse('hq:businesses')}?q={term}"
        })
    except Exception:
        pass
    try:
        out.append({
            "label": f'Invoices for â€œ{term}â€',
            "type": "Invoices",
            "url": f"{reverse('hq:invoices')}?q={term}"
        })
    except Exception:
        pass
    try:
        out.append({
            "label": f'Subscriptions with â€œ{term}â€',
            "type": "Subscriptions",
            "url": f"{reverse('hq:subscriptions')}?q={term}"
        })
    except Exception:
        pass
    try:
        out.append({
            "label": f'Agents named â€œ{term}â€',
            "type": "Agents",
            "url": f"{reverse('hq:agents')}?q={term}"
        })
    except Exception:
        pass
    return JsonResponse(out, safe=False)


@hq_admin_required
def api_notifications(request):
    return JsonResponse([], safe=False)


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
            sub.current_period_end = sub.trial_end if _field(Subscription, "current_period_end") else getattr(sub, "current_period_end", None)
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
                Plan.objects.filter(
                    Q(code=kwargs.get("code", None)) |
                    Q(name__iexact=catalog["name"])
                ).order_by("-id").first()
            )
            if not plan_obj:
                plan_obj = Plan.objects.create(**kwargs)

            sub.plan = plan_obj
            if _field(Subscription, "plan_code"):
                sub.plan_code = catalog["code"]
            if _field(Subscription, "amount"):
                sub.amount = catalog["amount"]
            sub.save(update_fields=[fn for fn in ["plan", "plan_code", "amount", "updated_at"] if _field(Subscription, fn)])
        else:
            # b) No Plan model â†’ store amount & optional plan_code on subscription
            update_fields = []
            if _field(Subscription, "amount"):
                sub.amount = catalog["amount"]; update_fields.append("amount")
            if _field(Subscription, "plan_code"):
                sub.plan_code = catalog["code"]; update_fields.append("plan_code")
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






