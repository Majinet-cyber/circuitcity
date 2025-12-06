# sales/signals.py
"""
Signal handlers for Sale model to automatically create wallet transactions.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Sale


@receiver(post_save, sender=Sale)
def create_commission_on_sale(sender, instance, created, **kwargs):
    """
    Automatically create a wallet transaction when a Sale is created.
    
    This ensures commissions are immediately reflected in agent wallets.
    """
    if not created:
        # Only create commission for new sales, not updates
        return
    
    try:
        from wallet.services_commission import record_sale_commission_to_wallet
        
        # Record commission to wallet
        record_sale_commission_to_wallet(
            sale=instance,
            created_by=None,  # System-generated
        )
    except Exception as e:
        # Log error but don't fail the sale
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create commission for Sale #{instance.id}: {e}")
