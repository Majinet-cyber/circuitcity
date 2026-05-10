# wallet/signals.py
"""
Signal handlers for automatic wallet operations:
- Commission tracking on sales
- Penalty deductions on timelogs
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

log = logging.getLogger(__name__)

from .money import q2


# =============================================================================
# COMMISSION TRACKING ON SALES
# =============================================================================

# REMOVED: Duplicate signal - commission is now created in sales/signals.py only
# This signal was causing duplicate commissions (WalletTransaction + AgentWalletTransaction)
# and double-counting of units sold. The sales/signals.py signal is the single source of truth.


# =============================================================================
# TIMELOG PENALTIES
# =============================================================================

@receiver(post_save, sender='timelogs.AgentWorkLog')
def process_timelog_penalties(sender, instance, created, **kwargs):
    """
    Automatically deduct penalties from agent wallet when timelog is marked with penalty.
    
    Rules:
    - Only process if penalty_amount > 0
    - Only process once (check wallet_processed flag)
    - Find agent's active membership
    - Use add_deduction helper
    """
    # Skip if already processed
    if getattr(instance, 'wallet_processed', False):
        return
    
    # Skip if no penalty
    penalty = Decimal(str(getattr(instance, 'penalty_amount', 0) or 0))
    if penalty <= Decimal("0.00"):
        return
    
    # Get agent and business
    try:
        agent = instance.agent
        business = instance.business
    except Exception as e:
        log.exception(f"Error getting agent/business for timelog {instance.pk}: {e}")
        return
    
    # Find membership
    try:
        from tenants.models import Membership
        membership = Membership.objects.filter(
            user=agent,
            business=business,
            role='AGENT',
            status='ACTIVE'
        ).first()
    except Exception as e:
        log.exception(f"Error finding membership for timelog {instance.pk}: {e}")
        return
    
    if not membership:
        log.warning(f"Timelog {instance.pk}: No active membership for {agent}")
        return
    
    # Check if agent has sufficient balance
    try:
        from wallet.agent_models import get_or_create_agent_wallet
        wallet = get_or_create_agent_wallet(membership)
        
        if wallet.balance < penalty:
            log.warning(
                f"Timelog {instance.pk}: Insufficient balance for penalty. "
                f"Balance: {wallet.balance}, Penalty: {penalty}"
            )
            # You might want to send a notification here
            return
    except Exception as e:
        log.exception(f"Error checking wallet balance for timelog {instance.pk}: {e}")
        return
    
    # Add deduction
    try:
        from wallet.agent_models import add_deduction
        
        reason = f"Late attendance penalty on {instance.date}"
        
        txn = add_deduction(
            membership=membership,
            amount=penalty,
            description=reason,
            related_timelog=instance,
        )
        
        # Mark as processed
        instance.wallet_processed = True
        instance.save(update_fields=['wallet_processed'])
        
        log.info(f"Deducted penalty {txn.pk} for timelog {instance.pk}: {penalty}")
    except Exception as e:
        log.exception(f"Failed to deduct penalty for timelog {instance.pk}: {e}")

