# inventory/views.py
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Sum, Count, Avg, F, Q
from django.shortcuts import render

@user_passes_test(lambda u: u.is_superuser)
def super_inventory_dashboard(request):
    # Example aggregations – adapt to your actual models/fields
    from .models import InventoryItem, Product, Business, Tenant

    by_tenant = (
        InventoryItem.objects.values("business_id", "business__name")
        .annotate(
            units=Sum("quantity"),
            aging_gt_90=Sum("quantity", filter=Q(age_days__gt=90)),
            stockouts=Count("id", filter=Q(quantity__lte=0)),
        )
        .order_by("-units")[:50]
    )

    by_sku = (
        InventoryItem.objects.values("product_id", "product__name")
        .annotate(
            tenants=Count("business_id", distinct=True),
            units=Sum("quantity"),
            aging_pct=100.0 * Sum("quantity", filter=Q(age_days__gt=90)) / (Sum("quantity") + 0.0001),
        )
        .order_by("-units")[:50]
    )

    ctx = {
        "kpi": {
            "businesses": Business.objects.count(),
            "skus": Product.objects.count(),
            "units": InventoryItem.objects.aggregate(n=Sum("quantity"))["n"] or 0,
        },
        "by_tenant": by_tenant,
        "by_sku": by_sku,
    }
    return render(request, "inventory/super_dashboard.html", ctx)
