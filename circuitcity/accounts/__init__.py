# circuitcity/accounts/utils/__init__.py

from typing import Any

def _safe_hasattr(obj: Any, name: str) -> bool:
    try:
        getattr(obj, name)
        return True
    except Exception:
        return False

def user_in_group(user, group_name: str) -> bool:
    """
    True if user is in a Django auth Group (case-insensitive).
    """
    try:
        return bool(user and user.is_authenticated and user.groups.filter(name__iexact=group_name).exists())
    except Exception:
        return False

def user_is_manager(user) -> bool:
    """
    Managers are:
      - superusers OR staff
      - OR in the 'Manager' group
      - OR have profile.is_manager True (if a Profile exists)
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    if user_in_group(user, "Manager"):
        return True

    # Profile flag (optional)
    try:
        # works if you've got a OneToOne related name 'profile'
        prof = getattr(user, "profile", None)
        if prof and _safe_hasattr(prof, "is_manager"):
            return bool(prof.is_manager)
    except Exception:
        pass

    return False

def user_is_agent(user) -> bool:
    """
    Define 'Agent' as any authenticated user who is NOT a manager,
    or explicitly in 'Agent' group, or profile.role == 'AGENT'.
    Adjust to your needs.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if user_is_manager(user):
        return False
    if user_in_group(user, "Agent"):
        return True
    try:
        prof = getattr(user, "profile", None)
        if prof and getattr(prof, "role", None) == "AGENT":
            return True
    except Exception:
        pass
    # Fallback: non-staff, non-superuser counts as agent
    return not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
