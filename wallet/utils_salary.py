# wallet/utils_salary.py
"""
Salary helpers for Phones vertical agents.

Requirements:
- Base salary of MWK 50,000 per month for all Phones agents
- Exactly 1 base salary transaction per agent per business per month
- Idempotent (no duplicates on wallet refresh/multiple sales)
- Timezone-aware month boundaries
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import WalletTransaction, TxnType, Ledger

log = logging.getLogger(__name__)

# Base salary amount for Phones agents (MWK 50,000)
PHONES_BASE_SALARY = Decimal("50000.00")

User = get_user_model()


def _is_phones_business(business) -> bool:
    """Check if business is Phones vertical."""
    if not business:
        return False
    
    business_kind = getattr(business, "business_kind", "").lower()
    return business_kind == "phones"


def _is_agent_for_business(user, business) -> bool:
    """
    Check if user is an AGENT for the given business.
    
    Tries to find an active AGENT membership via common patterns:
    - tenants.Membership model
    - profile.business
    - direct business FK
    """
    if not user or not business:
        return False
    
    # Try via Membership model (most common pattern)
    try:
        from tenants.models import Membership
        
        membership = Membership.objects.filter(
            user=user,
            business=business,
            role="AGENT",
            status="ACTIVE"
        ).exists()
        
        if membership:
            return True
    except (ImportError, Exception):
        pass
    
    # Fallback: check profile.business
    try:
        prof = getattr(user, "profile", None)
        if prof and getattr(prof, "business_id", None) == business.id:
            # Assume agents are not staff
            return not user.is_staff
    except Exception:
        pass
    
    return False


def ensure_monthly_base_salary_for_agent(
    business,
    user,
    today: Optional = None
) -> Optional[WalletTransaction]:
    """
    Ensure base salary transaction exists for the current month.
    
    Only runs if:
    - business is Phones vertical
    - user is an AGENT for that business (active membership)
    
    Returns:
    - Existing or newly created WalletTransaction if applicable
    - None if conditions not met or already exists
    
    Idempotency:
    - Checks for existing base salary txn for this (business, user, month_key)
    - If exists, returns None (no duplicate created)
    """
    today = today or timezone.localdate()
    
    # 1. Check if Phones business
    if not _is_phones_business(business):
        return None
    
    # 2. Check if user is agent for this business
    if not _is_agent_for_business(user, business):
        return None
    
    # 3. Determine current month start and month key
    month_start = today.replace(day=1)
    month_key = today.strftime("%Y-%m")  # e.g., "2025-12"
    
    # 4. Check if base salary already exists for this month
    existing = WalletTransaction.objects.filter(
        ledger=Ledger.AGENT,
        agent=user,
        business=business,
        type=TxnType.BONUS,  # We'll use BONUS type with special meta marker
        meta__kind="phones_base_salary",
        meta__month=month_key,
    ).first()
    
    if existing:
        log.debug(
            f"Base salary already exists for {user.username} "
            f"in {business.name} for {month_key}"
        )
        return None
    
    # 5. Create base salary transaction
    try:
        txn = WalletTransaction.objects.create(
            ledger=Ledger.AGENT,
            agent=user,
            business=business,
            type=TxnType.BONUS,  # Using BONUS type to distinguish from commission
            amount=PHONES_BASE_SALARY,
            note=f"Base salary for {month_key}",
            reference=f"SALARY-{month_key}",
            effective_date=month_start,  # Use month start for consistent grouping
            created_by=None,  # System-generated
            meta={
                "kind": "phones_base_salary",
                "month": month_key,
                "amount": str(PHONES_BASE_SALARY),
            },
        )
        
        log.info(
            f"Created base salary txn {txn.id} for {user.username} "
            f"in {business.name} for {month_key}: {PHONES_BASE_SALARY}"
        )
        
        return txn
    
    except Exception as e:
        log.exception(
            f"Failed to create base salary for {user.username} "
            f"in {business.name} for {month_key}: {e}"
        )
        return None


def get_base_salary_for_month(business, user, year: int, month: int) -> Decimal:
    """
    Get the base salary amount for a specific month.
    
    Args:
        business: Business instance
        user: User instance
        year: Year (e.g., 2025)
        month: Month (1-12)
    
    Returns:
        Decimal: Base salary amount if exists, else Decimal("0.00")
    """
    if not _is_phones_business(business):
        return Decimal("0.00")
    
    if not _is_agent_for_business(user, business):
        return Decimal("0.00")
    
    month_key = f"{year}-{month:02d}"
    
    txn = WalletTransaction.objects.filter(
        ledger=Ledger.AGENT,
        agent=user,
        business=business,
        type=TxnType.BONUS,
        meta__kind="phones_base_salary",
        meta__month=month_key,
    ).first()
    
    if txn:
        return txn.amount
    
    return Decimal("0.00")

