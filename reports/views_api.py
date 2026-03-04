from __future__ import annotations
from datetime import timedelta
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count, F, Q, DecimalField
from django.db.models.functions import TruncDay, TruncMonth, Coalesce
from django.http import JsonResponse
from django.utils import timezone

from .views import ReportFilters, _is_staff_or_auditor
from sales.models import Sale
from inventory.models import InventoryItem

def _apply_filters(qs, f: ReportFilters):
    if f.date_from: qs = qs.filter(created_at__gte=f.date_from)
    if f.date_to:   qs = qs.filter(created_at__lt=f.date_to + timedelta(days=1))
    if f.agent_id:  qs = qs.filter(agent_id=f.agent_id)
    if f.model_q:   qs = qs.filter(model__icontains=f.model_q)
    if f.channel:   qs = qs.filter(channel=f.channel)
    if f.ads == "with":
        qs = qs.filter(Q(had_ads=True) | Q(ad_source__isnull=False))
    elif f.ads == "without":
        qs = qs.filter(Q(had_ads=False) | Q(ad_source__isnull=True))
    return qs

@login_required
@user_passes_test(_is_staff_or_auditor)
def sales_summary_api(request):
    f = ReportFilters.from_request(request)
    base = _apply_filters(Sale.objects.all(), f)

    kpis = base.aggregate(
        total_sales=Coalesce(Sum("amount"), 0),
        total_profit=Coalesce(Sum("profit"), 0),
        orders=Coalesce(Count("id"), 0),
    )

    # Sales by month (MWK). Nice for long ranges.
    by_month = (
        base.annotate(m=TruncMonth("created_at"))
            .values("m")
            .annotate(amount=Coalesce(Sum("amount"), 0))
            .order_by("m")
    )
    return JsonResponse({"kpis": kpis, "by_month": list(by_month)})

@login_required
@user_passes_test(_is_staff_or_auditor)
def profit_trend_api(request):
    f = ReportFilters.from_request(request)
    base = _apply_filters(Sale.objects.all(), f)
    by_day = (
        base.annotate(d=TruncDay("created_at"))
            .values("d")
            .annotate(
                profit=Coalesce(Sum("profit"), 0),
                amount=Coalesce(Sum("amount"), 0),
            )
            .order_by("d")
    )
    return JsonResponse({"series": list(by_day)})

@login_required
@user_passes_test(_is_staff_or_auditor)
def agent_performance_api(request):
    f = ReportFilters.from_request(request)
    base = _apply_filters(Sale.objects.select_related("agent"), f)
    rows = (
        base.values("agent_id", "agent__name")
            .annotate(
                amount=Coalesce(Sum("amount"), 0),
                profit=Coalesce(Sum("profit"), 0),
                orders=Count("id"),
            )
            .order_by("-amount")[:50]
    )
    return JsonResponse({"rows": list(rows)})

@login_required
@user_passes_test(_is_staff_or_auditor)
def inventory_velocity_api(request):
    f = ReportFilters.from_request(request)
    # sold vs time vs model vs agent â†’ group by model, recent period
    base = _apply_filters(Sale.objects.all(), f)
    rows = (
        base.values("model")
            .annotate(
                sold=Count("id"),
                amount=Coalesce(Sum("amount"), 0),
            )
            .order_by("-sold")[:100]
    )
    return JsonResponse({"rows": list(rows)})

@login_required
@user_passes_test(_is_staff_or_auditor)
def ads_roi_api(request):
    f = ReportFilters.from_request(request)
    base = _apply_filters(Sale.objects.all(), f)

    # If you track ad spend per ad_source in another model, join it; here, a simple split:
    with_ads = base.filter(Q(had_ads=True) | Q(ad_source__isnull=False))
    no_ads   = base.filter(Q(had_ads=False) | Q(ad_source__isnull=True))

    agg_ads   = with_ads.aggregate(amount=Coalesce(Sum("amount"),0), profit=Coalesce(Sum("profit"),0), orders=Count("id"))
    agg_noads = no_ads.aggregate(amount=Coalesce(Sum("amount"),0), profit=Coalesce(Sum("profit"),0), orders=Count("id"))

    return JsonResponse({"with_ads": agg_ads, "without_ads": agg_noads})


