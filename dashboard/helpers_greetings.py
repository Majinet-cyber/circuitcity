# dashboard/helpers_greetings.py
"""
Greeting helpers for personalized dashboard experience.
Provides time-of-day greetings and milestone messages.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from django.db.models import Count
from django.utils import timezone


def get_time_of_day_greeting(now: Optional[datetime] = None) -> str:
    """
    Return a time-appropriate greeting based on the hour.

    Args:
        now: datetime object (defaults to current time in project timezone)

    Returns:
        str: "Good morning", "Good afternoon", or "Good evening"
    """
    if now is None:
        now = timezone.localtime()

    hour = now.hour

    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    else:  # 17-23 and 0-4
        return "Good evening"


def get_daily_sales_milestone(user, business) -> Optional[str]:
    """
    Check if user has hit a daily sales milestone and return a motivational message.

    Currently checks for 5+ sales today (conservative threshold).

    Args:
        user: Django User object
        business: Business object (for scoping)

    Returns:
        str or None: Milestone message if threshold met, else None
    """
    if not user or not business:
        return None

    try:
        from sales.models import Sale
        from tenants.models import get_current_business_id, set_current_business_id

        # Temporarily set business context for query
        prev_bid = get_current_business_id()
        set_current_business_id(business.pk)

        try:
            today = timezone.localdate()

            # Count sales for this user today
            sales_count = Sale.objects.filter(agent=user, sold_at=today).count()

            # Milestone threshold: 5 sales
            if sales_count >= 5:
                return f"You crossed a milestone today – {sales_count} sales so far. Keep going!"

            return None
        finally:
            set_current_business_id(prev_bid)

    except Exception:
        # Fail gracefully if Sale model doesn't exist or query fails
        return None


def should_show_first_welcome(user) -> bool:
    """
    Determine if this is the first time user is seeing the dashboard.

    Uses last_login to detect first visit. If last_login is None or very recent
    (within 5 minutes of join date), show welcome.

    Args:
        user: Django User object

    Returns:
        bool: True if welcome banner should be shown
    """
    if not user:
        return False

    # If no last_login, this is first login
    if not user.last_login:
        return True

    # If user joined very recently (within 5 minutes of last login), show welcome
    if hasattr(user, "date_joined") and user.date_joined:
        delta = user.last_login - user.date_joined
        if delta.total_seconds() < 300:  # 5 minutes
            return True

    return False


def get_personalized_greeting(user, business=None) -> dict:
    """
    Build a complete greeting context for dashboard.

    Args:
        user: Django User object
        business: Business object (optional, for milestones)

    Returns:
        dict with keys:
            - greeting: str (e.g., "Good morning")
            - user_name: str (first name or username)
            - show_welcome: bool
            - milestone: str or None
    """
    # Get first name or username
    user_name = ""
    if hasattr(user, "first_name") and user.first_name:
        user_name = user.first_name
    elif hasattr(user, "get_full_name"):
        full_name = user.get_full_name()
        if full_name:
            user_name = full_name.split()[0]  # First part of full name

    if not user_name:
        user_name = user.get_username()

    # Time-of-day greeting
    greeting = get_time_of_day_greeting()

    # Check if welcome banner should be shown
    show_welcome = should_show_first_welcome(user)

    # Check for milestones
    milestone = None
    if business and not show_welcome:  # Don't show milestone on first visit
        milestone = get_daily_sales_milestone(user, business)

    return {
        "greeting": greeting,
        "user_name": user_name,
        "show_welcome": show_welcome,
        "milestone": milestone,
    }
