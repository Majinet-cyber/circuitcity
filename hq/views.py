# circuitcity/hq/views.py
from __future__ import annotations

import datetime
import json
from datetime import datetime as dt, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, Sum, Value, DecimalField, Q
from django.db.models.functions import TruncDate, TruncMonth, Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.template import loader, TemplateDoesNotExist
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from hq.permissions import hq_admin_required
from tenants.models import Business, Membership
from billing.models import Subscription, Invoice
from inventory.models import InventoryItem


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _esc(s) -> str:
    s = "" if s is None else str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_safe(request, template_name: str, ctx: dict, inline_html_builder=None):
    """
    Try to render a Django template. If it doesn't exist, return a minimal
    inline HTML fallback so the page never 500s during early setup.
    """
    try:
        loader.get_template(template_name)
        return render(request, template_name, ctx)
    except TemplateDoesNotExist:
        if inline_html_builder:
            return HttpResponse(inline_html_builder(ctx))
        return HttpResponse("<h1 style='font-family:system-ui'>Page</h1>")


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
  <title>HQ · Dashboard</title>
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
  <div class="title">HQ · Dashboard</div>
  <div class="muted">Template <code>hq/dashboard.html</code> not found; showing a safe inline version.</div>
  <div class="notice">Create <code>templates/hq/dashboard.html</code> later to fully brand this page.</div>
  <div class="grid">{card_html}</div>
</body>
</html>
""".strip()


def _date_range_from_request(request):
    """Returns (start_date, end_date, range_str)."""
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
    # Always *order* before paginating to avoid UnorderedObjectListWarning.
    if not qs.query.order_by:
        qs = qs.order_by("-id")
    p = Paginator(qs, per_page)
    return p.get_page(request.GET.get("page") or 1)


def _field(model, name: str):
    """Return model field object by name, or None."""
    try:
        return model._meta.get_field(name)
    except Exception:
        return None


def _range_filter(qs, model, field_name: str, start, end):
    """
    Inclusive date range filter that supports both DateField and DateTimeField.
    """
    f = _field(model, field_name)
    if not f or start is None or end is None:
        return qs
    lookup = f"{field_name}__date__range" if isinstance(f, models.DateTimeField) else f"{field_name}__range"
    return qs.filter(**{lookup: (start, end)})


# -------------------------------------------------------------------
# Dashboard
# -------------------------------------------------------------------
@hq_admin_required
def dashboard(request):
    now = timezone.now()
    seven = now - timedelta(days=7)
    thirty = now - timedelta(days=30)

    ctx = {}

    # Businesses
    ctx["total_biz"] = Business.objects.count()
    ctx["new_biz_7d"] = Business.objects.filter(created_at__gte=seven).count() if _field(Business, "created_at") else 0

    # Subscriptions / MRR
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

    # Invoices
    open_inv = Invoice.objects.filter(status__in=["OPEN", "PAST_DUE", "UNPAID", "DUE", "open", "past_due"])
    ctx["open_invoices"] = open_inv.count()
    ctx["open_total"] = open_inv.aggregate(
        v=Coalesce(Sum("total"), Value(0, output_field=DecimalField(max_digits=18, decimal_places=2)))
    )["v"]

    # Agents
    ctx["agents_total"] = Membership.objects.filter(role="AGENT").count()
    ctx["agents_new_30d"] = (
        Membership.objects.filter(role="AGENT", created_at__gte=thirty).count()
        if _field(Membership, "created_at") else 0
    )

    # Inventory
    ctx["stock_in_7d"] = InventoryItem.objects.filter(received_at__gte=seven).count()
    ctx["stock_out_7d"] = InventoryItem.objects.filter(sold_at__isnull=False, sold_at__gte=seven).count()

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
    # pick a date-ish field available on Invoice for filtering (prefer issue_date > created_at)
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

    # simple monthly paid trajectory
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

    ctx = {
        "biz": biz,
        "range": rng, "start": start, "end": end,
        "paid_total": paid_total, "open_total": open_total,
        "active_subs": active_subs, "mrr": mrr,
        "agents_qs": agents_qs,
        "series_paid": [{"label": (r["m"].strftime("%Y-%m") if r["m"] else ""), "amount": float(r["amount"] or 0)} for r in paid_series_qs],
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

    rows = Subscription.objects.select_related("business", "plan")
    if q:
        rows = rows.filter(Q(business__name__icontains=q) | Q(customer_name__icontains=q) | Q(plan__name__icontains=q))
    if status:
        rows = rows.filter(status__iexact=status)

    if start and end and _field(Subscription, "created_at"):
        rows = _range_filter(rows, Subscription, "created_at", start, end)

    # Safe ordering before paginate
    order_field = "-created_at" if _field(Subscription, "created_at") else "-id"
    rows = rows.order_by(order_field)

    ctx = {
        "rows": rows,
        "page_obj": _paginate(request, rows, per_page=25),
        "q": q, "status": status, "range": rng, "start": start, "end": end,
    }
    return _render_safe(request, "hq/subscriptions.html", ctx, lambda c: "<h1 style='font-family:system-ui'>Subscriptions</h1>")


# -------------------------------------------------------------------
# Invoices
# -------------------------------------------------------------------
@hq_admin_required
def invoices(request):
    """
    Invoices list with robust relations.
    NOTE: we do NOT select_related('subscription') because it doesn't exist in your model.
    """
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
    ctx = {"rows": rows, "page_obj": _paginate(request, rows, per_page=30), "q": q}
    return _render_safe(request, "hq/agents.html", ctx, lambda c: "<h1 style='font-family:system-ui'>Agents</h1>")


# -------------------------------------------------------------------
# Stock trends
# -------------------------------------------------------------------
@hq_admin_required
def stock_trends(request):
    """
    Use _range_filter so DateField vs DateTimeField both work.
    """
    end = timezone.now().date()
    start = end - timedelta(days=13)

    # Incoming
    rec_field = "received_at" if _field(InventoryItem, "received_at") else None
    q_in = InventoryItem.objects.all()
    if rec_field:
        q_in = _range_filter(q_in, InventoryItem, rec_field, start, end)
        # TruncDate works for both DateField & DateTimeField
        daily_in = (
            q_in.annotate(d=TruncDate(rec_field))
               .values("d")
               .order_by("d")
               .annotate(count=Count("id"))
        )
    else:
        daily_in = []

    # Outgoing
    out_field = "sold_at" if _field(InventoryItem, "sold_at") else None
    q_out = InventoryItem.objects.filter(sold_at__isnull=False) if out_field else InventoryItem.objects.none()
    if out_field:
        q_out = _range_filter(q_out, InventoryItem, out_field, start, end)
        daily_out = (
            q_out.annotate(d=TruncDate(out_field))
                 .values("d")
                 .order_by("d")
                 .annotate(count=Count("id"))
        )
    else:
        daily_out = []

    ctx = {"daily_in": list(daily_in), "daily_out": list(daily_out), "start": start, "end": end}
    return _render_safe(request, "hq/stock_trends.html", ctx, lambda c: "<h1 style='font-family:system-ui'>Stock Trends</h1>")


# -------------------------------------------------------------------
# Wallet
# -------------------------------------------------------------------
@hq_admin_required
def wallet_home(request):
    """
    Minimal wallet: uses PAID invoices as income proxy and DUE/OPEN totals as obligations.
    Replace with a real Transaction model later without breaking the UI.
    """
    start, end, rng = _date_range_from_request(request)

    inv = Invoice.objects.all()
    date_field = "issue_date" if _field(Invoice, "issue_date") else ("created_at" if _field(Invoice, "created_at") else None)
    if date_field and start and end:
        inv = _range_filter(inv, Invoice, date_field, start, end)

    zero = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))
    income = inv.filter(status__in=["PAID", "SETTLED", "paid"]).aggregate(v=Coalesce(Sum("total"), zero))["v"]
    expense = Decimal("0.00")  # placeholder for a future Expense model
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
    """
    Returns [{date: 'YYYY-MM-DD', amount: <number>}]
    Filters by inclusive date range on a DateField/DateTimeField without using __date on DateField.
    """
    start_raw = request.GET.get('start') or ''
    end_raw = request.GET.get('end') or ''

    today = timezone.now().date()
    try:
        start_d = datetime.date.fromisoformat(start_raw) if start_raw else (today - datetime.timedelta(days=29))
        end_d = datetime.date.fromisoformat(end_raw) if end_raw else today
    except Exception:
        return JsonResponse([], safe=False)

    qs = Invoice.objects.filter(status__in=["PAID", "SETTLED", "paid"])

    # choose the best available date field
    df_name = "paid_at" if _field(Invoice, "paid_at") else ("issue_date" if _field(Invoice, "issue_date") else ("created_at" if _field(Invoice, "created_at") else None))
    if not df_name:
        return JsonResponse([], safe=False)

    # apply range (handles Date vs DateTime)
    qs = _range_filter(qs, Invoice, df_name, start_d, end_d)

    # group by day and sum totals (prefer 'total', fall back to 'amount')
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
    """
    Returns [{date:'YYYY-MM', mrr: float}] based on subscription plan amounts per month.
    """
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
    """
    Very lightweight suggestions for the search box.
    Returns a list of {label, type, url}.
    """
    term = (request.GET.get("q") or "").strip()
    out = []
    if not term:
        return JsonResponse(out, safe=False)

    try:
        out.append({
            "label": f'Businesses matching “{term}”',
            "type": "Businesses",
            "url": f"{reverse('hq:businesses')}?q={term}"
        })
    except Exception:
        pass
    try:
        out.append({
            "label": f'Invoices for “{term}”',
            "type": "Invoices",
            "url": f"{reverse('hq:invoices')}?q={term}"
        })
    except Exception:
        pass
    try:
        out.append({
            "label": f'Subscriptions with “{term}”',
            "type": "Subscriptions",
            "url": f"{reverse('hq:subscriptions')}?q={term}"
        })
    except Exception:
        pass
    try:
        out.append({
            "label": f'Agents named “{term}”',
            "type": "Agents",
            "url": f"{reverse('hq:agents')}?q={term}"
        })
    except Exception:
        pass
    return JsonResponse(out, safe=False)


@hq_admin_required
def api_notifications(request):
    """
    Polling endpoint. The UI seeds demo items on first click; returning []
    here keeps things simple until you wire real events.
    """
    return JsonResponse([], safe=False)


# -------------------------------------------------------------------
# Admin actions (Trials / Cancel / Refund)
# -------------------------------------------------------------------
def _json_body(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


@hq_admin_required
@require_POST
def sub_adjust_trial(request, pk: int):
    """
    Adjust a subscription's trial end date. If any PAID invoice exists for
    this subscription, we refuse (payment locks the period).
    """
    sub = get_object_or_404(Subscription, pk=pk)
    data = _json_body(request)
    new_date = data.get("trial_end")

    if Invoice.objects.filter(subscription=sub, status__in=["PAID", "SETTLED", "paid"]).exists():
        return JsonResponse({"ok": False, "error": "locked_by_payment"}, status=409)

    if not _field(Subscription, "trial_end"):
        return JsonResponse({"ok": False, "error": "no_trial_field"}, status=409)

    try:
        sub.trial_end = dt.strptime(new_date, "%Y-%m-%d").date()
        sub.save(update_fields=["trial_end"])
        return JsonResponse({"ok": True})
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_date"}, status=400)


@hq_admin_required
@require_POST
def sub_cancel(request, pk: int):
    """
    Cancel a subscription (graceful default). If your model supports
    cancel-at-period-end, we set it; otherwise we set status to CANCELED.
    """
    sub = get_object_or_404(Subscription, pk=pk)
    try:
        if _field(Subscription, "cancel_at_period_end"):
            sub.cancel_at_period_end = True
            sub.status = getattr(sub, "status", "CANCELED")
            sub.save(update_fields=["cancel_at_period_end", "status"])
        else:
            sub.status = "CANCELED"
            sub.save(update_fields=["status"])
        return JsonResponse({"ok": True})
    except Exception:
        return JsonResponse({"ok": False}, status=400)


@hq_admin_required
@require_POST
def invoice_refund(request, pk: int):
    """
    Simple refund:
    - If your Invoice model supports a related credit (e.g., 'related_to'),
      create a negative invoice as a credit note.
    - Else, if there's a boolean 'refunded', mark it.
    """
    inv = get_object_or_404(Invoice, pk=pk)
    try:
        if _field(Invoice, "related_to"):
            Invoice.objects.create(
                business=inv.business,
                subscription=getattr(inv, "subscription", None),
                total=-(inv.total or Decimal("0.00")),
                status="REFUND",
                related_to=inv,
                number=f"{getattr(inv, 'number', 'INV')}-R",
            )
        elif hasattr(inv, "refunded"):
            inv.refunded = True
            inv.save(update_fields=["refunded"])
        return JsonResponse({"ok": True})
    except Exception:
        return JsonResponse({"ok": False}, status=400)
