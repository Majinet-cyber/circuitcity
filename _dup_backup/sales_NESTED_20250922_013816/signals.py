from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from sales.models import Sale
from inventory.models import InventoryAudit

@receiver(post_save, sender=Sale)
def mark_item_sold(sender, instance: Sale, created, **kwargs):
    item = instance.item
    # Set item.sold_at if missing or older
    if not item.sold_at or item.sold_at < instance.created_at:
        item.sold_at = instance.created_at
    if item.status != "SOLD":
        item.status = "SOLD"
    item.save(update_fields=["sold_at", "status"])
    # Lightweight audit record
    InventoryAudit.objects.create(
        item=item,
        action="SOLD",
        by_user=instance.agent,
        details=f"Sold at {instance.location} for MK{instance.price} (commission {instance.commission_pct}%).",
    )




