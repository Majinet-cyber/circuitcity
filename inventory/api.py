# inventory/api.py
from datetime import timedelta
from django.contrib.auth.models import Group
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.utils import timezone

from sales.models import Sale
from .models import InventoryItem
from django.db.models.functions import TruncDate


def _is_manager_or_admin(user):
    # mirrors views._is_manager_or_admin without importing views (avoid circulars)
    try:
        return user.is_staff or user.groups.filter(name__in=["Admin", "Manager"]).exists()
    except Exception:
        return bool(getattr(user, "is_staff", False))


def _can_view_all(user):
    # mirrors views._can_view_all (Manager/Admin or Auditor)
    try:
        return _is_manager_or_admin(user) or user.groups.filter(name__in=["Auditor", "Auditors"]).exists()
    except Exception:
        return _is_manager_or_admin(user)


def predictions_summary(request):
    """
    Baseline forecast + stockout risk.
    Response shape:
    {
      "ok": true,
      "overall": [{"date": "YYYY-MM-DD", "predicted_units": n, "predicted_revenue": x}, ... 7 days],
      "risky": [{"product": "Brand Model", "on_hand": n, "stockout_date": "YYYY-MM-DD",
                 "suggested_restock": n, "urgent": bool}, ...]
    }
    """
    try:
        today = timezone.localdate()
        lookback_days = 14
        start = today - timedelta(days=lookback_days)
        end_excl = today + timedelta(days=1)

        sales = Sale.objects.select_related("item__product").filter(sold_at__gte=start, sold_at__lt=end_excl)
        items = InventoryItem.objects.select_related("product").filter(status="IN_STOCK")

        if not _can_view_all(request.user):
            sales = sales.filter(agent=request.user)
            items = items.filter(assigned_agent=request.user)

        # ----- Daily units average (last 14d)
        per_day_counts = (
            sales.annotate(d=TruncDate("sold_at"))
                 .values("d")
                 .annotate(c=Count("id"))
        )
        total_units_14 = sum(r["c"] for r in per_day_counts) or 0
        daily_units_avg = total_units_14 / float(lookback_days)

        # ----- Daily revenue average (last 14d)
        per_day_rev = (
            sales.annotate(d=TruncDate("sold_at"))
                 .values("d")
                 .annotate(v=Sum("price"))
        )
        total_rev_14 = float(sum(r["v"] or 0 for r in per_day_rev))
        daily_rev_avg = total_rev_14 / float(lookback_days) if total_rev_14 else 0.0

        overall = [
            {
                "date": (today + timedelta(days=i)).isoformat(),
                "predicted_units": round(daily_units_avg, 2),
                "predicted_revenue": round(daily_rev_avg, 2),
            }
            for i in range(1, 8)
        ]

        # ----- Model-level stockout risk (simple 14d usage rate)
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

    except Exception as e:
        # Never 500 the dashboard — return a harmless payload
        return JsonResponse({"ok": False, "error": f"predictions failed: {e}", "overall": [], "risky": []}, status=200)
