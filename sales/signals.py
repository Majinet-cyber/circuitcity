# sales/signals.py
"""
Signal handlers for Sale model to automatically create wallet transactions.

IMPORTANT: All commission creation is wrapped in transaction.on_commit() to ensure:
1. Commissions are only created after successful transaction commits
2. No DB writes occur during failed/rolled-back atomic blocks (Postgres safe)
3. No spurious ERROR logs for expected rollbacks
"""
import logging
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Sale

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Sale)
def create_commission_on_sale(sender, instance, created, **kwargs):
    """
    Automatically create a wallet transaction when a Sale is created.

    This is the SINGLE SOURCE OF TRUTH for sale commission creation.
    Creates BOTH WalletTransaction (for old system) and AgentWalletTransaction (for new system).

    Idempotency: Checks for existing commissions to prevent duplicates.
    
    Uses transaction.on_commit() to ensure commission creation only happens
    after the sale transaction successfully commits.
    """
    if not created:
        # Only create commission for new sales, not updates
        return

    # Check if agent is assigned
    if not instance.agent:
        return

    # Capture primitive values immediately (no lazy DB lookups later)
    sale_id = instance.id
    agent_id = instance.agent_id
    location_id = getattr(instance, 'location_id', None)
    
    # Get business_id from location
    business_id = None
    try:
        if instance.location and instance.location.business:
            business_id = instance.location.business_id
    except Exception:
        pass

    if not business_id:
        logger.warning(f"Sale #{sale_id} has no business, skipping commission")
        return

    def _create_commission():
        """
        Create commission for the sale.
        This runs ONLY after successful transaction commit.
        """
        try:
            from wallet.models import WalletTransaction, TxnType
            from sales.models import Sale as SaleModel
            from tenants.models import Business

            # Re-fetch sale and business since we're in a new context
            try:
                sale = SaleModel.objects.get(pk=sale_id)
                business = Business.objects.get(pk=business_id)
            except (SaleModel.DoesNotExist, Business.DoesNotExist) as e:
                logger.warning(f"Sale or business not found for commission: sale_id={sale_id}, business_id={business_id}")
                return

            # Check for idempotency - prevent duplicate commissions
            existing = WalletTransaction.objects.filter(
                business=business,
                agent_id=agent_id,
                type=TxnType.COMMISSION,
                meta__sale_id=sale_id,
            ).exists()

            if existing:
                logger.debug(f"Commission already exists for Sale #{sale_id}, skipping duplicate")
                return

            from wallet.services_commission import record_sale_commission_to_wallet

            # Record commission to wallet (creates WalletTransaction)
            record_sale_commission_to_wallet(
                sale=sale,
                created_by=None,  # System-generated
                business=business,
            )
        except Exception:
            logger.exception(f"Failed to create commission for sale_id={sale_id}")

    # Schedule commission creation to run only after successful commit
    transaction.on_commit(_create_commission)
