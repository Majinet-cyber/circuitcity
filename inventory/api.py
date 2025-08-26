# circuitcity/inventory/api.py
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.core.cache import cache


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
      "overall": [{"date":"YYYY-MM-DD","predicted_units":10,"predicted_revenue":12345.0}, ...],
      "risky": [
        {"product":"X","stockout_date":"YYYY-MM-DD","on_hand":6,"suggested_restock":30,"urgent":true},
        ...
      ]
    }
    """
    # ---- query params (clamped) ----
    days = _int_arg(request, "days", default=7, lo=1, hi=30)
    lead_days = _int_arg(request, "lead", default=3, lo=0, hi=14)
    risky_limit = _int_arg(request, "limit", default=3, lo=1, hi=10)

    cache_key = f"predictions_summary:v1:days={days}:lead={lead_days}:limit={risky_limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    today = timezone.now().date()
    horizon = today + timedelta(days=days)

    overall = []
    risky = []

    # ---- Lazy/defensive imports so missing apps never 500 ----
    Forecast = None
    stockout_and_restock = None
    Product = None
    try:
        from insights.models import Forecast as _Forecast  # type: ignore
        Forecast = _Forecast
    except Exception:
        Forecast = None

    try:
        from insights.services import stockout_and_restock as _stock  # type: ignore
        stockout_and_restock = _stock
    except Exception:
        stockout_and_restock = None

    try:
        from inventory.models import Product as _Product
        Product = _Product
    except Exception:
        Product = None

    # ---- Overall forecast (if insights present) ----
    if Forecast is not None:
        try:
            overall_qs = (
                Forecast.objects
                .filter(product__isnull=True, date__gte=today, date__lte=horizon)
                .order_by("date")
                .values("date", "predicted_units", "predicted_revenue")
            )
            for row in overall_qs:
                d = row.get("date")
                pu = row.get("predicted_units") or 0
                pr = row.get("predicted_revenue") or 0
                overall.append({
                    "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                    "predicted_units": int(pu) if pu is not None else 0,
                    "predicted_revenue": float(pr) if pr is not None else 0.0,
                })
        except Exception:
            # keep overall as []
            pass

    # ---- Risky products (only if Product + service are available) ----
    if (Product is not None) and (stockout_and_restock is not None):
        try:
            # keep it light — iterate first 100
            products_iter = Product.objects.all().only("id", "name", "brand", "model", "variant")[:100].iterator()
            for p in products_iter:
                try:
                    s = stockout_and_restock(p, horizon_days=days, lead_days=lead_days)
                except Exception:
                    continue

                stockout_date = s.get("stockout_date")
                if not stockout_date:
                    continue

                # Build a friendly product name
                name = getattr(p, "name", None)
                if not name:
                    parts = [getattr(p, "brand", None), getattr(p, "model", None), getattr(p, "variant", None)]
                    name = " ".join([str(x) for x in parts if x]) or f"Product {getattr(p, 'id', '—')}"

                risky.append({
                    "product": name,
                    "stockout_date": stockout_date.isoformat() if hasattr(stockout_date, "isoformat") else str(stockout_date),
                    "on_hand": s.get("on_hand", 0),
                    "suggested_restock": s.get("suggested_restock", 0),
                    "urgent": bool(s.get("urgent", False)),
                })

            # Urgent first, then earliest stockout
            risky.sort(key=lambda x: (not x["urgent"], x["stockout_date"]))
            risky = risky[:risky_limit]
        except Exception:
            pass

    payload = {"ok": True, "overall": overall, "risky": risky}
    cache.set(cache_key, payload, 300)  # 5 minutes
    return JsonResponse(payload)
