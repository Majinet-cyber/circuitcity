# notifications/signals.py
"""
Signal handlers for creating notifications on important events.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver, Signal
from django.contrib.auth import get_user_model
from .models import Notification

User = get_user_model()

# Custom signals
milestone_reached = Signal()


@receiver(post_save, sender='sales.Sale')
def notify_new_sale(sender, instance, created, **kwargs):
    """Notify when a new sale is recorded."""
    if not created:
        return
    
    try:
        # Get business from location (Sale model doesn't have direct business field)
        business = getattr(instance.location, 'business', None) if hasattr(instance, 'location') else None
        
        # Get product info from the item
        product_name = "Unknown Product"
        imei = ""
        if hasattr(instance, 'item') and instance.item:
            item = instance.item
            # Try to get product name from various possible fields
            if hasattr(item, 'product') and item.product:
                product = item.product
                product_name = f"{getattr(product, 'brand', '')} {getattr(product, 'model', '')}".strip() or str(product)
            elif hasattr(item, 'name'):
                product_name = item.name
            elif hasattr(item, 'sku'):
                product_name = f"SKU: {item.sku}"
            
            # Try to get IMEI/serial
            imei = getattr(item, 'imei', '') or getattr(item, 'serial', '') or getattr(item, 'code', '')
        
        # Format price safely
        sale_price = float(instance.price) if instance.price else 0
        
        # Create a notification for this sale so managers see it in the bell dropdown.
        # Notify all managers of the business
        if business:
            from tenants.models import Membership
            managers = Membership.objects.filter(
                business=business,
                role__in=['MANAGER', 'ADMIN'],
                status='ACTIVE'
            ).values_list('user_id', flat=True)
            
            # Format the notification message
            agent_name = instance.agent.username if instance.agent else 'Unknown'
            msg_parts = [f"Sale recorded: {product_name}"]
            if imei:
                msg_parts.append(f"(IMEI: {imei})")
            msg_parts.append(f"sold for MK {sale_price:,.0f}")
            message = " ".join(msg_parts)
            
            for manager_id in managers:
                Notification.objects.create(
                    audience='ADMIN',
                    user_id=manager_id,
                    message=message,
                    level='success',
                    meta={
                        'type': 'new_sale',
                        'sale_id': instance.id,
                        'amount': sale_price,
                        'agent_id': instance.agent.id if instance.agent else None,
                        'agent_name': agent_name,
                        'product': product_name,
                        'imei': imei,
                    }
                )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create sale notification: {e}")


@receiver(post_save, sender='tenants.Membership')
def notify_new_agent(sender, instance, created, **kwargs):
    """Notify managers when a new agent joins."""
    if not created or instance.role != 'AGENT' or instance.status != 'ACTIVE':
        return
    
    try:
        from tenants.models import Membership
        
        # Notify all managers of this business
        managers = Membership.objects.filter(
            business=instance.business,
            role='MANAGER',
            status='ACTIVE'
        ).exclude(user=instance.user).values_list('user_id', flat=True)
        
        for manager_id in managers:
            Notification.objects.create(
                audience='ADMIN',
                user_id=manager_id,
                message=f"New agent joined: {instance.user.username}",
                level='info',
                meta={
                    'type': 'new_agent',
                    'agent_id': instance.user.id,
                    'agent_username': instance.user.username
                }
            )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create agent notification: {e}")


@receiver(post_save, sender='inventory.InventoryItem')
def notify_low_stock(sender, instance, created, **kwargs):
    """Notify managers when stock is at or below threshold."""
    if created:
        return
    
    try:
        # Check if stock_available is at or below reorder_level
        stock = getattr(instance, 'stock_available', 0) or 0
        threshold = getattr(instance, 'reorder_level', 5) or 5
        
        if stock <= threshold and stock > 0:
            from tenants.models import Membership
            
            business = getattr(instance, 'business', None)
            if not business:
                return
            
            # Notify managers
            managers = Membership.objects.filter(
                business=business,
                role='MANAGER',
                status='ACTIVE'
            ).values_list('user_id', flat=True)
            
            product_name = getattr(instance, 'name', '') or str(instance)
            
            for manager_id in managers:
                # Check if we already notified about this recently (avoid spam)
                recent = Notification.objects.filter(
                    user_id=manager_id,
                    meta__type='low_stock',
                    meta__product_id=instance.id,
                    created_at__gte=timezone.now() - timedelta(hours=24)
                ).exists()
                
                if not recent:
                    Notification.objects.create(
                        audience='ADMIN',
                        user_id=manager_id,
                        message=f"Low stock alert: {product_name} ({stock} remaining)",
                        level='warning',
                        meta={
                            'type': 'low_stock',
                            'product_id': instance.id,
                            'product_name': product_name,
                            'stock': stock,
                            'threshold': threshold
                        }
                    )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create low stock notification: {e}")


@receiver(post_save, sender='support.Ticket')
def notify_ticket_changes(sender, instance, created, **kwargs):
    """Notify about ticket creation and status changes."""
    try:
        if created:
            # Notify HQ staff about new ticket
            staff_users = User.objects.filter(is_staff=True, is_active=True)
            for staff_user in staff_users:
                Notification.objects.create(
                    audience='ADMIN',
                    user=staff_user,
                    message=f"New ticket: {instance.reference} from {instance.business.name}",
                    level='info',
                    meta={
                        'type': 'new_ticket',
                        'ticket_id': instance.id,
                        'ticket_reference': instance.reference,
                        'priority': instance.priority
                    }
                )
        else:
            # Notify ticket creator about status change
            if instance.creator:
                Notification.objects.create(
                    audience='AGENT' if not instance.creator.is_staff else 'ADMIN',
                    user=instance.creator,
                    message=f"Ticket {instance.reference} status updated to {instance.get_status_display()}",
                    level='info',
                    meta={
                        'type': 'ticket_update',
                        'ticket_id': instance.id,
                        'ticket_reference': instance.reference,
                        'status': instance.status
                    }
                )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create ticket notification: {e}")


@receiver(milestone_reached)
def notify_sales_milestone(sender, business, current_total, previous_total, **kwargs):
    """Notify managers when monthly sales exceed previous month's total at the same date."""
    try:
        from tenants.models import Membership
        
        managers = Membership.objects.filter(
            business=business,
            role='MANAGER',
            status='ACTIVE'
        ).values_list('user_id', flat=True)
        
        for manager_id in managers:
            Notification.objects.create(
                audience='ADMIN',
                user_id=manager_id,
                message=f"🎉 Sales milestone! Current: {current_total:.2f}, Last period: {previous_total:.2f}",
                level='success',
                meta={
                    'type': 'sales_milestone',
                    'current_total': float(current_total),
                    'previous_total': float(previous_total),
                    'business_id': business.id
                }
            )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create milestone notification: {e}")


# Import timezone for date comparisons
from django.utils import timezone
from datetime import timedelta
