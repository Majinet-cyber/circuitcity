# inventory/signals.py
from __future__ import annotations

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from .models import InventoryItem, InventoryAudit, WalletTxn
from sales.models import Sale  # <-- correct app import

# Optional: version-bump cache invalidation for dashboard metrics
try:
    from .cache_utils import bump_dashboard_cache_version as _bump_cache
except Exception:  # cache utils not present in some envs/tests
    def _bump_cache() -> None:  # no-op
        pass


# ---------------------------------------------------------------------
# InventoryItem change snapshot + audit trail
# ---------------------------------------------------------------------
@receiver(pre_save, sender=InventoryItem)
def _invitem_snap(sender, instance, **kwargs):
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


@receiver(post_save, sender=InventoryItem)
def _invitem_audit(sender, instance, created, **kwargs):
    """
    Write audit rows for CREATE/UPDATE and bump dashboard cache version.
    """
    if created:
        InventoryAudit.objects.create(
            item=instance,
            by_user=getattr(instance, "_actor", None),
            action="CREATE",
            details=f"Created with status={instance.status}",
        )
        _bump_cache()
        return

    before = getattr(instance, "_before", None)
    if not before:
        return

    changed = []
    watch = (
        "status",
        "current_location_id",
        "assigned_agent_id",
        "selling_price",
        "order_price",
        "sold_at",
        "received_at",
        "is_active",
    )
    for f in watch:
        if getattr(before, f) != getattr(instance, f):
            changed.append(f"{f}: {getattr(before, f)} → {getattr(instance, f)}")

    if changed:
        InventoryAudit.objects.create(
            item=instance,
            by_user=getattr(instance, "_actor", None),
            action="UPDATE",
            details="\n".join(changed),
        )
        _bump_cache()  # invalidate aggregates derived from inventory


@receiver(post_delete, sender=InventoryItem)
def _invitem_deleted(sender, instance, **kwargs):
    """
    On delete/soft-delete operations, ensure dashboards refresh.
    (Audit for deletes is already handled in views; avoid duplicates here.)
    """
    _bump_cache()


# ---------------------------------------------------------------------
# Sale hooks: finalize item state on create + commission wallet + cache
# ---------------------------------------------------------------------
@receiver(post_save, sender=Sale)
def _sale_finalize(sender, instance, created, **kwargs):
    """
    When a Sale is created:
      - Ensure the related InventoryItem is finalized to SOLD and aligned.
      - Write explicit SOLD audit.
      - Create commission WalletTxn (COMMISSION) once (idempotent).
      - Bump dashboard cache version.
    """
    item = instance.item
    if created:
        updates = []

        if item.status != "SOLD":
            item.status = "SOLD"
            updates.append("status=SOLD")

        if not item.sold_at:
            item.sold_at = getattr(instance, "sold_at", None)
            if item.sold_at:
                updates.append("sold_at from sale")

        if not item.selling_price:
            item.selling_price = getattr(instance, "price", None)
            if item.selling_price:
                updates.append("selling_price from sale")

        # Align location from sale if different
        if getattr(item, "current_location_id", None) != getattr(instance, "location_id", None):
            item.current_location_id = instance.location_id
            updates.append("location from sale")

        # Mark actor for InventoryItem post_save audit
        item._actor = getattr(instance, "agent", None)

        item.save()  # triggers InventoryItem post_save audit

        InventoryAudit.objects.create(
            item=item,
            by_user=getattr(instance, "agent", None),
            action="SOLD",
            details=f"Sale #{instance.pk} – updates: {', '.join(updates) or 'none'}",
        )

        # ---- Commission wallet credit (idempotent) ----
        try:
            memo = f"Commission Sale #{instance.pk}"
            already = WalletTxn.objects.filter(
                user=instance.agent,
                reason="COMMISSION",
                memo=memo,
            ).exists()

            if not already:
                amt = instance.commission_amount
                # Only create if non-zero / not None
                if amt and float(amt) != 0.0:
                    WalletTxn.objects.create(
                        user=instance.agent,
                        amount=amt,                 # positive = credit
                        reason="COMMISSION",
                        memo=memo,
                    )
        except Exception:
            # Never break the request because of wallet side-effects
            pass

    # Whether created or updated, sales affect aggregates → bump cache
    _bump_cache()


@receiver(post_delete, sender=Sale)
def _sale_deleted(sender, instance, **kwargs):
    """
    Sales deletions also impact aggregates; bump the cache version.
    """
    _bump_cache()
