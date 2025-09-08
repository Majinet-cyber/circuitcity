# dashboard/views.py
from datetime import datetime, timedelta, time, date

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model
from django.db.models import (
    Sum, F, DecimalField, ExpressionWrapper, Count, Case, When
)
from django.db.models.functions import TruncMonth
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache

from importlib import import_module  # <-- added

from inventory.models import InventoryItem
from sales.models import Sale
from reports.kpis import compute_sales_kpis

# ---- Optional wallet model (graceful if missing) ----
try:
    # WalletTxn lives in inventory.models in your codebase
    from inventory.models import WalletTxn
except Exception:
    try:
        from wallets.models import WalletTxn  # fallback path if you moved it
    except Exception:
        WalletTxn = None


# ---------------------------
# Helpers
# ---------------------------
def _is_staff(user) -> bool:
    return user.is_authenticated and user.is_staff


def _start_of_day(d: date, tz):
    """Return tz-aware start of day for a date."""
    return datetime.combine(d, time.min, tzinfo=tz)


def _first_of_next_month(d: date):
    """Return a date for the first day of the next month (no calendar import)."""
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def _initials(user):
    """Initials from full name or username."""
    full = (getattr(user, "get_full_name", lambda: "")() or user.get_username()).strip()
    parts = full.split()
    if not parts:
        uname = user.get_username() or "User"
        return (uname[:2]).upper()
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()


def _reverse_agent_detail(user_id: int) -> str | None:
    """
    Try namespaced URL first, then legacy alias (for older templates).
    Returns None if neither exists.
    """
    try:
        return reverse("dashboard:admin_agent_detail", args=[user_id])
    except NoReverseMatch:
        try:
            return reverse("admin_agent_detail", args=[user_id])
        except NoReverseMatch:
            return None


def _wallet_summary_for(user):
    """
    Compact wallet summary for templates. Returns None if WalletTxn model
    isn't available so existing pages render unchanged.

    Shape:
    {
      "balance": <float>,
      "month": {
        "commission": <float>,
        "advance": <float>,
        "adjustment": <float>,
        "total": <float>,
      },
      "month_label": "Aug 2025",
    }
    """
    if WalletTxn is None:
        return None

    today = timezone.localdate()
    month_start = today.replace(day=1)

    qs = WalletTxn.objects.filter(user=user)

    # If your WalletTxn has kind='DEBIT'/'CREDIT', convert to signed;
    # otherwise we assume 'amount' is already signed.
    fields = {getattr(f, "name", None) for f in WalletTxn._meta.get_fields()}
    signed_expr = F("amount")
    if "kind" in fields:
        signed_expr = Case(
            When(kind="DEBIT", then=-F("amount")),
            default=F("amount"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )

    # Lifetime balance
    balance = qs.aggregate(v=Sum(signed_expr))["v"] or 0

    # This-month aggregates
    month_qs = qs.filter(created_at__date__gte=month_start, created_at__date__lte=today)

    def _sum_reason(code: str):
        q = month_qs
        if "reason" in fields:
            q = q.filter(reason=code)
        return q.aggregate(v=Sum(signed_expr))["v"] or 0

    month_commission = _sum_reason("COMMISSION")
    month_advance = _sum_reason("ADVANCE")
    month_adjustment = _sum_reason("ADJUSTMENT")
    month_total = month_qs.aggregate(v=Sum(signed_expr))["v"] or 0

    return {
        "balance": balance,
        "month": {
            "commission": month_commission,
            "advance": month_advance,
            "adjustment": month_adjustment,
            "total": month_total,
        },
        "month_label": month_start.strftime("%b %Y"),
    }


# ---------------------------
# Dashboards
# ---------------------------
@login_required
@user_passes_test(_is_staff)
def admin_dashboard(request):
    """
    Staff/admin dashboard:
      - KPI tiles (Today/MTD/All-time)
      - In stock / Sold (MTD) / Monthly profit
      - Global stock battery
      - Active agents grid (clickable, initials avatar; uses photo_url if present)
    """
    tz = timezone.get_current_timezone()
    now = timezone.localtime()
    today = now.date()

    # Month window (tz-aware bounds)
    month_start = _start_of_day(today.replace(day=1), tz)
    month_end = _start_of_day(_first_of_next_month(today), tz)

    # KPIs (safe fallback)
    sales_qs = Sale.objects.select_related("item", "agent").all()
    kpis = compute_sales_kpis(sales_qs, dt_field="sold_at", amount_field="price") or {}
    kpis["scope"] = "All agents"

    # In stock (global)
    in_stock_total = InventoryItem.objects.filter(status="IN_STOCK").count()

    # Sold (MTD)
    month_sales_qs = sales_qs.filter(sold_at__gte=month_start, sold_at__lt=month_end)
    sold_mtd_count = month_sales_qs.count()

    # Monthly profit = sum(price - order_price) for MTD
    profit_expr = ExpressionWrapper(
        F("price") - F("item__order_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    monthly_profit = month_sales_qs.aggregate(p=Sum(profit_expr))["p"] or 0

    # Global stock battery
    battery_max = 100
    battery_count = in_stock_total
    battery_pct = int(round(min(100, (battery_count / battery_max) * 100))) if battery_max else 0
    if battery_pct < 20:
        battery_label, battery_color = "Critical", "red"
    elif battery_pct < 60:
        battery_label, battery_color = "Low", "yellow"
    else:
        battery_label, battery_color = "Stable", "green"

    # Agents (clickable cards)
    User = get_user_model()
    agents_qs = User.objects.filter(groups__name="Agent").distinct()
    if not agents_qs.exists():
        agents_qs = User.objects.filter(is_staff=False)

    agent_cards = []
    for a in agents_qs:
        a_mtd_qs = month_sales_qs.filter(agent=a)
        a_mtd_amount = a_mtd_qs.aggregate(t=Sum("price"))["t"] or 0
        a_mtd_count = a_mtd_qs.count()
        photo_url = getattr(getattr(a, "agent_profile", None), "photo_url", None)  # optional
        detail_url = _reverse_agent_detail(a.id)
        agent_cards.append({
            "id": a.id,
            "name": a.get_username(),
            "initials": _initials(a),
            "photo_url": photo_url,
            "mtd_amount": a_mtd_amount,
            "mtd_count": a_mtd_count,
            "url": detail_url,
        })

    ctx = {
        "kpis": kpis,
        "in_stock_total": in_stock_total,
        "sold_mtd_count": sold_mtd_count,
        "monthly_profit": monthly_profit,
        "battery": {
            "count": battery_count, "max": battery_max, "pct": battery_pct,
            "label": battery_label, "color": battery_color
        },
        "agents": agent_cards,
        "staff_view": True,
    }
    return render(request, "dashboard.html", ctx)


@login_required
def agent_dashboard(request):
    """
    Agent dashboard: per-agent KPIs + personal stock battery.
    """
    # KPIs for this agent
    my_sales_qs = Sale.objects.select_related("item").filter(agent=request.user)
    kpis = compute_sales_kpis(my_sales_qs, dt_field="sold_at", amount_field="price") or {}
    kpis["scope"] = "My sales"

    # Agent battery (max 20 like before)
    my_in_stock = InventoryItem.objects.filter(
        assigned_agent=request.user, status="IN_STOCK"
    ).count()
    battery_max = 20
    pct = int(round(min(100, (my_in_stock / battery_max) * 100))) if battery_max else 0
    if my_in_stock < 10:
        label, color = "Critical", "red"
    elif my_in_stock < 12:
        label, color = "Low", "yellow"
    else:
        label, color = "Stable", "green"

    # NEW: wallet summary (optional tile in template)
    wallet = _wallet_summary_for(request.user)

    ctx = {
        "kpis": kpis,
        "agent_battery": {"count": my_in_stock, "max": battery_max, "pct": pct, "label": label, "color": color},
        "wallet": wallet,         # <- added, harmless if None
        "staff_view": False,
    }
    return render(request, "dashboard.html", ctx)


@login_required
@user_passes_test(_is_staff)
def agent_detail(request, pk: int):
    """
    Staff-only page showing KPIs and stock battery for a specific agent (clickable card).
    Reuses the same dashboard template for visual consistency.
    """
    User = get_user_model()
    agent = get_object_or_404(User, pk=pk)

    # KPIs for this agent (from staff context)
    sales_qs = Sale.objects.select_related("item").filter(agent=agent)
    kpis = compute_sales_kpis(sales_qs, dt_field="sold_at", amount_field="price") or {}
    kpis["scope"] = f"{agent.get_username()}'s sales"

    # Agent battery (same rules as agent_dashboard)
    in_stock = InventoryItem.objects.filter(assigned_agent=agent, status="IN_STOCK").count()
    battery_max = 20
    pct = int(round(min(100, (in_stock / battery_max) * 100))) if battery_max else 0
    if in_stock < 10:
        label, color = "Critical", "red"
    elif in_stock < 12:
        label, color = "Low", "yellow"
    else:
        label, color = "Stable", "green"

    # Optional avatar support if you have profile relation
    photo_url = getattr(getattr(agent, "agent_profile", None), "photo_url", None)

    # NEW: wallet summary for this agent
    wallet = _wallet_summary_for(agent)

    ctx = {
        "kpis": kpis,
        "agent_battery": {"count": in_stock, "max": battery_max, "pct": pct, "label": label, "color": color},
        "wallet": wallet,  # <- added
        "staff_view": False,  # show the “My stock battery” style component
        "view_agent": {
            "id": agent.id,
            "name": agent.get_username(),
            "initials": _initials(agent),
            "photo_url": photo_url,
        },
    }
    return render(request, "dashboard.html", ctx)


# ---------------------------
# Chart data endpoints
# ---------------------------
@login_required
def profit_data(request):
    """
    Returns bar-chart data.

    Params:
      - month=YYYY-MM  (optional; if omitted, uses current month)
      - group_by=model (optional; if present, group profits by product/model
                        for that selected month; otherwise a 12-month trend
                        ending at the selected month)

    Profit = Sale.price - InventoryItem.order_price
    """
    month_str = request.GET.get("month")
    group_by = request.GET.get("group_by")  # 'model' or None

    # Pick the anchor month (current if not provided)
    today = timezone.localdate()
    if month_str:
        anchor = datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
    else:
        anchor = today.replace(day=1)

    # Permissions: staff can see all; agents only their own
    base = Sale.objects.select_related("item__product")
    if not request.user.is_staff:
        base = base.filter(agent=request.user)

    profit_expr = ExpressionWrapper(
        F("price") - F("item__order_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    if group_by == "model":
        # Window = exactly the selected month
        start = anchor
        end = _first_of_next_month(anchor)
        qs = (base.filter(sold_at__date__gte=start, sold_at__date__lt=end)
                  .values("item__product__brand", "item__product__model")
                  .annotate(v=Sum(profit_expr))
                  .order_by("-v"))[:20]
        labels = [f"{r['item__product__brand']} {r['item__product__model']}".strip() for r in qs]
        data = [float(r["v"] or 0) for r in qs]
    else:
        # 12-month trend ending at anchor month
        end = _first_of_next_month(anchor)
        start = (anchor.replace(day=1) - timedelta(days=365))  # ~12 months
        qs = (base.filter(sold_at__date__gte=start, sold_at__date__lt=end)
                  .annotate(m=TruncMonth("sold_at"))
                  .values("m")
                  .annotate(v=Sum(profit_expr))
                  .order_by("m"))

        # Map onto an exact 12-slot sequence (oldest→newest)
        def add_month(y, m, delta):
            # returns (y, m) advanced by delta months
            total = y * 12 + (m - 1) + delta
            return total // 12, total % 12 + 1

        sequence = []
        y, m = anchor.year, anchor.month
        for i in range(11, -1, -1):
            yy, mm = add_month(y, m, -i)
            sequence.append(f"{yy}-{mm:02d}")

        found = {r["m"].strftime("%Y-%m"): float(r["v"] or 0) for r in qs if r["m"]}
        labels = sequence
        data = [found.get(lbl, 0.0) for lbl in sequence]

    return JsonResponse({"labels": labels, "data": data})


@login_required
def agent_trend_data(request):
    """
    Returns monthly sales/profit trend for agents.

    Params:
      - months=6 (default 6)
      - metric=sales|profit (default sales)
      - agent=<id> (optional; if omitted, all allowed agents aggregated)
        * If the caller is not staff, we always use the current user.
    """
    months = int(request.GET.get("months", 6))
    metric = request.GET.get("metric", "sales")
    agent_id = request.GET.get("agent")

    base = Sale.objects.select_related("agent", "item")

    # Permissions
    if request.user.is_staff:
        if agent_id:
            base = base.filter(agent_id=agent_id)
    else:
        base = base.filter(agent=request.user)

    # Window: last N months including current
    start = (timezone.localdate().replace(day=1) - timedelta(days=31 * (months - 1)))
    base = base.filter(sold_at__date__gte=start)

    if metric == "profit":
        value = ExpressionWrapper(
            F("price") - F("item__order_price"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
        qs = (base.annotate(m=TruncMonth("sold_at"))
                  .values("m")
                  .annotate(v=Sum(value))
                  .order_by("m"))
    else:
        qs = (base.annotate(m=TruncMonth("sold_at"))
                  .values("m")
                  .annotate(v=Count("id"))
                  .order_by("m"))

    rows = list(qs)
    labels = [r["m"].strftime("%b %Y") for r in rows]
    data = [float(r["v"] or 0) for r in rows]
    return JsonResponse({"labels": labels, "data": data})


# =========================
# APPEND-ONLY: Inventory proxies and gentle redirects
# (No changes to existing views above)
# =========================

def _inventory_dashboard_url() -> str:
    """
    Reverse the canonical inventory dashboard URL with multiple fallbacks.
    Never raises: returns a best-effort path even if reversing fails.
    """
    candidates = (
        "inventory:inventory_dashboard",  # preferred
        "inventory_dashboard",
        "inventory:dashboard",
        "inventory:home",
    )
    for name in candidates:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    from django.conf import settings
    prefix = getattr(settings, "FORCE_SCRIPT_NAME", "") or ""
    return f"{prefix}/inventory/dashboard/"

def _call_inventory_view(func_name, request):
    """
    Dynamically dispatch to inventory.views.<func_name>.
    Keep all inventory logic centralized and reuse its permissions/caching.
    """
    inv_views = import_module("inventory.views")
    func = getattr(inv_views, func_name)
    return func(request)


@never_cache
@login_required
def admin_dashboard_proxy(request):
    """Gentle redirect to the inventory dashboard (keeps old links working)."""
    return HttpResponseRedirect(_inventory_dashboard_url())


@never_cache
@login_required
def agent_dashboard_proxy(request):
    """Alias for agent home -> inventory dashboard."""
    return HttpResponseRedirect(_inventory_dashboard_url())


# JSON proxies to inventory APIs — safe fallbacks, no collisions with your existing endpoints

@never_cache
@login_required
@require_GET
def v2_sales_trend_data_proxy(request):
    """
    Proxy to inventory.views.api_sales_trend
    Accepts the same query params: ?period=7d|month&metric=count|amount
    """
    try:
        return _call_inventory_view("api_sales_trend", request)
    except Exception:
        return JsonResponse({"labels": [], "values": []})


@never_cache
@login_required
@require_GET
def v2_top_models_data_proxy(request):
    """
    Proxy to inventory.views.api_top_models
    Accepts: ?period=today|month
    """
    try:
        return _call_inventory_view("api_top_models", request)
    except Exception:
        return JsonResponse({"labels": [], "values": []})


@never_cache
@login_required
@require_GET
def v2_profit_data_proxy(request):
    """
    Proxy to inventory.views.api_profit_bar
    Accepts: ?month=YYYY-MM (optional) &group_by=model (optional)
    """
    try:
        return _call_inventory_view("api_profit_bar", request)
    except Exception:
        return JsonResponse({"labels": [], "data": []})


@never_cache
@login_required
@require_GET
def v2_agent_trend_data_proxy(request):
    """
    Proxy to inventory.views.api_agent_trend
    Accepts: ?months=6&metric=sales|profit&agent=<id> (optional)
    """
    try:
        return _call_inventory_view("api_agent_trend", request)
    except Exception:
        return JsonResponse({"labels": [], "data": []})


@never_cache
@login_required
@require_GET
def v2_cash_overview_proxy(request):
    """
    Proxy to inventory.views.api_cash_overview
    Returns: orders, revenue, paid_out, expenses, period_label
    """
    try:
        return _call_inventory_view("api_cash_overview", request)
    except Exception:
        today = timezone.localdate()
        return JsonResponse({
            "ok": True,
            "orders": 0,
            "revenue": 0.0,
            "paid_out": 0.0,
            "expenses": 0.0,
            "period_label": today.replace(day=1).strftime("%b %Y"),
        })


@never_cache
@login_required
@require_GET
def v2_recommendations_proxy(request):
    """
    Tries inventory.api.predictions_summary (if present),
    falls back to inventory.views.api_predictions,
    then returns a stub (never 500s).
    """
    try:
        inv_api = import_module("inventory.api")
        fn = getattr(inv_api, "predictions_summary", None)
        if callable(fn):
            return fn(request)
    except Exception:
        pass

    try:
        return _call_inventory_view("api_predictions", request)
    except Exception:
        pass

    today = timezone.localdate()
    return JsonResponse({
        "ok": True,
        "overall": [
            {
                "date": (today + timedelta(days=i)).isoformat(),
                "predicted_units": 0,
                "predicted_revenue": 0.0,
            } for i in range(1, 8)
        ],
        "risky": [],
        "message": "recommendations stub",
    })


# ---------------------------
# NEW: Local AI-style recommendations for /api/recommendations/
# ---------------------------
@never_cache
@login_required
@require_GET
def api_recommendations(request):
    """
    Lightweight, local-only recommendations used by the dashboard card.
    No external service required.

    Returns:
      { "success": true, "items": [ { "message": str, "confidence": float }, ... ] }
    """
    u = request.user
    now = timezone.now()
    last_30 = now - timedelta(days=30)
    items = []

    # 1) Personal stock level
    try:
        my_in_stock = InventoryItem.objects.filter(assigned_agent=u, status="IN_STOCK").count()
        if my_in_stock < 10:
            items.append({
                "message": f"Your stock is low ({my_in_stock}/20). Request replenishment.",
                "confidence": 0.90,
            })
        elif my_in_stock < 12:
            items.append({
                "message": f"Consider topping up: you have {my_in_stock}/20 units.",
                "confidence": 0.65,
            })
    except Exception:
        pass

    # 2) Stale inventory (try updated_at, else created_at)
    try:
        fields = {getattr(f, "name", None) for f in InventoryItem._meta.get_fields()}
        stale_cutoff = now - timedelta(days=14)
        stale_qs = InventoryItem.objects.filter(assigned_agent=u, status="IN_STOCK")
        if "updated_at" in fields:
            stale_qs = stale_qs.filter(updated_at__lt=stale_cutoff)
        elif "created_at" in fields:
            stale_qs = stale_qs.filter(created_at__lt=stale_cutoff)
        else:
            stale_qs = None
        if stale_qs is not None:
            stale_count = stale_qs.count()
            if stale_count:
                items.append({
                    "message": f"{stale_count} items haven’t moved in 14+ days — consider promos/rotation.",
                    "confidence": 0.75,
                })
    except Exception:
        pass

    # 3) What’s selling (last 30 days) — attempt a few label fields
    try:
        label_key = None
        top = []
        # attempt item__product__model first
        try:
            top = (Sale.objects.filter(sold_at__gte=last_30)
                   .values("item__product__model")
                   .annotate(n=Count("id"))
                   .order_by("-n")[:3])
            label_key = "item__product__model"
        except Exception:
            pass
        if not top:
            try:
                top = (Sale.objects.filter(sold_at__gte=last_30)
                       .values("item__model")
                       .annotate(n=Count("id"))
                       .order_by("-n")[:3])
                label_key = "item__model"
            except Exception:
                pass
        if not top:
            try:
                top = (Sale.objects.filter(sold_at__gte=last_30)
                       .values("model")
                       .annotate(n=Count("id"))
                       .order_by("-n")[:3])
                label_key = "model"
            except Exception:
                pass

        for t in top:
            label = (t.get(label_key) or "Popular model")
            items.append({
                "message": f"Push {label}: {t['n']} sold in the last 30 days.",
                "confidence": 0.60,
            })
    except Exception:
        pass

    return JsonResponse({"success": True, "items": items}, status=200)


@never_cache
@require_GET
def dashboard_healthz_proxy(request):
    """Lightweight liveness check for the dashboard app."""
    return JsonResponse({"ok": True, "time": timezone.now().isoformat()})
