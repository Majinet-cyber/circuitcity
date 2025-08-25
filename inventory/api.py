# inventory/api.py
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.http import require_GET
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

    today = timezone.now().date()
    horizon = today + timedelta(days=days)

    # ----- Overall (store-level) forecast for the next N days -----
    overall_qs = (
        Forecast.objects
        .filter(product__isnull=True, date__gte=today, date__lte=horizon)
        .order_by("date")
        .values("date", "predicted_units", "predicted_revenue")
    )

    # Serialize dates to ISO and coerce numbers safely
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
    # Limit to first 100 products as in your original code (tune if needed)
    for p in Product.objects.all()[:100]:
        try:
            s = stockout_and_restock(p, horizon_days=days, lead_days=lead_days)
        except Exception:
            # If the service raises, skip this product rather than failing the whole response
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
    # (note: sorting by (not urgent) puts urgent=True before False)
    risky.sort(key=lambda x: (not x["urgent"], x["stockout_date"] or horizon.isoformat()))
    risky = risky[:risky_limit]

    return JsonResponse({
        "ok": True,
        "overall": overall,
        "risky": risky,
    })
