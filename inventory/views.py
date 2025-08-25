# circuitcity/inventory/views.py
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.mail import mail_admins
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from django.db import transaction, connection
from django.db.models import (
    Sum, Q, Exists, OuterRef, Count, F, DecimalField, ExpressionWrapper, Case, When, Value
)
from django.db.models.deletion import ProtectedError
from django.db.models.functions import TruncMonth, TruncDate, Cast, Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.exceptions import TemplateDoesNotExist
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_http_methods, require_GET

import csv
import json
import math
from datetime import timedelta, datetime, date
from urllib.parse import urlencode

# Forms
from .forms import ScanInForm, ScanSoldForm, InventoryItemForm

# Models
from .models import (
    InventoryItem,
    Product,
    InventoryAudit,
    AgentPasswordReset,
    WarrantyCheckLog,
    TimeLog,
    WalletTxn,
    Location,
)
from sales.models import Sale

# Cache version (signals may bump this). Safe fallback.
try:
    from .cache_utils import get_dashboard_cache_version
except Exception:
    def get_dashboard_cache_version() -> int:
        return 1

User = get_user_model()

# ------------------------------------------------------------------
# Warranty lookups DISABLED: do NOT import warranty.py or requests.
# ------------------------------------------------------------------
_WARRANTY_LOOKUPS_DISABLED = True


# -----------------------
# Helpers
# -----------------------
def _user_home_location(user):
    prof = getattr(user, "agent_profile", None)
    return getattr(prof, "location", None)


def _is_manager_or_admin(user):
    return user.is_staff or user.groups.filter(name__in=["Admin", "Manager"]).exists()


def _is_admin(user):
    return user.is_staff or user.groups.filter(name="Admin").exists()


def _is_auditor(user):
    return user.groups.filter(name__in=["Auditor", "Auditors"]).exists()


def _can_view_all(user):
    return _is_manager_or_admin(user) or _is_auditor(user)


def _can_edit_inventory(user):
    return _is_manager_or_admin(user)


def _audit(item, user, action: str, details: str = ""):
    if not item:
        return
    InventoryAudit.objects.create(item=item, by_user=user, action=action, details=details or "")


def _haversine_m(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371000.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(round(R * c))


def _paginate_qs(request, qs, default_per_page=50, max_per_page=200):
    try:
        per_page = int(request.GET.get("page_size", default_per_page))
    except (TypeError, ValueError):
        per_page = default_per_page
    per_page = min(max(per_page, 1), max_per_page)

    paginator = Paginator(qs, per_page)
    page_num = request.GET.get("page") or 1
    try:
        page_obj = paginator.page(page_num)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    def url_for(page):
        params = request.GET.copy()
        params["page"] = page
        return f"?{urlencode(params)}"

    return page_obj, url_for


def _wallet_balance(user):
    try:
        return WalletTxn.balance_for(user)
    except Exception:
        return WalletTxn.objects.filter(user=user).aggregate(s=Sum("amount"))["s"] or 0


def _wallet_month_sum(user, year: int, month: int):
    try:
        return WalletTxn.month_sum_for(user, year, month)
    except Exception:
        return (
            WalletTxn.objects.filter(user=user, created_at__year=year, created_at__month=month)
            .aggregate(s=Sum("amount"))["s"] or 0
        )


def _inv_base(show_archived: bool):
    if show_archived:
        return InventoryItem.objects
    if hasattr(InventoryItem, "active"):
        return InventoryItem.active
    try:
        return InventoryItem.objects.filter(is_active=True)
    except Exception:
        return InventoryItem.objects


def _render_dashboard_safe(request, context, today, mtd_count, all_time_count):
    try:
        return render(request, "inventory/dashboard.html", context)
    except TemplateDoesNotExist:
        return HttpResponse(
            f"<h1>Inventory Dashboard</h1>"
            f"<p>Template <code>inventory/dashboard.html</code> not found.</p>"
            f"<pre>today={today}  mtd={mtd_count}  all_time={all_time_count}</pre>",
            content_type="text/html",
        )


# -----------------------
# Scan pages
# -----------------------
@never_cache
@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def scan_in(request):
    if _is_auditor(request.user) and request.method == "POST":
        messages.error(request, "Auditors cannot stock-in devices.")
        return redirect("inventory:stock_list")

    initial = {}
    loc = _user_home_location(request.user)
    if loc:
        initial["location"] = loc
    initial.setdefault("received_at", timezone.localdate())

    if request.method == "POST":
        form = ScanInForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please correct the errors below.")
            return render(request, "inventory/scan_in.html", {"form": form})

        data = form.cleaned_data

        if not data.get("product"):
            messages.error(request, "Select a product model.")
            return render(request, "inventory/scan_in.html", {"form": form})
        if not data.get("location"):
            messages.error(request, "Choose a location.")
            return render(request, "inventory/scan_in.html", {"form": form})
        if data.get("order_price") is None or data["order_price"] < 0:
            messages.error(request, "Order price must be a non-negative amount.")
            return render(request, "inventory/scan_in.html", {"form": form})

        imei = (data.get("imei") or "").strip()

        if imei and InventoryItem.objects.select_for_update().filter(imei=imei).exists():
            messages.error(request, f"Item with IMEI {imei} already exists.")
            return render(request, "inventory/scan_in.html", {"form": form})

        # Warranty checks are disabled
        WarrantyCheckLog.objects.create(
            imei=imei or "",
            result="SKIPPED",
            expires_at=None,
            notes="scan_in (warranty disabled)",
            by_user=request.user,
        )

        allow = True
        if not imei and not _is_manager_or_admin(request.user):
            allow = False

        if not allow:
            mail_admins(
                subject="Stock-in blocked",
                message=f"User {request.user} attempted to stock IMEI {imei} (warranty disabled).",
                fail_silently=True,
            )
            messages.error(request, "IMEI is required.")
            return render(request, "inventory/scan_in.html", {"form": form, "blocked": True})

        item = InventoryItem.objects.create(
            imei=imei or None,
            product=data["product"],
            received_at=data["received_at"],
            order_price=data["order_price"],
            current_location=data["location"],
            assigned_agent=request.user if data.get("assigned_to_me") else None,
            warranty_status="SKIPPED",
            warranty_expires_at=None,
            warranty_last_checked_at=None,
            activation_detected_at=None,
        )

        _audit(item, request.user, "STOCK_IN", "Warranty disabled")
        messages.success(request, f"Stocked: {imei or data['product']}")
        return redirect("inventory:scan_in")

    form = ScanInForm(initial=initial)
    return render(request, "inventory/scan_in.html", {"form": form})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def scan_sold(request):
    if _is_auditor(request.user) and request.method == "POST":
        messages.error(request, "Auditors cannot mark items as SOLD.")
        return redirect("inventory:stock_list")

    initial = {}
    loc = _user_home_location(request.user)
    if loc:
        initial["location"] = loc
    initial.setdefault("sold_at", timezone.localdate())

    if request.method == "POST":
        form = ScanSoldForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please correct the errors below.")
            return render(request, "inventory/scan_sold.html", {"form": form})

        data = form.cleaned_data
        imei = data["imei"]

        try:
            item = InventoryItem.objects.select_for_update().get(imei=imei)
        except InventoryItem.DoesNotExist:
            messages.error(request, "Item not found. Check the IMEI and try again.")
            return render(request, "inventory/scan_sold.html", {"form": form})

        if str(getattr(item, "status", "")) == "SOLD":
            messages.error(request, f"Item {item.imei} is already sold.")
            return render(request, "inventory/scan_sold.html", {"form": form})

        if data.get("price") is not None and data["price"] < 0:
            messages.error(request, "Price must be a non-negative amount.")
            return render(request, "inventory/scan_sold.html", {"form": form})

        item._actor = request.user
        item.status = "SOLD"
        item.selling_price = data.get("price")
        item.current_location = data["location"]
        item.sold_at = data.get("sold_at") or timezone.localdate()

        if hasattr(item, "sold_by") and getattr(item, "sold_by", None) is None:
            try:
                item.sold_by = request.user
            except Exception:
                pass

        item.save()

        Sale.objects.create(
            item=item,
            agent=request.user,
            location=data["location"],
            sold_at=item.sold_at,
            price=item.selling_price or 0,
            commission_pct=data.get("commission_pct"),
        )

        _audit(item, request.user, "SOLD_FORM", "V1 flow")
        messages.success(
            request,
            f"Marked SOLD: {item.imei}{' at ' + str(item.selling_price) if item.selling_price else ''}",
        )
        return redirect("inventory:scan_sold")

    form = ScanSoldForm(initial=initial)
    return render(request, "inventory/scan_sold.html", {"form": form})


@never_cache
@login_required
@require_http_methods(["GET"])
def scan_web(request):
    """
    Render the web-scanner page, but be resilient to template path differences.
    If neither template exists, render a minimal fallback so the page is never blank.
    """
    candidates = [
        "inventory/scan_web.html",             # current
        "circuitcity/templates/inventory/scan_web.html",  # legacy path (very rare)
    ]
    for tpl in candidates:
        try:
            return render(request, tpl, {})
        except TemplateDoesNotExist:
            continue

    # Minimal fallback (never blank)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Scan (Web) — Fallback</title>
  <style>body{{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;padding:24px;}}
  .wrap{{max-width:640px;margin:auto}}.f{{display:flex;gap:8px}}</style>
</head>
<body>
  <div class="wrap">
    <h2>Scan (Web) — Fallback</h2>
    <p>If you see this, the template wasn't found. You can still mark SOLD here.</p>
    <div class="f">
      <input id="imei" placeholder="IMEI (15 digits)" inputmode="numeric" maxlength="15" />
      <input id="price" type="number" step="0.01" placeholder="Price (optional)" />
      <button id="go">Mark SOLD</button>
    </div>
    <pre id="out"></pre>
  </div>
<script>
const imei=document.getElementById('imei'), price=document.getElementById('price'), out=document.getElementById('out');
document.getElementById('go').onclick=async()=>{{
  const v=(imei.value||'').replace(/\\D/g,'');
  if(v.length!==15){{out.textContent='IMEI must be exactly 15 digits.';return;}}
  const r = await fetch("{settings.FORCE_SCRIPT_NAME or ''}/inventory/api/mark-sold/", {{
    method:"POST", headers:{{"Content-Type":"application/json","X-CSRFToken":(document.cookie.match(/csrftoken=([^;]+)/)||[])[1]||""}},
    body:JSON.stringify({{imei:v, price:price.value||undefined}})
  }});
  out.textContent = 'HTTP '+r.status+'\\n'+await r.text();
}};
</script>
</body></html>"""
    return HttpResponse(html, content_type="text/html")


@never_cache
@login_required
@require_POST
@transaction.atomic
def api_mark_sold(request):
    if _is_auditor(request.user):
        return JsonResponse({"ok": False, "error": "Auditors cannot modify inventory."}, status=403)

    try:
        if request.content_type and "application/json" in request.content_type.lower():
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    imei = (payload.get("imei") or "").strip()
    comment = (payload.get("comment") or "").strip()
    price = payload.get("price")
    location_id = payload.get("location_id")

    if not imei.isdigit() or len(imei) != 15:
        return JsonResponse({"ok": False, "error": "IMEI must be exactly 15 digits."}, status=400)

    try:
        item = InventoryItem.objects.select_for_update().get(imei=imei)
    except InventoryItem.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Item not found."}, status=404)

    if str(getattr(item, "status", "")) == "SOLD":
        _audit(item, request.user, "SOLD_API_DUP", f"Duplicate mark-sold via API. Comment: {comment}")
        return JsonResponse({"ok": True, "imei": imei, "already_sold": True})

    if price is not None:
        try:
            price_val = float(price)
            if price_val < 0:
                return JsonResponse({"ok": False, "error": "Price must be a non-negative amount."}, status=400)
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid price format."}, status=400)
    else:
        price_val = None

    updates = {"status": "SOLD"}
    item._actor = request.user
    item.status = "SOLD"

    if hasattr(item, "sold_at") and not item.sold_at:
        item.sold_at = timezone.localdate()
        updates["sold_at"] = item.sold_at

    if price_val is not None:
        item.selling_price = price_val
        updates["selling_price"] = item.selling_price

    if location_id:
        try:
            item.current_location_id = int(location_id)
            updates["current_location_id"] = item.current_location_id
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid location id."}, status=400)

    if hasattr(item, "sold_by") and getattr(item, "sold_by", None) is None:
        try:
            item.sold_by = request.user
        except Exception:
            pass

    item.save()
    _audit(item, request.user, "SOLD_API", f"via scan_web; comment={comment}")

    try:
        sale_kwargs = {
            "item": item,
            "agent": request.user,
            "sold_at": getattr(item, "sold_at", timezone.localdate()),
            "price": item.selling_price or 0,
        }
        if location_id:
            sale_kwargs["location_id"] = item.current_location_id
        Sale.objects.create(**sale_kwargs)
    except Exception:
        pass

    return JsonResponse({"ok": True, "imei": imei, "updates": updates})


# -----------------------
# Dashboard & list
# -----------------------
@login_required
def inventory_dashboard(request):
    period = request.GET.get("period", "month")
    model_id = request.GET.get("model") or None
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    month_start = today.replace(day=1)

    ver = get_dashboard_cache_version()
    cache_key = f"dash:v{ver}:u{request.user.id}:p:{period}:m:{model_id or 'all'}"
    cached = cache.get(cache_key)
    if cached:
        return _render_dashboard_safe(
            request, cached, today, cached.get("mtd_count", 0), cached.get("all_time_count", 0)
        )

    # Scope for KPIs and stock widgets (respect permissions)
    if _can_view_all(request.user):
        sales_qs_all = Sale.objects.select_related("item", "agent", "item__product")
        items_qs = InventoryItem.objects.select_related("product", "assigned_agent", "current_location")
        scope_label = "All agents"
    else:
        sales_qs_all = Sale.objects.filter(agent=request.user).select_related("item", "agent", "item__product")
        items_qs = InventoryItem.objects.filter(assigned_agent=request.user).select_related(
            "product", "assigned_agent", "current_location"
        )
        scope_label = "My sales"

    if model_id:
        sales_qs_all = sales_qs_all.filter(item__product_id=model_id)
        items_qs = items_qs.filter(product_id=model_id)

    sales_qs_period = sales_qs_all
    if period == "month":
        sales_qs_period = sales_qs_all.filter(sold_at__gte=month_start)

    today_count = sales_qs_all.filter(sold_at__gte=today, sold_at__lt=tomorrow).count()
    mtd_count = sales_qs_all.filter(sold_at__gte=month_start, sold_at__lt=tomorrow).count()
    all_time_count = sales_qs_all.count()

    # ---- Agent ranking (ALL agents, ordered by earnings desc then sales desc) ----
    dec2 = DecimalField(max_digits=14, decimal_places=2)
    pct_dec = DecimalField(max_digits=5, decimal_places=2)

    rank_base = Sale.objects.select_related("agent")
    if model_id:
        rank_base = rank_base.filter(item__product_id=model_id)
    if period == "month":
        rank_base = rank_base.filter(sold_at__gte=month_start)

    commission_pct_dec = Cast(F("commission_pct"), pct_dec)
    commission_expr = ExpressionWrapper(
        Coalesce(F("price"), Value(0), output_field=dec2) *
        (Coalesce(commission_pct_dec, Value(0), output_field=pct_dec) / Value(100, output_field=pct_dec)),
        output_field=dec2,
    )

    agent_rank_qs = (
        rank_base.values("agent_id", "agent__username")
        .annotate(
            total_sales=Count("id"),
            earnings=Coalesce(Sum(commission_expr), Value(0), output_field=dec2),
            revenue=Coalesce(Sum("price"), Value(0), output_field=dec2),
        )
        .order_by("-earnings", "-total_sales", "agent__username")
    )
    agent_rank = list(agent_rank_qs)

    # Wallet summaries (decimal-safe defaults) for the agents present in ranking
    agent_wallet_summaries = {}
    agent_ids = [row["agent_id"] for row in agent_rank if row.get("agent_id")]
    if agent_ids:
        w = WalletTxn.objects.filter(user_id__in=agent_ids)
        agent_wallet_rows = w.values("user_id").annotate(
            balance=Sum("amount"),
            lifetime_commission=Sum(Case(When(reason="COMMISSION", then="amount"),
                                         default=Value(0, output_field=dec2))),
            lifetime_advance=Sum(Case(When(reason="ADVANCE", then="amount"),
                                      default=Value(0, output_field=dec2))),
            lifetime_adjustment=Sum(Case(When(reason="ADJUSTMENT", then="amount"),
                                         default=Value(0, output_field=dec2))),
            month_commission=Sum(
                Case(
                    When(reason="COMMISSION",
                         created_at__date__gte=month_start, created_at__date__lte=today,
                         then="amount"),
                    default=Value(0, output_field=dec2),
                )
            ),
            month_advance=Sum(
                Case(
                    When(reason="ADVANCE",
                         created_at__date__gte=month_start, created_at__date__lte=today,
                         then="amount"),
                    default=Value(0, output_field=dec2),
                )
            ),
            month_adjustment=Sum(
                Case(
                    When(reason="ADJUSTMENT",
                         created_at__date__gte=month_start, created_at__date__lte=today,
                         then="amount"),
                    default=Value(0, output_field=dec2),
                )
            ),
        )
        for r in agent_wallet_rows:
            uid = r["user_id"]
            m_total = (r["month_commission"] or 0) + (r["month_advance"] or 0) + (r["month_adjustment"] or 0)
            lt_total = (r["lifetime_commission"] or 0) + (r["lifetime_advance"] or 0) + (r["lifetime_adjustment"] or 0)
            agent_wallet_summaries[uid] = {
                "balance": float(r["balance"] or 0),
                "month": {
                    "commission": float(r["month_commission"] or 0),
                    "advance": float(r["month_advance"] or 0),
                    "adjustment": float(r["month_adjustment"] or 0),
                    "total": float(m_total or 0),
                },
                "lifetime": {
                    "commission": float(r["lifetime_commission"] or 0),
                    "advance": float(r["lifetime_advance"] or 0),
                    "adjustment": float(r["lifetime_adjustment"] or 0),
                    "total": float(lt_total or 0),
                },
            }

    # >>> Rank agents by WALLET BALANCE (desc). Tie-breakers keep original intent.
    for row in agent_rank:
        uid = row.get("agent_id")
        row["wallet_balance"] = float(agent_wallet_summaries.get(uid, {}).get("balance", 0.0))
    agent_rank.sort(
        key=lambda r: (
            r.get("wallet_balance", 0.0),
            float(r.get("earnings") or 0.0),
            int(r.get("total_sales") or 0),
        ),
        reverse=True,
    )
    # <<< End wallet-based ranking

    # ===== Revenue/Profit last 12 months =====
    def back_n_months(d: date, n: int) -> date:
        y = d.year
        m = d.month - n
        while m <= 0:
            m += 12
            y -= 1
        return date(y, m, 1)

    last_12_labels = [back_n_months(month_start, n).strftime("%Y-%m") for n in range(11, -1, -1)]

    rev_qs = Sale.objects.select_related("item").filter(
        sold_at__gte=back_n_months(month_start, 11)
    )
    if not _can_view_all(request.user):
        rev_qs = rev_qs.filter(agent=request.user)
    if model_id:
        rev_qs = rev_qs.filter(item__product_id=model_id)

    rev_by_month = (
        rev_qs.annotate(m=TruncMonth("sold_at"))
        .values("m")
        .annotate(total=Coalesce(Sum("price"), Value(0), output_field=dec2))
        .order_by("m")
    )
    totals_map = {r["m"].strftime("%Y-%m"): float(r["total"] or 0) for r in rev_by_month if r["m"]}

    # Profit uses Coalesce so NULL order prices don't nuke a month
    profit_expr_month = ExpressionWrapper(
        Coalesce(F("price"), Value(0), output_field=dec2) -
        Coalesce(F("item__order_price"), Value(0), output_field=dec2),
        output_field=dec2,
    )
    prof_by_month = (
        rev_qs.annotate(m=TruncMonth("sold_at"))
        .values("m")
        .annotate(total=Coalesce(Sum(profit_expr_month), Value(0), output_field=dec2))
        .order_by("m")
    )
    prof_map = {r["m"].strftime("%Y-%m"): float(r["total"] or 0) for r in prof_by_month if r["m"]}

    revenue_points = [totals_map.get(lbl, 0.0) for lbl in last_12_labels]
    profit_points = [prof_map.get(lbl, 0.0) for lbl in last_12_labels]

    # ===== Agents: total stock vs sold units (period filter applied) =====
    total_assigned = (
        items_qs.values("assigned_agent_id", "assigned_agent__username")
        .annotate(total_stock=Count("id"))
        .order_by("assigned_agent__username")
    )
    sold_units = sales_qs_period.values("agent_id").annotate(sold=Count("id"))
    sold_map = {r["agent_id"]: r["sold"] for r in sold_units}
    agent_rows = [
        {
            "agent_id": row["assigned_agent_id"],
            "agent": row["assigned_agent__username"] or "—",
            "total_stock": row["total_stock"],
            "sold_units": sold_map.get(row["assigned_agent_id"], 0),
        }
        for row in total_assigned
    ]

    # ===== Cost vs Revenue vs Profit (period/model filtered, decimal-safe) =====
    totals = sales_qs_period.aggregate(
        revenue=Coalesce(Sum("price"), Value(0), output_field=dec2),
        cost=Coalesce(Sum(Coalesce(F("item__order_price"), Value(0), output_field=dec2)), Value(0), output_field=dec2),
        profit=Coalesce(Sum(profit_expr_month), Value(0), output_field=dec2),
    )
    pie_revenue = float(totals.get("revenue") or 0)
    pie_cost = float(totals.get("cost") or 0)
    pie_profit = float(totals.get("profit") or 0)

    # ===== Battery =====
    in_stock_qs = items_qs.filter(status="IN_STOCK")
    jug_count = in_stock_qs.count()
    jug_fill_pct = min(100, int(round((jug_count / 100.0) * 100))) if jug_count > 0 else 0
    if jug_count <= 20:
        jug_color = "red"
    elif 21 <= jug_count <= 50:
        jug_color = "yellow"
    elif 51 <= jug_count <= 69:
        jug_color = "mildgreen"
    else:
        jug_color = "lightgreen"

    products = Product.objects.order_by("brand", "model", "variant").values("id", "brand", "model", "variant")

    # ===== Wallet (current user) =====
    def _sum(qs):
        return qs.aggregate(s=Sum("amount"))["s"] or 0

    my_balance = _wallet_balance(request.user)
    today_local = timezone.localdate()
    month_start_local = today_local.replace(day=1)
    month_qs = WalletTxn.objects.filter(user=request.user, created_at__date__gte=month_start_local, created_at__date__lte=today_local)
    my_month_commission = _sum(month_qs.filter(reason="COMMISSION"))
    my_month_advance = _sum(month_qs.filter(reason="ADVANCE"))
    my_month_adjustment = _sum(month_qs.filter(reason="ADJUSTMENT"))
    my_month_total = my_month_commission + my_month_advance + my_month_adjustment

    life_qs = WalletTxn.objects.filter(user=request.user)
    my_life_commission = _sum(life_qs.filter(reason="COMMISSION"))
    my_life_advance = _sum(life_qs.filter(reason="ADVANCE"))
    my_life_adjustment = _sum(life_qs.filter(reason="ADJUSTMENT"))
    my_life_total = _sum(life_qs)

    context = {
        "period": period,
        "model_id": int(model_id) if model_id else None,
        "products": list(products),

        # Leaderboard + wallet chips
        "agent_rank": agent_rank,
        "agent_wallet_summaries": agent_wallet_summaries,

        # Charts
        "labels_json": json.dumps(last_12_labels),
        "revenue_points_json": json.dumps(revenue_points),
        "profit_points_json": json.dumps(profit_points),
        "pie_data_json": json.dumps([pie_cost, pie_revenue, pie_profit]),

        # Agent stock table
        "agent_rows": agent_rows,

        # Battery
        "jug_count": jug_count,
        "jug_fill_pct": jug_fill_pct,
        "jug_color": jug_color,

        # KPIs (also expose legacy 'kpis' bag used in some templates)
        "is_manager_or_admin": _is_manager_or_admin(request.user),
        "today_count": today_count,
        "mtd_count": mtd_count,
        "all_time_count": all_time_count,
        "kpis": {
            "scope": scope_label,
            "today_count": today_count,
            "month_count": mtd_count,
            "all_count": all_time_count,
        },

        # My wallet (summary)
        "wallet": {
            "balance": my_balance,
            "month": {
                "commission": my_month_commission,
                "advance": my_month_advance,
                "adjustment": my_month_adjustment,
                "total": my_month_total,
                "month_label": month_start_local.strftime("%b %Y"),
            },
            "lifetime": {
                "commission": my_life_commission,
                "advance": my_life_advance,
                "adjustment": my_life_adjustment,
                "total": my_life_total,
            },
        },
    }

    # --- Feature flags & slide config (rotator will switch slides every 10s) ---
    context["PREDICTIVE_ENABLED"]   = bool(getattr(settings, "PREDICTIVE_ENABLED", True))
    context["THEME_ROTATE_ENABLED"] = bool(getattr(settings, "THEME_ROTATE_ENABLED", True))
    context["THEME_ROTATE_MS"]      = int(getattr(settings, "THEME_ROTATE_MS", 10000))
    context["THEME_DEFAULT"]        = str(getattr(settings, "THEME_DEFAULT", "style-1"))
    context["ROTATOR_MODE"]         = "slides"
    # ✅ corrected API URLs (were underscores before)
    context["DASHBOARD_SLIDES"] = [
        {
            "key": "trends",
            "title": "Sales Trends",
            "apis": ["/inventory/api/sales-trend/?period=7d&metric=count",
                     "/inventory/api/profit-bar/",
                     "/inventory/api/top-models/?period=today"]
        },
        {
            "key": "cash",
            "title": "Cash Overview",
            "apis": ["/inventory/api/cash-overview/"]
        },
        {
            "key": "agents",
            "title": "Agent Performance",
            "apis": ["/inventory/api/agent-trend/?months=6&metric=sales"]
        }
    ]

    cache.set(cache_key, context, 60)
    return _render_dashboard_safe(request, context, today, mtd_count, all_time_count)


@never_cache
@login_required
@require_http_methods(["GET"])
def stock_list(request):
    q = request.GET.get("q", "").strip()
    show_archived = request.GET.get("archived") == "1"
    want_csv = request.GET.get("export") == "csv"
    status = (request.GET.get("status") or "").lower()

    has_sales_subq = Sale.objects.filter(item=OuterRef("pk"))
    base = _inv_base(show_archived)

    base_qs = base.select_related("product", "current_location", "assigned_agent").annotate(
        has_sales=Exists(has_sales_subq)
    )

    if _can_view_all(request.user):
        qs = base_qs
    else:
        qs = base_qs.filter(assigned_agent=request.user)

    if q:
        qs = qs.filter(
            Q(imei__icontains=q)
            | Q(product__model__icontains=q)
            | Q(product__brand__icontains=q)
            | Q(product__variant__icontains=q)
        )

    if status == "in_stock":
        qs = qs.filter(status="IN_STOCK")
    elif status == "sold":
        qs = qs.filter(status="SOLD")

    qs = qs.order_by("-received_at", "product__model")

    if want_csv:
        filename = f"stock_export_{timezone.now():%Y%m%d_%H%M}.csv"
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response.write("\ufeff")  # BOM for Excel
        writer = csv.writer(response)
        writer.writerow(
            ["IMEI", "Product", "Status", "Order Price", "Selling Price", "Location", "Agent", "Received", "Archived", "Has Sales"]
        )
        for it in qs.iterator():
            product_str = str(it.product) if it.product else ""
            location_str = it.current_location.name if it.current_location_id else ""
            agent_str = it.assigned_agent.get_username() if it.assigned_agent_id else ""
            received_str = it.received_at.strftime("%Y-%m-%d") if it.received_at else ""
            writer.writerow(
                [
                    it.imei or "",
                    product_str,
                    it.status,
                    f"{it.order_price:.2f}" if it.order_price is not None else "",
                    f"{it.selling_price:.2f}" if it.selling_price is not None else "",
                    location_str,
                    agent_str,
                    received_str,
                    "No" if getattr(it, "is_active", True) else "Yes",
                    "Yes" if getattr(it, "has_sales", False) else "No",
                ]
            )
        return response

    in_stock = qs.filter(status="IN_STOCK").count()
    sold_count = qs.filter(status="SOLD").count()
    sum_order = qs.aggregate(s=Sum("order_price"))["s"] or 0
    sum_selling = qs.aggregate(s=Sum("selling_price"))["s"] or 0

    page_obj, url_for = _paginate_qs(request, qs, default_per_page=50, max_per_page=200)

    rows = [
        {
            "imei": (it.imei or ""),
            "product": str(it.product) if it.product else "",
            "status": ("SOLD" if it.status == "SOLD" else "In stock"),
            "order_price": f"{(it.order_price or 0):,.0f}",
            "selling_price": ("" if it.selling_price is None else f"{float(it.selling_price):,.0f}"),
            "location": it.current_location.name if it.current_location_id else "—",
            "agent": it.assigned_agent.get_username() if it.assigned_agent_id else "—",
        }
        for it in page_obj.object_list
    ]

    context = {
        "items": page_obj.object_list,
        "q": q,
        "is_admin": _is_admin(request.user),
        "can_edit": _can_edit_inventory(request.user),
        "show_archived": show_archived,
        "total_in_stock": in_stock,
        "total_sold": sold_count,
        "sum_order_price": sum_order,
        "sum_selling_price": sum_selling,
        "page_obj": page_obj,
        "url_for": url_for,
        "rows": rows,
        "in_stock": in_stock,
        "sold_count": sold_count,
        "sum_order": sum_order,
        "sum_selling": sum_selling,
        "status": status,
    }
    return render(request, "inventory/stock_list.html", context)


@never_cache
@login_required
@require_http_methods(["GET"])
def export_csv(request):
    # Same filters/permissions as stock_list, but always returns CSV
    q = request.GET.get("q", "").strip()
    show_archived = request.GET.get("archived") == "1"
    status = (request.GET.get("status") or "").lower()

    has_sales_subq = Sale.objects.filter(item=OuterRef("pk"))
    base = _inv_base(show_archived)

    qs = base.select_related("product", "current_location", "assigned_agent").annotate(has_sales=Exists(has_sales_subq))
    if not _can_view_all(request.user):
        qs = qs.filter(assigned_agent=request.user)

    if q:
        qs = qs.filter(
            Q(imei__icontains=q)
            | Q(product__model__icontains=q)
            | Q(product__brand__icontains=q)
            | Q(product__variant__icontains=q)
        )

    if status == "in_stock":
        qs = qs.filter(status="IN_STOCK")
    elif status == "sold":
        qs = qs.filter(status="SOLD")

    qs = qs.order_by("-received_at", "product__model")

    filename = f"stock_export_{timezone.now():%Y%m%d_%H%M}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        ["IMEI", "Product", "Status", "Order Price", "Selling Price", "Location", "Agent", "Received", "Archived", "Has Sales"]
    )
    for it in qs.iterator():
        product_str = str(it.product) if it.product else ""
        location_str = it.current_location.name if it.current_location_id else ""
        agent_str = it.assigned_agent.get_username() if it.assigned_agent_id else ""
        received_str = it.received_at.strftime("%Y-%m-%d") if it.received_at else ""
        writer.writerow(
            [
                it.imei or "",
                product_str,
                it.status,
                f"{it.order_price:.2f}" if it.order_price is not None else "",
                f"{it.selling_price:.2f}" if it.selling_price is not None else "",
                location_str,
                agent_str,
                received_str,
                "No" if getattr(it, "is_active", True) else "Yes",
                "Yes" if getattr(it, "has_sales", False) else "No",
            ]
        )
    return response


# -----------------------
# Time logging & Wallet
# -----------------------
@never_cache
@login_required
@require_http_methods(["GET"])
def time_checkin_page(request):
    prof = getattr(request.user, "agent_profile", None)
    pref_loc = getattr(prof, "location", None)
    return render(
        request,
        "inventory/time_checkin.html",
        {"pref_loc_id": pref_loc.id if pref_loc else "", "pref_loc_name": pref_loc.name if pref_loc else ""},
    )


@never_cache
@login_required
@require_POST
def api_time_checkin(request):
    try:
        if request.content_type and "application/json" in request.content_type.lower():
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    checkin_type = (payload.get("checkin_type") or payload.get("type") or "ARRIVAL").upper()
    if checkin_type not in (TimeLog.ARRIVAL, TimeLog.DEPARTURE):
        checkin_type = TimeLog.ARRIVAL

    lat_raw = payload.get("latitude", payload.get("lat"))
    lon_raw = payload.get("longitude", payload.get("lon"))
    acc_raw = payload.get("accuracy_m", payload.get("accuracy"))

    try:
        lat = float(lat_raw) if lat_raw not in (None, "") else None
        lon = float(lon_raw) if lon_raw not in (None, "") else None
        acc = int(acc_raw) if acc_raw not in (None, "") else None
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid lat/lon/accuracy."}, status=400)

    loc = None
    loc_id = payload.get("location_id")
    if loc_id:
        try:
            loc = Location.objects.get(pk=int(loc_id))
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid location_id."}, status=400)
    if not loc:
        loc = _user_home_location(request.user)

    dist = None
    within = False
    if loc and loc.latitude is not None and loc.longitude is not None and lat is not None and lon is not None:
        dist = _haversine_m(lat, lon, float(loc.latitude), float(loc.longitude))
        radius = (loc.geofence_radius_m or 150) + (acc or 0)
        within = dist <= radius

    tl = TimeLog.objects.create(
        user=request.user,
        location=loc,
        checkin_type=checkin_type,
        latitude=lat,
        longitude=lon,
        accuracy_m=acc,
        distance_m=dist,
        within_geofence=within,
        note=(payload.get("note") or "").strip()[:200],
    )

    return JsonResponse(
        {
            "ok": True,
            "id": tl.id,
            "logged_at": tl.logged_at.isoformat(),
            "location": (loc.name if loc else None),
            "distance_m": dist,
            "within_geofence": within,
            "checkin_type": checkin_type,
        }
    )


@never_cache
@login_required
@require_http_methods(["GET"])
def time_logs(request):
    if _can_view_all(request.user):
        qs = TimeLog.objects.select_related("user", "location").order_by("-logged_at")
    else:
        qs = TimeLog.objects.select_related("user", "location").filter(user=request.user).order_by("-logged_at")

    page_obj, url_for = _paginate_qs(request, qs, default_per_page=50, max_per_page=200)
    return render(
        request, "inventory/time_logs.html", {"logs": page_obj.object_list, "page_obj": page_obj, "url_for": url_for}
    )


@never_cache
@login_required
@require_http_methods(["GET"])
def api_wallet_summary(request):
    target = request.user
    user_id = request.GET.get("user_id")
    if user_id:
        if not _is_manager_or_admin(request.user):
            return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)
        try:
            target = User.objects.get(pk=int(user_id))
        except Exception:
            return JsonResponse({"ok": False, "error": "Unknown user_id."}, status=400)

    balance = _wallet_balance(target)

    year = request.GET.get("year")
    month = request.GET.get("month")
    data = {"ok": True, "user_id": target.id, "balance": balance}
    if year and month:
        try:
            y, m = int(year), int(month)
            data["month_sum"] = _wallet_month_sum(target, y, m)
            data["year"] = y
            data["month"] = m
        except Exception:
            data["month_sum"] = None
    return JsonResponse(data)


api_wallet_balance = api_wallet_summary


@never_cache
@login_required
@require_POST
def api_wallet_add_txn(request):
    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Admin only."}, status=403)

    try:
        if request.content_type and "application/json" in request.content_type.lower():
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    try:
        target = User.objects.get(pk=int(payload.get("user_id")))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid or missing user_id."}, status=400)

    try:
        amount = float(payload.get("amount"))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid amount."}, status=400)

    reason = (payload.get("reason") or "ADJUSTMENT").upper()
    allowed = {k for k, _ in getattr(WalletTxn, "REASON_CHOICES", [])} or {"ADJUSTMENT", "ADVANCE", "COMMISSION", "PAYOUT"}
    if reason not in allowed:
        return JsonResponse({"ok": False, "error": f"Invalid reason. Allowed: {sorted(list(allowed))}"}, status=400)

    memo = (payload.get("memo") or "").strip()[:200]

    txn = WalletTxn.objects.create(user=target, amount=amount, reason=reason, memo=memo)

    new_balance = _wallet_balance(target)
    return JsonResponse({"ok": True, "txn_id": txn.id, "balance": new_balance})


api_wallet_txn = api_wallet_add_txn


@never_cache
@login_required
@require_http_methods(["GET"])
def wallet_page(request):
    target = request.user
    user_id = request.GET.get("user_id")
    if user_id and _is_manager_or_admin(request.user):
        try:
            target = User.objects.get(pk=int(user_id))
        except Exception:
            target = request.user

    today = timezone.localdate()
    balance = _wallet_balance(target)
    month_sum = _wallet_month_sum(target, today.year, today.month)

    recent_txns = WalletTxn.objects.select_related("user").filter(user=target).order_by("-created_at")[:50]

    agents = []
    if _is_manager_or_admin(request.user):
        agents = list(User.objects.order_by("username").values("id", "username"))

    context = {
        "target": target,
        "balance": balance,
        "month_sum": month_sum,
        "recent_txns": recent_txns,
        "reasons": getattr(WalletTxn, "REASON_CHOICES", []),
        "is_admin": _is_admin(request.user),
        "is_manager_or_admin": _is_manager_or_admin(request.user),
        "agents": agents,
        "today_year": today.year,
        "today_month": today.month,
    }
    return render(request, "inventory/wallet.html", context)


# -----------------------
# Stock management
# -----------------------
@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def update_stock(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)

    if not _can_edit_inventory(request.user):
        msg = (
            f"EDIT attempt BLOCKED: user '{request.user.username}' tried to edit "
            f"item {item.imei or item.pk} at {timezone.now():%Y-%m-%d %H:%M}."
        )
        _audit(item, request.user, "EDIT_DENIED", "Insufficient permissions")
        mail_admins(subject="Edit attempt blocked", message=msg, fail_silently=True)
        messages.error(request, "Only managers/admins can edit inventory items.")
        return redirect("inventory:stock_list")

    if request.method == "POST":
        form = InventoryItemForm(request.POST, instance=item, user=request.user)
        if form.is_valid():
            changed_fields = list(form.changed_data)
            price_fields = {"order_price", "selling_price"}
            if (price_fields & set(changed_fields)) and not _is_admin(request.user):
                messages.error(request, "Only admins can edit order/selling prices.")
                return render(request, "inventory/edit_stock.html", {"form": form, "item": item})

            old_vals = {name: getattr(item, name) for name in changed_fields}
            saved_item = form.save()

            if _is_admin(request.user):
                bulk_updates = {}
                if "order_price" in changed_fields:
                    bulk_updates["order_price"] = form.cleaned_data.get("order_price")
                if "selling_price" in changed_fields:
                    bulk_updates["selling_price"] = form.cleaned_data.get("selling_price")

                if bulk_updates:
                    base_mgr = (
                        InventoryItem.active if hasattr(InventoryItem, "active") else InventoryItem.objects.filter(is_active=True)
                    )
                    qs = base_mgr.filter(product=saved_item.product).exclude(pk=saved_item.pk)
                    updated = qs.update(**bulk_updates)
                    if updated:
                        _audit(
                            saved_item,
                            request.user,
                            "BULK_PRICE_UPDATE",
                            f"Updated {updated} items for product '{saved_item.product}'. Fields: {bulk_updates}",
                        )
                        messages.info(
                            request, f"Applied {', '.join(bulk_updates.keys())} to {updated} other '{saved_item.product}' item(s)."
                        )

            details = "Changed fields:\n" + (
                "\n".join([f"{k}: {old_vals.get(k)} → {getattr(saved_item, k)}" for k in changed_fields])
                if changed_fields
                else "No field changes"
            )
            _audit(saved_item, request.user, "EDIT", details)

            messages.success(request, "Item updated.")
            return redirect("inventory:stock_list")
    else:
        form = InventoryItemForm(instance=item, user=request.user)

    return render(request, "inventory/edit_stock.html", {"form": form, "item": item})


@require_POST
@never_cache
@login_required
def delete_stock(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)

    if not _is_admin(request.user):
        msg = (
            f"Deletion attempt BLOCKED: user '{request.user.username}' tried to delete "
            f"item {item.imei or item.pk} at {timezone.now():%Y-%m-%d %H:%M}."
        )
        _audit(item, request.user, "DELETE_DENIED", msg)
        mail_admins(subject="Deletion attempt blocked", message=msg, fail_silently=True)
        messages.error(request, "Only admins can delete items. Admin has been notified.")
        return redirect("inventory:stock_list")

    item_repr = f"{item.imei or item.pk} ({item.product})"
    try:
        _audit(
            item,
            request.user,
            "DELETE",
            f"Attempt by {request.user.username} at {timezone.now():%Y-%m-%d %H:%M}. Item: {item_repr}",
        )
        item.delete()
        messages.success(request, "Item deleted.")
    except ProtectedError:
        item.is_active = False
        item.save(update_fields=["is_active"])
        _audit(item, request.user, "ARCHIVE_FALLBACK", "ProtectedError: related sales exist; archived instead.")
        messages.info(request, "This item has sales, so it was archived instead of deleted.")
    return redirect("inventory:stock_list")


@require_POST
@never_cache
@login_required
def restore_stock(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)

    if not _is_admin(request.user):
        msg = (
            f"Restore attempt BLOCKED: user '{request.user.username}' tried to restore "
            f"item {item.imei or item.pk} at {timezone.now():%Y-%m-%d %H:%M}."
        )
        _audit(item, request.user, "RESTORE_DENIED", msg)
        messages.error(request, "You do not have permission to restore items.")
        return redirect("inventory:stock_list")

    if getattr(item, "is_active", True):
        messages.info(request, "Item is already active.")
        return redirect("inventory:stock_list")

    item.is_active = True
    item.save(update_fields=["is_active"])
    _audit(item, request.user, "RESTORE", f"Restored by {request.user.username} at {timezone.now():%Y-%m-%d %H:%M}.")
    messages.success(request, "Item restored.")
    return redirect("inventory:stock_list")


# -----------------------
# Auth placeholders
# -----------------------
@never_cache
def agent_forgot_password(request):
    return HttpResponse("Forgot password page – not implemented yet.")


@never_cache
def agent_reset_confirm(request, token=None):
    return HttpResponse(f"Reset confirm – token received: {token}")


# -----------------------
# Charts & analytics APIs
# -----------------------
@never_cache
@login_required
def api_sales_trend(request):
    period = request.GET.get("period", "month")
    metric = request.GET.get("metric", "amount")  # amount|count

    ver = get_dashboard_cache_version()
    key = f"api:sales_trend:v{ver}:u{request.user.id}:p:{period}:m:{metric}"

    def _build():
        today = timezone.localdate()
        end_excl = today + timedelta(days=1)
        if period == "7d":
            start = today - timedelta(days=6)
        else:
            start = today.replace(day=1)

        if _can_view_all(request.user):
            qs = Sale.objects.all()
        else:
            qs = Sale.objects.filter(agent=request.user)

        qs = qs.filter(sold_at__gte=start, sold_at__lt=end_excl)
        qs = qs.annotate(d=TruncDate("sold_at")).values("d").order_by("d")

        if metric == "count":
            agg = qs.annotate(v=Count("id"))
        else:
            agg = qs.annotate(v=Sum("price"))
        raw = {row["d"]: float(row["v"] or 0) for row in agg}

        labels, values = [], []
        cur = start
        while cur < end_excl:
            labels.append(cur.strftime("%b %d"))
            values.append(raw.get(cur, 0.0))
            cur += timedelta(days=1)
        return {"labels": labels, "values": values}

    data = cache.get(key)
    if data is None:
        data = _build()
        cache.set(key, data, 60)
    return JsonResponse(data)


@never_cache
@login_required
def api_top_models(request):
    period = request.GET.get("period", "today")
    ver = get_dashboard_cache_version()
    key = f"api:top_models:v{ver}:u{request.user.id}:p:{period}"

    def _build():
        today = timezone.localdate()
        end_excl = today + timedelta(days=1)
        start = today if period == "today" else today.replace(day=1)

        if _can_view_all(request.user):
            qs = Sale.objects.select_related("item__product")
        else:
            qs = Sale.objects.select_related("item__product").filter(agent=request.user)

        qs = (
            qs.filter(sold_at__gte=start, sold_at__lt=end_excl)
            .values("item__product__brand", "item__product__model")
            .annotate(c=Count("id"))
            .order_by("-c")[:8]
        )

        labels = [f'{r["item__product__brand"]} {r["item__product__model"]}' for r in qs]
        values = [r["c"] for r in qs]
        return {"labels": labels, "values": values}

    data = cache.get(key)
    if data is None:
        data = _build()
        cache.set(key, data, 60)
    return JsonResponse(data)


@never_cache
@login_required
def api_profit_bar(request):
    month_str = request.GET.get("month")
    group_by = request.GET.get("group_by")  # 'model' or None
    ver = get_dashboard_cache_version()
    key = f"api:profit_bar:v{ver}:u{request.user.id}:m:{month_str or 'curr'}:g:{group_by or 'none'}"

    def _build():
        today = timezone.localdate()
        if month_str:
            dt = datetime.strptime(month_str, "%Y-%m")
            start = dt.replace(day=1)
        else:
            start = today.replace(day=1)

        if month_str and (start.year != today.year or start.month != today.month):
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        else:
            end = today
        end_excl = end + timedelta(days=1)

        base = Sale.objects.select_related("item__product")
        if not _can_view_all(request.user):
            base = base.filter(agent=request.user)

        base = base.filter(sold_at__gte=start, sold_at__lt=end_excl)

        profit_expr = ExpressionWrapper(
            Coalesce(F("price"), Value(0)) - Coalesce(F("item__order_price"), Value(0)),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )

        if group_by == "model":
            rows = base.values("item__product__brand", "item__product__model").annotate(v=Sum(profit_expr)).order_by("-v")[:20]
            labels = [f"{r['item__product__brand']} {r['item__product__model']}" for r in rows]
            data = [float(r["v"] or 0) for r in rows]
        else:
            monthly = base.annotate(m=TruncMonth("sold_at")).values("m").annotate(v=Sum(profit_expr)).order_by("m")
            labels = [r["m"].strftime("%b %Y") for r in monthly]
            data = [float(r["v"] or 0) for r in monthly]

        return {"labels": labels, "data": data}

    data = cache.get(key)
    if data is None:
        data = _build()
        cache.set(key, data, 60)
    return JsonResponse(data)


@never_cache
@login_required
def api_agent_trend(request):
    months = int(request.GET.get("months", 6))
    metric = request.GET.get("metric", "sales")
    agent_id = request.GET.get("agent")
    ver = get_dashboard_cache_version()
    key = f"api:agent_trend:v{ver}:u{request.user.id}:mo:{months}:met:{metric}:a:{agent_id or 'all'}"

    def _build():
        base = Sale.objects.select_related("agent", "item")
        if not _can_view_all(request.user):
            base = base.filter(agent=request.user)
        if agent_id:
            base = base.filter(agent_id=agent_id)

        today = timezone.localdate()
        end_excl = today + timedelta(days=1)
        start = today - timedelta(days=months * 31)

        base = base.filter(sold_at__gte=start, sold_at__lt=end_excl)

        if metric == "profit":
            agg = Sum(Coalesce(F("price"), Value(0)) - Coalesce(F("item__order_price"), Value(0)))
        else:
            agg = Count("id")

        rows = base.annotate(m=TruncMonth("sold_at")).values("m").annotate(v=agg).order_by("m")

        labels = [r["m"].strftime("%b %Y") for r in rows]
        data = [float(r["v"] or 0) for r in rows]
        return {"labels": labels, "data": data}

    data = cache.get(key)
    if data is None:
        data = _build()
        cache.set(key, data, 60)
    return JsonResponse(data)


# -----------------------
# AI & Cash APIs (NEW)
# -----------------------
@never_cache
@login_required
@require_GET
def api_predictions(request):
    """
    Baseline forecast used by the dashboard's 'AI Recommendations' card.
    - Predict next 7 days by averaging last 14 days (units & revenue).
    - Flag models likely to stock out: on_hand < 7 * model_daily_avg.
    Obeys permissions.
    """
    today = timezone.localdate()
    lookback_days = 14
    start = today - timedelta(days=lookback_days)
    end_excl = today + timedelta(days=1)

    sales = Sale.objects.select_related("item__product").filter(sold_at__gte=start, sold_at__lt=end_excl)
    items = InventoryItem.objects.select_related("product").filter(status="IN_STOCK")
    if not _can_view_all(request.user):
        sales = sales.filter(agent=request.user)
        items = items.filter(assigned_agent=request.user)

    # Per-day counts (last 14d)
    per_day_counts = (
        sales.annotate(d=TruncDate("sold_at"))
        .values("d")
        .annotate(c=Count("id"))
    )
    total_units_14 = sum(r["c"] for r in per_day_counts) or 0
    daily_units_avg = total_units_14 / float(lookback_days)

    # Per-day revenue (last 14d)
    per_day_rev = (
        sales.annotate(d=TruncDate("sold_at"))
        .values("d")
        .annotate(v=Sum("price"))
    )
    total_rev_14 = float(sum(r["v"] or 0 for r in per_day_rev))
    daily_rev_avg = total_rev_14 / float(lookback_days) if total_rev_14 else 0.0

    overall = [
        {
            "day": (today + timedelta(days=i)).isoformat(),
            "predicted_units": round(daily_units_avg, 2),
            "predicted_revenue": round(daily_rev_avg, 2),
        }
        for i in range(1, 8)
    ]

    # Model-level stockout risk
    by_model_14 = (
        sales.values("item__product_id", "item__product__brand", "item__product__model")
        .annotate(c=Count("id"))
    )
    model_count_map = {r["item__product_id"]: r["c"] for r in by_model_14}

    risky = []
    by_model_stock = (
        items.values("product_id", "product__brand", "product__model")
        .annotate(on_hand=Count("id"))
        .order_by("product__brand", "product__model")
    )
    for r in by_model_stock:
        pid = r["product_id"]
        daily_model_avg = (model_count_map.get(pid, 0) / float(lookback_days)) if pid in model_count_map else 0.0
        need_next_7 = daily_model_avg * 7.0
        on_hand = int(r["on_hand"] or 0)
        if daily_model_avg > 0 and on_hand < need_next_7:
            days_cover = (on_hand / daily_model_avg) if daily_model_avg else 0
            risky.append({
                "product": f'{r["product__brand"]} {r["product__model"]}',
                "on_hand": on_hand,
                "stockout_date": (today + timedelta(days=max(0, int(days_cover)))).isoformat(),
                "suggested_restock": int(round(max(0.0, need_next_7 - on_hand))),
                "urgent": on_hand <= (daily_model_avg * 2.0),
            })

    return JsonResponse({"ok": True, "overall": overall, "risky": risky})


@never_cache
@login_required
@require_GET
def api_cash_overview(request):
    """
    Totals for 'Cash' slide.
    - total_orders (current month)
    - total_revenue (current month)
    - total_paid_out (Wallet Payouts, current month)
    - total_expenses (Advances + Adjustments, current month)
    """
    today = timezone.localdate()
    start = today.replace(day=1)
    end_excl = today + timedelta(days=1)

    if _can_view_all(request.user):
        sales = Sale.objects.filter(sold_at__gte=start, sold_at__lt=end_excl)
        tx = WalletTxn.objects.filter(created_at__date__gte=start, created_at__date__lte=today)
    else:
        sales = Sale.objects.filter(agent=request.user, sold_at__gte=start, sold_at__lt=end_excl)
        tx = WalletTxn.objects.filter(user=request.user, created_at__date__gte=start, created_at__date__lte=today)

    totals = sales.aggregate(
        orders=Count("id"),
        revenue=Coalesce(Sum("price"), Value(0), output_field=DecimalField(max_digits=14, decimal_places=2)),
    )

    paid_out = tx.filter(reason="PAYOUT").aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
    advances = tx.filter(reason="ADVANCE").aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0
    adjustments = tx.filter(reason="ADJUSTMENT").aggregate(s=Coalesce(Sum("amount"), Value(0)))["s"] or 0

    data = {
        "orders": int(totals.get("orders") or 0),
        "revenue": float(totals.get("revenue") or 0),
        "paid_out": float(paid_out or 0),
        "expenses": float((advances or 0) + (adjustments or 0)),
        "period_label": start.strftime("%b %Y"),
    }
    return JsonResponse({"ok": True, **data})


# -----------------------
# Health check (Render)
# -----------------------
@never_cache
@require_http_methods(["GET"])
def healthz(request):
    ok = True
    err = None
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
    except Exception as e:
        ok = False
        err = str(e)
    payload = {"ok": ok, "time": timezone.now().isoformat()}
    if err:
        payload["error"] = err
    return JsonResponse(payload, status=200 if ok else 500)
