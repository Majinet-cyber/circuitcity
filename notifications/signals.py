# notifications/signals.py
"""
Signal handlers that fire notifications on key events:
- New sale
- New agent joined
- Stock zero / low stock
- Inventory stocked in
- Wallet transactions
"""
from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings
from django.db.models import F, Count

from inventory.models import InventoryItem, InventoryAudit
from sales.models import Sale
try:
    from inventory.models import WalletTxn
except Exception:
    try:
        from wallets.models import WalletTxn
    except Exception:
        WalletTxn = None

# Import tenants models for agent-joined notifications
try:
    from tenants.models import Membership, AgentInvite
except Exception:
    Membership = None
    AgentInvite = None

from .utils import create_notification


# ---------------------------------------------------------------------------
# Agent Joined Notifications
# ---------------------------------------------------------------------------

if Membership is not None:
    @receiver(post_save, sender=Membership)
    def _membership_created(sender, instance: Membership, created: bool, **kwargs):
        """Notify when a new agent joins (membership becomes ACTIVE)."""
        if not created:
            # Check if status changed to ACTIVE
            return
        
        if instance.status != "ACTIVE":
            return
        
        if instance.role.upper() != "AGENT":
            return
        
        user = instance.user
        business = instance.business
        
        # Notify the business manager(s)
        create_notification(
            audience="ADMIN",
            message=f"New agent {user.get_full_name() or user.username} joined {business.name}.",
            level="success",
            meta={
                "event": "agent_joined",
                "user_id": user.id,
                "business_id": business.id,
            },
        )


if AgentInvite is not None:
    @receiver(post_save, sender=AgentInvite)
    def _invite_accepted(sender, instance: AgentInvite, **kwargs):
        """Notify when an invite is accepted."""
        if instance.status != "JOINED":
            return
        
        if not instance.joined_user:
            return
        
        # Only notify if we haven't already (check meta or use a flag)
        # The membership signal above handles the main notification
        pass


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


# ---------------------------------------------------------------------------
# Stock Zero / Low Stock Notifications
# ---------------------------------------------------------------------------

def check_and_notify_low_stock(product, location=None, business=None):
    """
    Check if a product is at zero or below low_stock_threshold and notify.
    Called after sales or stock adjustments.
    """
    try:
        from inventory.models import InventoryItem, Product
        
        if not product:
            return
        
        # Get threshold from product or use default
        threshold = getattr(product, "low_stock_threshold", 5)
        
        # Build query for remaining stock
        qs = InventoryItem.objects.filter(product=product, status="IN_STOCK", is_active=True)
        
        if location:
            qs = qs.filter(current_location=location)
        elif business:
            qs = qs.filter(business=business)
        
        remaining = qs.count()
        
        product_name = getattr(product, "name", None) or str(product)
        location_name = getattr(location, "name", "") if location else ""
        
        if remaining == 0:
            # Stock is zero - critical alert
            msg = f"STOCK ZERO: {product_name}"
            if location_name:
                msg += f" at {location_name}"
            
            create_notification(
                audience="ADMIN",
                message=msg,
                level="error",
                meta={
                    "event": "stock_zero",
                    "product_id": product.id,
                    "location_id": getattr(location, "id", None),
                    "remaining": 0,
                },
            )
        elif remaining <= threshold:
            # Low stock warning
            msg = f"LOW STOCK: {product_name} - only {remaining} left"
            if location_name:
                msg += f" at {location_name}"
            
            create_notification(
                audience="ADMIN",
                message=msg,
                level="warning",
                meta={
                    "event": "low_stock",
                    "product_id": product.id,
                    "location_id": getattr(location, "id", None),
                    "remaining": remaining,
                    "threshold": threshold,
                },
            )
    except Exception:
        # Never break the main flow due to notification errors
        pass


# Hook into sale creation to check stock levels
@receiver(post_save, sender=Sale)
def _sale_check_stock(sender, instance: Sale, created: bool, **kwargs):
    """After a sale, check if stock is low or zero."""
    if not created:
        return
    
    try:
        item = instance.item
        product = getattr(item, "product", None)
        location = instance.location or getattr(item, "current_location", None)
        business = getattr(location, "business", None) if location else None
        
        check_and_notify_low_stock(product, location=location, business=business)
    except Exception:
        pass


# Hook into inventory item status changes (SOLD) to check stock
@receiver(post_save, sender=InventoryItem)
def _invitem_check_stock(sender, instance: InventoryItem, created: bool, **kwargs):
    """After an item is marked SOLD, check stock levels."""
    if created:
        return  # Only check on updates
    
    old_status = getattr(instance, "_old_status", None)
    
    # Only trigger when transitioning TO SOLD
    if old_status != "SOLD" and instance.status == "SOLD":
        try:
            product = instance.product
            location = instance.current_location
            business = instance.business
            
            check_and_notify_low_stock(product, location=location, business=business)
        except Exception:
            pass


