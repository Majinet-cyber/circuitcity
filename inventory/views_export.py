# inventory/views_export.py
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django.db.models import Q

from cc.csvutils import stream_csv
from .models import InventoryItem, InventoryAudit


@login_required
def export_inventory_csv(request: HttpRequest):
    qs = (InventoryItem.objects
          .select_related("product", "current_location", "assigned_agent"))

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    loc = request.GET.get("location")
    if loc:
        if str(loc).isdigit():
            qs = qs.filter(current_location_id=int(loc))
        else:
            qs = qs.filter(current_location__name__iexact=loc)

    prod = request.GET.get("product")
    if prod:
        if str(prod).isdigit():
            qs = qs.filter(product_id=int(prod))
        else:
            qs = qs.filter(
                Q(product__code__iexact=prod) |
                Q(product__name__icontains=prod) |
                Q(product__model__icontains=prod)
            )

    df = request.GET.get("date_from")
    if df:
        qs = qs.filter(received_at__gte=df)

    dt = request.GET.get("date_to")
    if dt:
        qs = qs.filter(received_at__lte=dt)

    q = request.GET.get("q")
    if q:
        qs = qs.filter(
            Q(imei__icontains=q) |
            Q(product__name__icontains=q) |
            Q(product__model__icontains=q) |
            Q(product__code__icontains=q) |
            Q(current_location__name__icontains=q) |
            Q(assigned_agent__username__icontains=q)
        )

    header = [
        "id", "imei",
        "product_name", "brand", "model", "variant",
        "location", "status",
        "received_at", "order_price", "selling_price",
        "assigned_agent", "sold_at",
    ]

    def rows():
        yield header
        for it in qs.iterator():
            prod = it.product
            loc = it.current_location
            agent = it.assigned_agent
            received = getattr(it, "received_at", None)
            sold_at = getattr(it, "sold_at", None)
            yield [
                it.id,
                (it.imei or ""),
                getattr(prod, "name", "") or f"{getattr(prod, 'brand', '')} {getattr(prod, 'model', '')} {getattr(prod, 'variant', '')}".strip(),
                getattr(prod, "brand", ""),
                getattr(prod, "model", ""),
                getattr(prod, "variant", ""),
                getattr(loc, "name", ""),
                it.status,
                received.isoformat() if hasattr(received, "isoformat") else str(received or ""),
                "" if it.order_price is None else f"{it.order_price}",
                "" if it.selling_price is None else f"{it.selling_price}",
                getattr(agent, "username", "") if agent else "",
                sold_at.isoformat() if hasattr(sold_at, "isoformat") else (str(sold_at) if sold_at else ""),
            ]

    return stream_csv(rows(), "inventory.csv")


@login_required
def export_audits_csv(request: HttpRequest):
    qs = (InventoryAudit.objects
          .select_related("item", "by_user", "item__product", "item__current_location"))

    action = request.GET.get("action")
    if action:
        qs = qs.filter(action=action)

    who = request.GET.get("by")
    if who and str(who).isdigit():
        qs = qs.filter(by_user_id=int(who))

    df = request.GET.get("date_from")
    if df:
        qs = qs.filter(at__date__gte=df)

    dt = request.GET.get("date_to")
    if dt:
        qs = qs.filter(at__date__lte=dt)

    q = request.GET.get("q")
    if q:
        qs = qs.filter(
            Q(details__icontains=q) |
            Q(item__imei__icontains=q) |
            Q(item__product__name__icontains=q) |
            Q(item__current_location__name__icontains=q)
        )

    header = ["id", "at", "action", "item_id", "imei", "product", "location", "by_user", "details"]

    def rows():
        yield header
        for a in qs.iterator():
            item = a.item
            prod = getattr(item, "product", None) if item else None
            loc = getattr(item, "current_location", None) if item else None
            at = getattr(a, "at", None)
            yield [
                a.id,
                at.isoformat() if hasattr(at, "isoformat") else str(at or ""),
                a.action,
                getattr(item, "id", "") if item else "",
                getattr(item, "imei", "") if item else "",
                (getattr(prod, "name", "") if prod else ""),
                (getattr(loc, "name", "") if loc else ""),
                getattr(a.by_user, "username", "") if a.by_user else "",
                (a.details or ""),
            ]

    return stream_csv(rows(), "audits.csv")
