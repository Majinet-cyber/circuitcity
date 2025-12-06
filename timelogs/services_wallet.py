# timelogs/services_wallet.py
"""
Time log wallet integration - sync penalties and bonuses to agent wallets.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from datetime import date

from django.db import transaction
from django.utils import timezone


def sync_timelog_to_wallet(work_log, *, created_by=None):
    """
    Sync a single AgentWorkLog's penalties and bonuses to the wallet.
    
    This is idempotent - only creates wallet transactions if not already processed.
    
    Args:
        work_log: AgentWorkLog instance
        created_by: User creating the transactions (optional)
        
    Returns:
        dict with created transactions
    """
    if work_log.wallet_processed:
        # Already processed, skip
        return {"already_processed": True, "transactions": []}
    
    try:
        from wallet.models import WalletTransaction, TxnType, Ledger
    except ImportError:
        return {"error": "Wallet models not available"}
    
    transactions = []
    
    # Create bonus transaction if applicable
    if work_log.bonus_amount > 0:
        txn = WalletTransaction.objects.create(
            ledger=Ledger.AGENT,
            agent=work_log.agent,
            type=TxnType.BONUS,
            amount=work_log.bonus_amount,
            note=f"Early arrival bonus ({work_log.arrived_early_minutes} min early)",
            reference=f"TIMELOG-{work_log.id}-BONUS",
            effective_date=work_log.work_date,
            created_by=created_by,
            business=work_log.business,
            meta={
                "work_log_id": work_log.id,
                "early_minutes": work_log.arrived_early_minutes,
                "work_date": str(work_log.work_date),
            },
        )
        transactions.append(txn)
    
    # Create penalty transaction if applicable
    if work_log.penalty_amount > 0:
        txn = WalletTransaction.objects.create(
            ledger=Ledger.AGENT,
            agent=work_log.agent,
            type=TxnType.PENALTY,
            amount=-work_log.penalty_amount,  # Negative for deduction
            note=f"Lateness penalty ({work_log.arrived_late_minutes} min late)",
            reference=f"TIMELOG-{work_log.id}-PENALTY",
            effective_date=work_log.work_date,
            created_by=created_by,
            business=work_log.business,
            meta={
                "work_log_id": work_log.id,
                "late_minutes": work_log.arrived_late_minutes,
                "work_date": str(work_log.work_date),
            },
        )
        transactions.append(txn)
    
    # Mark as processed
    work_log.wallet_processed = True
    work_log.save(update_fields=["wallet_processed"])
    
    return {
        "already_processed": False,
        "transactions": transactions,
        "bonus_amount": work_log.bonus_amount,
        "penalty_amount": work_log.penalty_amount,
    }


def bulk_sync_timelogs_to_wallet(business, start_date: date, end_date: date, *, created_by=None):
    """
    Sync all unprocessed time logs for a date range to wallet.
    
    Args:
        business: Business instance
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        created_by: User creating the transactions
        
    Returns:
        dict with stats
    """
    try:
        from timelogs.models import AgentWorkLog
    except ImportError:
        return {"error": "Timelogs models not available"}
    
    work_logs = AgentWorkLog.objects.filter(
        business=business,
        work_date__gte=start_date,
        work_date__lte=end_date,
        wallet_processed=False,
    ).select_related("agent")
    
    results = {
        "processed": 0,
        "skipped": 0,
        "total_bonus": Decimal("0.00"),
        "total_penalty": Decimal("0.00"),
        "errors": [],
    }
    
    for log in work_logs:
        try:
            result = sync_timelog_to_wallet(log, created_by=created_by)
            if result.get("already_processed"):
                results["skipped"] += 1
            else:
                results["processed"] += 1
                results["total_bonus"] += result.get("bonus_amount", Decimal("0.00"))
                results["total_penalty"] += result.get("penalty_amount", Decimal("0.00"))
        except Exception as e:
            results["errors"].append({
                "work_log_id": log.id,
                "agent_id": log.agent_id,
                "error": str(e),
            })
    
    return results


def calculate_timelog_bonuses_penalties(work_log):
    """
    Calculate and apply bonuses/penalties for a work log based on the business config.
    
    This should be called when a work log is finalized (end of day or manual close).
    
    Args:
        work_log: AgentWorkLog instance
        
    Returns:
        dict with calculated amounts
    """
    try:
        from sales.models import CommissionConfig
    except ImportError:
        # Fallback to default values
        config = None
    else:
        config = CommissionConfig.get_active(work_log.business) if work_log.business else None
    
    # Default values if no config
    early_bonus_per_30min = Decimal("5000.00")
    late_penalty_per_30min = Decimal("7000.00")
    early_bonus_enabled = True
    late_penalty_enabled = True
    
    if config:
        early_bonus_per_30min = config.early_bonus_per_30min
        late_penalty_per_30min = config.late_penalty_per_30min
        early_bonus_enabled = config.early_bonus_enabled
        late_penalty_enabled = config.lateness_penalties_enabled
    
    # Calculate bonuses
    bonus_amount = Decimal("0.00")
    if early_bonus_enabled and work_log.early_bonus_blocks > 0:
        bonus_amount = early_bonus_per_30min * work_log.early_bonus_blocks
    
    # Calculate penalties
    penalty_amount = Decimal("0.00")
    if late_penalty_enabled and work_log.late_penalty_blocks > 0:
        penalty_amount = late_penalty_per_30min * work_log.late_penalty_blocks
    
    # Update work log
    work_log.bonus_amount = bonus_amount
    work_log.penalty_amount = penalty_amount
    work_log.save(update_fields=["bonus_amount", "penalty_amount"])
    
    return {
        "bonus_amount": bonus_amount,
        "penalty_amount": penalty_amount,
        "early_blocks": work_log.early_bonus_blocks,
        "late_blocks": work_log.late_penalty_blocks,
    }

