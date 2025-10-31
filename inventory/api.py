# inventory/api.py
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional, Tuple

from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.db import models as djmodels
from django.db.models import (
    Count, Sum, F, Value, DecimalField, ExpressionWrapper, Q,
)
from django.db.models.functions import TruncDate, Coalesce, Cast, Trim, Concat, NullIf
from django.http import JsonResponse, HttpRequest
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# Optional: if tenants.utils is present, we can require an active business for some endpoints
try:
    from tenants.utils import require_business, get_active_business  # type: ignore
except Exception:  # pragma: no cover
    def require_business(fn):  # type: ignore
        return fn
    def get_active_business(request):  # type: ignore
        return getattr(request, "business", None)

from .models import InventoryItem, Product, OrderPrice
from sales.models import Sale

# Optional Location import (works even if Location lives elsewhere or is absent)
try:
    from .models import Location as _LocationModel  # inventory.Location (common)
except Exception:  # pragma: no cover
    _LocationModel = None  # type: ignore

# Canonical stock predicates
try:
    from .constants import IN_STOCK_Q  # our single source of truth for "in stock"
except Exception:  # pragma: no cover
    # Very-safe fallback if constants.py isn't present
    def IN_STOCK_Q():
        return ~(
            Q(status__iexact="SOLD")
            | Q(sold_at__isnull=False)
            | Q(is_sold=True)
            | Q(in_stock=False)
        )

# Canonical updater
try:
    from .utils_status import mark_item_sold as _canonical_mark_item_sold
except Exception:  # pragma: no cover
    _canonical_mark_item_sold = None  # type: ignore

log = logging.getLogger(__name__)

# ---------- Celery (async) ----------
try:
    from celery.result import AsyncResult
except Exception:  # pragma: no cover
    AsyncResult = None  # type: ignore

# Optional tasks (we'll resolve by name at submit-time)
_TASK_MODULES = (
    "inventory.tasks",
    "insights.tasks",
    "dashboard.tasks",
    "wallet.tasks",
    "sales.tasks",
    "cc.celery",  # fallback provides 'ping'
)

def _resolve_task_callable(task_name: str) -> Optional[Callable[..., Any]]:
    """
    Resolve a dotted or short task name to a callable that supports .delay().
    - If `task_name` contains a dot, attempt import directly.
    - Otherwise scan common task modules and return the attribute if found.
    """
    if not task_name:
        return None
    task_name = task_name.strip()

    # Dotted path?
    if "." in task_name:
        mod_name, attr = task_name.rsplit(".", 1)
        try:
            mod = __import__(mod_name, fromlist=[attr])
            candidate = getattr(mod, attr, None)
            return candidate
        except Exception:
            pass

    # Short name: scan known modules
    for mod_name in _TASK_MODULES:
        try:
            mod = __import__(mod_name, fromlist=[task_name])
            candidate = getattr(mod, task_name, None)
            if candidate is not None:
                return candidate
        except Exception:
            continue

    return None


# ---------- helpers ----------

def _ok(data: dict, status: int = 200) -> JsonResponse:
    payload = {"ok": True}
    payload.update(data)
    return JsonResponse(payload, status=status)

def _err(msg: str, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": msg}
    if extra:
        payload.update(extra)
    return JsonResponse(payload, status=status)

def _can_view_all(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False):
        return True
    # Manager / Admin groups
    return user.groups.filter(name__in=["Admin", "Manager", "Auditor", "Auditors"]).exists()

def _scope_mode(request: HttpRequest) -> str:
    """
    Default to per-agent scope (self) unless the caller explicitly asks for ?scope=all.
    """
    val = (request.GET.get("scope") or "").strip().lower()
    return "all" if val in {"all", "global"} else "self"

def _has_field(model, name: str) -> bool:
    return any(getattr(f, "name", None) == name for f in model._meta.get_fields())

# -- Dynamic field discovery for Sales/Inventory --

def _sale_date_field() -> str:
    for c in ("sold_at", "created_at", "created", "timestamp", "date"):
        if _has_field(Sale, c):
            return c
    return "created_at"

def _sale_amount_field() -> str | None:
    for c in ("price", "amount", "total_amount", "sale_price", "total", "grand_total"):
        if _has_field(Sale, c):
            return c
    return None

def _sale_cost_field() -> str | None:
    for c in ("cost", "total_cost", "cost_amount"):
        if _has_field(Sale, c):
            return c
    return None

def _item_imei_field() -> str:
    for c in ("imei", "serial", "barcode", "code"):
        if _has_field(InventoryItem, c):
            return c
    return "imei"

def _item_status_field() -> str:
    return "status" if _has_field(InventoryItem, "status") else "state"

def _best_item_date_field() -> str:
    for c in ("sold_at", "sold_on", "checked_out_at", "dispatched_at", "updated_at", "created_at", "created"):
        if _has_field(InventoryItem, c):
            return c
    return "created_at"

def _best_item_price_field() -> str | None:
    for c in ("selling_price", "price", "sale_price", "amount", "total_amount", "sell_price", "order_price"):
        if _has_field(InventoryItem, c):
            return c
    return None

# --------- Ownership logic ----------

_OWNER_FIELD_CANDIDATES = [
    # very common
    "assigned_agent", "assigned_to", "assignee", "owner",
    "user", "agent", "created_by", "added_by", "received_by",
    "handled_by", "custodian", "stocked_by", "checked_in_by",
    "sold_by", "creator", "createdby",
]

def _agent_owner_q(model, user) -> Q:
    """
    Build an OR'd Q() across many possible agent/owner fields for InventoryItem or Sale.
    Works with FK fields (*_id), user relation, or username text fields.
    """
    q = Q(pk__in=[])  # start false
    for name in _OWNER_FIELD_CANDIDATES:
        if not _has_field(model, name):
            continue
        # FK relation or user field
        q |= Q(**{name: user})
        q |= Q(**{f"{name}_id": getattr(user, "id", None)})
        # username/text fallback
        q |= Q(**{f"{name}__username": getattr(user, "username", None)})
    return q

def _apply_self_scope_or_none(qs, model, user):
    """
    If caller is agent-level, restrict to self-ownership.
    If no recognizable ownership field exists, return qs.none()
    to avoid leaking global data.
    """
    q = _agent_owner_q(model, user)
    if q.children:
        return qs.filter(q)
    # No ownership columns we recognize -> show nothing for agents
    return qs.none()

def _scoped_sales_qs(request: HttpRequest):
    qs = Sale.objects.all()
    try:
        qs = qs.select_related("item__product")
    except Exception:
        pass

    # Only managers/admins can see global; agents default to self
    if _scope_mode(request) == "all":
        if _can_view_all(request.user):
            return qs
    return _apply_self_scope_or_none(qs, Sale, request.user)

def _scoped_stock_qs(request: HttpRequest):
    qs = InventoryItem.objects.all()
    try:
        qs = qs.select_related("product")
    except Exception:
        pass

    if _scope_mode(request) == "all":
        if _can_view_all(request.user):
            return qs
    return _apply_self_scope_or_none(qs, InventoryItem, request.user)

# ---------- tenant/business helpers (for default location) ----------
def _get_active_business(request):
    """
    Use tenants.utils.get_active_business if available; fallback to request.business.
    """
    try:
        return get_active_business(request)
    except Exception:
        return getattr(request, "business", None)

def _locations_for_active_business(request) -> list[dict[str, Any]]:
    """
    Return [{'id': ..., 'name': ...}, ...] for locations in the active business.
    Safe if Location model doesn't exist.
    """
    if _LocationModel is None:
        return []
    try:
        qs = _LocationModel.objects.all()
        biz = _get_active_business(request)
        for fld in ("business", "tenant", "organization"):
            if _has_field(_LocationModel, fld) and biz is not None:
                qs = qs.filter(**{fld: biz})
                break
        # order by name if present
        order_by = "name" if _has_field(_LocationModel, "name") else "id"
        qs = qs.order_by(order_by)
        return [{"id": getattr(l, "id", None), "name": getattr(l, "name", str(l))} for l in qs[:200]]
    except Exception:
        return []

def _agent_home_location_id(request) -> Optional[int]:
    try:
        prof = getattr(request.user, "agent_profile", None)
        if prof and getattr(prof, "location_id", None):
            return int(prof.location_id)
    except Exception:
        pass
    return None

def _pick_default_location(request) -> tuple[Optional[int], Optional[str]]:
    """
    Priority:
      1) agent_profile.location (if in business list)
      2) location with name == active business name
      3) first available
    """
    locs = _locations_for_active_business(request)
    if not locs:
        return None, None

    # 1) agent home
    pref = _agent_home_location_id(request)
    if pref:
        for it in locs:
            if it["id"] == pref:
                return it["id"], it["name"]

    # 2) business name match
    biz = _get_active_business(request)
    biz_name = getattr(biz, "name", None)
    if biz_name:
        bn = str(biz_name).strip().lower()
        for it in locs:
            if str(it["name"]).strip().lower() == bn:
                return it["id"], it["name"]

    # 3) first
    first = locs[0]
    return first.get("id"), first.get("name")


# ---------- local normalization + lookup used by api_mark_sold ----------

def _normalize_code(raw: str | None) -> str:
    if not raw:
        return ""
    return "".join(ch for ch in str(raw).strip() if ch.isdigit())

def _find_instock_for_business(request: HttpRequest, raw: str) -> Optional[InventoryItem]:
    """
    Business-scoped, unsold-only lookup by IMEI (15) or code.
    This mirrors the helper used by the UI so all flows agree.
    """
    biz = _get_active_business(request)
    if biz is None:
        # fall back to user-scope (already applied by _scoped_stock_qs)
        base = _scoped_stock_qs(request)
    else:
        # tenant scope by business field if present; otherwise rely on _scoped_stock_qs
        try:
            if _has_field(InventoryItem, "business"):
                base = InventoryItem.objects.filter(business=biz)
            else:
                base = _scoped_stock_qs(request)
        except Exception:
            base = _scoped_stock_qs(request)

    base = base.filter(IN_STOCK_Q())

    digits = _normalize_code(raw)
    if not digits:
        return None

    fields = {f.name for f in InventoryItem._meta.get_fields()}

    # Prefer IMEI = last 15 digits (common scanner behavior)
    if "imei" in fields and len(digits) >= 15:
        item = base.filter(imei=digits[-15:]).order_by("-id").first()
        if item:
            return item

    # Fallback to exact code
    if "code" in fields:
        item = base.filter(code=digits).order_by("-id").first()
        if item:
            return item

    # Final fallback: try IMEI even when <15 if that's how data was stored
    if "imei" in fields:
        return base.filter(imei=digits).order_by("-id").first()

    return None


# ---------- utilities ----------

def date_range_filter(qs, field_name: str, start, end_excl):
    field = qs.model._meta.get_field(field_name)
    if isinstance(field, djmodels.DateTimeField):
        return qs.filter(**{f"{field_name}__date__gte": start, f"{field_name}__date__lt": end_excl})
    return qs.filter(**{f"{field_name}__gte": start, f"{field_name}__lt": end_excl})

def _amount_sum_expression(afield: str | None):
    """
    Cross-DB safe sum for amount-like columns.
    On SQLite, prefer FloatField inside SUM to avoid Decimal UDF errors.
    """
    if not afield:
        # Provide a typed zero that matches DB vendor characteristics
        if connection.vendor == "sqlite":
            return Value(0.0, output_field=djmodels.FloatField())
        return Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))

    if connection.vendor == "sqlite":
        return Coalesce(Sum(Cast(F(afield), djmodels.FloatField())), Value(0.0, output_field=djmodels.FloatField()))
    else:
        dec = DecimalField(max_digits=14, decimal_places=2)
        return Coalesce(Sum(Cast(F(afield), dec)), Value(0, output_field=dec))

def _json_body(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}

def _norm_digits(s: str | None) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


# ---------- Currency helpers ----------

try:
    from insights.models import CurrencySetting  # optional singleton
except Exception:  # pragma: no cover
    CurrencySetting = None  # type: ignore

_CURRENCY_SIGNS = {
    "MWK": "MK","USD": "$","EUR": "€","GBP": "£","ZAR": "R",
    "ZMW": "K","TZS": "TSh","KES": "KSh","NGN": "₦",
}

def _normalize_ccy(code: str | None) -> str:
    if not code:
        return "MWK"
    code = code.strip().upper()
    return "MWK" if code in ("MKW", "MWK") else code

def _get_currency_setting():
    base = "MWK"; display = "MWK"; rates = {}
    if CurrencySetting:
        try:
            obj = CurrencySetting.get()
            base = _normalize_ccy(getattr(obj, "base_currency", "MWK"))
            display = _normalize_ccy(getattr(obj, "display_currency", base))
            rates = getattr(obj, "rates", {}) or {}
        except Exception:
            pass
    return base, display, rates

def _convert_amount(amount: Decimal | float | int, base: str, display: str, rates: dict) -> float:
    if base == display:
        return float(amount or 0)
    try:
        r = float(rates.get(display) or 0)
        if r > 0:
            return float(amount or 0) * r
    except Exception:
        pass
    return float(amount or 0)

def _currency_payload():
    base, display, rates = _get_currency_setting()
    sign = _CURRENCY_SIGNS.get(display, display)
    return {"base": base, "display": display, "sign": sign}


# ---------- date utils ----------


# ---------- Product helpers used by place-order ----------

@never_cache
@login_required
def api_order_price(request: HttpRequest, product_id: int):
    """
    GET /inventory/api/order-price/<product_id>/
    Returns the active default *order* price for the product.
    Falls back to Product.sale_price or cost_price if no OrderPrice row exists.
    """
    # Find product
    try:
        product = Product.objects.get(pk=int(product_id))
    except (Product.DoesNotExist, ValueError):
        return _err("Product not found", status=404)

    # Get active price from catalog, then fallback
    price = OrderPrice.get_active_price(product.id)
    if price is None:
        # prefer sale_price if set, otherwise cost_price, otherwise 0
        if getattr(product, "sale_price", None) not in (None, ""):
            price = product.sale_price
        elif getattr(product, "cost_price", None) not in (None, ""):
            price = product.cost_price
        else:
            price = Decimal("0")

    # Normalize to float for JSON
    try:
        price_f = float(price)
    except Exception:
        price_f = 0.0

    payload = {
        "product_id": product.id,
        "product": str(product),
        "price": round(price_f, 2),
        "currency": _currency_payload(),
    }
    return _ok(payload)


@never_cache
@login_required
def api_stock_models(request: HttpRequest):
    """
    GET /inventory/api/stock-models/?q=<search>
    Lightweight product picker for place-order UI.
    Returns up to 50 products as [{id, label}].
    """
    q = (request.GET.get("q") or "").strip()
    qs = Product.objects.all().order_by("brand", "model")[:50]

    if q:
        # very forgiving search across brand/model/variant/name/code
        filt = (
            Q(brand__icontains=q) |
            Q(model__icontains=q) |
            Q(variant__icontains=q) |
            Q(name__icontains=q) |
            Q(code__icontains=q)
        )
        qs = Product.objects.filter(filt).order_by("brand", "model")[:50]

    items = []
    for p in qs:
        label_bits = [p.brand, p.model, p.variant]
        label = " ".join(b for b in label_bits if b).strip() or (p.name or f"Product {p.id}")
        items.append({"id": p.id, "label": label})

    return _ok({"items": items})

def _parse_date_loose(s: str | None) -> Optional[date]:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None

def _extract_range(request: HttpRequest, *, default_period: str = "month") -> Tuple[date, date, dict]:
    """
    Determine [start, end_inclusive] from GET:
      - on=<YYYY-MM-DD> or date=<YYYY-MM-DD>   (single day)
      - start/end (or from/to, df/dt, date_from/date_to, start_date/end_date)
      - period=today|7d|month|all  (fallback)
    Returns (start, end_inclusive, meta_range_dict)
    """
    today = timezone.localdate()

    # 1) single day (support both ?on= and ?date=)
    on = _parse_date_loose(
        (request.GET.get("on") or request.GET.get("date") or request.GET.get("day"))
    )
    if on:
        return on, on, {"start": on.isoformat(), "end": on.isoformat()}

    # 2) many alias pairs for convenience
    aliases_start = ["start", "from", "df", "date_from", "start_date"]
    aliases_end   = ["end", "to", "dt", "date_to", "end_date"]
    start = None
    end_incl = None
    for key in aliases_start:
        start = _parse_date_loose(request.GET.get(key))
        if start:
            break
    for key in aliases_end:
        end_incl = _parse_date_loose(request.GET.get(key))
        if end_incl:
            break

    if start and not end_incl:
        end_incl = start
    if start and end_incl:
        if end_incl < start:
            start, end_incl = end_incl, start
        return start, end_incl, {"start": start.isoformat(), "end": end_incl.isoformat()}

    # 3) fall back to period
    period = (request.GET.get("period") or default_period).lower()
    if period in ("today", "day", "date"):
        start = end_incl = today
    elif period in ("7d", "last7", "last_7", "week"):
        start = today - timedelta(days=6)
        end_incl = today
    elif period in ("all", "alltime"):
        start = date(2000, 1, 1)
        end_incl = today
    else:  # month (default)
        start = today.replace(day=1)
        end_incl = today

    return start, end_incl, {"start": start.isoformat(), "end": end_incl.isoformat()}


# ---------- SOLD-like logic & day filler ----------

_SOLD_LIKE = (
    "SOLD","Sold","sold",
    "DISPATCHED","Dispatched","dispatched",
    "CHECKED_OUT","CHECKED-OUT","Checked_out","checked_out","checked-out",
    "OUT","Out","out",
    "DELIVERED","Delivered","delivered",
    "ISSUED","Issued","issued",
    "PAID","Paid","paid",
)
_IN_STOCK_LIKE = ("IN_STOCK","IN STOCK","AVAILABLE","Available","available","NEW","New","new")

def _fill_days(
    start: date,
    end_excl: date,
    data_map: dict[date, float],
    *,
    fmt: str | Callable[[date], str] = "iso",
) -> tuple[list[str], list[float]]:
    """
    Build parallel lists of labels and values for each day in [start, end_excl).
    fmt:
      - "iso"    -> YYYY-MM-DD
      - "pretty" -> Mon DD (e.g., 'Sep 10')
      - callable -> function(date)->str
    """
    labels, values = [], []
    day = start

    if fmt == "pretty":
        render = lambda d: d.strftime("%b %d")
    elif callable(fmt):
        render = fmt
    else:
        render = lambda d: d.strftime("%Y-%m-%d")

    while day < end_excl:
        labels.append(render(day))
        values.append(float(data_map.get(day, 0.0)))
        day += timedelta(days=1)
    return labels, values


# ---------- Fallback from InventoryItem when Sales empty ----------

def _fallback_items_daily(
    request: HttpRequest,
    start,
    end_excl,
    metric: str,
    model_id: str | None,
    *,
    label_fmt: str | Callable[[date], str] = "iso",
):
    status_field = _item_status_field()
    date_field   = _best_item_date_field()
    price_field  = _best_item_price_field()

    qs = _scoped_stock_qs(request)

    if _has_field(InventoryItem, status_field):
        cond = Q(**{f"{status_field}__in": _SOLD_LIKE}) \
             | Q(**{f"{status_field}__istartswith": "sold"}) \
             | Q(**{f"{status_field}__istartswith": "dispatch"}) \
             | Q(**{f"{status_field}__istartswith": "check"}) \
             | Q(**{f"{status_field}__iexact": "out"}) \
             | Q(**{f"{status_field}__istartswith": "deliver"}) \
             | Q(**{f"{status_field}__istartswith": "issue"})
        cond |= ~Q(**{f"{status_field}__in": _IN_STOCK_LIKE})
        qs = qs.filter(cond)

    if _has_field(InventoryItem, date_field):
        qs = date_range_filter(qs, date_field, start, end_excl)
    else:
        return [], []

    if model_id:
        try:
            qs = qs.filter(product_id=int(model_id))
        except Exception:
            pass

    if metric == "amount" and price_field and _has_field(InventoryItem, price_field):
        val_expr = _amount_sum_expression(price_field)
    else:
        val_expr = Count("id")

    agg = (
        qs.annotate(d=TruncDate(date_field))
          .values("d").annotate(val=val_expr).order_by("d")
    )

    base, display, rates = _get_currency_setting()
    data_map: dict[date, float] = {}
    for r in agg:
        raw = float(r["val"] or 0)
        if metric == "amount":
            raw = _convert_amount(raw, base, display, rates)
            raw = round(float(raw), 2)
        data_map[r["d"]] = raw

    return _fill_days(start, end_excl, data_map, fmt=label_fmt)


# ---------- /inventory/list/ ----------
@never_cache
@login_required
def inventory_list(request: HttpRequest):
    """
    Returns inventory for the active business (scoped). Superusers can pass ?all=1 to bypass scope.
    """
    use_all = request.GET.get("all") == "1" and getattr(request.user, "is_superuser", False)

    qs = _scoped_stock_qs(request)
    if use_all and _can_view_all(request.user):
        qs = InventoryItem.objects.select_related("product")

    data = [{
        "id": i.id,
        "imei": i.imei,
        "product": str(i.product),
        "status": getattr(i, _item_status_field(), None),
        "location": getattr(getattr(i, "current_location", None), "name", None),
        "received_at": i.received_at.isoformat() if getattr(i, "received_at", None) else None,
        "selling_price": float(i.selling_price) if getattr(i, "selling_price", None) is not None else None,
    } for i in qs.order_by("-id")[:500]]

    return _ok({"data": data})


# ---------- API: AI predictions (last 14d) ----------

@never_cache
@login_required
def predictions_summary(request: HttpRequest):
    """
    Returns simple next-7-day projections and risky stock.
    Always uses Python aggregation (safe on SQLite).
    """
    today = timezone.localdate()
    lookback_days = 14
    start = today - timedelta(days=lookback_days)
    end_excl = today + timedelta(days=1)

    dfield = _sale_date_field()
    afield = _sale_amount_field()

    sales_qs = date_range_filter(_scoped_sales_qs(request), dfield, start, end_excl)
    items_qs = _scoped_stock_qs(request)

    # -------- Python accumulation --------
    total_units_14 = 0
    total_rev_14_dec = Decimal("0")

    def _dec(x):
        if x in (None, ""):
            return Decimal(0)
        try:
            return Decimal(str(x).replace(",", "").strip())
        except Exception:
            return Decimal(0)

    for s in sales_qs.iterator():
        total_units_14 += 1
        if afield:
            total_rev_14_dec += _dec(getattr(s, afield, 0))

    daily_units_avg = (total_units_14 / float(lookback_days)) if lookback_days else 0.0
    daily_rev_avg = float(total_rev_14_dec) / float(lookback_days) if lookback_days else 0.0

    base, display, rates = _get_currency_setting()
    daily_rev_avg_display = _convert_amount(daily_rev_avg, base, display, rates)

    overall = [{
        "date": (today + timedelta(days=i)).isoformat(),
        "predicted_units": round(daily_units_avg, 2),
        "predicted_revenue": round(daily_rev_avg_display, 2),
    } for i in range(1, 8)]

    # 14-day per-model run-rate (Python)
    model_count: dict[int, int] = {}
    for s in sales_qs.values("item__product_id"):
        pid = s.get("item__product_id")
        if pid is not None:
            model_count[pid] = model_count.get(pid, 0) + 1

    risky = []
    # Build a per-product on-hand count via Python (safe across DBs)
    products = list(items_qs.values("product_id", "product__brand", "product__model"))
    # group counts
    onhand_map: dict[int, int] = {}
    for p in products:
        pid = p["product_id"]
        onhand_map[pid] = onhand_map.get(pid, 0) + 1

    seen: set[int] = set()
    for p in products:
        pid = p["product_id"]
        if pid in seen:
            continue
        seen.add(pid)
        name = f'{p["product__brand"]} {p["product__model"]}'
        on_hand = int(onhand_map.get(pid, 0))

        daily_model_avg = (model_count.get(pid, 0) / float(lookback_days)) if lookback_days else 0.0
        need_next_7 = daily_model_avg * 7.0

        if on_hand <= 2:
            risky.append({
                "product": name,
                "on_hand": on_hand,
                "stockout_date": today.isoformat(),
                "suggested_restock": max(1, 5 - on_hand),
                "urgent": True,
                "reason": "critical_low_stock",
            })
        elif daily_model_avg > 0 and on_hand < need_next_7:
            days_cover = (on_hand / daily_model_avg) if daily_model_avg else 0
            risky.append({
                "product": name,
                "on_hand": on_hand,
                "stockout_date": (today + timedelta(days=max(0, int(days_cover)))).isoformat(),
                "suggested_restock": int(round(max(0.0, need_next_7 - on_hand))),
                "urgent": on_hand <= (daily_model_avg * 2.0),
                "reason": "runrate_shortfall",
            })

    return _ok({"overall": overall, "risky": risky, "currency": _currency_payload()})


# ---------------------------------------------
# SAFE: api_value_trend (SQLite-safe with Python fallback)
# ---------------------------------------------
@never_cache
@login_required
def api_value_trend(request: HttpRequest):
    """
    /inventory/api/value_trend/?metric=revenue|cost|profit&period=today|7d|all&model=<product_id?>
    Also supports:
      - on=YYYY-MM-DD  (alias: date=YYYY-MM-DD)
      - start/end (or from/to, df/dt, date_from/date_to)
      - labels=iso|pretty
    """
    metric = (request.GET.get("metric") or "revenue").lower()
    model_id = (request.GET.get("model") or "").strip() or None
    labels_fmt = (request.GET.get("labels") or "iso").lower()

    start_incl, end_incl, range_meta = _extract_range(request, default_period="7d")
    end_excl = end_incl + timedelta(days=1)

    dfield = _sale_date_field()
    afield = _sale_amount_field()
    cfield = _sale_cost_field()

    qs = date_range_filter(_scoped_sales_qs(request), dfield, start_incl, end_excl)
    if model_id:
        try:
            qs = qs.filter(item__product_id=int(model_id))
        except Exception:
            pass

    # Always prefer Python aggregation on SQLite (safe) — and keep it simple.
    is_sqlite = (connection.vendor == "sqlite")

    if not is_sqlite:
        # Non-SQLite: try DB aggregation first, fall back to Python if anything goes wrong.
        try:
            dec = DecimalField(max_digits=14, decimal_places=2)

            def _sum_expr(col):
                if not col:
                    return Value(0, output_field=dec)
                return Coalesce(Sum(Cast(F(col), dec)), Value(0, output_field=dec))

            if metric == "revenue":
                expr = _sum_expr(afield)
            elif metric == "cost":
                expr = _sum_expr(cfield)
            else:
                rev = _sum_expr(afield)
                cost = _sum_expr(cfield)
                expr = ExpressionWrapper(
                    Coalesce(rev, Value(0, output_field=dec)) - Coalesce(cost, Value(0, output_field=dec)),
                    output_field=dec,
                )

            agg = (qs.annotate(d=TruncDate(dfield)).values("d").annotate(val=expr).order_by("d"))

            base, display, rates = _get_currency_setting()
            data_map: dict[date, float] = {}
            for r in agg:
                raw = r.get("val") or 0
                try:
                    v = float(raw)
                except Exception:
                    try:
                        v = float(Decimal(str(raw)))
                    except Exception:
                        v = 0.0
                data_map[r["d"]] = round(_convert_amount(v, base, display, rates), 2)

            labels, values = _fill_days(start_incl, end_excl, data_map, fmt=labels_fmt)

            if metric == "revenue" and sum(values) == 0:
                flabels, fvalues = _fallback_items_daily(
                    request, start_incl, end_excl, "amount", model_id, label_fmt=labels_fmt
                )
                if flabels:
                    labels, values = flabels, fvalues

            return _ok({"labels": labels, "values": values, "range": range_meta, "currency": _currency_payload()})
        except Exception as e:
            log.warning("api_value_trend (DB agg) failed: %s. Falling back to Python.", e)

    # Python accumulation (SQLite-safe and general fallback)
    def _dec(x):
        if x in (None, ""):
            return Decimal(0)
        try:
            return Decimal(str(x).replace(",", "").strip())
        except Exception:
            return Decimal(0)

    per_day: dict[date, Decimal] = {}
    for sale in qs.iterator():
        dval = getattr(sale, dfield, None)
        try:
            dkey = dval.date() if hasattr(dval, "date") else dval
        except Exception:
            dkey = dval

        if metric == "revenue":
            amt = _dec(getattr(sale, afield, 0) if afield else 0)
        elif metric == "cost":
            amt = _dec(getattr(sale, cfield, 0) if cfield else 0)
        else:
            rev_d = _dec(getattr(sale, afield, 0) if afield else 0)
            cost_d = _dec(getattr(sale, cfield, 0) if cfield else 0)
            amt = rev_d - cost_d

        per_day[dkey] = per_day.get(dkey, Decimal(0)) + amt

    base, display, rates = _get_currency_setting()
    data_map: dict[date, float] = {
        k: round(_convert_amount(float(v), base, display, rates), 2) for k, v in per_day.items()
    }

    labels, values = _fill_days(start_incl, end_excl, data_map, fmt=labels_fmt)

    if metric == "revenue" and sum(values) == 0:
        flabels, fvalues = _fallback_items_daily(
            request, start_incl, end_excl, "amount", model_id, label_fmt=labels_fmt
        )
        if flabels:
            labels, values = flabels, fvalues

    return _ok({"labels": labels, "values": values, "range": range_meta, "currency": _currency_payload()})


# ---------- API: Sales trend (line chart) ----------

@never_cache
@login_required
def api_sales_trend(request: HttpRequest):
    """
    /inventory/api_sales_trend/?period=month|7d|all&metric=amount|count&model=<product_id?>
    Also supports explicit ranges:
      - on=YYYY-MM-DD  (alias: date=YYYY-MM-DD)
      - start/end (or from/to, df/dt, date_from/date_to)
      - labels=iso|pretty  (default iso)
    """
    metric = (request.GET.get("metric") or "amount").lower()
    model_id = request.GET.get("model")
    labels_fmt = (request.GET.get("labels") or "iso").lower()

    start_incl, end_incl, range_meta = _extract_range(request, default_period="month")
    end_excl = end_incl + timedelta(days=1)

    dfield = _sale_date_field()
    afield = _sale_amount_field()

    qs = date_range_filter(_scoped_sales_qs(request), dfield, start_incl, end_excl)
    if model_id:
        try:
            qs = qs.filter(item__product_id=int(model_id))
        except Exception:
            pass

    try:
        if metric == "amount":
            val_expr = _amount_sum_expression(afield)
        else:
            val_expr = Count("id")

        agg = (qs.annotate(d=TruncDate(dfield))
                 .values("d").annotate(val=val_expr).order_by("d"))

        base, display, rates = _get_currency_setting()
        data_map: dict[date, float] = {}
        for r in agg:
            raw = r["val"] or 0
            try:
                raw_f = float(raw)
            except Exception:
                try:
                    raw_f = float(Decimal(str(raw)))
                except Exception:
                    raw_f = 0.0
            if metric == "amount":
                raw_f = _convert_amount(raw_f, base, display, rates)
                raw_f = round(float(raw_f), 2)
            data_map[r["d"]] = raw_f

        labels, values = _fill_days(start_incl, end_excl, data_map, fmt=labels_fmt)

        if metric == "amount" and sum(values) == 0:
            flabels, fvalues = _fallback_items_daily(
                request, start_incl, end_excl,
                "amount",
                model_id,
                label_fmt=labels_fmt,
            )
            if flabels:
                labels, values = flabels, fvalues

        return _ok({
            "labels": labels,
            "values": values,
            "range": range_meta,
            "currency": _currency_payload() if metric == "amount" else None
        })

    except Exception as e:
        log.warning("api_sales_trend primary aggregation failed: %s", e)

    # Secondary: python accumulation then fallback
    per_day = {}
    for sale in qs.iterator():
        dval = getattr(sale, dfield)
        try:
            dkey = dval.date()
        except Exception:
            dkey = dval
        if metric == "amount" and afield:
            raw = getattr(sale, afield, 0)
            try:
                v = Decimal(str(raw).replace(",", "").strip()) if raw not in (None, "") else Decimal(0)
            except (InvalidOperation, AttributeError):
                v = Decimal(0)
        else:
            v = 1
        per_day[dkey] = per_day.get(dkey, Decimal(0)) + (v if isinstance(v, Decimal) else Decimal(v))

    base, display, rates = _get_currency_setting()
    data_map: dict[date, float] = {}
    for k, v in per_day.items():
        data_map[k] = _convert_amount(float(v), base, display, rates) if metric == "amount" else float(v)

    labels, values = _fill_days(start_incl, end_excl, data_map, fmt=labels_fmt)

    if metric == "amount" and sum(values) == 0:
        flabels, fvalues = _fallback_items_daily(
            request, start_incl, end_excl,
            "amount",
            model_id,
            label_fmt=labels_fmt,
        )
        if flabels:
            labels, values = flabels, fvalues

    return _ok({
        "labels": labels,
        "values": values,
        "range": range_meta,
        "currency": _currency_payload() if metric == "amount" else None
    })


# ---------- API: Top models (bar chart) ----------

@never_cache
@login_required
def api_top_models(request: HttpRequest):
    """
    /inventory/api_top_models/?period=today|month
    Also supports explicit ranges:
      - on=YYYY-MM-DD  (alias: date=YYYY-MM-DD)
      - start/end (or from/to, df/dt, date_from/date_to)
    Groups by a normalized BRAND + MODEL label with tolerant fallbacks.
    Treats blank-after-trim as NULL so Coalesce can fall back to 'Unknown'.
    """
    # Default to month for dashboard parity; allow overrides via query like &period=today
    start_incl, end_incl, range_meta = _extract_range(request, default_period="month")
    end_excl = end_incl + timedelta(days=1)

    dfield = _sale_date_field()
    sales_qs = date_range_filter(_scoped_sales_qs(request), dfield, start_incl, end_excl)

    def _sales_group(qs):
        brand = Coalesce(
            NullIf(Trim(F("item__product__brand")), Value("")),
            NullIf(Trim(F("product__brand")), Value("")),
        )
        model = Coalesce(
            NullIf(Trim(F("item__product__model")), Value("")),
            NullIf(Trim(F("item__model")), Value("")),
            NullIf(Trim(F("product__model")), Value("")),
            NullIf(Trim(F("item__product__name")), Value("")),
            NullIf(Trim(F("product__name")), Value("")),
        )
        label = Coalesce(
            NullIf(Trim(Concat(brand, Value(" "), model, output_field=djmodels.CharField())), Value("")),
            model,
            Value("Unknown", output_field=djmodels.CharField()),
        )
        return (
            qs.annotate(label=label)
              .values("label")
              .annotate(c=Count("id"))
              .order_by("-c", "label")[:12]
        )

    def _items_group(qs):
        brand = Coalesce(
            NullIf(Trim(F("product__brand")), Value("")),
            NullIf(Trim(F("brand")), Value("")),
        )
        model = Coalesce(
            NullIf(Trim(F("product__model")), Value("")),
            NullIf(Trim(F("model")), Value("")),
            NullIf(Trim(F("product__name")), Value("")),
            NullIf(Trim(F("name")), Value("")),
        )
        label = Coalesce(
            NullIf(Trim(Concat(brand, Value(" "), model, output_field=djmodels.CharField())), Value("")),
            model,
            Value("Unknown", output_field=djmodels.CharField()),
        )
        return (
            qs.annotate(label=label)
              .values("label")
              .annotate(c=Count("id"))
              .order_by("-c", "label")[:12]
        )

    labels: list[str] = []
    values: list[int] = []

    # 1) Prefer Sales (most accurate)
    try:
        rows = list(_sales_group(sales_qs))
        labels = [r["label"] or "Unknown" for r in rows]
        values = [int(r["c"] or 0) for r in rows]
    except Exception:
        labels, values = [], []

    # 2) Fallback to InventoryItem rows that look sold in the window
    if sum(values) == 0:
        status_field = _item_status_field()
        date_field   = _best_item_date_field()
        iqs = _scoped_stock_qs(request)
        if _has_field(InventoryItem, status_field):
            cond = Q(**{f"{status_field}__in": _SOLD_LIKE}) \
                 | Q(**{f"{status_field}__istartswith": "sold"}) \
                 | Q(**{f"{status_field}__istartswith": "dispatch"}) \
                 | Q(**{f"{status_field}__istartswith": "check"}) \
                 | Q(**{f"{status_field}__iexact": "out"}) \
                 | Q(**{f"{status_field}__istartswith": "deliver"}) \
                 | Q(**{f"{status_field}__istartswith": "issue"}) \
                 | ~Q(**{f"{status_field}__in": _IN_STOCK_LIKE})
            iqs = iqs.filter(cond)
        if _has_field(InventoryItem, date_field):
            iqs = date_range_filter(iqs, date_field, start_incl, end_excl)

        try:
            rows = list(_items_group(iqs))
            labels = [r["label"] or "Unknown" for r in rows]
            values = [int(r["c"] or 0) for r in rows]
        except Exception:
            labels, values = [], []

    # 3) Last resort: group all current stock (helps brand-new installs)
    if sum(values) == 0:
        s_qs = _scoped_stock_qs(request)
        try:
            rows = list(_items_group(s_qs))
            labels = [r["label"] or "Unknown" for r in rows]
            values = [int(r["c"] or 0) for r in rows]
        except Exception:
            labels, values = [], []

    return _ok({"labels": labels, "values": values, "range": range_meta})


# ---------- API: Alerts (window-aware) ----------

@never_cache
@login_required
def alerts_feed(request: HttpRequest):
    """
    Computes low-stock / near-stockout alerts using a lookback window.
    Accepts:
      - days=N  (default 14)  OR explicit date range via start/end/on (same as other APIs)
    """
    days_param = request.GET.get("days")
    if days_param:
        try:
            lookback_days = max(1, min(90, int(days_param)))
        except Exception:
            lookback_days = 14
        today = timezone.localdate()
        start_incl = today - timedelta(days=lookback_days)
        end_incl = today
        range_meta = {"start": start_incl.isoformat(), "end": end_incl.isoformat()}
    else:
        start_incl, end_incl, range_meta = _extract_range(request, default_period="7d")

    dfield = _sale_date_field()
    sales_qs = date_range_filter(_scoped_sales_qs(request), dfield, start_incl, end_incl + timedelta(days=1))
    stock_qs  = _scoped_stock_qs(request)

    model_id = request.GET.get("model")
    if model_id:
        try:
            pid = int(model_id)
            sales_qs = sales_qs.filter(item__product_id=pid)
            stock_qs = stock_qs.filter(product_id=pid)
        except Exception:
            pass

    # Convert chosen window to daily run-rate
    lookback_days = max(1, (end_incl - start_incl).days + 1)

    stock = stock_qs.values("product_id", "product__brand", "product__model").annotate(on_hand=Count("id"))
    recent = sales_qs.values("item__product_id").annotate(c=Count("id"))
    runrate_map = {r["item__product_id"]: (r["c"] / float(lookback_days)) for r in recent}

    alerts = []
    for r in stock:
        brand = r["product__brand"]; model = r["product__model"]
        name = f"{brand} {model}"
        on_hand = int(r["on_hand"] or 0)
        daily = runrate_map.get(r["product_id"], 0.0)
        need7 = daily * 7.0

        if on_hand <= 2:
            alerts.append({"type": "Low stock", "severity": "high", "message": f"{name} has only {on_hand} on hand."})
        elif daily > 0 and on_hand < need7:
            alerts.append({"type": "Near stockout", "severity": "warn",
                           "message": f"{name} may stock out within 7 days. On-hand {on_hand}, needed ~{int(round(need7))}."})

    sev_order = {"high": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: sev_order.get(a.get("severity", "info"), 9))
    return _ok({"alerts": alerts, "range": range_meta})


# ---------- Scanner & Time APIs ----------

@never_cache
@login_required
@require_POST
@transaction.atomic
def api_mark_sold(request: HttpRequest):
    """
    POST JSON: { imei|code, price?, sold_date?, location_id? }
    - Lookup is business-scoped and unsold-only (IN_STOCK_Q()).
    - Flips all sold flags via the canonical updater.
    - Creates a Sale row so charts move immediately.
    """
    body = _json_body(request)

    # Accept either "imei" or "code" inputs
    code = body.get("imei") or body.get("code") or request.POST.get("imei") or request.POST.get("code")
    code = (code or "").strip()
    if not code:
        return _err("Missing code/IMEI", status=400)

    item = _find_instock_for_business(request, code)
    if not item:
        return _err("Item not found or already sold", status=404)

    # Location handling (optional)
    loc_id = body.get("location_id") or body.get("location")
    if not loc_id:
        loc_id, _ = _pick_default_location(request)
    def _set_item_location_by_id(_item, _loc_id):
        if not _loc_id:
            return
        try:
            _loc_id = int(_loc_id)
        except Exception:
            return
        if _has_field(InventoryItem, "current_location_id"):
            try:
                setattr(_item, "current_location_id", _loc_id)
                return
            except Exception:
                pass
        if _has_field(InventoryItem, "location_id"):
            try:
                setattr(_item, "location_id", _loc_id)
                return
            except Exception:
                pass
        if _LocationModel is not None:
            try:
                loc_obj = _LocationModel.objects.filter(id=_loc_id).only("id").first()
                if loc_obj:
                    if _has_field(InventoryItem, "current_location"):
                        setattr(_item, "current_location", loc_obj)
                    elif _has_field(InventoryItem, "location"):
                        setattr(_item, "location", loc_obj)
            except Exception:
                pass
    _set_item_location_by_id(item, loc_id)

    # Parse price & sold date
    price_val = None
    if body.get("price") not in (None, ""):
        try:
            price_val = Decimal(str(body.get("price")).replace(",", "").strip())
        except Exception:
            price_val = None

    sold_dt = timezone.now()
    if body.get("sold_date"):
        try:
            sold_dt = datetime.fromisoformat(str(body["sold_date"]))
            if timezone.is_naive(sold_dt):
                sold_dt = timezone.make_aware(sold_dt, timezone.get_current_timezone())
        except Exception:
            sold_dt = timezone.now()

    # Flip all flags via canonical updater (single source of truth)
    if _canonical_mark_item_sold is not None:
        _canonical_mark_item_sold(item, price=price_val, sold_date=sold_dt, user=request.user, loc_id=loc_id)
    else:
        # ultra-safe fallback if utils_status isn't available
        status_field = _item_status_field()
        try: setattr(item, status_field, "SOLD")
        except Exception: pass
        sfield = _best_item_date_field()
        if _has_field(InventoryItem, sfield):
            try: setattr(item, sfield, sold_dt)
            except Exception: pass
        if _has_field(InventoryItem, "is_sold"):
            item.is_sold = True
        if _has_field(InventoryItem, "in_stock"):
            item.in_stock = False
        item.save()

    # Create Sale row so charts/kpis move (dashboard also has item fallback)
    afield = _sale_amount_field()
    dfield = _sale_date_field()
    sale = Sale(item=item)
    if _has_field(Sale, "agent"):
        try: setattr(sale, "agent", request.user)
        except Exception: pass
    if afield and price_val is not None:
        try: setattr(sale, afield, price_val)
        except Exception: pass
    try: setattr(sale, dfield, sold_dt)
    except Exception: pass
    sale.save()

    return _ok({"ok": True, "id": item.id, "sale_id": sale.id})



@never_cache
@login_required
@csrf_exempt  # Dev-friendly: allow AJAX without CSRF token; remove if you enforce CSRF
def api_time_checkin(request: HttpRequest):
    if request.method != "POST":
        return _err("POST required", status=405)

    payload = _json_body(request)

    TimeLog = None
    for dotted in ("timeclock.models", "times.models", "inventory.models"):
        try:
            mod = __import__(dotted, fromlist=["TimeLog"])
            TimeLog = getattr(mod, "TimeLog", None)
            if TimeLog: break
        except Exception:
            continue

    if TimeLog is None:
        return _ok({"stored": False, "echo": payload})

    obj = TimeLog()
    mapping = {
        "user": request.user,
        "type": payload.get("checkin_type") or payload.get("type"),
        "timestamp": timezone.now(),
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "accuracy": payload.get("accuracy"),
        "address": payload.get("address"),
        "notes": payload.get("notes"),
    }
    for k, v in mapping.items():
        if _has_field(TimeLog, k) or hasattr(TimeLog, k):
            try: setattr(obj, k, v)
            except Exception: pass
    try:
        obj.save()
        return _ok({"stored": True, "id": getattr(obj, "id", None)})
    except Exception as e:
        log.warning("api_time_checkin failed to save TimeLog: %s", e)
        return _ok({"stored": False, "echo": payload})


# ---------- NEW: Async Task Submit & Status ----------

@never_cache
@login_required
def api_task_submit(request: HttpRequest):
    """
    POST /inventory/api_task_submit/
    Body (JSON or form):
      - task: optional task name (e.g., "rebuild_caches", "ping", "insights.tasks.forecast_daily")
      - args: optional list
      - kwargs: optional dict

    Returns: { ok, id, task, state }
    """
    if request.method != "POST":
        return _err("POST required", status=405)

    body = _json_body(request)
    task_name = (body.get("task") or request.POST.get("task") or "ping").strip()

    # Resolve a callable with .delay()
    callable_task = _resolve_task_callable(task_name)
    if callable_task is None:
        # last-chance fallback to cc.celery.ping
        callable_task = _resolve_task_callable("cc.celery.ping")
        if callable_task is None:
            return _err("Task not found", status=404, task=task_name)

    args = body.get("args") or []
    kwargs = body.get("kwargs") or {}

    try:
        res = callable_task.delay(*args, **kwargs)  # type: ignore[attr-defined]
    except Exception as e:
        log.warning("api_task_submit failed for %s: %s", task_name, e)
        return _err("Task submission failed", status=500, task=task_name)

    state = getattr(res, "state", "PENDING")
    return _ok({"id": str(getattr(res, "id", "")), "task": task_name, "state": state})


@never_cache
@login_required
def api_task_status(request: HttpRequest):
    """
    GET /inventory/api_task_status/?id=<celery_task_id>
    Returns: { ok, id, state, ready, successful, result? }
    """
    if AsyncResult is None:
        return _err("Celery not installed", status=501)

    task_id = (request.GET.get("id") or "").strip()
    if not task_id:
        return _err("id required", status=400)

    try:
        res = AsyncResult(task_id)
        state = res.state
        ready = res.ready()
        successful = res.successful() if ready else False
        payload: dict[str, Any] = {
            "id": task_id,
            "state": state,
            "ready": ready,
            "successful": successful,
        }
        if ready:
            try:
                payload["result"] = res.get(propagate=False)
            except Exception as e:
                payload["error"] = str(e)
        return _ok(payload)
    except Exception as e:
        log.warning("api_task_status failed for id=%s: %s", task_id, e)
        return _err("Lookup failed", status=500, id=task_id)


# ---------- NEW: Quick audit-chain verify (API) ----------

@never_cache
@login_required
def api_audit_verify(request: HttpRequest):
    """
    GET /inventory/api_audit_verify/?limit=5000
    Quickly verify the most recent N audit rows (hash chain).
    """
    try:
        from .models_audit import AuditLog  # local import to avoid hard dependency
    except Exception:
        return _ok({"supported": False, "checked": 0, "ok_chain": True})

    try:
        limit = int(request.GET.get("limit", "5000"))
    except Exception:
        limit = 5000
    limit = max(100, min(limit, 200000))

    # Verify newest→oldest slice by reversing after fetch to walk forward
    rows = list(AuditLog.objects.order_by("-id").values(
        "id", "prev_hash", "hash", "actor_id", "entity", "entity_id", "action", "payload"
    )[:limit])
    rows.reverse()

    import hashlib as _hashlib
    import json as _json

    ok_chain = True
    broken_at = None
    prev = rows[0]["prev_hash"] if rows else ""
    checked = 0

    for r in rows:
        payload = {
            "prev": prev,
            "actor": r["actor_id"],
            "ip": None,
            "ua": None,
            "entity": r["entity"],
            "entity_id": r["entity_id"],
            "action": r["action"],
            "payload": r["payload"],
        }
        packed = _json.dumps(payload, sort_keys=True).encode()
        recomputed = _hashlib.sha256(packed).hexdigest()
        if recomputed != r["hash"]:
            ok_chain = False
            broken_at = r["id"]
            break
        prev = r["hash"]
        checked += 1

    return _ok({"supported": True, "ok_chain": ok_chain, "broken_at": broken_at, "checked": checked})


# ---------- NEW: Restock heatmap (safe stub) ----------

@never_cache
@login_required
@require_business
def restock_heatmap(request: HttpRequest):
    """
    GET /inventory/api/restock-heatmap/
    Safe stub so the dashboard doesn't error. Returns an empty list of points.
    Replace later with real geo/grid data if you add coordinates to locations.
    Response shape stays stable: { ok: true, points: [...] }.
    """
    return _ok({
        "points": [],         # e.g. [{ "label": "Area 25", "value": 0.0 }]
        "generated_at": timezone.now().isoformat(),
    })


# ---------- Back-compat aliases ----------

api_predictions = predictions_summary       # /inventory/api/predictions (no slash) compat
api_alerts = alerts_feed                    # keep older route names working
