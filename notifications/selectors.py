# notifications/selectors.py
"""
Recipient resolution helpers for email notifications.
Filters users based on role, business, and notification preferences.
"""
from __future__ import annotations

from typing import List, Optional

from django.contrib.auth import get_user_model
from django.db.models import Q

from notifications.models import NotificationPreference
from tenants.models import Membership, Business

User = get_user_model()


# Transactional events that bypass preference checks
# MUST match notifications/services.py TRANSACTIONAL_EVENTS
_TRANSACTIONAL_EVENTS = {
    "OTP_RESET", "OTP_VERIFY", "OTP_CODE",
    "WELCOME_MANAGER", "WELCOME_AGENT",
    "SALE_INSTANT", "SALE_BATCH",  # Managers MUST get sale emails
}


def get_business_manager_emails(
    business: Business,
    *,
    include_owner: bool = True,
    event_type: Optional[str] = None,
) -> List[str]:
    """
    Get email addresses of managers (and optionally owner) for a business.
    Applies notification preferences based on event_type UNLESS event is transactional.
    
    CRITICAL: SALE_INSTANT and SALE_BATCH are transactional - managers ALWAYS receive them.
    
    Args:
        business: The business
        include_owner: Whether to include owner(s)
        event_type: Event type to check preferences for. Must match NotificationEvent.event_type.
                    If None or transactional, preferences are not checked.
    
    Returns:
        List of email addresses (filtered by preferences if event_type provided and non-transactional)
    """
    if not business:
        return []
    
    # Get active memberships with manager role
    role_filter = Q(role="MANAGER")
    if include_owner:
        # Check if there's an OWNER role (might not exist in all setups)
        role_filter |= Q(role="OWNER")
    
    # Combine all filters into Q object to avoid positional/keyword argument mixing
    filter_q = role_filter & Q(business=business, status="ACTIVE")
    memberships = Membership.objects.filter(filter_q).select_related("user")
    
    # CRITICAL: Transactional events bypass preference checks entirely
    is_transactional = event_type in _TRANSACTIONAL_EVENTS
    
    emails = []
    for membership in memberships:
        user = membership.user
        if not user or not user.is_active:
            continue
        
        email = getattr(user, "email", "").strip()
        if not email or "@" not in email:
            continue
        
        # Check notification preferences ONLY for non-transactional events
        if event_type and not is_transactional:
            try:
                if not _should_send_email(user, event_type):
                    continue
            except Exception as e:
                # If preference check fails, log and continue (don't block)
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to check email preference for user {user.id}: {e}")
                # Default to sending if check fails
                pass
        
        emails.append(email)
    
    # Deduplicate
    return list(set(emails))


def _should_send_email(user: User, event_type: str) -> bool:
    """
    Check if user should receive email based on their preferences and event type.
    Always ensures NotificationPreference exists (creates on-demand if missing).
    
    Args:
        user: The user
        event_type: The event type (e.g., "SALE_INSTANT", "DAILY_SUMMARY")
    
    Returns:
        True if user should receive the email, False otherwise
    """
    # Ensure preference exists (create on-demand if missing)
    # get_or_create_default already sets sale_emails_enabled based on role
    pref = NotificationPreference.get_or_create_default(user)
    
    # Map event types to preference fields
    preference_map = {
        "WELCOME_MANAGER": "welcome_emails",
        "WELCOME_AGENT": "welcome_emails",
        "SALE_INSTANT": "sale_emails_enabled",  # Use sale_emails_enabled
        "SALE_BATCH": "sale_emails_enabled",  # Use sale_emails_enabled
        "DAILY_SUMMARY": "daily_summary_email",
        "HIGH_SALES_ALERT": "high_sales_alerts",
        "IMPORTANT_ALERT": "important_alerts_email",
        "AGENT_COMMISSION": "commission_emails_enabled",
        "WEEKLY_DIGEST": "weekly_digest_enabled",
    }
    
    preference_field = preference_map.get(event_type)
    if not preference_field:
        # Unknown event type: default to True (send)
        return True
    
    # Fallback to instant_sale_email if sale_emails_enabled doesn't exist (backward compat)
    if preference_field == "sale_emails_enabled" and not hasattr(pref, "sale_emails_enabled"):
        preference_field = "instant_sale_email"
    
    return getattr(pref, preference_field, True)


def get_business_owner_emails(business: Business) -> List[str]:
    """Get email addresses of business owners."""
    if not business:
        return []
    
    memberships = Membership.objects.filter(
        business=business,
        role="OWNER",
        status="ACTIVE",
    ).select_related("user")
    
    emails = []
    for membership in memberships:
        user = membership.user
        if not user or not user.is_active:
            continue
        
        email = getattr(user, "email", "").strip()
        if email and "@" in email:
            emails.append(email)
    
    return list(set(emails))

