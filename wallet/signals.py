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


def q2(x) -> Decimal:
    """Quantize to 2 decimal places."""
    from decimal import ROUND_HALF_UP
    if x is None:
        return Decimal("0.00")
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# =============================================================================
# COMMISSION TRACKING ON SALES
# =============================================================================

@receiver(post_save, sender='sales.Sale')
def create_commission_on_phone_sale(sender, instance, created, **kwargs):
    """
    Automatically create commission when a phone sale is created.
    
    Rules:
    - Only for new sales (created=True)
    - Only if agent is assigned
    - Only if sale has a valid price
    """
    if not created:
        return
    
    # Check if this sale has an agent
    agent = getattr(instance, 'agent', None)
    if not agent:
        return
    
    # Get business from item location
    try:
        business = instance.location.business if hasattr(instance, 'location') else None
    except Exception:
        business = None
    
    if not business:
        log.warning(f"Sale {instance.pk} has no business, skipping commission")
        return
    
    # Find agent's membership for this business
    try:
        from tenants.models import Membership
        membership = Membership.objects.filter(
            user=agent,
            business=business,
            role='AGENT',
            status='ACTIVE'
        ).first()
    except Exception as e:
        log.exception(f"Error finding membership for sale {instance.pk}: {e}")
        return
    
    if not membership:
        log.debug(f"Sale {instance.pk}: No active agent membership found for {agent}")
        return
    
    # Calculate commission amount
    price = q2(getattr(instance, 'price', Decimal("0.00")))
    if price <= Decimal("0.00"):
        log.debug(f"Sale {instance.pk} has zero/negative price, skipping commission")
        return
    
    # Get commission percentage (either from sale or from config)
    commission_pct = q2(getattr(instance, 'commission_pct', Decimal("0.00")))
    
    # If no commission percentage on sale, try to get from CommissionConfig
    if commission_pct <= Decimal("0.00"):
        try:
            from sales.models import CommissionConfig
            config = CommissionConfig.objects.filter(
                business=business,
                is_active=True
            ).first()
            if config:
                commission_pct = q2(config.default_rate)
        except Exception:
            pass
    
    # Calculate commission amount
    if commission_pct <= Decimal("0.00"):
        log.debug(f"Sale {instance.pk} has zero commission rate, skipping")
        return
    
    commission_amount = q2((price * commission_pct) / Decimal("100.00"))
    
    if commission_amount <= Decimal("0.00"):
        return
    
    # Add commission to agent wallet
    try:
        from wallet.agent_models import add_commission
        
        txn = add_commission(
            membership=membership,
            amount=commission_amount,
            description=f"Commission for phone sale #{instance.pk}",
            related_sale_id=instance.pk,
            related_sale_model='Sale',
        )
        log.info(f"Created commission {txn.pk} for sale {instance.pk}: {commission_amount}")
    except Exception as e:
        log.exception(f"Failed to create commission for sale {instance.pk}: {e}")


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

