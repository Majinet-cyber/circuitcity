# inventory/views_export.py
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django.utils import timezone
from django.db.models import Q
from django.views.decorators.cache import never_cache

from cc.csvutils import stream_csv
from .models import InventoryItem, InventoryAudit, Product


# ---- Local permission helpers (keep lightweight & consistent with views.py) ----
def _is_manager_or_admin(user) -> bool:
    return bool(getattr(user, "is_staff", False)) or user.groups.filter(name__in=["Admin", "Manager"]).exists()


def _is_auditor(user) -> bool:
    return user.groups.filter(name__in=["Auditor", "Auditors"]).exists()


def _can_view_all(user) -> bool:
    return _is_manager_or_admin(user) or _is_auditor(user)


def _inv_base(show_archived: bool):
    """
    Mirror the stock_list/export logic:
      - if archived=1 -> all objects manager
      - else prefer InventoryItem.active, then fallback to is_active=True, else all
    """
    if show_archived:
        return InventoryItem.objects
    if hasattr(InventoryItem, "active"):
        return InventoryItem.active
    try:
        return InventoryItem.objects.filter(is_active=True)
    except Exception:
        return InventoryItem.objects


@never_cache
@login_required
def export_inventory_csv(request: HttpRequest):
    """
    CSV export of inventory items with flexible filtering and permission-aware scoping.

    Query params supported (all optional):
      - q: free text (imei, product brand/model/variant/name/code, location, agent)
      - status: exact status filter (e.g., IN_STOCK or SOLD)
      - location: id or name (iexact)
      - product: id or code/name/model text
      - date_from, date_to: received_at range (YYYY-MM-DD)
      - archived=1: include archived items (default: active only)
    """
    show_archived = request.GET.get("archived") == "1"
    base = _inv_base(show_archived)

    qs = base.select_related("product", "current_location", "assigned_agent")

    # Permission scope
    if not _can_view_all(request.user):
        qs = qs.filter(assigned_agent=request.user)

    # Status
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    # Location (id or name)
    loc = request.GET.get("location")
    if loc:
        if str(loc).isdigit():
            qs = qs.filter(current_location_id=int(loc))
        else:
            qs = qs.filter(current_location__name__iexact=loc)

    # Product (id or code/name/brand/model)
    prod = request.GET.get("product")
    if prod:
        if str(prod).isdigit():
            qs = qs.filter(product_id=int(prod))
        else:
            qs = qs.filter(
                Q(product__code__iexact=prod) |  # if 'code' exists
                Q(product__name__icontains=prod) |  # if 'name' exists
                Q(product__brand__icontains=prod) |
                Q(product__model__icontains=prod) |
                Q(product__variant__icontains=prod)
            )

    # Received date range
    df = request.GET.get("date_from")
    if df:
        qs = qs.filter(received_at__gte=df)

    dt = request.GET.get("date_to")
    if dt:
        qs = qs.filter(received_at__lte=dt)

    # Free text search
    q = request.GET.get("q")
    if q:
        qs = qs.filter(
            Q(imei__icontains=q) |
            Q(product__name__icontains=q) |       # if 'name' exists
            Q(product__brand__icontains=q) |
            Q(product__model__icontains=q) |
            Q(product__variant__icontains=q) |
            Q(product__code__icontains=q) |       # if 'code' exists
            Q(current_location__name__icontains=q) |
            Q(assigned_agent__username__icontains=q)
        )

    # Sensible ordering
    qs = qs.order_by("-received_at", "product__brand", "product__model", "product__variant")

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

            # Derive a display name that's robust whether Product.name exists or not
            product_name = (
                getattr(prod, "name", "")  # type: ignore[attr-defined]
                or " ".join(
                    part for part in [
                        getattr(prod, "brand", ""),
                        getattr(prod, "model", ""),
                        getattr(prod, "variant", "")
                    ] if part
                ).strip()
            )

            yield [
                it.id,
                (it.imei or ""),
                product_name,
                getattr(prod, "brand", ""),
                getattr(prod, "model", ""),
                getattr(prod, "variant", ""),
                getattr(loc, "name", ""),
                it.status,
                received.isoformat() if hasattr(received, "isoformat") else (str(received) if received else ""),
                "" if it.order_price is None else f"{it.order_price}",
                "" if it.selling_price is None else f"{it.selling_price}",
                (getattr(agent, "username", "") if agent else ""),
                sold_at.isoformat() if hasattr(sold_at, "isoformat") else (str(sold_at) if sold_at else ""),
            ]

    fname = f"inventory_export_{timezone.now():%Y%m%d_%H%M}.csv"
    return stream_csv(rows(), fname)


@never_cache
@login_required
def export_audits_csv(request: HttpRequest):
    """
    CSV export of inventory audits, permission-aware.

    Query params supported (all optional):
      - q: free text across details, imei, product name/brand/model, location
      - action: exact action code
      - by: user id (numeric)
      - date_from, date_to: filter a.at date range (YYYY-MM-DD)
    """
    qs = (InventoryAudit.objects
          .select_related("item", "by_user", "item__product", "item__current_location"))

    # Permission scope: non-managers see their own activity or audits for items they hold
    if not _can_view_all(request.user):
        qs = qs.filter(
            Q(by_user=request.user) |
            Q(item__assigned_agent=request.user)
        )

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
            Q(item__product__name__icontains=q) |      # if 'name' exists
            Q(item__product__brand__icontains=q) |
            Q(item__product__model__icontains=q) |
            Q(item__current_location__name__icontains=q)
        )

    qs = qs.order_by("-at", "-id")

    header = ["id", "at", "action", "item_id", "imei", "product", "location", "by_user", "details"]

    def rows():
        yield header
        for a in qs.iterator():
            item = a.item
            prod = getattr(item, "product", None) if item else None
            loc = getattr(item, "current_location", None) if item else None
            at = getattr(a, "at", None)

            product_name = (
                getattr(prod, "name", "") if prod else ""
            ) or (
                " ".join(
                    part for part in [
                        getattr(prod, "brand", "") if prod else "",
                        getattr(prod, "model", "") if prod else "",
                        getattr(prod, "variant", "") if prod else "",
                    ] if part
                ).strip()
            )

            yield [
                a.id,
                at.isoformat() if hasattr(at, "isoformat") else (str(at) if at else ""),
                a.action,
                getattr(item, "id", "") if item else "",
                getattr(item, "imei", "") if item else "",
                product_name,
                (getattr(loc, "name", "") if loc else ""),
                (getattr(a.by_user, "username", "") if a.by_user else ""),
                (a.details or ""),
            ]

    fname = f"inventory_audits_{timezone.now():%Y%m%d_%H%M}.csv"
    return stream_csv(rows(), fname)


