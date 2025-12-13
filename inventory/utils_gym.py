"""
Gym-specific utility functions for membership status and business logic.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Optional, TypedDict
from django.utils import timezone

if TYPE_CHECKING:
    from inventory.models_verticals import GymMember


# Constant: 30-day membership period
GYM_MEMBERSHIP_DAYS = 30

# Gym pricing: MWK 55,000 for 30 days
GYM_MONTHLY_FEE = Decimal("55000.00")
GYM_DAILY_RATE = GYM_MONTHLY_FEE / Decimal("30")


class MembershipStatus(TypedDict):
    """Return type for get_membership_status"""
    status_code: str  # "none" | "active" | "expired"
    label: str  # "No membership" | "Active" | "Expired"
    days_remaining: int
    total_days: Optional[int]
    start_date: Optional[date]
    end_date: Optional[date]


def get_membership_status(member: "GymMember", today: Optional[date] = None) -> MembershipStatus:
    """
    Single source of truth for gym membership status calculation (GYM ONLY).
    
    Returns a dict with:
        - status_code: "none" | "active" | "expired"
        - label: "No membership" | "Active" | "Expired"
        - days_remaining: int (inclusive count of days left, including today)
        - total_days: int or None
        - start_date: date or None
        - end_date: date or None
    
    Logic:
        - If no membership period exists: status_code = "none"
        - If membership_end >= today: status_code = "active", days_remaining is calculated inclusively
        - If membership_end < today: status_code = "expired", days_remaining = 0
    
    Days calculation:
        - For a new member with membership starting today and ending in 29 days:
          days_remaining = 30 (inclusive: today + 29 future days)
        - Formula: (membership_end - today).days + 1
    
    Args:
        member: GymMember instance
        today: Optional date for testing; defaults to business-local date
    
    Returns:
        MembershipStatus dict
    """
    if today is None:
        # Use business-local timezone-aware date
        today = timezone.now().date()
    
    # Check if membership dates exist
    if not member.membership_start or not member.membership_end:
        # No membership at all
        return MembershipStatus(
            status_code="none",
            label="No membership",
            days_remaining=0,
            total_days=None,
            start_date=None,
            end_date=None,
        )
    
    # Calculate total days in membership period (inclusive)
    total_days = (member.membership_end - member.membership_start).days + 1
    
    # Check if membership is still active
    if member.membership_end >= today:
        # Active membership: calculate remaining days (inclusive)
        # If membership_end is today, days_remaining should be 1 (today counts)
        # If membership_end is tomorrow, days_remaining should be 2 (today + tomorrow)
        days_remaining = (member.membership_end - today).days + 1
        
        return MembershipStatus(
            status_code="active",
            label="Active",
            days_remaining=days_remaining,
            total_days=total_days,
            start_date=member.membership_start,
            end_date=member.membership_end,
        )
    else:
        # Expired membership
        return MembershipStatus(
            status_code="expired",
            label="Expired",
            days_remaining=0,
            total_days=total_days,
            start_date=member.membership_start,
            end_date=member.membership_end,
        )


def set_membership_dates(payment_date: Optional[date] = None) -> tuple[date, date]:
    """
    Calculate membership start and end dates for a new payment.
    
    Ensures exactly 30 days of membership (inclusive).
    
    Args:
        payment_date: Date of payment; defaults to today
    
    Returns:
        Tuple of (membership_start, membership_end)
        
    Example:
        If payment_date = Jan 1:
        - membership_start = Jan 1
        - membership_end = Jan 30
        - Total days = 30 (Jan 1 through Jan 30 inclusive)
    """
    if payment_date is None:
        payment_date = timezone.now().date()
    
    membership_start = payment_date
    # For exactly 30 days inclusive, end date is start + 29 days
    # Day 1 (start) + 29 days = Day 30 (end)
    membership_end = membership_start + timedelta(days=GYM_MEMBERSHIP_DAYS - 1)
    
    return membership_start, membership_end


def compute_membership_days(start_date: date, duration_days: int, today: Optional[date] = None) -> tuple[int, int]:
    """
    Compute days left and total days for a membership period.
    
    This ensures that days_left NEVER exceeds duration_days, fixing the "31 / 30 days" bug.
    
    Args:
        start_date: When the membership started
        duration_days: Total duration of the membership (e.g., 30)
        today: Current date (defaults to today)
    
    Returns:
        Tuple of (days_left, total_days)
        - days_left: Number of days remaining (0 to duration_days, inclusive)
        - total_days: The duration_days parameter
    
    Example:
        start_date = Jan 1, duration_days = 30, today = Jan 1:
        - days_used = 0 (today is day 0 of elapsed time)
        - days_left = 30
        - Display: "30 / 30 days"
        
        start_date = Jan 1, duration_days = 30, today = Jan 6:
        - days_used = 5 (5 days have elapsed)
        - days_left = 25
        - Display: "25 / 30 days"
        
        start_date = Jan 1, duration_days = 30, today = Jan 31+:
        - days_used >= 30
        - days_left = 0 (capped, never negative)
        - Display: "0 / 30 days"
    """
    if today is None:
        today = timezone.now().date()
    
    total_days = duration_days
    
    # Calculate how many days have passed (including start day)
    # If today == start_date, then 0 days have elapsed
    days_used = (today - start_date).days
    
    # Clamp days_used to [0, total_days]
    if days_used < 0:
        days_used = 0
    if days_used > total_days:
        days_used = total_days
    
    # Calculate days remaining
    days_left = total_days - days_used
    
    return days_left, total_days


def compute_next_payment_date(last_payment_date: Optional[date], duration_days: int) -> Optional[date]:
    """
    Calculate the next payment due date.
    
    Business rule: Next payment is due exactly duration_days after the last payment.
    
    Args:
        last_payment_date: Date of the most recent payment
        duration_days: Membership duration (e.g., 30 days)
    
    Returns:
        The next payment date, or None if no payment has been made
    
    Example:
        last_payment_date = Jan 1, duration_days = 30:
        - next_payment_date = Jan 31 (30 days after Jan 1)
        
        For a 30-day membership starting Jan 1:
        - Membership period: Jan 1 - Jan 30 (30 days inclusive)
        - Next payment due: Jan 31
    """
    if not last_payment_date:
        return None
    
    return last_payment_date + timedelta(days=duration_days)


def calculate_prorated_days(amount: Decimal) -> int:
    """
    Calculate the number of days granted for a payment amount.
    
    Gym pricing: MWK 55,000 for 30 days
    Daily rate: 55,000 / 30 = 1,833.33...
    
    Formula: days = ROUND_HALF_UP(amount / daily_rate), minimum 1 day
    
    Examples:
        - 55,000 MWK => 30 days
        - 110,000 MWK => 60 days
        - 100,000 MWK => 55 days (100,000 / 1,833.33 = 54.545... => 55)
        - 1,000 MWK => 1 day (minimum)
    
    Args:
        amount: Payment amount in MWK
    
    Returns:
        Number of days to grant (minimum 1)
    """
    if amount <= 0:
        return 1
    
    # Calculate days with ROUND_HALF_UP
    days_decimal = (amount / GYM_DAILY_RATE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    days = int(days_decimal)
    
    # Ensure minimum 1 day
    return max(1, days)


def calculate_membership_period(
    amount: Decimal,
    member: "GymMember",
    start_date: Optional[date] = None,
    today: Optional[date] = None
) -> tuple[date, date, int]:
    """
    Calculate the membership start and end dates based on payment amount.
    
    Implements auto-extension logic:
    - If member has active membership (valid_until >= today), extend from current end date
    - Otherwise, start from specified start_date (or today)
    
    Args:
        amount: Payment amount in MWK
        member: GymMember instance
        start_date: Desired start date (defaults to today if member inactive)
        today: Current date for testing (defaults to timezone.now().date())
    
    Returns:
        Tuple of (new_start, new_end, days_granted)
    
    Examples:
        Member inactive, paying 55,000 on Jan 1:
        - new_start = Jan 1
        - new_end = Jan 30 (30 days inclusive)
        - days_granted = 30
        
        Member active until Jan 30, paying 55,000 on Jan 15:
        - new_start = Jan 31 (current_end + 1)
        - new_end = Feb 29 (Jan 31 + 29 days)
        - days_granted = 30
        
        Member inactive, paying 100,000 on Jan 1:
        - new_start = Jan 1
        - new_end = Feb 24 (55 days inclusive)
        - days_granted = 55
    """
    if today is None:
        today = timezone.now().date()
    
    # Calculate days to grant based on amount
    days_granted = calculate_prorated_days(amount)
    
    # Determine start date based on auto-extension logic
    if member.membership_end and member.membership_end >= today:
        # Active member: extend from current end date
        new_start = member.membership_end + timedelta(days=1)
    else:
        # Inactive member: start from specified date or today
        new_start = start_date if start_date else today
    
    # Calculate end date (inclusive)
    # For N days inclusive: end = start + (N - 1) days
    new_end = new_start + timedelta(days=days_granted - 1)
    
    return new_start, new_end, days_granted


def get_business_costs_for_period(business, start_date: date, end_date: date) -> Decimal:
    """
    Calculate total admin costs for a business in a given period.
    
    This uses the same logic as the admin wallet costs page to ensure consistency.
    Costs are pulled from WalletTransaction with:
    - ledger=COMPANY
    - type in [COST_ONCE_OFF, COST_RECURRING]
    - business scoping (no location scoping since WalletTransaction doesn't have location)
    
    Args:
        business: Business instance
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
    
    Returns:
        Total costs as positive Decimal (costs are stored as negative in DB)
    """
    from django.db.models import Sum, Q
    from django.db.models.functions import Coalesce
    from wallet.models import WalletTransaction, Ledger, TxnType
    
    if not business:
        return Decimal("0.00")
    
    # Query admin costs for this business
    admin_costs_qs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
    )
    
    # Filter by effective date range
    # For once-off costs: use effective_date within period
    once_off_q = Q(
        type=TxnType.COST_ONCE_OFF,
        is_recurring=False,
        effective_date__gte=start_date,
        effective_date__lte=end_date,
    )
    
    # For recurring costs: include if effective_from <= end_date
    # (assumes they continue indefinitely once started)
    recurring_q = Q(
        type=TxnType.COST_RECURRING,
        is_recurring=True,
        effective_from__lte=end_date,
    )
    
    period_costs_qs = admin_costs_qs.filter(once_off_q | recurring_q)
    
    # Sum costs (they're stored as negative, so we take absolute value)
    costs_agg = period_costs_qs.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )
    admin_costs_sum = costs_agg.get("total") or Decimal("0.00")
    
    # Convert to positive for display
    return abs(admin_costs_sum)