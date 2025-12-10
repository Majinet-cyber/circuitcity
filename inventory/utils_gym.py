"""
Gym-specific utility functions for membership status and business logic.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional, TypedDict
from django.utils import timezone

if TYPE_CHECKING:
    from inventory.models_verticals import GymMember


# Constant: 30-day membership period
GYM_MEMBERSHIP_DAYS = 30


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

