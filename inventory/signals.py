# inventory/signals.py
from __future__ import annotations

from typing import Dict, List, Optional, Any

from django.conf import settings
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import InventoryItem
try:
    from .models import InventoryAudit  # optional in some setups
except Exception:  # pragma: no cover
    InventoryAudit = None  # type: ignore

try:
    from .models import WalletTxn  # optional
except Exception:  # pragma: no cover
    WalletTxn = None  # type: ignore

# Import Sale (FK is usually Sale.item -> InventoryItem)
try:
    from sales.models import Sale
except Exception:  # pragma: no cover
    Sale = None  # type: ignore

# ---- Tamper-evident audit (hash chain) optional import ----
_AUDIT_ENABLED = bool(getattr(settings, "AUDIT_LOG_SETTINGS", {}).get("ENABLED", True))
try:
    from .models_audit import log_audit  # helper to create AuditLog rows
except Exception:  # pragma: no cover
    log_audit = None  # type: ignore

# ---------------------------------------------------------------------
# Minimal request-local so signals can see actor/ip/ua
# ---------------------------------------------------------------------
try:
    from asgiref.local import Local
except Exception:  # pragma: no cover
    class Local:  # fall-back stub
        def __init__(self): self.value = None

_request_local = Local()

def get_current_request():
    return getattr(_request_local, "value", None)

class RequestMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        _request_local.value = request
        try:
            return self.get_response(request)
        finally:
            _request_local.value = None

# Optional: dashboard cache version bump
try:
    from .cache_utils import bump_dashboard_cache_version as _bump_cache
except Exception:  # pragma: no cover
    def _bump_cache() -> None:
        pass

# ---------------------------------------------------------------------
# InventoryItem change snapshot + audit trail
# ---------------------------------------------------------------------
@receiver(pre_save, sender=InventoryItem)
def _invitem_snap(sender, instance: InventoryItem, **kwargs):
    # Escape hatch used by hot paths to avoid any pre-save DB I/O
    if getattr(instance, "_skip_snap", False):
        instance._before = None
        return

    pk = getattr(instance, "pk", None)
    if not pk:
        instance._before = None
        return

    try:
        qs = sender.objects
        instance._before = qs.only(
            "id", "status", "location_id", "current_location_id",
            "assigned_agent_id", "agent_id",
            "selling_price", "price", "order_price", "cost",
            "sold_at", "received_at", "is_active", "active",
        ).get(pk=pk)
    except sender.DoesNotExist:
        instance._before = None
    except Exception:
        instance._before = None


def _collect_changed_fields(instance: InventoryItem, before: InventoryItem | None) -> List[str]:
    if not before:
        return []
    changed: list[str] = []
    candidates = [
        ("status", "status"),
        ("location_id", "location_id"),
        ("current_location_id", "current_location_id"),
        ("assigned_agent_id", "assigned_agent_id"),
        ("agent_id", "agent_id"),
        ("selling_price", "selling_price"),
        ("price", "price"),
        ("order_price", "order_price"),
        ("cost", "cost"),
        ("sold_at", "sold_at"),
        ("received_at", "received_at"),
        ("is_active", "is_active"),
        ("active", "active"),
    ]
    seen = set()
    for public_name, attr in candidates:
        if attr in seen:
            continue
        if hasattr(instance, attr) and hasattr(before, attr):
            if getattr(before, attr) != getattr(instance, attr):
                before_val = getattr(before, attr)
                after_val = getattr(instance, attr)
                changed.append(f"{public_name}: {before_val} -> {after_val}")
            seen.add(attr)
    return changed


@receiver(post_save, sender=InventoryItem)
def _invitem_audit(sender, instance: InventoryItem, created: bool, **kwargs):
    # Escape hatch to disable audit work for hot paths
    if getattr(instance, "_skip_audit", False):
        return

    request = get_current_request()

    # CREATE
    if created:
        if InventoryAudit is not None:
            try:
                InventoryAudit.objects.create(
                    item=instance,
                    by_user=getattr(instance, "_actor", None),
                    action="CREATE",
                    details=f"Created with status={getattr(instance, 'status', None)}",
                )
            except Exception:
                pass

        if _AUDIT_ENABLED and log_audit:
            try:
                payload = {
                    "status": getattr(instance, "status", None),
                    "location_id": getattr(instance, "location_id", None),
                    "current_location_id": getattr(instance, "current_location_id", None),
                    "selling_price": getattr(instance, "selling_price", None)
                        if hasattr(instance, "selling_price")
                        else getattr(instance, "price", None),
                }
                log_audit(
                    actor=getattr(request, "user", None),
                    entity="InventoryItem",
                    entity_id=str(instance.pk),
                    action="CREATE",
                    payload=payload,
                    request=request,
                )
            except Exception:
                pass

        _bump_cache()
        return

    # UPDATE
    before = getattr(instance, "_before", None)
    changes = _collect_changed_fields(instance, before)

    if changes:
        if InventoryAudit is not None:
            try:
                InventoryAudit.objects.create(
                    item=instance,
                    by_user=getattr(instance, "_actor", None),
                    action="UPDATE",
                    details="\n".join(changes),
                )
            except Exception:
                pass

        if _AUDIT_ENABLED and log_audit:
            try:
                log_audit(
                    actor=getattr(request, "user", None),
                    entity="InventoryItem",
                    entity_id=str(instance.pk),
                    action="UPDATE",
                    payload={"changes": changes, "before_id": getattr(before, "pk", None) if before else None},
                    request=request,
                )
            except Exception:
                pass

        _bump_cache()


@receiver(post_delete, sender=InventoryItem)
def _invitem_deleted(sender, instance: InventoryItem, **kwargs):
    request = get_current_request()

    if _AUDIT_ENABLED and log_audit:
        try:
            log_audit(
                actor=getattr(request, "user", None),
                entity="InventoryItem",
                entity_id=str(instance.pk),
                action="DELETE",
                payload={"status": getattr(instance, "status", None)},
                request=request,
            )
        except Exception:
            pass

    _bump_cache()

# ---------------------------------------------------------------------
# Sale hooks (guarded if sales app not present)
# ---------------------------------------------------------------------

def _wallet_fields() -> Dict[str, Optional[str]]:
    """
    Build a tolerant map of wallet field names. If WalletTxn is missing,
    return a map of Nones so the caller can no-op safely.
    """
    if WalletTxn is None:
        return {
            "agent_key": None,
            "reason_key": None,
            "memo_key": None,
            "ref_key": None,
            "when_key": None,
            "kind_credit_value": "CREDIT",
        }
    try:
        field_names = {f.name for f in WalletTxn._meta.get_fields()}
    except Exception:
        field_names = set()

    agent_key = "agent" if "agent" in field_names else ("user" if "user" in field_names else None)
    reason_key = "reason" if "reason" in field_names else ("kind" if "kind" in field_names else None)
    memo_key = "memo" if "memo" in field_names else ("note" if "note" in field_names else None)
    ref_key = "ref" if "ref" in field_names else None
    when_key = "happened_at" if "happened_at" in field_names else ("created_at" if "created_at" in field_names else None)
    kind_credit_value = "CREDIT"
    return {
        "agent_key": agent_key,
        "reason_key": reason_key,
        "memo_key": memo_key,
        "ref_key": ref_key,
        "when_key": when_key,
        "kind_credit_value": kind_credit_value,
    }


def _compute_commission_amount(sale: Any):
    price = getattr(sale, "price", None) or 0
    # commission_amount wins if explicitly present
    amt = getattr(sale, "commission_amount", None)
    if amt is not None:
        return amt
    pct = getattr(sale, "commission_pct", None)
    try:
        if pct:
            return round(float(price) * float(pct), 2)
    except Exception:
        pass
    return None


if Sale is not None:
    @receiver(post_save, sender=Sale)
    def _sale_finalize(sender, instance: Any, created: bool, **kwargs):
        """
        When a Sale is created, keep the linked InventoryItem in sync
        and optionally post a wallet commission. Never force is_active,
        and be tolerant about missing optional models/tables.
        """
        # If API created the Sale and already finalized the item, skip heavy work
        if getattr(instance, "_skip_finalize", False):
            _bump_cache()
            return

        # Some projects name the FK "item", others "inventory_item"
        item = getattr(instance, "item", None) or getattr(instance, "inventory_item", None)
        if item is None:
            _bump_cache()
            return

        if created:
            updates: list[str] = []
            try:
                # Status to SOLD (uppercase to normalize)
                if getattr(item, "status", None) != "SOLD":
                    item.status = "SOLD"; updates.append("status=SOLD")

                # sold_at from sale timestamp if not already set
                if not getattr(item, "sold_at", None):
                    item.sold_at = getattr(instance, "sold_at", None) or timezone.now()
                    updates.append("sold_at from sale")

                # carry price if item does not already have a selling value
                sale_price = getattr(instance, "price", None)
                if hasattr(item, "selling_price"):
                    if not getattr(item, "selling_price", None) and sale_price is not None:
                        item.selling_price = sale_price; updates.append("selling_price from sale")
                elif hasattr(item, "price"):
                    if not getattr(item, "price", None) and sale_price is not None:
                        item.price = sale_price; updates.append("price from sale")

                # location coherence (prefer current_location_id)
                sale_loc_id = getattr(instance, "location_id", None)
                if sale_loc_id:
                    if hasattr(item, "current_location_id"):
                        if getattr(item, "current_location_id", None) != sale_loc_id:
                            item.current_location_id = sale_loc_id; updates.append("location from sale")
                    elif hasattr(item, "location_id"):
                        if getattr(item, "location_id", None) != sale_loc_id:
                            item.location_id = sale_loc_id; updates.append("location from sale")

                # optional flags that represent availability (do not touch is_active)
                if hasattr(item, "is_sold"):
                    if not getattr(item, "is_sold", False):
                        item.is_sold = True; updates.append("is_sold=True")
                if hasattr(item, "in_stock"):
                    if getattr(item, "in_stock", True):
                        item.in_stock = False; updates.append("in_stock=False")
                if hasattr(item, "available"):
                    if getattr(item, "available", True):
                        item.available = False; updates.append("available=False")
                if hasattr(item, "availability"):
                    if getattr(item, "availability", True):
                        item.availability = False; updates.append("availability=False")

                # save without triggering _invitem_snap re-fetch (allowed audit)
                item._actor = getattr(instance, "agent", None)
                item._skip_snap = True
                item._skip_audit = False
                item.save()
            except Exception:
                pass

            # Lightweight audit
            if InventoryAudit is not None:
                try:
                    InventoryAudit.objects.create(
                        item=item,
                        by_user=getattr(instance, "agent", None),
                        action="SOLD",
                        details=f"Sale #{getattr(instance, 'pk', None)} - updates: {', '.join(updates) if updates else 'none'}",
                    )
                except Exception:
                    pass

            # Hash-audit
            if _AUDIT_ENABLED and log_audit:
                request = get_current_request()
                try:
                    log_audit(
                        actor=getattr(request, "user", None),
                        entity="Sale",
                        entity_id=str(getattr(instance, "pk", None)),
                        action="CREATE",
                        payload={
                            "item_id": getattr(item, "pk", None),
                            "agent_id": getattr(instance, "agent_id", None),
                            "price": getattr(instance, "price", None),
                            "location_id": getattr(instance, "location_id", None),
                            "sold_at": getattr(instance, "sold_at", None) or getattr(item, "sold_at", None),
                        },
                        request=request,
                    )
                    if updates:
                        log_audit(
                            actor=getattr(request, "user", None),
                            entity="InventoryItem",
                            entity_id=str(getattr(item, "pk", None)),
                            action="UPDATE",
                            payload={"updates_from_sale": updates, "sale_id": getattr(instance, "pk", None)},
                            request=request,
                        )
                except Exception:
                    pass

            # Wallet credit (optional)
            try:
                fields = _wallet_fields()
                agent_key = fields["agent_key"]; reason_key = fields["reason_key"]
                memo_key = fields["memo_key"]; ref_key = fields["ref_key"]
                when_key = fields["when_key"]; credit_value = fields["kind_credit_value"]

                if WalletTxn is not None and agent_key and memo_key:
                    memo = f"Commission Sale #{getattr(instance, 'pk', None)}"
                    ref_val = f"SALE:{getattr(instance, 'pk', None)}" if ref_key else None

                    tx_qs = WalletTxn.objects.all()
                    exists = False
                    try:
                        if ref_key:
                            exists = tx_qs.filter(**{ref_key: ref_val}).exists()
                        else:
                            exists = tx_qs.filter(**{
                                agent_key: getattr(instance, "agent", None),
                                memo_key: memo
                            }).exists()
                    except Exception:
                        exists = False

                    if not exists:
                        amt = _compute_commission_amount(instance)
                        if amt is not None:
                            create_kwargs: Dict[str, Any] = {memo_key: memo, "amount": amt}
                            create_kwargs[agent_key] = getattr(instance, "agent", None)
                            if reason_key:
                                # keep "COMMISSION" for reason, else generic CREDIT-kind
                                create_kwargs[reason_key] = "COMMISSION" if reason_key == "reason" else credit_value
                            if ref_key:
                                create_kwargs[ref_key] = ref_val
                            if when_key:
                                create_kwargs[when_key] = getattr(instance, "sold_at", None) or timezone.now()
                            try:
                                WalletTxn.objects.create(**create_kwargs)
                            except Exception:
                                pass
            except Exception:
                pass

        _bump_cache()


if Sale is not None:
    @receiver(post_delete, sender=Sale)
    def _sale_deleted(sender, instance: Any, **kwargs):
        if _AUDIT_ENABLED and log_audit:
            request = get_current_request()
            try:
                log_audit(
                    actor=getattr(request, "user", None),
                    entity="Sale",
                    entity_id=str(getattr(instance, "pk", None)),
                    action="DELETE",
                    payload={"item_id": getattr(instance, "item_id", None)},
                    request=request,
                )
            except Exception:
                pass
        _bump_cache()
