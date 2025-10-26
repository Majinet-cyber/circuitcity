# notifications/signals.py
from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings
from django.db.models import F

from inventory.models import InventoryItem, InventoryAudit
from sales.models import Sale
try:
    # Optional wallet model
    from inventory.models import WalletTxn  # your codebase primary location
except Exception:
    try:
        from wallets.models import WalletTxn  # fallback
    except Exception:
        WalletTxn = None

from .utils import create_notification


# ---------------------------
# InventoryItem: detect stock-in on create or status transition -> IN_STOCK
# ---------------------------
@receiver(pre_save, sender=InventoryItem)
def _invitem_pre(sender, instance: InventoryItem, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=InventoryItem)
def _invitem_post(sender, instance: InventoryItem, created: bool, **kwargs):
    # Determine a friendly product label
    prod = getattr(instance, "product", None)
    label = (
        getattr(prod, "name", None)
        or f"{getattr(prod, 'brand', '')} {getattr(prod, 'model', '')}".strip()
        or "Item"
    )

    became_in = (created and instance.status == "IN_STOCK") or (
        not created and getattr(instance, "_old_status", None) != "IN_STOCK" and instance.status == "IN_STOCK"
    )
    if became_in:
        # Admin notice
        create_notification(
            audience="ADMIN",
            message=f"{label} stocked in.",
            level="success",
            meta={"item_id": instance.id},
        )

        # Agent notice (if assigned)
        if getattr(instance, "assigned_agent", None):
            create_notification(
                audience="AGENT",
                user=instance.assigned_agent,
                message=f"{label} added to your stock.",
                level="info",
                meta={"item_id": instance.id},
            )


# ---------------------------
# InventoryAudit: mirror important events (optional)
# ---------------------------
@receiver(post_save, sender=InventoryAudit)
def _audit_post(sender, instance: InventoryAudit, created: bool, **kwargs):
    if not created:
        return
    action = getattr(instance, "action", "")
    item = getattr(instance, "item", None)
    prod = getattr(getattr(item, "product", None), "model", None) or getattr(getattr(item, "product", None), "name", None) or "Item"

    # Examples: STOCK_IN / RECEIVED / TRANSFER_IN / SOLD
    if action in {"STOCK_IN", "RECEIVED", "TRANSFER_IN"}:
        create_notification(audience="ADMIN", message=f"{prod} stocked in.", level="success")
    elif action in {"TRANSFER_OUT"}:
        create_notification(audience="ADMIN", message=f"{prod} transferred out.", level="info")


# ---------------------------
# Sale: on new sale -> admin summary + agent commission + remaining stock
# ---------------------------
def _estimate_commission(sale: Sale) -> float:
    # Try explicit fields if present
    for name in ("commission_amount", "agent_commission", "commission"):
        val = getattr(sale, name, None)
        if val:
            try:
                return float(val)
            except Exception:
                pass
    # Fallback rate from settings (e.g., 0.02 = 2%)
    rate = float(getattr(settings, "SALES_DEFAULT_COMMISSION_RATE", 0.0))
    price = getattr(sale, "price", 0) or getattr(sale, "total_price", 0) or 0
    try:
        return float(price) * rate
    except Exception:
        return 0.0


@receiver(post_save, sender=Sale)
def _sale_post(sender, instance: Sale, created: bool, **kwargs):
    if not created:
        return

    item = getattr(instance, "item", None)
    prod = getattr(getattr(item, "product", None), "model", None) or getattr(getattr(item, "product", None), "name", None) or "Item"
    admin_msg = f"{prod} sold"
    create_notification(audience="ADMIN", message=admin_msg, level="info", meta={"sale_id": instance.id})

    # Agent notices
    agent = getattr(instance, "agent", None) or getattr(instance, "user", None)
    if agent:
        commission = _estimate_commission(instance)
        if commission > 0:
            create_notification(
                audience="AGENT",
                user=agent,
                message=f"Commission earned: {commission:,.2f} on {prod}.",
                level="success",
                meta={"sale_id": instance.id, "commission": commission},
            )

        # Remaining stock for the agent
        try:
            from inventory.models import InventoryItem  # local import to avoid circulars at app load
            remaining = InventoryItem.objects.filter(assigned_agent=agent, status="IN_STOCK").count()
            create_notification(
                audience="AGENT",
                user=agent,
                message=f"{remaining} phone(s) left in your stock.",
                level="info",
                meta={"remaining": remaining},
            )
        except Exception:
            pass


# ---------------------------
# Wallet / Cash events (optional model)
# ---------------------------
if WalletTxn is not None:
    @receiver(post_save, sender=WalletTxn)
    def _wallet_post(sender, instance: WalletTxn, created: bool, **kwargs):
        if not created:
            return

        # Try common fields: user, amount, reason
        user = getattr(instance, "user", None)
        amount = getattr(instance, "amount", 0)
        reason = getattr(instance, "reason", "") or getattr(instance, "kind", "")

        # Budget request / advance
        if str(reason).upper() in {"ADVANCE", "BUDGET", "BUDGET_REQUEST"}:
            create_notification(
                audience="ADMIN",
                message=f"Cash request {amount:,.2f} from {getattr(user, 'username', 'agent')}.",
                level="warning",
                meta={"wallet_id": instance.id},
            )
            if user:
                create_notification(
                    audience="AGENT",
                    user=user,
                    message=f"Budget request submitted: {amount:,.2f}.",
                    level="info",
                    meta={"wallet_id": instance.id},
                )

        # Payday withdrawals/payouts
        if str(reason).upper() in {"WITHDRAWAL", "PAYOUT"}:
            create_notification(
                audience="ADMIN",
                message=f"Payday withdrawal {amount:,.2f} by {getattr(user, 'username', 'agent')}.",
                level="info",
                meta={"wallet_id": instance.id},
            )
            if user:
                create_notification(
                    audience="AGENT",
                    user=user,
                    message=f"Withdrawal processed: {amount:,.2f}.",
                    level="success",
                    meta={"wallet_id": instance.id},
                )


