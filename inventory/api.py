# inventory/api.py

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional, Tuple

from django.contrib.auth.decorators import login_required
from django.db import models as djmodels
from django.db import transaction
from django.db.models import (
    Count, Sum, F, Value, DecimalField, ExpressionWrapper, Q,
)
from django.db.models.functions import TruncDate, Coalesce, Cast
from django.http import JsonResponse, HttpRequest
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .models import InventoryItem
from sales.models import Sale

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
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    return user.groups.filter(name__in=["Admin", "Manager", "Auditor", "Auditors"]).exists()

def _scope_mode(request: HttpRequest) -> str:
    val = (request.GET.get("scope") or "").strip().lower()
    return "self" if val in {"self", "mine", "me", "user", "agent"} else "all"

def _has_field(model, name: str) -> bool:
    return any(getattr(f, "name", None) == name for f in model._meta.get_fields())

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

def _scoped_sales_qs(request: HttpRequest):
    qs = Sale.objects.all()
    try:
        qs = qs.select_related("item__product")
    except Exception:
        pass
    if _scope_mode(request) == "self" and not _can_view_all(request.user):
        if _has_field(Sale, "agent"):
            qs = qs.filter(agent=request.user)
    return qs

def _scoped_stock_qs(request: HttpRequest):
    qs = InventoryItem.objects.all()
    try:
        qs = qs.select_related("product")
    except Exception:
        pass
    if _scope_mode(request) == "self" and not _can_view_all(request.user):
        if _has_field(InventoryItem, "assigned_agent"):
            qs = qs.filter(assigned_agent=request.user)
    return qs

def date_range_filter(qs, field_name: str, start, end_excl):
    field = qs.model._meta.get_field(field_name)
    if isinstance(field, djmodels.DateTimeField):
        return qs.filter(**{f"{field_name}__date__gte": start, f"{field_name}__date__lt": end_excl})
    return qs.filter(**{f"{field_name}__gte": start, f"{field_name}__lt": end_excl})

def _amount_sum_expression(afield: str | None):
    dec = DecimalField(max_digits=14, decimal_places=2)
    if not afield:
        return Value(0, output_field=dec)
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


# ---------- date utils (NEW) ----------

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
    if period in ("today", "day", "date"):  # accept "date" as synonym of a single-day window when no ?date=
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
        qs.annotate(d=TruncDate(date_field, tzinfo=timezone.get_current_timezone()))
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


# ---------- API: AI predictions (kept as-is; based on last 14d) ----------

@never_cache
@login_required
def predictions_summary(request: HttpRequest):
    today = timezone.localdate()
    lookback_days = 14
    start = today - timedelta(days=lookback_days)
    end_excl = today + timedelta(days=1)

    dfield = _sale_date_field()
    afield = _sale_amount_field()

    sales = date_range_filter(_scoped_sales_qs(request), dfield, start, end_excl)
    items = _scoped_stock_qs(request)

    per_day_counts = (sales.annotate(d=TruncDate(dfield, tzinfo=timezone.get_current_timezone()))
                           .values("d").annotate(c=Count("id")))
    total_units_14 = sum(r["c"] for r in per_day_counts) or 0
    daily_units_avg = total_units_14 / float(lookback_days) if lookback_days else 0.0

    per_day_rev = (sales.annotate(d=TruncDate(dfield, tzinfo=timezone.get_current_timezone()))
                        .values("d").annotate(v=_amount_sum_expression(afield)))
    total_rev_14 = float(sum(r["v"] or 0 for r in per_day_rev))
    daily_rev_avg = total_rev_14 / float(lookback_days) if lookback_days else 0.0

    base, display, rates = _get_currency_setting()
    daily_rev_avg_display = _convert_amount(daily_rev_avg, base, display, rates)

    overall = [{
        "date": (today + timedelta(days=i)).isoformat(),
        "predicted_units": round(daily_units_avg, 2),
        "predicted_revenue": round(daily_rev_avg_display, 2),
    } for i in range(1, 7 + 1)]

    by_model_14 = sales.values("item__product_id").annotate(c=Count("id"))
    model_count_map = {r["item__product_id"]: r["c"] for r in by_model_14}

    risky = []
    by_model_stock = items.values("product_id", "product__brand", "product__model").annotate(on_hand=Count("id")).order_by("product__brand", "product__model")
    for r in by_model_stock:
        pid = r["product_id"]
        on_hand = int(r["on_hand"] or 0)
        daily_model_avg = (model_count_map.get(pid, 0) / float(lookback_days)) if lookback_days else 0.0
        need_next_7 = daily_model_avg * 7.0

        # Flag critical low stock even with zero run-rate
        if on_hand <= 2:
            risky.append({
                "product": f'{r["product__brand"]} {r["product__model"]}',
                "on_hand": on_hand,
                "stockout_date": today.isoformat(),
                "suggested_restock": max(1, 5 - on_hand),
                "urgent": True,
                "reason": "critical_low_stock",
            })
        elif daily_model_avg > 0 and on_hand < need_next_7:
            days_cover = (on_hand / daily_model_avg) if daily_model_avg else 0
            risky.append({
                "product": f'{r["product__brand"]} {r["product__model"]}',
                "on_hand": on_hand,
                "stockout_date": (today + timedelta(days=max(0, int(days_cover)))).isoformat(),
                "suggested_restock": int(round(max(0.0, need_next_7 - on_hand))),
                "urgent": on_hand <= (daily_model_avg * 2.0),
                "reason": "runrate_shortfall",
            })

    return _ok({"overall": overall, "risky": risky, "currency": _currency_payload()})


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
        val_expr = _amount_sum_expression(afield) if metric == "amount" else Count("id")
        agg = (qs.annotate(d=TruncDate(dfield, tzinfo=timezone.get_current_timezone()))
                 .values("d").annotate(val=val_expr).order_by("d"))

        base, display, rates = _get_currency_setting()
        data_map: dict[date, float] = {}
        for r in agg:
            raw = float(r["val"] or 0)
            if metric == "amount":
                raw = _convert_amount(raw, base, display, rates)
                raw = round(float(raw), 2)
            data_map[r["d"]] = raw

        labels, values = _fill_days(start_incl, end_excl, data_map, fmt=labels_fmt)

        if sum(values) == 0:
            flabels, fvalues = _fallback_items_daily(
                request, start_incl, end_excl,
                "amount" if metric == "amount" else "count",
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

    if sum(values) == 0:
        flabels, fvalues = _fallback_items_daily(
            request, start_incl, end_excl,
            "amount" if metric == "amount" else "count",
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


# ---------- API: Value Trend (Revenue / Cost / Profit) ----------

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
    model_id = request.GET.get("model")
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

    dec = DecimalField(max_digits=14, decimal_places=2)
    if metric == "revenue":
        expr = _amount_sum_expression(afield)
    elif metric == "cost":
        expr = _amount_sum_expression(cfield)
    else:
        rev = _amount_sum_expression(afield)
        cost = _amount_sum_expression(cfield)
        expr = ExpressionWrapper(Coalesce(rev, Value(0, output_field=dec)) - Coalesce(cost, Value(0, output_field=dec)),
                                 output_field=dec)

    agg = (qs.annotate(d=TruncDate(dfield, tzinfo=timezone.get_current_timezone()))
             .values("d").annotate(val=expr).order_by("d"))

    base, display, rates = _get_currency_setting()
    data_map: dict[date, float] = {}
    for r in agg:
        raw_val = float(r["val"] or 0)
        conv_val = _convert_amount(raw_val, base, display, rates)
        data_map[r["d"]] = round(conv_val, 2)

    labels, values = _fill_days(start_incl, end_excl, data_map, fmt=labels_fmt)

    if metric == "revenue" and sum(values) == 0:
        flabels, fvalues = _fallback_items_daily(
            request, start_incl, end_excl, "amount", model_id, label_fmt=labels_fmt
        )
        if flabels:
            labels, values = flabels, fvalues

    return _ok({"labels": labels, "values": values, "range": range_meta, "currency": _currency_payload()})


# ---------- API: Top models (bar chart) ----------

@never_cache
@login_required
def api_top_models(request: HttpRequest):
    """
    /inventory/api_top_models/?period=today|month
    Also supports explicit ranges:
      - on=YYYY-MM-DD  (alias: date=YYYY-MM-DD)
      - start/end (or from/to, df/dt, date_from/date_to)
    """
    # Range first; if no explicit range, keep existing behavior for month/today
    start_incl, end_incl, range_meta = _extract_range(request, default_period="today")
    end_excl = end_incl + timedelta(days=1)

    dfield = _sale_date_field()
    qs = date_range_filter(_scoped_sales_qs(request), dfield, start_incl, end_excl)

    labels: list[str] = []
    values: list[int] = []

    try:
        agg = (qs.values("item__product__brand", "item__product__model")
                 .annotate(c=Count("id")).order_by("-c")[:8])
        labels = [f'{r["item__product__brand"]} {r["item__product__model"]}' for r in agg]
        values = [int(r["c"]) for r in agg]
    except Exception:
        labels = []; values = []

    if sum(values) == 0:
        try:
            agg2 = (qs.values("product__brand", "product__model")
                      .annotate(c=Count("id")).order_by("-c")[:8])
            labels = [f'{r["product__brand"]} {r["product__model"]}' for r in agg2]
            values = [int(r["c"]) for r in agg2]
        except Exception:
            labels = []; values = []

    if sum(values) == 0:
        date_field = _best_item_date_field()
        status_field = _item_status_field()
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
            iagg = (iqs.values("product__brand", "product__model")
                        .annotate(c=Count("id")).order_by("-c")[:8])
            labels = [f'{r["product__brand"]} {r["product__model"]}' for r in iagg]
            values = [int(r["c"]) for r in iagg]
        except Exception:
            labels = []; values = []

    if sum(values) == 0:
        s_qs = _scoped_stock_qs(request)
        try:
            sagg = (s_qs.values("product__brand", "product__model")
                       .annotate(c=Count("id")).order_by("-c")[:8])
            labels = [f'{r["product__brand"]} {r["product__model"]}' for r in sagg]
            values = [int(r["c"]) for r in sagg]
        except Exception:
            labels = []; values = []

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
@transaction.atomic
def api_mark_sold(request: HttpRequest):
    if request.method != "POST":
        return _err("POST required", status=405)

    body = _json_body(request)
    imei = _norm_digits(body.get("imei"))
    if not imei or len(imei) < 10:
        return _err("Invalid IMEI", status=400)

    imei_field = _item_imei_field()
    status_field = _item_status_field()
    sold_at_field = _best_item_date_field()

    try:
        item = InventoryItem.objects.get(**{imei_field: imei})
    except InventoryItem.DoesNotExist:
        cand = InventoryItem.objects.all()
        def _digits_or_none(x):
            try: return _norm_digits(getattr(x, imei_field))
            except Exception: return ""
        item = next((x for x in cand if _digits_or_none(x) == imei), None)

    if not item:
        return _err("IMEI not found", status=404)

    loc_id = body.get("location_id")
    if loc_id and _has_field(InventoryItem, "location_id"):
        try: setattr(item, "location_id", int(loc_id))
        except Exception: pass

    already = False
    try:
        already = (getattr(item, status_field) != "IN_STOCK")
    except Exception:
        already = Sale.objects.filter(item=item).exists()
    if already:
        return _ok({"imei": imei, "already_sold": True})

    price_val = None
    try:
        if body.get("price") not in (None, ""):
            price_val = Decimal(str(body.get("price")).replace(",", "").strip())
    except Exception:
        price_val = None

    afield = _sale_amount_field()
    dfield = _sale_date_field()

    sale = Sale(item=item)
    if _has_field(Sale, "agent"):
        setattr(sale, "agent", request.user)
    if afield and price_val is not None:
        try: setattr(sale, afield, price_val)
        except Exception: pass
    try: setattr(sale, dfield, timezone.now())
    except Exception: pass
    sale.save()

    try: setattr(item, status_field, "SOLD")
    except Exception: pass
    if sold_at_field and _has_field(InventoryItem, sold_at_field):
        try: setattr(item, sold_at_field, timezone.now())
        except Exception: pass
    item.save()

    return _ok({"imei": imei, "sale_id": sale.id, "already_sold": False})


@never_cache
@login_required
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
    rows = list(AuditLog.objects.order_by("-id").values("id", "prev_hash", "hash", "actor_id", "entity", "entity_id", "action", "payload")[:limit])
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
