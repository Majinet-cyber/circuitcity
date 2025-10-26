# inventory/api_sales_metrics.py
from __future__ import annotations

from datetime import timedelta
from typing import Optional, Iterable

from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, Sum, F, Value
from django.db.models.functions import Coalesce, TruncDate
from django.http import JsonResponse, HttpRequest
from django.utils import timezone
from django.views.decorators.http import require_http_methods

# ---- tolerant import of Sale -------------------------------------------------
def _try_import(modpath: str, attr: str | None = None):
    import importlib
    try:
        mod = importlib.import_module(modpath)
        return getattr(mod, attr) if attr else mod
    except Exception:
        return None

Sale = _try_import("sales.models", "Sale")

# ---- small helpers -----------------------------------------------------------
def _ok(payload: dict, message: Optional[str] = None) -> JsonResponse:
    """Match your API envelope: {ok, data, message?}"""
    out = {"ok": True, "data": payload}
    if message:
        out["message"] = message
    return JsonResponse(out)

def _err(message: str, extra: Optional[dict] = None) -> JsonResponse:
    out = {"ok": False, "error": message}
    if extra:
        out.update(extra)
    return JsonResponse(out, status=200)

def _field_names(model) -> set[str]:
    try:
        return {getattr(f, "name", None) for f in model._meta.get_fields()}  # type: ignore[attr-defined]
    except Exception:
        return set()

def _sale_time_field() -> Optional[str]:
    """Prefer 'sold_at', else 'date', else None."""
    if Sale is None:
        return None
    names = _field_names(Sale)
    if "sold_at" in names:
        return "sold_at"
    if "date" in names:
        return "date"
    return None

def _amount_field() -> str:
    """Best available amount/price field on Sale."""
    if Sale is None:
        return "price"
    names = _field_names(Sale)
    for cand in ("total", "amount", "sold_price", "price"):
        if cand in names:
            return cand
    return "price"

def _period_bounds(period: str) -> tuple[timezone.datetime.date, timezone.datetime.date]:
    """
    Return (start_date, end_date_exclusive) in LOCAL date terms.
    period: "today" | "week" (7d) | "month" (30d default)
    """
    now = timezone.localtime()
    if period == "today":
        start = now.date()
        end = start + timedelta(days=1)
    elif period in {"week", "7d"}:
        end = now.date() + timedelta(days=1)
        start = end - timedelta(days=7)
    else:  # "month" default (30d)
        end = now.date() + timedelta(days=1)
        start = end - timedelta(days=30)
    return start, end

def _maybe_scope_business(request: HttpRequest, qs):
    """
    If Sale has a business field AND we can infer an active business id
    from session, scope the queryset. Otherwise leave as-is.
    """
    if Sale is None:
        return qs
    names = _field_names(Sale)
    if "business" not in names and "business_id" not in names:
        return qs

    biz_id = None
    # Common places people stash it; harmless if missing.
    for key in ("business_id", "active_business_id", "tenant_id", "company_id", "org_id"):
        if key in request.session:
            biz_id = request.session.get(key)
            break
    if biz_id:
        try:
            return qs.filter(models.Q(business_id=biz_id) | models.Q(business__id=biz_id))
        except Exception:
            return qs
    return qs

# ---- API: Top Models ---------------------------------------------------------
@login_required
@require_http_methods(["GET"])
def api_top_models(request: HttpRequest) -> JsonResponse:
    """
    Returns top selling 'models' for a period.

    Response:
      { ok, data:
          { period, count, series: [{name, qty, amount}] }
      }
    """
    if Sale is None:
        return _ok({"series": [], "period": "today", "count": 0}, "Sale model unavailable")

    period = (request.GET.get("period") or "today").lower()
    start, end = _period_bounds(period)
    time_field = _sale_time_field()
    amount_field = _amount_field()

    qs = Sale._default_manager.all()
    qs = _maybe_scope_business(request, qs)

    # date filter (works whether DateField or DateTimeField)
    if time_field:
        try:
            qs = qs.filter(**{f"{time_field}__gte": start, f"{time_field}__lt": end})
            trunc_expr = TruncDate(F(time_field))
        except Exception:
            qs = qs.filter(**{f"{time_field}__date__gte": start, f"{time_field}__date__lt": end})
            trunc_expr = TruncDate(time_field)
    else:
        # No sold field; nothing to aggregate
        return _ok({"series": [], "period": period, "count": 0}, "No sold_at/date field on Sale")

    # Resolve a model/product name
    name_expr = Value("Unknown")
    names = _field_names(Sale)
    try:
        if "product" in names:
            name_expr = Coalesce(F("product__name"), name_expr)
    except Exception:
        pass
    try:
        # If inventory FK exists, prefer that name when product field missing
        if "inventory_item" in names:
            name_expr = Coalesce(name_expr, F("inventory_item__product__name"), Value("Unknown"))
    except Exception:
        pass

    rows = (
        qs.values("id")  # dummy to enable annotate in SQLite safely
          .annotate(model_name=name_expr)
          .values("model_name")
          .annotate(
              qty=Count("id"),
              amount=Coalesce(Sum(amount_field), Value(0))
          )
          .order_by("-qty", "-amount")[:10]
    )

    series = [
        {"name": r["model_name"] or "Unknown", "qty": int(r["qty"] or 0), "amount": float(r["amount"] or 0.0)}
        for r in rows
    ]
    return _ok({"series": series, "period": period, "count": len(series)})

# ---- API: Sales Trend --------------------------------------------------------
@login_required
@require_http_methods(["GET"])
def api_sales_trend(request: HttpRequest) -> JsonResponse:
    """
    Returns daily sales trend for the period.

    Query:
      period: today|week|month (default: month)
      metric: amount|qty (UI can choose what to plot; both are returned)

    Response:
      { ok, data:
          { period, series:[{date:'YYYY-MM-DD', qty:int, amount:float}],
            total_qty, total_amount }
      }
    """
    if Sale is None:
        return _ok({"series": [], "period": "month", "total_qty": 0, "total_amount": 0.0}, "Sale model unavailable")

    period = (request.GET.get("period") or "month").lower()
    start, end = _period_bounds(period)
    time_field = _sale_time_field()
    amount_field = _amount_field()

    if not time_field:
        return _ok({"series": [], "period": period, "total_qty": 0, "total_amount": 0.0}, "No sold_at/date field on Sale")

    qs = Sale._default_manager.all()
    qs = _maybe_scope_business(request, qs)

    # date filter (Date vs DateTime safe)
    try:
        qs = qs.filter(**{f"{time_field}__gte": start, f"{time_field}__lt": end})
        trunc_expr = TruncDate(F(time_field))
    except Exception:
        qs = qs.filter(**{f"{time_field}__date__gte": start, f"{time_field}__date__lt": end})
        trunc_expr = TruncDate(time_field)

    daily = (
        qs.annotate(day=trunc_expr)
          .values("day")
          .annotate(qty=Count("id"), amount=Coalesce(Sum(amount_field), Value(0)))
          .order_by("day")
    )

    # Fill missing days
    by_day = { (r["day"] or timezone.localdate()).isoformat(): r for r in daily }
    cursor = start
    series = []
    total_qty = 0
    total_amount = 0.0
    while cursor < end:
        k = cursor.isoformat()
        r = by_day.get(k) or {}
        q = int(r.get("qty") or 0)
        a = float(r.get("amount") or 0.0)
        total_qty += q
        total_amount += a
        series.append({"date": k, "qty": q, "amount": a})
        cursor += timedelta(days=1)

    return _ok(
        {
            "period": period,
            "series": series,
            "total_qty": total_qty,
            "total_amount": total_amount,
        }
    )
