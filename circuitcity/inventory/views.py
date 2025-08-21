# inventory/views.py
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.mail import mail_admins
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.cache import cache
from django.db import transaction
from django.db.models import (
    Sum, Q, Exists, OuterRef, Count, F, DecimalField, ExpressionWrapper, Case, When, Value
)
from django.db.models.deletion import ProtectedError
from django.db.models.functions import TruncMonth, TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.exceptions import TemplateDoesNotExist
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.cache import never_cache

import csv
import json
import math
from datetime import timedelta, datetime
from urllib.parse import urlencode

# FORMS — keep only the ones that exist
from .forms import ScanInForm, ScanSoldForm, InventoryItemForm

from .models import (
    InventoryItem,
    Product,
    InventoryAudit,
    AgentPasswordReset,  # ok if unused
    WarrantyCheckLog,
    TimeLog,
    WalletTxn,
    Location,
)
from sales.models import Sale

# ---- Dashboard cache version (signals should bump this).
try:
    from .cache_utils import get_dashboard_cache_version
except Exception:
    def get_dashboard_cache_version() -> int:  # fallback
        return 1

User = get_user_model()

# -------------------------------------------------
# Warranty client: fully disabled (no imports from warranty.py)
# -------------------------------------------------
_WARRANTY_CLIENT_AVAILABLE = False


class CarlcareClient:  # shim kept only so type references don't blow up
    def __init__(self, *args, **kwargs):
        self._shim = True

    def check(self, imei: str):
        return type("WarrantyResult", (), {"status": "SKIPPED", "expires_at": None})()


def _get_warranty_client():
    """Always return None so no warranty lookups are attempted."""
    return None


# -----------------------
# Helpers
# -----------------------
def _user_home_location(user):
    """Preselect the user's home location if they have an AgentProfile."""
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
    """Create an audit row if we have an item."""
    if not item:
        return
    InventoryAudit.objects.create(item=item, by_user=user, action=action, details=details or "")


def _haversine_meters(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371000.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _paginate_qs(request, qs, default_per_page=50, max_per_page=200):
    """Uniform paginator with a hard cap of 200 rows/page. Supports ?page & ?page_size=."""
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


def _cache_get_set(key: str, builder, ttl: int = 60):
    """Small helper for 60s server-side caching."""
    data = cache.get(key)
    if data is None:
        data = builder()
        cache.set(key, data, ttl)
    return data


def _wallet_balance(user):
    """Safe wallet balance even if custom helper is missing."""
    try:
        return WalletTxn.balance_for(user)
    except Exception:
        return WalletTxn.objects.filter(user=user).aggregate(s=Sum("amount"))["s"] or 0


def _wallet_month_sum(user, year: int, month: int):
    """Safe month sum even if custom helper is missing."""
    try:
        return WalletTxn.month_sum_for(user, year, month)
    except Exception:
        return (
            WalletTxn.objects.filter(user=user, created_at__year=year, created_at__month=month).aggregate(s=Sum("amount"))[
                "s"
            ]
            or 0
        )


def _inv_base(show_archived: bool):
    """InventoryItem.active when present; else .objects (and is_active=True when possible)."""
    if show_archived:
        return InventoryItem.objects
    if hasattr(InventoryItem, "active"):
        return InventoryItem.active
    try:
        return InventoryItem.objects.filter(is_active=True)
    except Exception:
        return InventoryItem.objects


def _render_dashboard_safe(request, context, today, mtd_count, all_time_count):
    """Render dashboard with a fallback if the template is missing."""
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
    """
    Invariants:
      - No orphan items: product & location required.
      - Unique IMEI enforced.
      - Warranty lookup is disabled; we always record SKIPPED.
    """
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

        # Warranty is disabled: record SKIPPED (no external calls / imports)
        warranty_status = "SKIPPED"
        warranty_expires_at = None
        warranty_checked_at = None
        activation_at = None

        WarrantyCheckLog.objects.create(
            imei=imei or "",
            result=warranty_status,
            expires_at=warranty_expires_at,
            notes="scan_in (warranty disabled)",
            by_user=request.user,
        )

        allow, reason = True, None
        if not imei and not _is_manager_or_admin(request.user):
            allow = False
            reason = "IMEI is required."

        if not allow:
            mail_admins(
                subject="Stock-in blocked",
                message=f"User {request.user} attempted to stock IMEI {imei} (warranty disabled).",
                fail_silently=True,
            )
            messages.error(request, reason or "Stock-in blocked.")
            return render(request, "inventory/scan_in.html", {"form": form, "warranty": None, "blocked": True})

        item = InventoryItem.objects.create(
            imei=imei or None,
            product=data["product"],
            received_at=data["received_at"],
            order_price=data["order_price"],
            current_location=data["location"],
            assigned_agent=request.user if data.get("assigned_to_me") else None,
            warranty_status=warranty_status,
            warranty_expires_at=warranty_expires_at,
            warranty_last_checked_at=warranty_checked_at,
            activation_detected_at=activation_at,
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
    """
    Invariants:
      - Only IN_STOCK items can be sold (row lock prevents race).
      - No negative/invalid price accepted.
    Writes: InventoryItem(status→SOLD), Sale, InventoryAudit
    """
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

        if item.status == "SOLD":
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
        messages.success(request, f"Marked SOLD: {item.imei}{' at ' + str(item.selling_price) if item.selling_price else ''}")
        return redirect("inventory:scan_sold")

    form = ScanSoldForm(initial=initial)
    return render(request, "inventory/scan_sold.html", {"form": form})


@never_cache
@login_required
@require_http_methods(["GET"])
def scan_web(request):
    """Desktop-friendly scanner page (paste/type IMEI; webcam optional)."""
    return render(request, "inventory/scan_web.html", {})


@never_cache
@login_required
@require_POST
@transaction.atomic
def api_mark_sold(request):
    """
    Accepts JSON or form data.
    Body (JSON): { "imei": "15-digit", "comment": "optional", "price": 123.45, "location_id": 1 }
    Idempotent on already SOLD items.
    """
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
# Inventory dashboard & list
# -----------------------
@login_required
def inventory_dashboard(request):
    """
    Cached (60s) heavy aggregates for the dashboard.
    Cache key includes user + filters so no cross-user leakage.
    """
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

    # Base querysets according to permissions
    if _can_view_all(request.user):
        sales_qs_all = Sale.objects.select_related("item", "agent", "item__product")
        items_qs = InventoryItem.objects.select_related("product", "assigned_agent", "current_location")
    else:
        sales_qs_all = Sale.objects.filter(agent=request.user).select_related("item", "agent", "item__product")
        items_qs = InventoryItem.objects.filter(assigned_agent=request.user).select_related(
            "product", "assigned_agent", "current_location"
        )

    if model_id:
        sales_qs_all = sales_qs_all.filter(item__product_id=model_id)
        items_qs = items_qs.filter(product_id=model_id)

    # Period-filtered sales for widgets that intentionally show "this month"
    sales_qs_period = sales_qs_all
    if period == "month":
        sales_qs_period = sales_qs_all.filter(sold_at__gte=month_start)

    # Header chip counts (corrected):
    today_count = sales_qs_all.filter(sold_at__gte=today, sold_at__lt=tomorrow).count()
    mtd_count = sales_qs_all.filter(sold_at__gte=month_start, sold_at__lt=tomorrow).count()
    all_time_count = sales_qs_all.count()

    # Ranking (use selected period so it matches the dashboard view)
    commission_expr = ExpressionWrapper(
        F("price") * (F("commission_pct") / 100.0),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    agent_rank_qs = (
        sales_qs_period.values("agent_id", "agent__username")
        .annotate(total_sales=Count("id"), earnings=Sum(commission_expr), revenue=Sum("price"))
        .order_by("-earnings", "-total_sales")
    )
    agent_rank = list(agent_rank_qs)

    # ---- Wallet aggregates for admins (lifetime & month breakdown) ----
    agent_wallet_summaries = {}
    agent_ids = [row["agent_id"] for row in agent_rank if row.get("agent_id")]
    if agent_ids:
        w = WalletTxn.objects.filter(user_id__in=agent_ids)
        agent_wallet_rows = w.values("user_id").annotate(
            balance=Sum("amount"),
            lifetime_commission=Sum(
                Case(When(reason="COMMISSION", then="amount"), default=Value(0)),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            lifetime_advance=Sum(
                Case(When(reason="ADVANCE", then="amount"), default=Value(0)),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            lifetime_adjustment=Sum(
                Case(When(reason="ADJUSTMENT", then="amount"), default=Value(0)),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            month_commission=Sum(
                Case(
                    When(reason="COMMISSION", created_at__date__gte=month_start, created_at__date__lte=today, then="amount"),
                    default=Value(0),
                ),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            month_advance=Sum(
                Case(
                    When(reason="ADVANCE", created_at__date__gte=month_start, created_at__date__lte=today, then="amount"),
                    default=Value(0),
                ),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            month_adjustment=Sum(
                Case(
                    When(reason="ADJUSTMENT", created_at__date__gte=month_start, created_at__date__lte=today, then="amount"),
                    default=Value(0),
                ),
                output_field=DecimalField(max_digits=14, decimal_places=2),
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

    # Last 12 months revenue & profit (permission + model respected)
    last_12_start = month_start - timedelta(days=365)
    rev_qs = Sale.objects.select_related("item").filter(sold_at__gte=last_12_start)
    if not _can_view_all(request.user):
        rev_qs = rev_qs.filter(agent=request.user)
    if model_id:
        rev_qs = rev_qs.filter(item__product_id=model_id)

    rev_by_month = rev_qs.annotate(m=TruncMonth("sold_at")).values("m").annotate(total=Sum("price")).order_by("m")

    labels = []
    totals_map = {r["m"].strftime("%Y-%m"): float(r["total"] or 0) for r in rev_by_month if r["m"]}

    for i in range(11, -1, -1):
        y = (month_start.year * 12 + month_start.month - 1 - i) // 12
        m = (month_start.year * 12 + month_start.month - 1 - i) % 12 + 1
        labels.append(f"{y}-{m:02d}")
    revenue_points = [totals_map.get(lbl, 0.0) for lbl in labels]

    profit_expr = ExpressionWrapper(
        F("price") - F("item__order_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    prof_by_month = rev_qs.annotate(m=TruncMonth("sold_at")).values("m").annotate(total=Sum(profit_expr)).order_by("m")
    prof_map = {r["m"].strftime("%Y-%m"): float(r["total"] or 0) for r in prof_by_month if r["m"]}
    profit_points = [prof_map.get(lbl, 0.0) for r in labels for lbl in [r]]

    # Agent stock vs sold (sold respects selected period)
    total_assigned = (
        items_qs.values("assigned_agent_id", "assigned_agent__username").annotate(total_stock=Count("id")).order_by(
            "assigned_agent__username"
        )
    )
    sold_units = sales_qs_period.values("agent_id").annotate(sold=Count("id"))
    sold_map = {r["agent_id"]: r["sold"] for r in sold_units}
    agent_rows = []
    for row in total_assigned:
        agent_rows.append(
            {
                "agent_id": row["assigned_agent_id"],
                "agent": row["assigned_agent__username"] or "—",
                "total_stock": row["total_stock"],
                "sold_units": sold_map.get(row["assigned_agent_id"], 0),
            }
        )

    # Cost/Revenue/Profit pie (respects selected period)
    cost_expr = ExpressionWrapper(F("item__order_price"), output_field=DecimalField(max_digits=14, decimal_places=2))
    totals = sales_qs_period.aggregate(revenue=Sum("price"), cost=Sum(cost_expr), profit=Sum(profit_expr))
    pie_revenue = float(totals.get("revenue") or 0)
    pie_cost = float(totals.get("cost") or 0)
    pie_profit = float(totals.get("profit") or 0)

    # Stock level battery
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

    # Current user's wallet (chip)
    def _sum(qs):
        return qs.aggregate(s=Sum("amount"))["s"] or 0

    my_balance = _wallet_balance(request.user)
    month_qs = WalletTxn.objects.filter(user=request.user, created_at__date__gte=month_start, created_at__date__lte=today)
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
        "agent_rank": agent_rank,
        "agent_wallet_summaries": agent_wallet_summaries,
        "labels_json": json.dumps(labels),
        "revenue_points_json": json.dumps(revenue_points),
        "profit_points_json": json.dumps(profit_points),
        "agent_rows": agent_rows,
        "pie_data_json": json.dumps([pie_cost, pie_revenue, pie_profit]),
        "jug_count": jug_count,
        "jug_fill_pct": jug_fill_pct,
        "jug_color": jug_color,
        "is_manager_or_admin": _is_manager_or_admin(request.user),
        "today_count": today_count,
        "mtd_count": mtd_count,
        "all_time_count": all_time_count,
        "wallet": {
            "balance": my_balance,
            "month": {
                "commission": my_month_commission,
                "advance": my_month_advance,
                "adjustment": my_month_adjustment,
                "total": my_month_total,
                "month_label": month_start.strftime("%b %Y"),
            },
            "lifetime": {
                "commission": my_life_commission,
                "advance": my_life_advance,
                "adjustment": my_life_adjustment,
                "total": my_life_total,
            },
        },
    }
    cache.set(cache_key, context, 60)
    return _render_dashboard_safe(request, context, today, mtd_count, all_time_count)


@never_cache
@login_required
@require_http_methods(["GET"])  # list/export is GET-only
def stock_list(request):
    """
    Stock list with optional search by IMEI/brand/model/variant.
    Managers/Admins/Auditors see all; Agents see only their own assigned items.
    Adds pagination (cap 200/pg) and header metrics. CSV via ?export=csv.
    """
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

    # CSV export (no pagination by design)
    if want_csv:
        filename = f"stock_export_{timezone.now():%Y%m%d_%H%M}.csv"
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response.write("\ufeff")  # BOM for Excel UTF-8
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

    # Header metrics for filtered set
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
    """Export filtered stock as CSV (same filters/permissions as list)."""
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
# JSON endpoints for charts (trend + top models)
# -----------------------
@never_cache
@login_required
def api_sales_trend(request):
    """
    JSON for the line chart — cached for 60s per-user + params.
    Query: ?period=month|7d & metric=amount|count
    Fills missing days with zeroes so the chart scales nicely.
    """
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

        # Aggregate raw
        if metric == "count":
            agg = qs.annotate(v=Count("id"))
        else:
            agg = qs.annotate(v=Sum("price"))
        raw = {row["d"]: float(row["v"] or 0) for row in agg}

        # Build full date range with zero fill
        labels, values = [], []
        cur = start
        while cur < end_excl:
            labels.append(cur.strftime("%b %d"))
            values.append(raw.get(cur, 0.0))
            cur += timedelta(days=1)
        return {"labels": labels, "values": values}

    data = _cache_get_set(key, _build, 60)
    return JsonResponse(data)


@never_cache
@login_required
def api_top_models(request):
    """
    JSON for the pie chart of best sellers — cached 60s per-user + period.
    Query: ?period=today|month
    """
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

    data = _cache_get_set(key, _build, 60)
    return JsonResponse(data)


# -----------------------
# New JSON endpoints for profits + agent trend
# -----------------------
@never_cache
@login_required
def api_profit_bar(request):
    """
    Bar data for profits — cached 60s per-user + params.
    Params:
      - month=YYYY-MM  (optional; default current month)
      - group_by=model (optional; if present, group profits by product model)
    """
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

        profit_expr = F("price") - F("item__order_price")

        if group_by == "model":
            rows = base.values("item__product__brand", "item__product__model").annotate(v=Sum(profit_expr)).order_by("-v")[
                :20
            ]
            labels = [f"{r['item__product__brand']} {r['item__product__model']}" for r in rows]
            data = [float(r["v"] or 0) for r in rows]
        else:
            monthly = base.annotate(m=TruncMonth("sold_at")).values("m").annotate(v=Sum(profit_expr)).order_by("m")
            labels = [r["m"].strftime("%b %Y") for r in monthly]
            data = [float(r["v"] or 0) for r in monthly]

        return {"labels": labels, "data": data}

    data = _cache_get_set(key, _build, 60)
    return JsonResponse(data)


@never_cache
@login_required
def api_agent_trend(request):
    """
    Agent performance trend — cached 60s per-user + params.
    Params:
      - months=6 (default)
      - metric=sales|profit (default sales)
      - agent=<id> (optional)
    """
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
            agg = Sum(F("price") - F("item__order_price"))
        else:
            agg = Count("id")

        rows = base.annotate(m=TruncMonth("sold_at")).values("m").annotate(v=agg).order_by("m")

        labels = [r["m"].strftime("%b %Y") for r in rows]
        data = [float(r["v"] or 0) for r in rows]
        return {"labels": labels, "data": data}

    data = _cache_get_set(key, _build, 60)
    return JsonResponse(data)


# -----------------------
# Time logging (page + API) & Wallet APIs
# -----------------------
@never_cache
@login_required
@require_http_methods(["GET"])
def time_checkin_page(request):
    """Simple page for agents to perform a GPS check-in/out."""
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
    """
    Body (JSON or form):
      {
        "checkin_type" | "type": "ARRIVAL" | "DEPARTURE",
        "latitude" | "lat": -13.9621,
        "longitude" | "lon": 33.7745,
        "accuracy_m" | "accuracy": 25,
        "location_id": 3,
        "note": "optional"
      }
    Computes distance to store (if store has lat/lon) and flags within_geofence.
    """
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
        dist = int(round(_haversine_meters(lat, lon, float(loc.latitude), float(loc.longitude))))
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
    """
    Simple page to view recent time logs.
    Managers/Admins see all, others see their own.
    """
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
    """
    Returns wallet balance (and optional month sum).
    Params:
      - user_id (admins/managers only; default self)
      - year, month (optional; if provided, also returns month_sum)
    """
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


api_wallet_balance = api_wallet_summary  # back-compat alias


@never_cache
@login_required
@require_POST
def api_wallet_add_txn(request):
    """
    Admin-only: create a wallet transaction for an agent.
    Body (JSON or form):
      {
        "user_id": 12,
        "amount": 5000.00,
        "reason": "ADVANCE"|"PAYOUT"|...,
        "memo": "optional note"
      }
    Returns new balance.
    """
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
    allowed = {k for k, _ in getattr(WalletTxn, "REASON_CHOICES", [])} or {
        "ADJUSTMENT",
        "ADVANCE",
        "COMMISSION",
        "PAYOUT",
    }
    if reason not in allowed:
        return JsonResponse({"ok": False, "error": f"Invalid reason. Allowed: {sorted(list(allowed))}"}, status=400)

    memo = (payload.get("memo") or "").strip()[:200]

    txn = WalletTxn.objects.create(user=target, amount=amount, reason=reason, memo=memo)

    new_balance = _wallet_balance(target)
    return JsonResponse({"ok": True, "txn_id": txn.id, "balance": new_balance})


api_wallet_txn = api_wallet_add_txn  # alias


@never_cache
@login_required
@require_http_methods(["GET"])
def wallet_page(request):
    """
    Wallet page:
      - Agents see their own balance & recent transactions.
      - Admins/Managers can pick any user via ?user_id= and add transactions via API.
    """
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
# Stock management (Edit / Delete / Restore)
# -----------------------
@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def update_stock(request, pk):
    """
    Edit an inventory item.
    Admins/Managers can edit; Agents/Auditors cannot.
    Admin-only rule for price changes. When an admin changes price(s), the same
    field is bulk-updated for ALL active items with the same Product.
    """
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

            # Guard: only admins can change prices
            price_fields = {"order_price", "selling_price"}
            if (price_fields & set(changed_fields)) and not _is_admin(request.user):
                messages.error(request, "Only admins can edit order/selling prices.")
                return render(request, "inventory/edit_stock.html", {"form": form, "item": item})

            old_vals = {name: getattr(item, name) for name in changed_fields}
            saved_item = form.save()

            # Bulk propagate price changes to same product (active items only)
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
    """
    Only admins can delete. If the item has related sales and the FK is PROTECT,
    archive (soft-delete) instead of crashing; always audit the attempt.
    """
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
    """Admin-only: restore a previously archived (soft-deleted) item."""
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
# Auth: Forgot / Reset (placeholders)
# -----------------------
@never_cache
def agent_forgot_password(request):
    return HttpResponse("Forgot password page – not implemented yet.")


@never_cache
def agent_reset_confirm(request, token=None):
    return HttpResponse(f"Reset confirm – token received: {token}")


# -----------------------
# Health check (for Render)
# -----------------------
@never_cache
@require_http_methods(["GET"])
def healthz(request):
    """Simple DB-backed health check."""
    from django.db import connection

    db_ok, err = True, None
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
    except Exception as e:
        db_ok, err = False, str(e)

    payload = {"ok": db_ok, "time": timezone.now().isoformat()}
    if err:
        payload["error"] = err
    return JsonResponse(payload, status=200 if db_ok else 500)
