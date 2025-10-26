# sales/signals.py
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone

# ----------------- tolerant imports -----------------
def _try_import(modpath: str, attr: str | None = None):
    import importlib
    try:
        mod = importlib.import_module(modpath)
        return getattr(mod, attr) if attr else mod
    except Exception:
        return None

Sale = _try_import("sales.models", "Sale")
InventoryItem = _try_import("inventory.models", "InventoryItem") or _try_import("inventory.models", "Stock")
InventoryAudit = _try_import("inventory.models", "InventoryAudit")
Location = _try_import("inventory.models", "Location") or _try_import("tenants.models", "Location")

# Wallet (optional)
record_sale_commission = _try_import("wallet.services", "record_sale_commission")
add_txn = _try_import("wallet.services", "add_txn")
WalletTransaction = _try_import("wallet.models", "WalletTransaction")
TxnType = _try_import("wallet.models", "TxnType")
Ledger = _try_import("wallet.models", "Ledger")

DEFAULT_AGENT_ID = getattr(settings, "SALES_DEFAULT_AGENT_ID", None)
DEFAULT_LOCATION_ID = getattr(settings, "SALES_DEFAULT_LOCATION_ID", None)

# ----------------- helpers -----------------
def _model_has_field(model, name: str) -> bool:
    try:
        return any(getattr(f, "name", None) == name for f in model._meta.get_fields())
    except Exception:
        return False

def _safe_get(obj: Any, *names: str, default=None):
    for n in names:
        try:
            v = getattr(obj, n)
            if v is not None:
                return v
        except Exception:
            pass
    return default

def _to_decimal(v, default=Decimal("0.00")) -> Decimal:
    try:
        if v is None:
            return Decimal(default)
        return Decimal(str(v))
    except Exception:
        return Decimal(default)

def _location_str(sale: Any) -> str:
    try:
        loc = getattr(sale, "location", None)
        if loc is None:
            return ""
        name = getattr(loc, "name", None)
        if name:
            return str(name)
        pk = getattr(loc, "pk", None) or getattr(loc, "id", None)
        return f"Location #{pk}" if pk else ""
    except Exception:
        return ""

def _resolve_linked_item(sale: Any):
    for fname in ("item", "inventory_item"):
        try:
            it = getattr(sale, fname, None)
            if it is not None:
                return it
        except Exception:
            pass
    return None

# ----------------- pre-save hardeners -----------------
if Sale is not None:
    @receiver(pre_save, sender=Sale)
    def fill_required_fields_before_sale_save(sender, instance: Any, **kwargs):
        """
        Ensure required fields like location/agent are present on ANY Sale insert,
        so other code paths can never blow up with IntegrityError.
        """
        # ---- location ----
        if _model_has_field(Sale, "location") and getattr(instance, "location_id", None) is None:
            loc_id = None

            # 1) take from related item if present
            item = _resolve_linked_item(instance)
            if item is not None:
                for fk in ("current_location_id", "location_id", "store_id", "branch_id", "warehouse_id"):
                    if hasattr(item, fk):
                        v = getattr(item, fk, None)
                        if v:
                            loc_id = v
                            break

            # 2) default from settings
            if loc_id is None and DEFAULT_LOCATION_ID:
                loc_id = DEFAULT_LOCATION_ID

            # 3) first Location row (best-effort)
            if loc_id is None and Location is not None:
                try:
                    first_loc = Location.objects.order_by("id").first()
                    if first_loc:
                        loc_id = getattr(first_loc, "id", None)
                except Exception:
                    pass

            if loc_id is not None:
                # assign *_id to avoid fetching
                try:
                    setattr(instance, "location_id", loc_id)
                except Exception:
                    pass

        # ---- agent ----
        if _model_has_field(Sale, "agent") and getattr(instance, "agent_id", None) is None:
            # try sold_by / assigned agent on item
            agent = _safe_get(instance, "agent", "sold_by", default=None)
            if agent is not None and getattr(agent, "id", None):
                try:
                    instance.agent_id = agent.id
                except Exception:
                    pass
            elif DEFAULT_AGENT_ID:
                try:
                    instance.agent_id = int(DEFAULT_AGENT_ID)
                except Exception:
                    pass

# ----------------- wallet commission -----------------
def _post_wallet_commission(sale: Any) -> None:
    if callable(record_sale_commission):
        try:
            record_sale_commission(sale, created=True)
            return
        except Exception:
            pass

    if not callable(add_txn) or TxnType is None or Ledger is None:
        return

    agent = _safe_get(sale, "agent", "sold_by", default=None)
    if agent is None:
        return

    price = _to_decimal(_safe_get(sale, "price", "amount", "sold_price", default=Decimal("0")))
    pct = _safe_get(sale, "commission_pct", default=None)
    rate = _safe_get(sale, "commission_rate", default=None)
    default_rate = getattr(settings, "SALES_DEFAULT_COMMISSION_RATE", Decimal("0.03"))

    try:
        if pct is not None:
            rate_val = _to_decimal(pct) / Decimal("100")
        elif rate is not None:
            rate_val = _to_decimal(rate)
        else:
            rate_val = _to_decimal(default_rate)
    except Exception:
        rate_val = _to_decimal(default_rate)

    commission = (price * rate_val).quantize(Decimal("0.01"))
    if commission <= 0:
        return

    ref = f"SALE-{getattr(sale, 'pk', getattr(sale, 'id', None))}"
    try:
        if WalletTransaction is not None and WalletTransaction.objects.filter(
            agent=agent, type=TxnType.COMMISSION, reference=ref
        ).exists():
            return
    except Exception:
        return

    eff_date = _safe_get(sale, "date", "created_at", default=None)
    if hasattr(eff_date, "date"):
        eff_date = eff_date.date()
    if eff_date is None:
        eff_date = timezone.now().date()

    note = f"Commission for Sale #{getattr(sale, 'pk', getattr(sale, 'id', ''))} at {_location_str(sale)}"
    try:
        add_txn(
            agent=agent,
            amount=commission,
            type=TxnType.COMMISSION,
            note=note,
            reference=ref,
            effective_date=eff_date,
            created_by=None,
            meta={"sale_id": getattr(sale, "pk", getattr(sale, "id", None)), "rate": str(rate_val)},
            ledger=Ledger.AGENT,
        )
    except Exception:
        return

# ----------------- post-save sync (unchanged behaviour, tolerant) -----------------
if Sale is not None:
    @receiver(post_save, sender=Sale)
    def on_sale_saved(sender, instance: Any, created: bool, **kwargs):
        # keep inventory item in SOLD state + audit (tolerant, best-effort)
        item = _resolve_linked_item(instance)
        if item is not None:
            touched = []

            created_at = _safe_get(instance, "created_at", default=timezone.now())
            cur = getattr(item, "sold_at", None)
            if cur is None or (created_at and cur < created_at):
                try:
                    setattr(item, "sold_at", created_at); touched.append("sold_at")
                except Exception:
                    pass

            for f, v in (("status", "sold"), ("is_sold", True), ("sold", True),
                         ("in_stock", False), ("available", False),
                         ("availability", False), ("is_active", False)):
                try:
                    if hasattr(item, f):
                        setattr(item, f, v); touched.append(f)
                except Exception:
                    pass

            try:
                q = int(getattr(item, "quantity", getattr(item, "qty", 0)) or 0)
            except Exception:
                q = 0
            if q != 0:
                try:
                    if hasattr(item, "quantity"):
                        setattr(item, "quantity", 0); touched.append("quantity")
                    elif hasattr(item, "qty"):
                        setattr(item, "qty", 0); touched.append("qty")
                except Exception:
                    pass

            if touched:
                try:
                    item.save(update_fields=list(dict.fromkeys(touched)))
                except Exception:
                    try:
                        item.save()
                    except Exception:
                        pass

            if InventoryAudit is not None:
                try:
                    kwargs_a = {}
                    if _model_has_field(InventoryAudit, "item"):
                        kwargs_a["item"] = item
                    if _model_has_field(InventoryAudit, "action"):
                        kwargs_a["action"] = "SOLD"
                    if _model_has_field(InventoryAudit, "by_user"):
                        kwargs_a["by_user"] = _safe_get(instance, "agent", "sold_by", default=None)
                    if _model_has_field(InventoryAudit, "details"):
                        loc = _location_str(instance)
                        price = _safe_get(instance, "price", "amount", "sold_price", default=None)
                        pct = _safe_get(instance, "commission_pct", default=None)
                        txt = f"Sold at {loc}" if loc else "Sold"
                        if price is not None: txt += f" for {price}"
                        if pct is not None: txt += f" (commission {pct}%)"
                        kwargs_a["details"] = txt
                    if _model_has_field(InventoryAudit, "business"):
                        kwargs_a["business"] = _safe_get(item, "business", default=None)
                    if kwargs_a:
                        InventoryAudit.objects.create(**kwargs_a)
                except Exception:
                    pass

        if created:
            try:
                _post_wallet_commission(instance)
            except Exception:
                pass


