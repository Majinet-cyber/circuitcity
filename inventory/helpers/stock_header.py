from __future__ import annotations
from decimal import Decimal
from typing import Dict
from django.db.models import Q, Sum


def compute_stock_header(request, Model) -> Dict[str, Decimal | int]:
    """
    Business-wide header metrics for the stock list.
    Returns: {"in_stock": int, "sold": int, "sum_order": Decimal, "sum_selling": Decimal}
    """

    def hasf(name: str) -> bool:
        try:
            return any(f.name == name for f in Model._meta.get_fields())
        except Exception:
            return False

    def sum_any(qs, names: tuple[str, ...]) -> Decimal:
        for n in names:
            if n and hasf(n):
                try:
                    v = qs.aggregate(_t=Sum(n))["_t"]
                    return Decimal(v or 0)
                except Exception:
                    continue
        return Decimal("0")

    # ---- base queryset (scoped to business/active/not-archived) ----
    manager = getattr(Model, "_base_manager", Model.objects)
    qs = manager.all()

    biz_id = (
        getattr(request, "business_id", None)
        or getattr(getattr(request, "business", None), "id", None)
    )
    if biz_id:
        if hasf("business_id"):
            qs = qs.filter(business_id=biz_id)
        elif hasf("business"):
            qs = qs.filter(business__id=biz_id)

    if hasf("is_active"):
        qs = qs.filter(is_active=True)
    if hasf("archived"):
        qs = qs.filter(archived=False)

    # optional location filter (opt-in)
    loc_id = request.GET.get("location") or request.GET.get("location_id")
    if loc_id:
        for fk in ("current_location", "location", "store", "branch"):
            if hasf(f"{fk}_id"):
                qs = qs.filter(**{f"{fk}_id": loc_id})
                break
            if hasf(fk):
                qs = qs.filter(**{fk: loc_id})
                break

    # ---- SOLD predicate (OR of many possible signals) ----
    sold_q = Q(pk__in=[])  # start empty; OR in signals
    if hasf("sold_at"):
        sold_q |= Q(sold_at__isnull=False)
    if hasf("status"):
        sold_q |= Q(status__iexact="sold")
    if hasf("is_sold"):
        sold_q |= Q(is_sold=True)
    if hasf("in_stock"):
        sold_q |= Q(in_stock=False)
    # if a final price exists, treat as sold (covers your current data)
    price_fields = ("selling_price", "sale_price", "price")
    for pf in price_fields:
        if hasf(pf):
            sold_q |= Q(**{f"{pf}__isnull": False}) & ~Q(**{pf: 0})

    # ---- IN-STOCK predicate (AND of positive signals) ----
    instock_q = Q()
    added = False
    if hasf("sold_at"):
        instock_q &= Q(sold_at__isnull=True); added = True
    if hasf("status"):
        instock_q &= ~Q(status__iexact="sold"); added = True
    if hasf("is_sold"):
        instock_q &= Q(is_sold=False); added = True
    if hasf("in_stock"):
        instock_q &= Q(in_stock=True); added = True
    if hasf("quantity"):
        instock_q &= Q(quantity__gt=0); added = True
    if hasf("qty"):
        instock_q &= Q(qty__gt=0); added = True
    if not added:
        instock_q = ~Q(pk__in=[])  # fallback: everything

    # ---- compute metrics ----
    sold_qs = qs.filter(sold_q)
    instock_qs = qs.filter(instock_q)

    return {
        "in_stock": int(instock_qs.count()),
        "sold": int(sold_qs.count()),
        "sum_order": sum_any(instock_qs, ("order_price", "order_cost", "cost_price", "purchase_price", "buy_price")),
        "sum_selling": sum_any(sold_qs, price_fields),
    }
