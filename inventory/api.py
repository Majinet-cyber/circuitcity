# circuitcity/inventory/api.py
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.core.cache import cache  # optional simple caching
from datetime import timedelta

from insights.models import Forecast
from insights.services import stockout_and_restock
from inventory.models import Product


def _int_arg(request, name, default, lo, hi):
    """Clamp an optional int query param to [lo, hi]."""
    v = request.GET.get(name)
    if v is None:
        return default
    try:
        v = int(v)
        return max(lo, min(hi, v))
    except ValueError:
        return default


@require_GET
def predictions_summary(request):
    """
    GET /inventory/api/predictions/?days=7&lead=3&limit=3

    Response:
    {
      "ok": true,
      "overall": [{"date":"2025-08-25","predicted_units":10,"predicted_revenue":12345.0}, ...],
      "risky": [
        {"product":"X","stockout_date":"2025-08-28","on_hand":6,"suggested_restock":30,"urgent":true},
        ...
      ]
    }
    """
    # parameters (clamped for safety)
    days = _int_arg(request, "days", default=7, lo=1, hi=30)
    lead_days = _int_arg(request, "lead", default=3, lo=0, hi=14)
    risky_limit = _int_arg(request, "limit", default=3, lo=1, hi=10)

    cache_key = f"predictions_summary:v1:days={days}:lead={lead_days}:limit={risky_limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)  # ~5ms

    today = timezone.now().date()
    horizon = today + timedelta(days=days)

    # ----- Overall (store-level) forecast for the next N days -----
    overall_qs = (
        Forecast.objects
        .filter(product__isnull=True, date__gte=today, date__lte=horizon)
        .order_by("date")
        .values("date", "predicted_units", "predicted_revenue")
    )

    overall = []
    for row in overall_qs:
        d = row.get("date")
        pu = row.get("predicted_units") or 0
        pr = row.get("predicted_revenue") or 0
        overall.append({
            "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
            "predicted_units": int(pu) if pu is not None else 0,
            "predicted_revenue": float(pr) if pr is not None else 0.0,
        })

    # ----- Top risky products (stockout risk) -----
    risky = []
    # Filter to active products if you have such a field; else keep .all()
    products = Product.objects.all().only("id", "name")[:100].iterator()
    for p in products:
        try:
            s = stockout_and_restock(p, horizon_days=days, lead_days=lead_days)
        except Exception as e:
            # Skip this product; keep the API alive
            continue

        stockout_date = s.get("stockout_date")
        if stockout_date:
            risky.append({
                "product": getattr(p, "name", None) or f"Product {p.id}",
                "stockout_date": stockout_date.isoformat() if hasattr(stockout_date, "isoformat") else str(stockout_date),
                "on_hand": s.get("on_hand", 0),
                "suggested_restock": s.get("suggested_restock", 0),
                "urgent": bool(s.get("urgent", False)),
            })

    # Urgent first, then earliest stockout date
    risky.sort(key=lambda x: (not x["urgent"], x["stockout_date"] or horizon.isoformat()))
    risky = risky[:risky_limit]

    payload = {
        "ok": True,
        "overall": overall,
        "risky": risky,
    }

    # Cache for 5 minutes (tweak or remove)
    cache.set(cache_key, payload, 300)
    return JsonResponse(payload)
