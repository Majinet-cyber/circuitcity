# circuitcity/inventory/api.py
from datetime import timedelta
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views.decorators.cache import cache_page

# If you want auth, wrap with @login_required (and handle 302 in frontend).
# from django.contrib.auth.decorators import login_required

SAFE_EMPTY = {"ok": True, "predictions": [], "detail": "no data yet"}

@require_GET
@cache_page(60 * 5)  # cache 5 minutes to keep it fast; adjust as needed
def predictions_summary(request):
    """
    Returns simple AI-like recommendations based on recent sales velocity.
    Gracefully degrades to empty results if tables or data are missing.

    Response:
    {
      "ok": true,
      "generated_at": "...",
      "horizon_days": 30,
      "predictions": [
        {
          "sku": "TECNO-Spark10",
          "model_name": "Tecno Spark 10",
          "recommended_restock": 12,
          "reason": "High 30d sales vs low on-hand",
          "stats": {"sold_30d": 27, "on_hand": 5, "avg_daily": 0.9}
        },
        ...
      ]
    }
    """
    now = timezone.now()
    horizon_days = int(request.GET.get("days", 30))
    since = now - timedelta(days=horizon_days)

    # Try to import models but *never* crash if schema changes.
    try:
        from .models import Stock, StockTransaction  # adjust to your actual models
    except Exception:
        return JsonResponse(SAFE_EMPTY, status=200)

    # Guard: fields may differ per schema; try best-effort access
    try:
        # --- Example logic (adapt if your schema differs) ---
        # Assumptions:
        # - Stock has fields: sku, model_name (or name), quantity (on-hand)
        # - StockTransaction records sales with:
        #       type='sold' (or negative quantity)
        #       model FK or sku + created_at timestamp
        # You can modify the query to match your real schema.
        from django.db.models import Sum, F
        from django.db.models.functions import Coalesce

        sold_qs = (
            StockTransaction.objects
            .filter(type__iexact="sold", created_at__gte=since)
            .values("sku", "model_name")
            .annotate(sold_30d=Coalesce(Sum("quantity"), 0))
        )

        on_hand_map = {
            (s.sku, getattr(s, "model_name", getattr(s, "name", s.sku))): s.quantity
            for s in Stock.objects.all()
        }

        preds = []
        for row in sold_qs:
            sku = row["sku"]
            mname = row.get("model_name") or sku
            sold_30d = int(row["sold_30d"]) if row["sold_30d"] else 0
            avg_daily = round(sold_30d / max(1, horizon_days), 2)
            on_hand = int(on_hand_map.get((sku, mname), 0))

            # Simple “AI-like” rule: keep ~2 weeks of cover based on recent velocity.
            target_cover_days = 14
            target_stock = int(round(avg_daily * target_cover_days))
            recommended = max(0, target_stock - on_hand)

            if recommended > 0:
                preds.append({
                    "sku": sku,
                    "model_name": mname,
                    "recommended_restock": recommended,
                    "reason": "High {}d sales vs low on-hand".format(horizon_days),
                    "stats": {
                        "sold_30d": sold_30d,
                        "on_hand": on_hand,
                        "avg_daily": avg_daily,
                    },
                })

        # Sort by biggest gap first
        preds.sort(key=lambda x: x["recommended_restock"], reverse=True)

        return JsonResponse({
            "ok": True,
            "generated_at": now.isoformat(),
            "horizon_days": horizon_days,
            "predictions": preds,
        }, status=200)

    except Exception as e:
        # Never 500—always a safe response + minimal hint for logs
        return JsonResponse({
            "ok": True,
            "predictions": [],
            "detail": "predictions failed gracefully",
            "hint": str(e)[:200],
        }, status=200)
