# inventory/signals.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.conf import settings
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import InventoryItem, InventoryAudit, WalletTxn
from sales.models import Sale  # correct import (your FK on Sale is item)

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
    """
    Add 'inventory.signals.RequestMiddleware' to MIDDLEWARE (already done in settings).
    Makes the current request accessible to signal handlers for audit metadata.
    """
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
    """
    Stash a 'before' copy so we can diff fields in post_save.
    """
    if instance.pk:
        try:
            instance._before = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._before = None
    else:
        instance._before = None


def _collect_changed_fields(instance: InventoryItem, before: InventoryItem | None) -> List[str]:
    """
    Return human-readable changes (public_name: before → after), tolerant of schema variations.
    """
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
            before_val = getattr(before, attr)
            after_val = getattr(instance, attr)
            if before_val != after_val:
                changed.append(f"{public_name}: {before_val} → {after_val}")
            seen.add(attr)
    return changed


@receiver(post_save, sender=InventoryItem)
def _invitem_audit(sender, instance: InventoryItem, created: bool, **kwargs):
    """
    Write audit rows for CREATE/UPDATE and bump dashboard cache version.
    Also writes tamper-evident AuditLog rows if enabled.
    """
    request = get_current_request()
    actor = getattr(instance, "_actor", None) or getattr(getattr(request, "user", None), "pk", None)

    if created:
        # Legacy row (human summary)
        try:
            InventoryAudit.objects.create(
                item=instance,
                by_user=getattr(instance, "_actor", None),
                action="CREATE",
                details=f"Created with status={getattr(instance, 'status', None)}",
            )
        except Exception:
            pass

        # Hash-chained row
        if _AUDIT_ENABLED and log_audit:
            try:
                log_audit(
                    actor=getattr(request, "user", None),
                    entity="InventoryItem",
                    entity_id=str(instance.pk),
                    action="CREATE",
                    payload={
                        "status": getattr(instance, "status", None),
                        "location_id": getattr(instance, "location_id", None),
                        "current_location_id": getattr(instance, "current_location_id", None),
                        "selling_price": getattr(instance, "selling_price", None) if hasattr(instance, "selling_price") else getattr(instance, "price", None),
                    },
                    request=request,
                )
            except Exception:
                pass

        _bump_cache()
        return

    before = getattr(instance, "_before", None)
    changes = _collect_changed_fields(instance, before)

    if changes:
        # Legacy row
        try:
            InventoryAudit.objects.create(
                item=instance,
                by_user=getattr(instance, "_actor", None),
                action="UPDATE",
                details="\n".join(changes),
            )
        except Exception:
            pass

        # Hash-chained row
        if _AUDIT_ENABLED and log_audit:
            try:
                payload = {
                    "changes": changes,
                    "before_id": getattr(before, "pk", None) if before else None,
                }
                log_audit(
                    actor=getattr(request, "user", None),
                    entity="InventoryItem",
                    entity_id=str(instance.pk),
                    action="UPDATE",
                    payload=payload,
                    request=request,
                )
            except Exception:
                pass

        _bump_cache()


@receiver(post_delete, sender=InventoryItem)
def _invitem_deleted(sender, instance: InventoryItem, **kwargs):
    """
    On delete/soft-delete operations, ensure dashboards refresh and write tamper-audit.
    """
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
# Sale hooks: finalize item state on create + commission wallet + cache
# ---------------------------------------------------------------------
def _wallet_fields() -> Dict[str, Optional[str]]:
    """
    Introspect WalletTxn flexible field names.
    Returns dict with keys: agent_key, reason_key, memo_key, ref_key, when_key, kind_credit_value
    """
    field_names = {f.name for f in WalletTxn._meta.get_fields()}

    agent_key = "agent" if "agent" in field_names else ("user" if "user" in field_names else None)
    reason_key = "reason" if "reason" in field_names else ("kind" if "kind" in field_names else None)
    memo_key = "memo" if "memo" in field_names else ("note" if "note" in field_names else None)
    ref_key = "ref" if "ref" in field_names else None
    when_key = "happened_at" if "happened_at" in field_names else ("created_at" if "created_at" in field_names else None)

    # Typical credit indicator if using "kind"
    kind_credit_value = "CREDIT"

    return {
        "agent_key": agent_key,
        "reason_key": reason_key,
        "memo_key": memo_key,
        "ref_key": ref_key,
        "when_key": when_key,
        "kind_credit_value": kind_credit_value,
    }


def _compute_commission_amount(sale: Sale):
    """
    Try Sale.commission_amount first; else compute from commission_pct if present.
    """
    amt = getattr(sale, "commission_amount", None)
    if amt is not None:
        return amt
    pct = getattr(sale, "commission_pct", None)
    price = getattr(sale, "price", None) or 0
    try:
        if pct:
            return round(float(price) * float(pct), 2)
    except Exception:
        pass
    return None


@receiver(post_save, sender=Sale)
def _sale_finalize(sender, instance: Sale, created: bool, **kwargs):
    """
    When a Sale is created:
      - Ensure the related InventoryItem is finalized to SOLD and aligned.
      - Write explicit SOLD audit.
      - Create commission WalletTxn (idempotent).
      - Bump dashboard cache version.
      - Append tamper-evident AuditLog rows for Sale and the linked item.
    """
    item: InventoryItem = instance.item

    if created:
        updates: list[str] = []

        # 1) Finalize InventoryItem from Sale
        try:
            if getattr(item, "status", None) != "SOLD":
                item.status = "SOLD"
                updates.append("status=SOLD")

            # sold_at
            if not getattr(item, "sold_at", None):
                item.sold_at = getattr(instance, "sold_at", None) or timezone.now()
                updates.append("sold_at from sale")

            # selling price vs price
            sale_price = getattr(instance, "price", None)
            if hasattr(item, "selling_price"):
                if not getattr(item, "selling_price", None) and sale_price is not None:
                    item.selling_price = sale_price
                    updates.append("selling_price from sale")
            elif hasattr(item, "price"):
                if not getattr(item, "price", None) and sale_price is not None:
                    item.price = sale_price
                    updates.append("price from sale")

            # location align (location or current_location)
            sale_loc_id = getattr(instance, "location_id", None)
            if sale_loc_id:
                if hasattr(item, "current_location_id"):
                    if getattr(item, "current_location_id", None) != sale_loc_id:
                        item.current_location_id = sale_loc_id
                        updates.append("location from sale")
                elif hasattr(item, "location_id"):
                    if getattr(item, "location_id", None) != sale_loc_id:
                        item.location_id = sale_loc_id
                        updates.append("location from sale")

            # actor for inventory audit trail
            item._actor = getattr(instance, "agent", None)

            item.save()  # triggers InventoryItem post_save audit
        except Exception:
            # Don't let side-effects break the original save
            pass

        # 2) Explicit SOLD audit row (legacy)
        try:
            InventoryAudit.objects.create(
                item=item,
                by_user=getattr(instance, "agent", None),
                action="SOLD",
                details=f"Sale #{instance.pk} – updates: {', '.join(updates) if updates else 'none'}",
            )
        except Exception:
            pass

        # 2b) Hash-chained AuditLog rows
        if _AUDIT_ENABLED and log_audit:
            request = get_current_request()
            try:
                # Sale event
                log_audit(
                    actor=getattr(request, "user", None),
                    entity="Sale",
                    entity_id=str(instance.pk),
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
                # Linkage/update summary for item
                if updates:
                    log_audit(
                        actor=getattr(request, "user", None),
                        entity="InventoryItem",
                        entity_id=str(item.pk),
                        action="UPDATE",
                        payload={"updates_from_sale": updates, "sale_id": instance.pk},
                        request=request,
                    )
            except Exception:
                pass

        # 3) Commission WalletTxn (idempotent)
        try:
            fields = _wallet_fields()
            agent_key = fields["agent_key"]
            reason_key = fields["reason_key"]
            memo_key = fields["memo_key"]
            ref_key = fields["ref_key"]
            when_key = fields["when_key"]
            credit_value = fields["kind_credit_value"]

            if agent_key is None or memo_key is None:
                # model doesn't have recognizable fields; skip safely
                pass
            else:
                memo = f"Commission Sale #{instance.pk}"
                tx_qs = WalletTxn.objects.all()
                if ref_key:
                    tx_qs = tx_qs.filter(**{ref_key: f"SALE:{instance.pk}"})
                    exists = tx_qs.exists()
                else:
                    # fallback idempotency: agent + memo
                    exists = WalletTxn.objects.filter(**{
                        agent_key: getattr(instance, "agent", None),
                        memo_key: memo,
                    }).exists()

                if not exists:
                    amt = _compute_commission_amount(instance)
                    if amt is not None:
                        create_kwargs = {
                            memo_key: memo,
                            "amount": amt,
                        }
                        if agent_key:
                            create_kwargs[agent_key] = getattr(instance, "agent", None)
                        if reason_key:
                            # prefer semantic reason; else use 'CREDIT' kind
                            create_kwargs[reason_key] = "COMMISSION" if reason_key == "reason" else credit_value
                        if ref_key:
                            create_kwargs[ref_key] = f"SALE:{instance.pk}"
                        if when_key:
                            create_kwargs[when_key] = getattr(instance, "sold_at", None) or timezone.now()

                        WalletTxn.objects.create(**create_kwargs)
        except Exception:
            # Never break the request because of wallet side-effects
            pass

    # 4) Sales affect aggregates → bump cache every time
    _bump_cache()


@receiver(post_delete, sender=Sale)
def _sale_deleted(sender, instance: Sale, **kwargs):
    """
    Sales deletions also impact aggregates; bump the cache version.
    Optionally append a tamper-audit row for the deleted sale reference.
    """
    if _AUDIT_ENABLED and log_audit:
        request = get_current_request()
        try:
            log_audit(
                actor=getattr(request, "user", None),
                entity="Sale",
                entity_id=str(instance.pk),
                action="DELETE",
                payload={"item_id": getattr(instance, "item_id", None)},
                request=request,
            )
        except Exception:
            pass

    _bump_cache()
