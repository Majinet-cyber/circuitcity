# notifications/signals.py
"""
Signal handlers for creating notifications on important events.

IMPORTANT: All notification creation is wrapped in transaction.on_commit() to ensure:
1. Notifications are only created after successful transaction commits
2. No DB writes occur during failed/rolled-back atomic blocks (Postgres safe)
3. No spurious ERROR logs for expected rollbacks
"""
import logging
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver, Signal
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from .models import Notification, NotificationPreference

logger = logging.getLogger(__name__)

User = get_user_model()

# Custom signals
milestone_reached = Signal()


@receiver(post_save, sender="sales.Sale")
def notify_new_sale(sender, instance, created, **kwargs):
    """
    Notify when a new sale is recorded.
    
    Uses transaction.on_commit() to ensure notifications are only created
    after the sale transaction successfully commits.
    """
    if not created:
        return

    # Capture primitive values immediately (no lazy DB lookups)
    sale_id = instance.id
    sale_price = float(instance.price) if instance.price else 0
    agent_id = instance.agent.id if instance.agent else None
    agent_name = instance.agent.username if instance.agent else "Unknown"
    
    # Get location and business IDs safely
    location_id = getattr(instance, 'location_id', None)
    business_id = None
    if hasattr(instance, 'location') and instance.location:
        business_id = getattr(instance.location, 'business_id', None)
    
    # Get product info from the item (capture values, not references)
    product_name = "Unknown Product"
    imei = ""
    if hasattr(instance, "item") and instance.item:
        item = instance.item
        # Try to get product name from various possible fields
        if hasattr(item, "product") and item.product:
            product = item.product
            product_name = f"{getattr(product, 'brand', '')} {getattr(product, 'model', '')}".strip() or str(product)
        elif hasattr(item, "name"):
            product_name = item.name
        elif hasattr(item, "sku"):
            product_name = f"SKU: {item.sku}"
        
        # Try to get IMEI/serial
        imei = getattr(item, "imei", "") or getattr(item, "serial", "") or getattr(item, "code", "") or ""

    def _create_sale_notifications():
        """
        Create notifications for managers about the sale.
        This runs ONLY after successful transaction commit.
        """
        try:
            if not business_id:
                return
            
            from tenants.models import Membership
            
            managers = Membership.objects.filter(
                business_id=business_id, 
                role__in=["MANAGER", "ADMIN"], 
                status="ACTIVE"
            ).values_list("user_id", flat=True)
            
            # Format the notification message
            msg_parts = [f"Sale recorded: {product_name}"]
            if imei:
                msg_parts.append(f"(IMEI: {imei})")
            msg_parts.append(f"sold for MK {sale_price:,.0f}")
            message = " ".join(msg_parts)
            
            for manager_id in managers:
                Notification.objects.create(
                    audience="ADMIN",
                    user_id=manager_id,
                    message=message,
                    level="success",
                    meta={
                        "type": "new_sale",
                        "sale_id": sale_id,
                        "amount": sale_price,
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "product": product_name,
                        "imei": imei,
                    },
                )
        except Exception:
            logger.exception(f"Failed to create sale notification for sale_id={sale_id}")

    def _send_sale_email():
        """Send email notification after commit."""
        try:
            from sales.models import Sale
            from notifications.services import notify_sale_completion
            
            # Re-fetch the sale since we're in a new context
            try:
                sale = Sale.objects.get(pk=sale_id)
                notify_sale_completion(sale)
            except Sale.DoesNotExist:
                logger.warning(f"Sale {sale_id} not found when sending email notification")
        except Exception:
            logger.exception(f"Failed to send sale email for sale_id={sale_id}")

    # Schedule both operations to run only after successful commit
    transaction.on_commit(_create_sale_notifications)
    transaction.on_commit(_send_sale_email)


@receiver(post_save, sender="tenants.Membership")
def notify_new_agent(sender, instance, created, **kwargs):
    """
    Notify managers when a new agent joins.
    
    Uses transaction.on_commit() to ensure notifications are only created
    after the membership transaction successfully commits.
    """
    if not created or instance.role != "AGENT" or instance.status != "ACTIVE":
        return

    # Capture primitive values immediately
    business_id = instance.business_id
    user_id = instance.user_id
    username = instance.user.username if instance.user else "Unknown"

    def _create_agent_notification():
        """Create notifications for managers about the new agent."""
        try:
            from tenants.models import Membership
            
            managers = (
                Membership.objects.filter(
                    business_id=business_id, 
                    role="MANAGER", 
                    status="ACTIVE"
                )
                .exclude(user_id=user_id)
                .values_list("user_id", flat=True)
            )
            
            for manager_id in managers:
                Notification.objects.create(
                    audience="ADMIN",
                    user_id=manager_id,
                    message=f"New agent joined: {username}",
                    level="info",
                    meta={
                        "type": "new_agent", 
                        "agent_id": user_id, 
                        "agent_username": username
                    },
                )
        except Exception:
            logger.exception(f"Failed to create agent notification for user_id={user_id}")

    transaction.on_commit(_create_agent_notification)


@receiver(post_save, sender="inventory.InventoryItem")
def notify_low_stock(sender, instance, created, **kwargs):
    """
    Notify managers when stock is at or below threshold.
    
    Uses transaction.on_commit() to ensure notifications are only created
    after the inventory update transaction successfully commits.
    """
    if created:
        return

    # Capture primitive values immediately
    item_id = instance.id
    stock = getattr(instance, "stock_available", 0) or 0
    threshold = getattr(instance, "reorder_level", 5) or 5
    business_id = getattr(instance, "business_id", None)
    product_name = getattr(instance, "name", "") or str(instance)

    # Early exit if not low stock
    if stock > threshold or stock <= 0 or not business_id:
        return

    def _create_low_stock_notification():
        """Create low stock notifications for managers."""
        try:
            from tenants.models import Membership
            
            managers = Membership.objects.filter(
                business_id=business_id, 
                role="MANAGER", 
                status="ACTIVE"
            ).values_list("user_id", flat=True)
            
            for manager_id in managers:
                # Check if we already notified about this recently (avoid spam)
                recent = Notification.objects.filter(
                    user_id=manager_id,
                    meta__type="low_stock",
                    meta__product_id=item_id,
                    created_at__gte=timezone.now() - timedelta(hours=24),
                ).exists()
                
                if not recent:
                    Notification.objects.create(
                        audience="ADMIN",
                        user_id=manager_id,
                        message=f"Low stock alert: {product_name} ({stock} remaining)",
                        level="warning",
                        meta={
                            "type": "low_stock",
                            "product_id": item_id,
                            "product_name": product_name,
                            "stock": stock,
                            "threshold": threshold,
                        },
                    )
        except Exception:
            logger.exception(f"Failed to create low stock notification for item_id={item_id}")

    transaction.on_commit(_create_low_stock_notification)


@receiver(post_save, sender="support.Ticket")
def notify_ticket_changes(sender, instance, created, **kwargs):
    """
    Notify about ticket creation and status changes.
    
    Uses transaction.on_commit() to ensure notifications are only created
    after the ticket transaction successfully commits.
    """
    # Capture primitive values immediately
    ticket_id = instance.id
    ticket_reference = instance.reference
    is_created = created
    priority = instance.priority
    status = instance.status
    status_display = instance.get_status_display() if hasattr(instance, 'get_status_display') else status
    
    business_name = instance.business.name if hasattr(instance, 'business') and instance.business else "Unknown"
    creator_id = instance.creator_id if hasattr(instance, 'creator') else None
    is_creator_staff = instance.creator.is_staff if hasattr(instance, 'creator') and instance.creator else False

    def _create_ticket_notification():
        """Create ticket notifications."""
        try:
            if is_created:
                # Notify HQ staff about new ticket
                staff_users = User.objects.filter(is_staff=True, is_active=True)
                for staff_user in staff_users:
                    Notification.objects.create(
                        audience="ADMIN",
                        user=staff_user,
                        message=f"New ticket: {ticket_reference} from {business_name}",
                        level="info",
                        meta={
                            "type": "new_ticket",
                            "ticket_id": ticket_id,
                            "ticket_reference": ticket_reference,
                            "priority": priority,
                        },
                    )
            else:
                # Notify ticket creator about status change
                if creator_id:
                    Notification.objects.create(
                        audience="AGENT" if not is_creator_staff else "ADMIN",
                        user_id=creator_id,
                        message=f"Ticket {ticket_reference} status updated to {status_display}",
                        level="info",
                        meta={
                            "type": "ticket_update",
                            "ticket_id": ticket_id,
                            "ticket_reference": ticket_reference,
                            "status": status,
                        },
                    )
        except Exception:
            logger.exception(f"Failed to create ticket notification for ticket_id={ticket_id}")

    transaction.on_commit(_create_ticket_notification)


@receiver(milestone_reached)
def notify_sales_milestone(sender, business, current_total, previous_total, **kwargs):
    """
    Notify managers when monthly sales exceed previous month's total at the same date.
    
    Uses transaction.on_commit() to ensure notifications are only created
    after the transaction successfully commits.
    """
    # Capture primitive values immediately
    business_id = business.id if business else None
    current_total_float = float(current_total) if current_total else 0
    previous_total_float = float(previous_total) if previous_total else 0

    if not business_id:
        return

    def _create_milestone_notification():
        """Create milestone notifications for managers."""
        try:
            from tenants.models import Membership
            
            managers = Membership.objects.filter(
                business_id=business_id, 
                role="MANAGER", 
                status="ACTIVE"
            ).values_list("user_id", flat=True)
            
            for manager_id in managers:
                Notification.objects.create(
                    audience="ADMIN",
                    user_id=manager_id,
                    message=f"🎉 Sales milestone! Current: {current_total_float:.2f}, Last period: {previous_total_float:.2f}",
                    level="success",
                    meta={
                        "type": "sales_milestone",
                        "current_total": current_total_float,
                        "previous_total": previous_total_float,
                        "business_id": business_id,
                    },
                )
        except Exception:
            logger.exception(f"Failed to create milestone notification for business_id={business_id}")

    transaction.on_commit(_create_milestone_notification)


@receiver(post_save, sender=User)
def create_notification_preference(sender, instance, created, **kwargs):
    """
    Auto-create NotificationPreference when a user is created.
    
    Uses transaction.on_commit() to ensure preference is only created
    after the user transaction successfully commits.
    """
    if not created:
        return
    
    user_id = instance.id

    def _create_preference():
        """Create notification preference for user."""
        try:
            NotificationPreference.get_or_create_default(instance)
        except Exception:
            logger.exception(f"Failed to create notification preference for user_id={user_id}")

    transaction.on_commit(_create_preference)
