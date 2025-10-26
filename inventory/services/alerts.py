# inventory/services/alerts.py
from __future__ import annotations

from decimal import Decimal
from hashlib import sha1
from typing import Iterable, Optional, Any, Tuple, Dict
from datetime import timedelta

from django.utils import timezone
from django.db.models import Sum, F, QuerySet


# ---------------------------------------------------------------------------
# Best-effort import of the Alert model (and optional Business/Wallet types)
# ---------------------------------------------------------------------------
try:
    from ..models import Alert  # noqa: F401
except Exception:  # pragma: no cover
    Alert = None  # type: ignore

# Optional: your codebase may have these; we never hard-require them.
try:
    from tenants.models import Business  # type: ignore
except Exception:  # pragma: no cover
    Business = Any  # type: ignore


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
Decimal0 = Decimal("0")
_NOW = timezone.now


def _d(val: Any, default: Decimal = Decimal0) -> Decimal:
    """Coerce numbers/strings to Decimal safely."""
    try:
        if val is None:
            return default
        if isinstance(val, Decimal):
            return val
        return Decimal(str(val))
    except Exception:
        return default


def _today() -> timezone.datetime:
    return _NOW()


def _sum(queryset: QuerySet, field_names: Tuple[str, ...]) -> Decimal:
    """
    Sum the first field present in the queryset's model. If none exist, returns 0.
    """
    if not hasattr(queryset, "model"):
        return Decimal0
    model_fields = {f.name for f in getattr(queryset.model, "_meta").fields}  # type: ignore
    for name in field_names:
        if name in model_fields:
            try:
                agg = queryset.aggregate(total=Sum(name))
                return _d(agg.get("total"))
            except Exception:
                continue
    # Try dynamic F() expression fallbacks (rare)
    for name in field_names:
        try:
            agg = queryset.aggregate(total=Sum(F(name)))
            return _d(agg.get("total"))
        except Exception:
            continue
    return Decimal0


def _first_existing_field(obj: Any, candidates: Tuple[str, ...]) -> Optional[str]:
    """Return the first attribute from candidates found on obj (or obj.model fields for QS)."""
    try:
        if isinstance(obj, QuerySet):
            fields = {f.name for f in obj.model._meta.fields}  # type: ignore
            for c in candidates:
                if c in fields:
                    return c
        else:
            for c in candidates:
                if hasattr(obj, c):
                    return c
    except Exception:
        pass
    return None


def _hash_key(*parts: str) -> str:
    h = sha1()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Alert emission (idempotent by dedupe_key within a TTL window)
# ---------------------------------------------------------------------------
def emit_alert(
    biz: Any,
    kind: str,
    title: str,
    body: str = "",
    *,
    severity: str = "warn",
    dedupe_key: Optional[str] = None,
    ttl_hours: int = 48,
) -> Optional[Any]:
    """
    Create an Alert row if the same (kind+key) wasn't created in the last ttl_hours.
    Returns the Alert instance or None if Alert model missing.
    """
    if Alert is None:
        # Soft-fail if model not available
        return None

    key = dedupe_key or _hash_key(kind, title, body)
    since = _today() - timedelta(hours=max(1, ttl_hours))

    try:
        # Look for an existing alert for this business in TTL window
        existing = (
            Alert.objects.filter(business=biz, alert_type=kind, created_at__gte=since)
            .only("id", "title", "body", "created_at")
        )
        for a in existing:
            # naive match; if your model has an explicit dedupe_key, prefer that
            if a.title == title and (not body or a.body == body):
                return a

        obj = Alert.objects.create(
            business=biz,
            alert_type=kind,
            title=title,
            body=body or "",
            severity=severity,
            created_at=_today(),
        )
        return obj
    except Exception:
        # Never break the page if alerts table is absent
        return None


# ---------------------------------------------------------------------------
# CFO Signals
# ---------------------------------------------------------------------------
def _avg_daily_sales_30d(sales_qs: Optional[QuerySet]) -> Decimal:
    """
    Compute average daily sales for the last 30 days from a sales queryset.
    Tries common field names: amount/total/grand_total/price.
    """
    if not sales_qs:
        return Decimal0

    try:
        since = _today() - timedelta(days=30)
        qs = sales_qs.filter(created_at__gte=since) if _first_existing_field(sales_qs, ("created_at",)) else sales_qs
    except Exception:
        qs = sales_qs

    total = _sum(qs, ("amount", "total", "grand_total", "price", "value"))
    return (total / Decimal("30")) if total > 0 else Decimal0


def _format_days(val: Decimal) -> str:
    try:
        return f"{int(val)}"
    except Exception:
        return "0"


def _get_bank_balance_default(biz: Any) -> Decimal:
    """
    Best-effort: try to pull a wallet/cash balance if caller didn't pass one.
    If not available, returns 0.
    """
    # If your Business has `.wallet_balance` or `.cash_balance`, use it.
    for attr in ("wallet_balance", "cash_balance", "bank_balance", "balance"):
        try:
            v = getattr(biz, attr, None)
            if v is not None:
                return _d(v)
        except Exception:
            pass
    # If you have a Wallet model, you could import and sum here. We keep it generic.
    return Decimal0


def generate_cfo_signals(
    biz: Any,
    *,
    sales_qs: Optional[QuerySet] = None,
    stock_qs: Optional[QuerySet] = None,
    bank_balance: Optional[Decimal] = None,
    low_stock_threshold: Optional[int] = None,
    reorder_level_field: str = "reorder_level",
) -> Dict[str, int]:
    """
    Generates:
      - CFO cash runway alert (danger when <14 days)
      - Stock-low alerts for items under reorder level or threshold

    Returns a dict with counts: {"cfo": n, "stock_low": m}
    """
    made = {"cfo": 0, "stock_low": 0}

    # --- CFO runway ---
    try:
        avg_daily_sales = _avg_daily_sales_30d(sales_qs)
        cash = _d(bank_balance) if bank_balance is not None else _get_bank_balance_default(biz)
        runway_days = Decimal0 if avg_daily_sales <= 0 else (cash / avg_daily_sales)

        if avg_daily_sales > 0 and runway_days < Decimal("14"):
            title = "Low cash runway"
            body = f"Estimated runway { _format_days(runway_days) } days; consider topping up or reducing spend."
            if emit_alert(biz, "cfo_cash", title, body, severity="danger"):
                made["cfo"] += 1
    except Exception:
        # Never break dashboard
        pass

    # --- Stock low ---
    try:
        for item, reason in _iter_low_stock_items(stock_qs, low_stock_threshold, reorder_level_field):
            pname = getattr(item, "name", None) or getattr(item, "title", None) or getattr(item, "product_name", None) or "Item"
            qty = _first_value(item, ("quantity", "qty", "on_hand", "stock", "count"))
            rlevel = _first_value(item, (reorder_level_field, "reorder_point", "min_qty", "minimum"))
            title = f"Low stock: {pname}"
            desc = []
            if qty is not None:
                desc.append(f"Qty {qty}")
            if rlevel is not None:
                desc.append(f"below threshold {rlevel}")
            body = (", ".join(desc) or reason)

            # Dedupe by item id + rule
            dedupe = _hash_key("stock_low", str(getattr(item, "id", "")), str(qty), str(rlevel))
            if emit_alert(biz, "stock_low", title, body, severity="warn", dedupe_key=dedupe, ttl_hours=24):
                made["stock_low"] += 1
    except Exception:
        pass

    return made


# ---------------------------------------------------------------------------
# Stock helpers
# ---------------------------------------------------------------------------
def _first_value(obj: Any, candidates: Tuple[str, ...]) -> Optional[Any]:
    for c in candidates:
        try:
            if hasattr(obj, c):
                return getattr(obj, c)
        except Exception:
            continue
    return None


def _iter_low_stock_items(
    stock_qs: Optional[QuerySet],
    fallback_threshold: Optional[int],
    reorder_level_field: str,
) -> Iterable[Tuple[Any, str]]:
    """
    Yields (item, reason) for items that should trigger a low-stock alert.
    Tries to be compatible with common inventory schemas.

    Logic:
      - If item has `reorder_level_field` (or min_qty/reorder_point), compare qty <= level
      - Else if a global `fallback_threshold` is provided, compare qty <= fallback_threshold
    """
    if not stock_qs:
        return []

    # Find quantity-like field on the model
    qty_field = _first_existing_field(stock_qs, ("quantity", "qty", "on_hand", "stock", "count"))
    level_fields = (reorder_level_field, "reorder_point", "min_qty", "minimum")

    try:
        items = list(stock_qs[:500])  # limit to something sane for dashboard pass
    except Exception:
        try:
            items = list(stock_qs.all()[:500])
        except Exception:
            items = []

    for it in items:
        try:
            qty = _d(_first_value(it, ("quantity", "qty", "on_hand", "stock", "count")), Decimal0)
            level = _first_value(it, level_fields)
            if level is not None:
                level_d = _d(level, Decimal0)
                if qty <= level_d:
                    yield it, "qty <= reorder level"
                    continue
            if fallback_threshold is not None:
                try:
                    thr = int(fallback_threshold)
                except Exception:
                    thr = None
                if thr is not None and qty <= _d(thr, Decimal0):
                    yield it, "qty <= global threshold"
                    continue
        except Exception:
            continue
    return []


# ---------------------------------------------------------------------------
# (Optional) pruning helper
# ---------------------------------------------------------------------------
def prune_old_alerts(days: int = 90) -> int:
    """
    Delete alerts older than `days`. Returns number deleted.
    Safe no-op if Alert model is missing.
    """
    if Alert is None:
        return 0
    try:
        cutoff = _today() - timedelta(days=max(7, days))
        qs = Alert.objects.filter(created_at__lt=cutoff)
        n = qs.count()
        qs.delete()
        return n
    except Exception:
        return 0


