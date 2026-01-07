# inventory/signals_alerts.py
"""
Signal handlers for automatic alert generation.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from datetime import timedelta
from django.utils import timezone
from decimal import Decimal


# Out of Stock Alert
def check_and_create_out_of_stock_alert(product, business, location=None):
    """Check if product is out of stock and create alert if needed."""
    try:
        from inventory.models_alerts import Alert

        # Check if we already have a recent alert for this product
        recent_alert_exists = Alert.objects.filter(
            business=business,
            alert_type="out_of_stock",
            meta__product_name=product.name if hasattr(product, "name") else str(product),
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).exists()

        if recent_alert_exists:
            return  # Don't spam alerts

        # Create alert
        product_name = getattr(product, "name", getattr(product, "model_name", str(product)))
        Alert.create_out_of_stock_alert(business, product_name, location)

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to create out of stock alert: {e}")


# Low Stock Alert
def check_and_create_low_stock_alert(product, business, location=None):
    """Check if product is low on stock and create alert if needed."""
    try:
        from inventory.models_alerts import Alert

        quantity = getattr(product, "quantity", 0)
        threshold = getattr(product, "low_stock_threshold", 10)

        if quantity <= 0 or quantity > threshold:
            return  # Not low stock

        product_name = getattr(product, "name", getattr(product, "model_name", str(product)))

        # Check if we already have a recent alert for this product
        recent_alert_exists = Alert.objects.filter(
            business=business,
            alert_type="low_stock",
            meta__product_name=product_name,
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).exists()

        if recent_alert_exists:
            return  # Don't spam alerts

        # Create alert
        Alert.create_low_stock_alert(business, product_name, quantity, threshold, location)

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to create low stock alert: {e}")


# Top Agent Alert (triggered weekly)
def check_and_create_top_agent_alert(business):
    """Check for top performing agent and create alert."""
    try:
        from inventory.models_alerts import Alert
        from sales.models import Sale
        from datetime import date
        from django.db.models import Count, Sum

        # Check if we already have a top agent alert this week
        week_start = timezone.now().date() - timedelta(days=timezone.now().weekday())
        recent_alert_exists = Alert.objects.filter(
            business=business,
            alert_type="top_agent",
            created_at__gte=timezone.make_aware(timezone.datetime.combine(week_start, timezone.datetime.min.time())),
        ).exists()

        if recent_alert_exists:
            return  # Already created this week

        # Find top agent this week
        week_end = timezone.now().date()

        top_agents = (
            Sale.objects.filter(
                item__business=business,
                sold_at__date__gte=week_start,
                sold_at__date__lte=week_end,
                agent__isnull=False,
            )
            .values("agent__username", "agent__first_name", "agent__last_name")
            .annotate(
                sales_count=Count("id"),
                revenue=Sum("price"),
            )
            .order_by("-sales_count")[:1]
        )

        if not top_agents:
            return  # No sales this week

        top = top_agents[0]
        agent_name = f"{top['agent__first_name']} {top['agent__last_name']}".strip() or top["agent__username"]

        # Create alert
        Alert.create_top_agent_alert(
            business,
            agent_name,
            period="week",
            sales_count=top["sales_count"],
            revenue=top["revenue"] or Decimal("0.00"),
        )

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to create top agent alert: {e}")


# Signal handlers for pharmacy products
try:
    from inventory.models_pharmacy import PharmacyProduct

    @receiver(post_save, sender=PharmacyProduct)
    def pharmacy_product_stock_check(sender, instance, created, **kwargs):
        """Check pharmacy product stock levels and create alerts."""
        if created:
            return  # Don't alert on creation

        business = instance.business
        location = getattr(instance, "location", None)

        if instance.quantity == 0:
            check_and_create_out_of_stock_alert(instance, business, location)
        elif instance.quantity > 0:
            check_and_create_low_stock_alert(instance, business, location)

except ImportError:
    pass


# Signal handlers for liquor products
try:
    from inventory.models_verticals import LiquorProduct

    @receiver(post_save, sender=LiquorProduct)
    def liquor_product_stock_check(sender, instance, created, **kwargs):
        """Check liquor product stock levels and create alerts."""
        if created:
            return

        business = instance.business
        location = getattr(instance, "location", None)

        if instance.quantity == 0:
            check_and_create_out_of_stock_alert(instance, business, location)
        elif instance.quantity > 0 and instance.quantity <= 10:  # Assume 10 as threshold
            check_and_create_low_stock_alert(instance, business, location)

except ImportError:
    pass


# Signal handlers for clothing products
try:
    from inventory.models_verticals import ClothingProduct

    @receiver(post_save, sender=ClothingProduct)
    def clothing_product_stock_check(sender, instance, created, **kwargs):
        """Check clothing product stock levels and create alerts."""
        if created:
            return

        business = instance.business
        location = getattr(instance, "location", None)

        if instance.quantity == 0:
            check_and_create_out_of_stock_alert(instance, business, location)
        elif instance.quantity > 0 and instance.quantity <= 5:
            check_and_create_low_stock_alert(instance, business, location)

except ImportError:
    pass


# Weekly top agent check (called via management command or celery task)
def generate_weekly_top_agent_alerts():
    """Generate top agent alerts for all businesses (called weekly)."""
    try:
        from tenants.models import Business

        for business in Business.objects.filter(status="ACTIVE"):
            check_and_create_top_agent_alert(business)

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to generate weekly top agent alerts: {e}")
