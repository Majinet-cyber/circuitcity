from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.utils.timezone import now
from datetime import timedelta
from django.db.models import Count, Sum, F
from .models import ForecastItem, ReorderAdvice, Notification
from inventory.models import Sale

@require_GET
def api_forecast(request):
    store = int(request.GET["store"])
    product = int(request.GET["product"])
    horizon = int(request.GET.get("horizon", 14))
    items = list(ForecastItem.objects.filter(store_id=store, product_id=product)
                 .order_by("date").values("date","yhat","ylo","yhi")[:horizon])
    return JsonResponse({"store":store, "product":product, "horizon":horizon, "daily":items})

@require_GET
def api_leaderboard(request):
    period = request.GET.get("period","week")
    metric = request.GET.get("metric","units")
    start = (now() - timedelta(days=now().weekday())).date() if period == "week" else now().date().replace(day=1)

    rows = (Sale.objects.filter(sold_at__date__gte=start)
            .values("agent_id","agent__name")
            .annotate(units=Count("id"),
                      revenue=Sum("sale_price"),
                      profit=Sum(F("sale_price")-F("cost_price")))
            .order_by("-"+metric))
    data = [{"agent_id":r["agent_id"], "name":r["agent__name"], "units":r["units"],
             "revenue":float(r["revenue"] or 0), "profit":float(r["profit"] or 0),
             "rank": i+1} for i, r in enumerate(rows)]
    return JsonResponse({"period":period, "metric":metric, "rows":data})

@require_GET
def api_alerts(request):
    # latest 20 alerts for current user
    user = request.user
    rows = list(Notification.objects.filter(user=user).order_by("-created_at")[:20]
                .values("id","kind","title","body","severity","created_at","read_at"))
    return JsonResponse({"alerts": rows})


