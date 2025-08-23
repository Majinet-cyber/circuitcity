from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from insights.models import Forecast
from insights.services import stockout_and_restock
from inventory.models import Product

def predictions_summary(request):
    today = timezone.now().date()
    horizon = today + timedelta(days=7)
    overall = list(Forecast.objects.filter(product__isnull=True, date__gte=today, date__lte=horizon)
                   .order_by("date").values("date","predicted_units","predicted_revenue"))

    # top 3 products with risk of stockout
    risky = []
    for p in Product.objects.all()[:100]:
        s = stockout_and_restock(p, horizon_days=7, lead_days=3)
        if s["stockout_date"]:
            risky.append({
                "product": getattr(p,"name", f"Product {p.id}"),
                "stockout_date": s["stockout_date"],
                "on_hand": s["on_hand"],
                "suggested_restock": s["suggested_restock"],
                "urgent": s["urgent"],
            })
    risky.sort(key=lambda x: (x["urgent"] is True, x["stockout_date"] or horizon))
    risky = risky[:3]

    return JsonResponse({"overall": overall, "risky": risky})
