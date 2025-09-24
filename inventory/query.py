# inventory/query.py
from datetime import timedelta
from django.db.models import Q, Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Inventory, Sale  # adjust if your Sale model lives elsewhere


def base_scope(request):
    """
    Returns (biz, qs) for the active business, already scoped to that business.
    Never filter by location here; views can further clamp when needed.
    """
    biz = getattr(request, "active_business", None) or getattr(request, "business", None)
    qs = Inventory.objects.all()
    if biz:
        qs = qs.filter(business=biz)
    return biz, qs


def build_inventory_queryset(
    request,
    *,
    search: str = "",
    status: str = "all",
    include_archived: bool = False,
    location_id: int | None = None,
):
    """
    Single source of truth for Stock queries.
    - status in {"all","in_stock","sold","layby","returned","lost"} (case-insensitive)
    - search matches IMEI, brand, model, product name, etc.
    """
    _, qs = base_scope(request)

    if not include_archived:
        qs = qs.filter(is_archived=False)

    if location_id:
        qs = qs.filter(location_id=location_id)

    st = (status or "all").lower()
    if st != "all":
        qs = qs.filter(status=st)  # status is stored as lowercase string in your DB

    q = (search or "").strip()
    if q:
        qs = qs.filter(
            Q(imei__icontains=q)
            | Q(product__name__icontains=q)
            | Q(product__brand__icontains=q)
            | Q(product__model__icontains=q)
        )

    return qs


def dashboard_counts(request):
    """Products, Items in stock, Sales MTD etc., all consistent with build_inventory_queryset."""
    biz, inv = base_scope(request)
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    items_in_stock = inv.filter(status="in_stock", is_archived=False).count()

    # "Products" = DISTINCT SKUs currently present (any status, not archived) for this business
    products = (
        inv.filter(is_archived=False)
           .values("product_id")
           .distinct()
           .count()
    )

    sales_mtd = (
        Sale.objects.filter(business=biz, sold_at__gte=month_start)
        .aggregate(total=Coalesce(Sum("final_amount"), 0))["total"]
        if biz else 0
    )

    return {
        "products": products,
        "items_in_stock": items_in_stock,
        "sales_mtd": sales_mtd,
    }


def sales_in_range(request, *, days: int = 7):
    """For dashboard filters like 'Last 7 days'."""
    biz, _ = base_scope(request)
    if not biz:
        return 0
    since = timezone.now() - timedelta(days=days)
    return (
        Sale.objects.filter(business=biz, sold_at__gte=since)
        .aggregate(total=Coalesce(Sum("final_amount"), 0))["total"]
    )
