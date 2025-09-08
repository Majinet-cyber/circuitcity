# inventory/api_views.py
from datetime import date, timedelta
from collections import defaultdict

from django.db.models import Count, Sum, F, Value as V
from django.db.models.functions import TruncDay, Coalesce
from django.http import JsonResponse
from django.utils.timezone import now

from .models import InventoryItem  # adjust if your model name differs

CURRENCY_SIGN = "MK"  # change if needed


def _period_bounds(period: str):
    """Return (start_date, end_date_inclusive) for 'today'|'7d'|'month'|'all'."""
    today = date.today()
    if period == "today":
        return today, today
    if period in ("7d", "7days", "week"):
        return today - timedelta(days=6), today
    if period in ("month", "this_month"):
        return today.replace(day=1), today
    # all time → None means no lower bound
    return None, today


def _base_qs(period: str):
    """Filter sold records by period if we have dates available."""
    start, end = _period_bounds(period)
    qs = InventoryItem.objects.all()

    # Prefer a 'sold_at' field; otherwise fall back to 'updated_at' or 'created_at'
    date_field = None
    for cand in ("sold_at", "updated_at", "created_at"):
        if cand in [f.name for f in InventoryItem._meta.get_fields()]:
            date_field = cand
            break

    if date_field:
        if start:
            qs = qs.filter(**{f"{date_field}__date__gte": start})
        if end:
            qs = qs.filter(**{f"{date_field}__date__lte": end})

    return qs, date_field


# ---------- /inventory/api/sales-trend/ ----------
def api_sales_trend(request):
    """
    metric = 'amount' (sum selling_price) | 'count' (sold units)
    period = 'today'|'7d'|'month'|'all'
    model  = optional product id/name filter (?model=)
    """
    metric = request.GET.get("metric", "amount")
    period = request.GET.get("period", "month")

    qs, date_field = _base_qs(period)

    # Only count SOLD rows when available
    if "status" in [f.name for f in InventoryItem._meta.get_fields()]:
        qs = qs.filter(status="SOLD")

    # Optional model filter via ?model= (id or substring)
    model_q = request.GET.get("model")
    if model_q:
        # try id → else substring on product name/label/model
        if model_q.isdigit() and "product_id" in [f.name for f in InventoryItem._meta.get_fields()]:
            qs = qs.filter(product_id=int(model_q))
        else:
            for fname in ("product__model", "product__name", "product__label", "product"):
                if fname.split("__")[0] in [f.name for f in InventoryItem._meta.get_fields()]:
                    qs = qs.filter(**{f"{fname}__icontains": model_q})
                    break

    if not date_field:
        # No date field? Return a single bucket with totals so the chart still shows something.
        if metric == "count":
            total = qs.count()
            return JsonResponse({"labels": ["All time"], "values": [total]})
        total = qs.aggregate(v=Coalesce(Sum("selling_price"), V(0)))["v"] or 0
        return JsonResponse({"labels": ["All time"], "values": [int(total)], "currency": {"sign": CURRENCY_SIGN}})

    # Group per day
    per_day = (
        qs.annotate(d=TruncDay(date_field))
          .values("d")
          .annotate(
              cnt=Count("id"),
              amt=Coalesce(Sum("selling_price"), V(0)),
          )
          .order_by("d")
    )

    labels, values = [], []
    for row in per_day:
        labels.append(row["d"].strftime("%b %d"))
        values.append(int(row["cnt"] if metric == "count" else row["amt"] or 0))

    payload = {"labels": labels, "values": values}
    if metric != "count":
        payload["currency"] = {"sign": CURRENCY_SIGN}
    return JsonResponse(payload)


# ---------- /inventory/api/top-models/ ----------
def api_top_models(request):
    """
    period = 'today'|'7d'|'month'|'all'
    Returns top models by SOLD count.
    """
    period = request.GET.get("period", "today")
    qs, _ = _base_qs(period)

    if "status" in [f.name for f in InventoryItem._meta.get_fields()]:
        qs = qs.filter(status="SOLD")

    # Resolve a readable product field
    product_name_field = None
    for fname in ("product__model", "product__name", "product__label", "product"):
        if fname.split("__")[0] in [f.name for f in InventoryItem._meta.get_fields()]:
            product_name_field = fname
            break

    if not product_name_field:
        product_name_field = "id"

    agg = (
        qs.values(product_name_field)
          .annotate(n=Count("id"))
          .order_by("-n")[:8]
    )

    labels = [str(x[product_name_field]) for x in agg]
    values = [int(x["n"]) for x in agg]
    return JsonResponse({"labels": labels, "values": values})


# ---------- /inventory/api/value-trend/ ----------
def api_value_trend(request):
    """
    metric = 'revenue'|'cost'|'profit'
    period = 'today'|'7d'|'month'|'all'
    """
    metric = request.GET.get("metric", "revenue")
    period = request.GET.get("period", "7d")

    qs, date_field = _base_qs(period)
    if "status" in [f.name for f in InventoryItem._meta.get_fields()]:
        qs = qs.filter(status="SOLD")

    # choose fields safely
    has_sell = "selling_price" in [f.name for f in InventoryItem._meta.get_fields()]
    has_cost = "order_price" in [f.name for f in InventoryItem._meta.get_fields()]

    if not date_field:
        rev = qs.aggregate(v=Coalesce(Sum("selling_price"), V(0)))["v"] if has_sell else 0
        cost = qs.aggregate(v=Coalesce(Sum("order_price"), V(0)))["v"] if has_cost else 0
        prof = (rev or 0) - (cost or 0)
        val = {"revenue": rev, "cost": cost, "profit": prof}[metric]
        return JsonResponse({"labels": ["All time"], "values": [int(val)], "currency": {"sign": CURRENCY_SIGN}})

    per_day = (
        qs.annotate(d=TruncDay(date_field))
          .values("d")
          .annotate(
              revenue=Coalesce(Sum("selling_price"), V(0)) if has_sell else V(0),
              cost=Coalesce(Sum("order_price"), V(0)) if has_cost else V(0),
          )
          .order_by("d")
    )

    labels, values = [], []
    for row in per_day:
        rev = int(row.get("revenue") or 0)
        cost = int(row.get("cost") or 0)
        prof = rev - cost
        pick = {"revenue": rev, "cost": cost, "profit": prof}[metric]
        labels.append(row["d"].strftime("%b %d"))
        values.append(pick)

    return JsonResponse({"labels": labels, "values": values, "currency": {"sign": CURRENCY_SIGN}})


# ---------- /inventory/api/alerts/ (optional simple fallback) ----------
def api_alerts(request):
    """
    Basic low-stock alerts by product. If you already have an alerts endpoint,
    keep it; otherwise this gives the UI something to render.
    """
    # Count on-hand by product
    product_name_field = None
    for fname in ("product__model", "product__name", "product__label", "product"):
        if fname.split("__")[0] in [f.name for f in InventoryItem._meta.get_fields()]:
            product_name_field = fname
            break
    if not product_name_field:
        product_name_field = "id"

    on_hand = (
        InventoryItem.objects.exclude(status="SOLD")
        .values(product_name_field)
        .annotate(c=Count("id"))
        .order_by("c")
    )

    alerts = []
    for row in on_hand:
        if int(row["c"]) <= 1:  # threshold
            alerts.append({
                "severity": "warn",
                "type": "Low stock",
                "message": f"{row[product_name_field]} has only {row['c']} on hand."
            })

    return JsonResponse({"alerts": alerts})
