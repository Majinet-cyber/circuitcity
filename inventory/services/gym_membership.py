"""
Single Source of Truth (SSOT) for Gym Membership Period Computations.

This service centralizes ALL membership period calculations including:
- days_used, days_left, days_left_current
- membership_end
- next_payment_date

All date calculations use timezone-aware dates and consistent plan duration defaults (30 days).

Usage:
    from inventory.services.gym_membership import GymMembershipService
    
    service = GymMembershipService(member)
    
    # Get all membership computations at once
    status = service.get_membership_status()
    print(f"Days left: {status['days_left']}/{status['total_days']}")
    print(f"Next payment: {status['next_payment_date']}")
    
    # Or get individual computations
    days_left = service.get_days_left()
    days_used = service.get_days_used()
    next_payment = service.get_next_payment_date()
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional, TypedDict
from django.utils import timezone

if TYPE_CHECKING:
    from inventory.models_verticals import GymMember

# Constants
DEFAULT_MEMBERSHIP_DURATION_DAYS = 30


class MembershipStatusDict(TypedDict):
    """Return type for membership status computation."""
    
    # Status indicators
    status_code: str  # "none" | "active" | "expired"
    status_label: str  # "No membership" | "Active" | "Expired"
    is_active: bool
    
    # Period dates
    membership_start: Optional[date]
    membership_end: Optional[date]
    
    # Day calculations
    total_days: int  # Total duration of membership period
    days_used: int  # Days elapsed since start (0 to total_days)
    days_left: int  # Days remaining (0 to total_days)
    days_left_current: int  # Alias for days_left (for backward compatibility)
    
    # Display formatting
    days_display: str  # "25 / 30 days"
    
    # Payment information
    last_payment_date: Optional[date]
    next_payment_date: Optional[date]


class GymMembershipService:
    """
    Single source of truth for gym membership period computations.
    
    This service provides all membership-related calculations using consistent
    logic and timezone-aware dates.
    
    Business Rules:
    - Default membership duration: 30 days
    - Membership period is INCLUSIVE: start_date to end_date both count
    - For 30-day membership starting Jan 1: end_date is Jan 30 (start + 29 days)
    - Days used calculation: (today - start_date).days (0 on payment day)
    - Days left calculation: (end_date - today).days + 1 (30 on payment day)
    - Next payment date: last_payment_date + duration_days
    
    Examples:
        # New member on Jan 1
        member.membership_start = Jan 1
        member.membership_end = Jan 30
        service.get_days_left(today=Jan 1) => 30
        service.get_days_used(today=Jan 1) => 0
        service.get_next_payment_date() => Jan 31
        
        # 5 days later on Jan 6
        service.get_days_left(today=Jan 6) => 25
        service.get_days_used(today=Jan 6) => 5
        
        # Last day on Jan 30
        service.get_days_left(today=Jan 30) => 1
        service.get_days_used(today=Jan 30) => 29
        
        # Expired on Jan 31
        service.get_days_left(today=Jan 31) => 0
        service.get_days_used(today=Jan 31) => 30 (capped)
    """
    
    def __init__(self, member: "GymMember"):
        """
        Initialize service with a gym member.
        
        Args:
            member: GymMember instance to calculate periods for
        """
        self.member = member
    
    def _get_today(self, today: Optional[date] = None) -> date:
        """
        Get today's date (timezone-aware).
        
        Args:
            today: Optional date for testing; defaults to business-local date
            
        Returns:
            Date instance (not datetime)
        """
        if today is not None:
            return today
        return timezone.now().date()
    
    def get_duration_days(self) -> int:
        """
        Get the total duration of the membership period in days.
        
        If member has an active membership period (membership_start and membership_end),
        calculates the actual duration (inclusive).
        
        Otherwise returns the default duration (30 days).
        
        Returns:
            Total membership duration in days
            
        Examples:
            # Member with membership Jan 1 to Jan 30
            get_duration_days() => 30  # (Jan 30 - Jan 1).days + 1
            
            # Member with no membership
            get_duration_days() => 30  # default
        """
        if self.member.membership_start and self.member.membership_end:
            # Calculate actual duration (inclusive)
            return (self.member.membership_end - self.member.membership_start).days + 1
        
        return DEFAULT_MEMBERSHIP_DURATION_DAYS
    
    def get_membership_end(self, today: Optional[date] = None) -> Optional[date]:
        """
        Get the membership end date.
        
        Returns the member's membership_end field directly.
        This is set when payment is made.
        
        Args:
            today: Optional date for testing (not used, here for API consistency)
            
        Returns:
            End date of current membership period, or None if no membership
            
        Examples:
            # Member with membership Jan 1 to Jan 30
            get_membership_end() => Jan 30
            
            # Member with no membership
            get_membership_end() => None
        """
        return self.member.membership_end
    
    def get_days_used(self, today: Optional[date] = None) -> int:
        """
        Calculate how many days have been used in the current membership period.
        
        Formula: (today - membership_start).days
        - On payment day (today == start): returns 0
        - After 5 days: returns 5
        - Capped at duration_days if exceeded
        
        Returns 0 if:
        - No membership exists (no membership_start)
        - Today is before the membership start date (negative days clamped to 0)
        
        Returns duration_days if:
        - Today is after the membership has expired (capped at duration_days)
        
        Args:
            today: Optional date for testing; defaults to today
            
        Returns:
            Number of days used (0 to duration_days)
            
        Examples:
            # Jan 1: Payment day
            get_days_used(today=Jan 1) => 0
            
            # Jan 6: 5 days later
            get_days_used(today=Jan 6) => 5
            
            # Feb 1: Expired (31 days later)
            get_days_used(today=Feb 1) => 30 (capped at duration)
        """
        if not self.member.membership_start:
            return 0
        
        today = self._get_today(today)
        duration_days = self.get_duration_days()
        
        # Calculate days elapsed since start
        used = (today - self.member.membership_start).days
        
        # Clamp to valid range [0, duration_days]
        if used < 0:
            return 0
        if used > duration_days:
            return duration_days
        
        return used
    
    def get_days_left(self, today: Optional[date] = None) -> int:
        """
        Calculate remaining days in the current membership period (inclusive).
        
        Formula: (membership_end - today).days + 1
        - On payment day: returns duration_days (e.g., 30)
        - After 5 days: returns duration_days - 5 (e.g., 25)
        - On last day (today == end_date): returns 1
        - After expiry: returns 0
        
        The +1 is because the end date is inclusive (the member can still use
        the gym on membership_end date).
        
        Returns 0 if:
        - No membership exists (no membership_end)
        - Membership has expired (today > membership_end)
        
        Args:
            today: Optional date for testing; defaults to today
            
        Returns:
            Number of days remaining (0 to duration_days, inclusive)
            
        Examples:
            # Jan 1: Payment day (membership ends Jan 30)
            get_days_left(today=Jan 1) => 30
            
            # Jan 6: 5 days later
            get_days_left(today=Jan 6) => 25
            
            # Jan 30: Last day
            get_days_left(today=Jan 30) => 1
            
            # Jan 31: Expired
            get_days_left(today=Jan 31) => 0
        """
        if not self.member.membership_end:
            return 0
        
        today = self._get_today(today)
        
        # Check if expired
        if self.member.membership_end < today:
            return 0
        
        # Inclusive calculation: (end - today).days + 1
        # If end is today, we get (0).days + 1 = 1
        # If end is tomorrow, we get (1).days + 1 = 2
        return (self.member.membership_end - today).days + 1
    
    def get_days_left_current(self, today: Optional[date] = None) -> int:
        """
        Alias for get_days_left() for backward compatibility.
        
        This provides the same calculation as get_days_left().
        The name "current" is kept for backward compatibility with existing code.
        
        Args:
            today: Optional date for testing; defaults to today
            
        Returns:
            Number of days remaining (0 to duration_days, inclusive)
        """
        return self.get_days_left(today)
    
    def get_next_payment_date(self) -> Optional[date]:
        """
        Calculate the next payment due date.
        
        Business rule: Next payment is due exactly duration_days after the last payment.
        
        Formula: last_payment_date + duration_days
        
        Returns None if member has never made a payment.
        
        Returns:
            Date when next payment is due, or None if no payment history
            
        Examples:
            # Member paid on Jan 1 (30-day membership)
            get_next_payment_date() => Jan 31
            
            # Membership period: Jan 1 - Jan 30 (30 days inclusive)
            # Next payment due: Jan 31 (30 days after Jan 1)
            
            # Member never paid
            get_next_payment_date() => None
        """
        if not self.member.last_payment_date:
            return None
        
        duration_days = self.get_duration_days()
        return self.member.last_payment_date + timedelta(days=duration_days)
    
    def get_days_display(self, today: Optional[date] = None) -> str:
        """
        Get a formatted string for displaying days left.
        
        Format: "{days_left} / {total_days} days"
        
        Args:
            today: Optional date for testing; defaults to today
            
        Returns:
            Formatted string like "25 / 30 days"
            
        Examples:
            # Payment day
            get_days_display(today=Jan 1) => "30 / 30 days"
            
            # After 5 days
            get_days_display(today=Jan 6) => "25 / 30 days"
            
            # Expired
            get_days_display(today=Jan 31) => "0 / 30 days"
        """
        days_left = self.get_days_left(today)
        total_days = self.get_duration_days()
        return f"{days_left} / {total_days} days"
    
    def is_active(self, today: Optional[date] = None) -> bool:
        """
        Check if the member has an active membership.
        
        Active means:
        - Has made a payment (last_payment_date exists)
        - AND has days remaining (days_left > 0)
        
        Args:
            today: Optional date for testing; defaults to today
            
        Returns:
            True if membership is active, False otherwise
            
        Examples:
            # Payment day
            is_active(today=Jan 1) => True
            
            # During membership period
            is_active(today=Jan 15) => True
            
            # Expired
            is_active(today=Jan 31) => False
            
            # Never paid
            is_active() => False
        """
        return bool(self.member.last_payment_date and self.get_days_left(today) > 0)
    
    def get_status_code(self, today: Optional[date] = None) -> str:
        """
        Get the membership status code.
        
        Returns:
            - "none": No membership exists (never paid)
            - "active": Active membership with days remaining
            - "expired": Membership has expired
            
        Args:
            today: Optional date for testing; defaults to today
            
        Returns:
            Status code string
        """
        if not self.member.membership_start or not self.member.membership_end:
            return "none"
        
        if self.is_active(today):
            return "active"
        
        return "expired"
    
    def get_status_label(self, today: Optional[date] = None) -> str:
        """
        Get a human-readable status label for display.
        
        Args:
            today: Optional date for testing; defaults to today
            
        Returns:
            - "No membership": No payment or expired
            - "Active": Active membership with days remaining
            - "Expired": Membership has expired
        """
        status_code = self.get_status_code(today)
        
        if status_code == "none":
            return "No membership"
        elif status_code == "active":
            return "Active"
        else:  # expired
            return "Expired"
    
    def get_membership_status(self, today: Optional[date] = None) -> MembershipStatusDict:
        """
        Get complete membership status with all computed fields.
        
        This is the main method that returns all membership calculations
        in a single dictionary.
        
        Args:
            today: Optional date for testing; defaults to today
            
        Returns:
            Dictionary containing all membership status fields
            
        Example:
            status = service.get_membership_status()
            print(f"Status: {status['status_label']}")
            print(f"Days: {status['days_display']}")
            print(f"Next payment: {status['next_payment_date']}")
        """
        today = self._get_today(today)
        
        status_code = self.get_status_code(today)
        status_label = self.get_status_label(today)
        is_active = self.is_active(today)
        
        total_days = self.get_duration_days()
        days_used = self.get_days_used(today)
        days_left = self.get_days_left(today)
        days_display = self.get_days_display(today)
        
        next_payment_date = self.get_next_payment_date()
        
        return MembershipStatusDict(
            status_code=status_code,
            status_label=status_label,
            is_active=is_active,
            membership_start=self.member.membership_start,
            membership_end=self.member.membership_end,
            total_days=total_days,
            days_used=days_used,
            days_left=days_left,
            days_left_current=days_left,  # Alias for backward compatibility
            days_display=days_display,
            last_payment_date=self.member.last_payment_date,
            next_payment_date=next_payment_date,
        )


def get_membership_service(member: "GymMember") -> GymMembershipService:
    """
    Factory function to create a GymMembershipService instance.
    
    Args:
        member: GymMember instance
        
    Returns:
        GymMembershipService instance
        
    Usage:
        from inventory.services.gym_membership import get_membership_service
        
        service = get_membership_service(member)
        days_left = service.get_days_left()
    """
    return GymMembershipService(member)

