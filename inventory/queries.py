# circuitcity/inventory/queries.py
from __future__ import annotations

from typing import Iterable, Union, Dict, Any, Optional, Tuple, List
from django.apps import apps
from django.db.models import (
    QuerySet, Manager, Sum, Value, DecimalField, IntegerField, F, Expression, Q
)
from django.db.models.functions import Coalesce

from tenants.utils import scoped, user_is_agent
from .models import InventoryItem
from .constants import SOLD_Q, IN_STOCK_Q

# ---------------- Actor scoping ---------------- #

_AGENT_FIELD_CANDIDATES: Iterable[str] = (
    "agent",
    "sold_by",
    "created_by",
    "user",
    "owner",
    "checked_in_by",
)

def _model_has_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False

def limit_to_actor(qs: QuerySet, user) -> QuerySet:
    if not user_is_agent(user):
        return qs
    model = getattr(qs, "model", None)
    if not model:
        return qs.none()
    for field in _AGENT_FIELD_CANDIDATES:
        if _model_has_field(model, field):
            try:
                return qs.filter(**{field: user})
            except Exception:
                try:
                    return qs.filter(**{f"{field}_id": getattr(user, "id", None)})
                except Exception:
                    continue
    return qs.none()

def scoped_for_user(qs_or_manager: Union[QuerySet, Manager], request) -> QuerySet:
    qs = scoped(qs_or_manager, request)
    return limit_to_actor(qs, getattr(request, "user", None))

# ---------------- Inventory helpers ---------------- #

def inventory_qs_for_user(request) -> QuerySet:
    return scoped_for_user(InventoryItem.objects, request)

def inventory_qs_tenant(request) -> QuerySet:
    return scoped(InventoryItem.objects, request)

# ---------------- Sales discovery ---------------- #

_AMOUNT_FIELD_CANDIDATES = (
    "selling_price", "sold_price", "final_price",
    "unit_price", "price", "amount",
    "total_price", "line_total", "total",
)
_QTY_FIELD_CANDIDATES = ("quantity", "qty", "count", "units")
_DATE_FIELD_CANDIDATES = ("sold_at", "date", "created_at", "created", "timestamp")

# Likely label fields on product / line / item
_LABEL_FIELD_CANDIDATES = (
    # product relation (preferred)
    "product__model",
    "product__name",
    "product__title",
    "product__variant",
    # direct on line / item
    "model",
    "model_name",
    "device_model",
    "variant",
    "name",
    "title",
    "brand_model",  # e.g., prejoined text
)

_LINE_MODEL_NAMES = {"saleitem", "salesitem", "orderitem", "receiptitem", "transactionitem", "lineitem"}
_HEADER_MODEL_NAMES = {"sale", "sales", "order", "receipt", "transaction"}

_EXPLICIT_MODELS = (
    ("sales", "SaleItem"),
    ("sales", "Sale"),
    ("inventory", "SaleItem"),
    ("inventory", "Sale"),
    ("inventory", "ReceiptItem"),
    ("inventory", "OrderItem"),
)

def _pick_field(model, names: Iterable[str]) -> Optional[str]:
    for n in names:
        if _model_has_field(model, n):
            return n
    return None

def _amount_expr_for(model) -> Tuple[Optional[Expression], Optional[str]]:
    money = DecimalField(max_digits=14, decimal_places=2)
    f = _pick_field(model, _AMOUNT_FIELD_CANDIDATES)
    if f:
        return Coalesce(F(f), Value(0, output_field=money), output_field=money), f
    qty = _pick_field(model, _QTY_FIELD_CANDIDATES)
    unit = _pick_field(model, ("unit_price", "selling_price", "sold_price", "price", "amount"))
    if qty and unit:
        return (
            Coalesce(
                F(qty) * Coalesce(F(unit), Value(0, output_field=money)),
                Value(0, output_field=money),
                output_field=money,
            ),
            f"{qty}*{unit}",
        ), None
    return None, None

def _quantity_expr_for(model) -> Optional[Expression]:
    qf = _pick_field(model, _QTY_FIELD_CANDIDATES)
    if qf:
        return Coalesce(F(qf), Value(0, output_field=IntegerField()), output_field=IntegerField())
    return None

def _is_probably_sales_line(model) -> bool:
    return model._meta.model_name.lower() in _LINE_MODEL_NAMES

def _is_probably_sales_header(model) -> bool:
    return model._meta.model_name.lower() in _HEADER_MODEL_NAMES

def _discover_sales_models() -> Tuple[Optional[type], Optional[type]]:
    line = None
    header = None
    for m in apps.get_models():
        try:
            if _is_probably_sales_line(m):
                line = m
            elif _is_probably_sales_header(m):
                header = m
        except Exception:
            continue
    return line, header

def _first_existing_model(candidates: Iterable[Tuple[str, str]]) -> Optional[type]:
    for app_label, model_name in candidates:
        try:
            m = apps.get_model(app_label, model_name)
            if m is not None:
                return m
        except Exception:
            continue
    return None

def _best_sales_qs(request, include_actor: bool = True) -> Optional[QuerySet]:
    explicit_line = _first_existing_model([t for t in _EXPLICIT_MODELS if t[1].lower().endswith("item")])
    explicit_head = _first_existing_model([t for t in _EXPLICIT_MODELS if not t[1].lower().endswith("item")])

    if explicit_line:
        return scoped_for_user(explicit_line.objects, request) if include_actor else scoped(explicit_line.objects, request)
    if explicit_head:
        return scoped_for_user(explicit_head.objects, request) if include_actor else scoped(explicit_head.objects, request)

    line, head = _discover_sales_models()
    if line:
        return scoped_for_user(line.objects, request) if include_actor else scoped(line.objects, request)
    if head:
        return scoped_for_user(head.objects, request) if include_actor else scoped(head.objects, request)
    return None

# ---------------- KPIs ---------------- #

def business_metrics(request, *, include_agent_scope: bool = True) -> Dict[str, Any]:
    money = DecimalField(max_digits=14, decimal_places=2)

    base_inv = inventory_qs_for_user(request) if include_agent_scope else inventory_qs_tenant(request)
    qs_instock = base_inv.filter(IN_STOCK_Q())
    sum_order = qs_instock.aggregate(
        total=Coalesce(Sum("order_price"), Value(0, output_field=money), output_field=money)
    )["total"] or 0

    qs_sales = _best_sales_qs(request, include_agent_scope)
    if qs_sales is not None:
        amt_expr, _ = _amount_expr_for(qs_sales.model)
        qty_expr = _quantity_expr_for(qs_sales.model)

        sold_filter = Q()
        for f in _DATE_FIELD_CANDIDATES:
            if _model_has_field(qs_sales.model, f):
                sold_filter |= Q(**{f"{f}__isnull": False})
        if _model_has_field(qs_sales.model, "status"):
            sold_filter |= Q(status__iexact="sold") | Q(status__istartswith="sold")
        if sold_filter:
            qs_sales = qs_sales.filter(sold_filter)

        sum_selling = 0
        if amt_expr is not None:
            sum_selling = qs_sales.aggregate(
                total=Coalesce(Sum(amt_expr), Value(0, output_field=money), output_field=money)
            )["total"] or 0

        if qty_expr is not None:
            count_sold = int(qs_sales.aggregate(
                n=Coalesce(Sum(qty_expr), Value(0, output_field=IntegerField()), output_field=IntegerField())
            )["n"] or 0)
        else:
            count_sold = qs_sales.count()

        return {
            "count_instock": qs_instock.count(),
            "count_sold": count_sold,
            "sum_order": float(sum_order),
            "sum_selling": float(sum_selling),
        }

    qs_sold = base_inv.filter(SOLD_Q())
    inv_amount_field = None
    for name in _AMOUNT_FIELD_CANDIDATES:
        if _model_has_field(InventoryItem, name):
            inv_amount_field = name
            break

    if inv_amount_field:
        sum_selling = base_inv.filter(SOLD_Q()).aggregate(
            total=Coalesce(Sum(inv_amount_field), Value(0, output_field=money), output_field=money)
        )["total"] or 0
    else:
        sum_selling = 0

    return {
        "count_instock": qs_instock.count(),
        "count_sold": qs_sold.count(),
        "sum_order": float(sum_order),
        "sum_selling": float(sum_selling),
    }

# ---------------- Top models (for charts/cards) ---------------- #

def _first_usable_group_field(qs: QuerySet, candidates: Iterable[str]) -> Optional[str]:
    """
    Return the first candidate that works in qs.values(<field>).
    This lets us try 'product__model', then fallback to direct fields etc.
    """
    for c in candidates:
        try:
            # touch the queryset to validate the path; won't execute until evaluation
            qs.values(c)  # type: ignore[arg-type]
            return c
        except Exception:
            continue
    return None

def top_models(request, *, limit: int = 8, include_agent_scope: bool = True) -> List[Dict[str, Any]]:
    """
    Returns [{label: 'Tecno Camon 20', units: 12}, ...] for the chart.
    Prefers sales line-items; falls back to InventoryItem SOLD().
    """
    qs_sales = _best_sales_qs(request, include_agent_scope)
    qty_int = IntegerField()

    if qs_sales is not None:
        # Restrict to sold-ish
        sold_filter = Q()
        for f in _DATE_FIELD_CANDIDATES:
            if _model_has_field(qs_sales.model, f):
                sold_filter |= Q(**{f"{f}__isnull": False})
        if _model_has_field(qs_sales.model, "status"):
            sold_filter |= Q(status__iexact="sold") | Q(status__istartswith="sold")
        if sold_filter:
            qs_sales = qs_sales.filter(sold_filter)

        qty_expr = _quantity_expr_for(qs_sales.model) or Value(1, output_field=qty_int)

        group_field = _first_usable_group_field(qs_sales, _LABEL_FIELD_CANDIDATES)
        if group_field is None:
            # no usable label on the sales model → fall back to inventory items
            qs_sales = None
        else:
            rows = (
                qs_sales.values(group_field)
                .annotate(units=Coalesce(Sum(qty_expr), Value(0, output_field=qty_int), output_field=qty_int))
                .order_by("-units")[:limit]
            )
            out = []
            for r in rows:
                label = r.get(group_field, "") or "Unknown"
                out.append({"label": str(label), "units": int(r.get("units") or 0)})
            return out

    # Fallback: derive from InventoryItem (brand + model best-effort)
    base_inv = inventory_qs_for_user(request) if include_agent_scope else inventory_qs_tenant(request)
    base_inv = base_inv.filter(SOLD_Q())

    # Try to construct a decent label: brand + model if both exist; else whichever exists; else name/title
    label_candidates = []
    if _model_has_field(InventoryItem, "brand") and _model_has_field(InventoryItem, "model"):
        # Build a concatenated label in DB when possible
        label_candidates = ["brand", "model"]  # will combine in Python below
    else:
        for c in ("model", "device_model", "model_name", "name", "title"):
            if _model_has_field(InventoryItem, c):
                label_candidates = [c]
                break

    if not label_candidates:
        # No recognizable label fields at all → count by id (will show Unknown)
        rows = (
            base_inv.values("id")
            .annotate(units=Value(1, output_field=qty_int))
            .order_by("-units")[:limit]
        )
        return [{"label": "Unknown", "units": int(sum(r["units"] for r in rows))}]

    if label_candidates == ["brand", "model"]:
        # Fetch both and combine to a label in Python
        rows = (
            base_inv.values("brand", "model")
            .annotate(units=Coalesce(Sum(Value(1, output_field=qty_int)), Value(1, output_field=qty_int)))
            .order_by("-units")[: (limit * 3)]  # overfetch to de-dup blank combos
        )
        agg: Dict[str, int] = {}
        for r in rows:
            b = (r.get("brand") or "").strip()
            m = (r.get("model") or "").strip()
            label = (f"{b} {m}").strip() or "Unknown"
            agg[label] = agg.get(label, 0) + int(r.get("units") or 0)
        top = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [{"label": k, "units": v} for k, v in top]

    # Single field candidate path
    field = label_candidates[0]
    rows = (
        base_inv.values(field)
        .annotate(units=Coalesce(Sum(Value(1, output_field=qty_int)), Value(1, output_field=qty_int)))
        .order_by("-units")[:limit]
    )
    return [{"label": str(r.get(field) or "Unknown"), "units": int(r.get("units") or 0)}]
