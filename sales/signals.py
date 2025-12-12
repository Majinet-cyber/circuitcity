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
    
    This is the SINGLE SOURCE OF TRUTH for sale commission creation.
    Creates BOTH WalletTransaction (for old system) and AgentWalletTransaction (for new system).
    
    Idempotency: Checks for existing commissions to prevent duplicates.
    """
    if not created:
        # Only create commission for new sales, not updates
        return
    
    # Check if agent is assigned
    if not instance.agent:
        return
    
    # Get business from location
    try:
        business = instance.location.business if instance.location else None
    except Exception:
        business = None
    
    if not business:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Sale #{instance.id} has no business, skipping commission")
        return
    
    # Check for idempotency - prevent duplicate commissions
    try:
        from wallet.models import WalletTransaction, TxnType, Ledger
        
        existing = WalletTransaction.objects.filter(
            business=business,
            agent=instance.agent,
            type=TxnType.COMMISSION,
            meta__sale_id=instance.id,
        ).exists()
        
        if existing:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Commission already exists for Sale #{instance.id}, skipping duplicate")
            return
    except Exception:
        pass  # If WalletTransaction doesn't exist, continue
    
    try:
        from wallet.services_commission import record_sale_commission_to_wallet
        
        # Record commission to wallet (creates WalletTransaction)
        record_sale_commission_to_wallet(
            sale=instance,
            created_by=None,  # System-generated
            business=business,
        )
    except Exception as e:
        # Log error but don't fail the sale
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create commission for Sale #{instance.id}: {e}")
