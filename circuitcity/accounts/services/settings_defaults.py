# circuitcity/accounts/services/settings_defaults.py
"""
Settings Defaults Service

This module provides functions to ensure user profiles and notification preferences
have proper default values set. These functions are called when users visit settings
pages or during onboarding.

**Default Values:**
- Language: English
- Country: Malawi
- Time zone: Africa/Blantyre
- City: Lilongwe (Malawi)
- Notifications: ALL enabled by default (except agent-specific ones)

**Important:** These functions NEVER overwrite user-chosen values. They only fill
in empty/blank fields with sensible defaults.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

# ============================================================
# Default Values (Single Source of Truth)
# ============================================================
DEFAULT_LANGUAGE = "English"
DEFAULT_COUNTRY = "Malawi"
DEFAULT_TIMEZONE = "Africa/Blantyre"
DEFAULT_CITY = "Lilongwe"


# ============================================================
# Profile Defaults
# ============================================================
def ensure_user_profile_defaults(user: User) -> bool:
    """
    Ensure user profile has sensible defaults for empty fields.

    Sets defaults for:
    - language: English
    - country: Malawi
    - timezone: Africa/Blantyre
    - city: Lilongwe

    **IMPORTANT:** Only fills in blank/empty values. NEVER overwrites existing choices.

    Args:
        user: User instance

    Returns:
        True if any changes were made, False otherwise
    """
    from circuitcity.accounts.models import Profile

    # Get or create profile
    profile, created = Profile.objects.get_or_create(user=user)

    changes_made = False
    update_fields = []

    # Apply defaults only if fields are empty/blank
    if not profile.language or profile.language.strip() == "":
        profile.language = DEFAULT_LANGUAGE
        update_fields.append("language")
        changes_made = True

    if not profile.country or profile.country.strip() == "":
        profile.country = DEFAULT_COUNTRY
        update_fields.append("country")
        changes_made = True

    if not profile.timezone or profile.timezone.strip() == "":
        profile.timezone = DEFAULT_TIMEZONE
        update_fields.append("timezone")
        changes_made = True

    # City field (may not exist on old profiles)
    if hasattr(profile, "city"):
        if not profile.city or profile.city.strip() == "":
            profile.city = DEFAULT_CITY
            update_fields.append("city")
            changes_made = True

    # Save only if changes were made
    if changes_made and update_fields:
        profile.save(update_fields=update_fields)
        logger.info(f"Applied profile defaults for user {user.username}: {update_fields}")

    return changes_made


# ============================================================
# Notification Defaults
# ============================================================
def ensure_notification_defaults(user: User) -> bool:
    """
    Ensure user has notification preferences with ALL notifications enabled by default.

    **Default Policy:**
    - All email notifications: True (for managers)
    - Commission emails: False (for agents only)

    **IMPORTANT:** Only sets defaults for newly created preferences or NULL values.
    NEVER re-enables notifications that users have explicitly disabled.

    Args:
        user: User instance

    Returns:
        True if preferences were created or updated, False if already existed
    """
    from notifications.models import NotificationPreference

    # Try to get existing preference
    pref, created = NotificationPreference.objects.get_or_create(
        user=user,
        defaults={
            "welcome_emails": True,
            "instant_sale_email": True,
            "sale_emails_enabled": True,
            "daily_summary_email": True,
            "important_alerts_email": True,
            "high_sales_alerts": True,
            "commission_emails_enabled": False,  # False for agents by default
            "weekly_digest_enabled": True,
        },
    )

    if created:
        logger.info(f"Created notification preferences for user {user.username} with all defaults enabled")
        return True

    # For existing preferences, only fill in NULL/None values (not False values)
    # This ensures we don't re-enable notifications users have explicitly disabled
    changes_made = False
    update_fields = []

    # Map of fields and their default values
    defaults_map = {
        "welcome_emails": True,
        "instant_sale_email": True,
        "sale_emails_enabled": True,
        "daily_summary_email": True,
        "important_alerts_email": True,
        "high_sales_alerts": True,
        "weekly_digest_enabled": True,
        # Note: commission_emails_enabled defaults to False, so we only set it if None
    }

    for field, default_value in defaults_map.items():
        current_value = getattr(pref, field, None)
        # Only set if value is None (NULL in DB), not if it's False (user disabled it)
        if current_value is None:
            setattr(pref, field, default_value)
            update_fields.append(field)
            changes_made = True

    # Handle commission_emails_enabled (defaults to False for agents)
    if getattr(pref, "commission_emails_enabled", None) is None:
        pref.commission_emails_enabled = False
        update_fields.append("commission_emails_enabled")
        changes_made = True

    if changes_made and update_fields:
        pref.save(update_fields=update_fields)
        logger.info(f"Applied notification defaults for user {user.username}: {update_fields}")

    return changes_made


# ============================================================
# Combined Defaults (convenience function)
# ============================================================
def ensure_all_settings_defaults(user: User) -> dict:
    """
    Ensure both profile and notification defaults are set for a user.

    Convenience function that calls both ensure_user_profile_defaults
    and ensure_notification_defaults.

    Args:
        user: User instance

    Returns:
        dict with keys:
        - profile_changed: bool
        - notifications_changed: bool
    """
    profile_changed = ensure_user_profile_defaults(user)
    notifications_changed = ensure_notification_defaults(user)

    return {
        "profile_changed": profile_changed,
        "notifications_changed": notifications_changed,
    }
