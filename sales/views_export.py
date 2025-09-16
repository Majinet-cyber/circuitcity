# sales/views_export.py
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q
from django.views.decorators.cache import never_cache

from cc.csvutils import stream_csv
from .utils import sales_qs_for_user


@never_cache
@login_required
def export_sales_csv(request):
    """
    CSV export of sales with flexible filtering and permission-aware scoping.

    Query params supported (all optional):
      - q: free text across IMEI, product (brand/model/variant/name), agent, location
      - date_from, date_to: SOLD date range (YYYY-MM-DD) against Sale.sold_at
      - location: id or name (iexact)
      - product: id or brand/model/variant/name text (matched via item__product)
      - agent: id or username (iexact)
    """
    # Base queryset (scoped per user permissions)
    qs = sales_qs_for_user(request.user)

    # Eager-load common relations for export
    qs = qs.select_related("item", "item__product", "agent", "location")

    # Date range (sold date)
    df = request.GET.get("date_from")
    dt = request.GET.get("date_to")
    if df:
        qs = qs.filter(sold_at__gte=df)
    if dt:
        qs = qs.filter(sold_at__lte=dt)

    # Location filter (id or name)
    loc = request.GET.get("location")
    if loc:
        if str(loc).isdigit():
            qs = qs.filter(location_id=int(loc))
        else:
            qs = qs.filter(location__name__iexact=loc)

    # Product filter (id or text)
    prod = request.GET.get("product")
    if prod:
        if str(prod).isdigit():
            qs = qs.filter(item__product_id=int(prod))
        else:
            qs = qs.filter(
                Q(item__product__name__icontains=prod) |
                Q(item__product__brand__icontains=prod) |
                Q(item__product__model__icontains=prod) |
                Q(item__product__variant__icontains=prod)
            )

    # Agent filter (id or username)
    agent = request.GET.get("agent")
    if agent:
        if str(agent).isdigit():
            qs = qs.filter(agent_id=int(agent))
        else:
            qs = qs.filter(agent__username__iexact=agent)

    # Free text search
    q = request.GET.get("q")
    if q:
        qs = qs.filter(
            Q(item__imei__icontains=q) |
            Q(item__product__name__icontains=q) |
            Q(item__product__brand__icontains=q) |
            Q(item__product__model__icontains=q) |
            Q(item__product__variant__icontains=q) |
            Q(agent__username__icontains=q) |
            Q(location__name__icontains=q)
        )

    # Sensible ordering
    qs = qs.order_by("-sold_at", "-id")

    header = [
        "id",
        "sold_at",
        "product",
        "imei",
        "price",
        "order_price",
        "profit",
        "commission_pct",
        "agent",
        "location",
    ]

    def _product_name(prod):
        if not prod:
            return ""
        # Prefer `name` if present; otherwise compose from brand/model/variant
        name = getattr(prod, "name", "") or " ".join(
            part for part in [
                getattr(prod, "brand", ""),
                getattr(prod, "model", ""),
                getattr(prod, "variant", ""),
            ] if part
        ).strip()
        return name

    def rows():
        yield header
        for s in qs.iterator():
            item = getattr(s, "item", None)
            prod = getattr(item, "product", None) if item else None
            imei = getattr(item, "imei", "") if item else ""
            price = getattr(s, "price", None)
            order_price = getattr(item, "order_price", None) if item else None
            profit = None
            try:
                if price is not None and order_price is not None:
                    profit = (price or 0) - (order_price or 0)
            except Exception:
                profit = None

            sold_at = getattr(s, "sold_at", None)
            yield [
                getattr(s, "id", ""),
                sold_at.isoformat() if hasattr(sold_at, "isoformat") else (str(sold_at) if sold_at else ""),
                _product_name(prod),
                imei or "",
                "" if price is None else f"{price}",
                "" if order_price is None else f"{order_price}",
                "" if profit is None else f"{profit}",
                getattr(s, "commission_pct", "") if getattr(s, "commission_pct", None) is not None else "",
                getattr(getattr(s, "agent", None), "username", ""),
                getattr(getattr(s, "location", None), "name", ""),
            ]

    fname = f"sales_{timezone.now():%Y%m%d_%H%M}.csv"
    return stream_csv(rows(), fname)
