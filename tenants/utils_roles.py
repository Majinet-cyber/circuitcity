# tenants/utils_roles.py
"""
SINGLE SOURCE OF TRUTH for role detection across the entire application.

This module provides authoritative role determination with MANAGER PRECEDENCE.
All other modules MUST import from here to ensure consistency.

Critical Rules:
1. Manager precedence: If user is OWNER/MANAGER, is_agent MUST return False
2. Role is business-scoped: same user can be manager in one business, agent in another
3. Staff/superuser are always treated as managers
4. Checks multiple sources in priority order

Usage:
    from tenants.utils_roles import get_role, is_manager, is_agent
    
    # In views
    if is_manager(request.user, request.business):
        # Show manager content
    
    # In middleware
    request.cc_role = get_role(request.user, request.business)
    request.cc_is_manager = is_manager(request.user, request.business)
    request.cc_is_agent = is_agent(request.user, request.business)
"""
from __future__ import annotations
from typing import Optional, Tuple

try:
    from django.contrib.auth import get_user_model
except ImportError:  # pragma: no cover
    def get_user_model():
        return None

User = get_user_model()


def _safe_getattr(obj, attr: str, default=None):
    """Safe attribute access that never raises."""
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def _safe_bool(val) -> bool:
    """Safe boolean conversion that never raises."""
    try:
        return bool(val)
    except Exception:
        return False


def get_active_business(request) -> Optional[object]:
    """
    Get the active business from request.
    Checks request.business first, then request.active_business.
    
    Args:
        request: HttpRequest object
        
    Returns:
        Business object or None
    """
    return _safe_getattr(request, "business", None) or _safe_getattr(request, "active_business", None)


def get_membership(user, business) -> Optional[object]:
    """
    Get the ACTIVE Membership record for user in business.
    
    Args:
        user: User instance
        business: Business instance
        
    Returns:
        Membership instance or None
    """
    if not user or not business:
        return None
    
    if not _safe_getattr(user, "is_authenticated", False):
        return None
    
    try:
        from tenants.models import Membership
        
        qs = Membership.objects.filter(
            user=user,
            business=business
        )
        
        # Filter by ACTIVE status if field exists
        if hasattr(Membership, "status"):
            qs = qs.filter(status__iexact="ACTIVE")
        
        # Return first match (should only be one per user/business for managers)
        return qs.first()
    except Exception:
        return None


def get_role(user, business) -> str:
    """
    Determine the role for user in business context.
    
    Priority order:
    1. Staff/superuser → "MANAGER"
    2. Membership.role == "MANAGER" (ACTIVE status) → "MANAGER"
    3. Django group "Manager" (global) → "MANAGER"
    4. user.profile.is_manager → "MANAGER"
    5. biz:{business_id}:OWNER group → "MANAGER" (owner implies manager)
    6. biz:{business_id}:MANAGER group → "MANAGER"
    7. Membership.role == "AGENT" (ACTIVE status) → "AGENT"
    8. biz:{business_id}:AGENT group → "AGENT"
    9. Default → "NONE"
    
    CRITICAL: Manager precedence means once any manager indicator is found,
    user is treated as manager even if they also have agent indicators.
    
    Args:
        user: User instance
        business: Business instance
        
    Returns:
        str: One of "MANAGER", "AGENT", "OWNER", "AUDITOR", "BAR_MANAGER", or "NONE"
    """
    if not user or not _safe_getattr(user, "is_authenticated", False):
        return "NONE"
    
    # 1. Staff/superuser are always managers
    if _safe_bool(_safe_getattr(user, "is_staff", False)):
        return "MANAGER"
    if _safe_bool(_safe_getattr(user, "is_superuser", False)):
        return "MANAGER"
    
    # If we have a business, do business-scoped checks
    if business:
        # 2. Check Membership model first (most authoritative for business-scoped roles)
        membership = get_membership(user, business)
        if membership:
            mem_role = _safe_getattr(membership, "role", "").upper()
            if mem_role == "MANAGER":
                return "MANAGER"
            # Don't return AGENT yet - need to check global manager flags first
        
        # 3-6. Check various manager indicators (global and business-scoped groups)
        try:
            # 3. Global "Manager" group
            if user.groups.filter(name__iexact="Manager").exists():
                return "MANAGER"
        except Exception:
            pass
        
        # 4. Profile.is_manager flag
        try:
            profile = _safe_getattr(user, "profile", None)
            if profile and _safe_bool(_safe_getattr(profile, "is_manager", False)):
                return "MANAGER"
        except Exception:
            pass
        
        # 5-6. Business-scoped groups (biz:{business_id}:ROLE)
        try:
            prefix = f"biz:{business.pk}:"
            group_names = user.groups.filter(name__startswith=prefix).values_list("name", flat=True)
            
            roles_found = []
            for name in group_names:
                try:
                    role = name.split(":", 2)[2].upper()
                    roles_found.append(role)
                except Exception:
                    continue
            
            # Check for manager-level roles first (owner implies manager)
            if "OWNER" in roles_found:
                return "MANAGER"
            if "MANAGER" in roles_found:
                return "MANAGER"
            
            # Check for other special roles
            if "AUDITOR" in roles_found:
                return "AUDITOR"
            if "BAR_MANAGER" in roles_found:
                return "BAR_MANAGER"
            
            # Only now check for agent role
            # CRITICAL: We already checked all manager sources above
            # If user has AGENT group but also any manager indicator, they'd have returned "MANAGER" already
            if "AGENT" in roles_found:
                # Double-check: if membership exists and is MANAGER, return MANAGER (belt & suspenders)
                if membership and _safe_getattr(membership, "role", "").upper() == "MANAGER":
                    return "MANAGER"
                return "AGENT"
        except Exception:
            pass
        
        # 7. Membership.role == "AGENT" (only if no manager indicators found)
        if membership:
            mem_role = _safe_getattr(membership, "role", "").upper()
            if mem_role == "AGENT":
                return "AGENT"
    
    else:
        # No business context - check global manager indicators only
        # 3. Global "Manager" group
        try:
            if user.groups.filter(name__iexact="Manager").exists():
                return "MANAGER"
        except Exception:
            pass
        
        # 4. Profile.is_manager flag
        try:
            profile = _safe_getattr(user, "profile", None)
            if profile and _safe_bool(_safe_getattr(profile, "is_manager", False)):
                return "MANAGER"
        except Exception:
            pass
    
    # 9. Default: no role found
    return "NONE"


def is_manager(user, business=None) -> bool:
    """
    Check if user is a manager in the given business context.
    
    CRITICAL: This implements manager precedence.
    Even if user has agent indicators, if they have any manager indicator, returns True.
    
    Args:
        user: User instance
        business: Business instance (optional, if None checks global manager status)
        
    Returns:
        bool: True if user is a manager, False otherwise
    """
    role = get_role(user, business)
    # MANAGER, OWNER, AUDITOR, and BAR_MANAGER all have manager-level permissions
    return role in ("MANAGER", "OWNER", "AUDITOR", "BAR_MANAGER")


def is_agent(user, business=None) -> bool:
    """
    Check if user is an agent (and NOT a manager) in the given business context.
    
    CRITICAL: This implements manager precedence.
    Returns True ONLY if user is explicitly an agent AND not a manager.
    
    Args:
        user: User instance
        business: Business instance (optional, if None checks against no business context)
        
    Returns:
        bool: True if user is an agent and NOT a manager, False otherwise
    """
    role = get_role(user, business)
    # Agent ONLY if role is exactly "AGENT" (not manager, not none)
    return role == "AGENT"


def is_owner(user, business=None) -> bool:
    """
    Check if user is the owner of the business.
    
    Args:
        user: User instance
        business: Business instance (optional)
        
    Returns:
        bool: True if user is the owner, False otherwise
    """
    if not user or not business:
        return False
    
    if not _safe_getattr(user, "is_authenticated", False):
        return False
    
    # Check business owner field if it exists
    try:
        owner = _safe_getattr(business, "owner", None)
        if owner and owner.pk == user.pk:
            return True
    except Exception:
        pass
    
    # Check business created_by field if it exists
    try:
        created_by = _safe_getattr(business, "created_by", None)
        if created_by and created_by.pk == user.pk:
            return True
    except Exception:
        pass
    
    # Check for biz:{business_id}:OWNER group
    try:
        prefix = f"biz:{business.pk}:"
        group_names = user.groups.filter(name__startswith=prefix).values_list("name", flat=True)
        for name in group_names:
            try:
                role = name.split(":", 2)[2].upper()
                if role == "OWNER":
                    return True
            except Exception:
                continue
    except Exception:
        pass
    
    return False


def get_role_display(user, business=None) -> str:
    """
    Get human-readable role name for display.
    
    Args:
        user: User instance
        business: Business instance (optional)
        
    Returns:
        str: Human-readable role name
    """
    role = get_role(user, business)
    
    role_display_map = {
        "MANAGER": "Manager",
        "AGENT": "Agent",
        "OWNER": "Owner",
        "AUDITOR": "Auditor",
        "BAR_MANAGER": "Bar Manager",
        "NONE": "No Role",
    }
    
    return role_display_map.get(role, role.title())


def attach_role_to_request(request) -> None:
    """
    Attach authoritative role flags to request object.
    Should be called by middleware after business resolution.
    
    Attaches:
        - request.cc_business: Business object
        - request.cc_role: Role string ("MANAGER", "AGENT", etc.)
        - request.cc_is_manager: Boolean
        - request.cc_is_agent: Boolean
        - request.cc_is_owner: Boolean
    
    Args:
        request: HttpRequest object
    """
    user = _safe_getattr(request, "user", None)
    business = get_active_business(request)
    
    request.cc_business = business
    request.cc_role = get_role(user, business)
    request.cc_is_manager = is_manager(user, business)
    request.cc_is_agent = is_agent(user, business)
    request.cc_is_owner = is_owner(user, business)


__all__ = [
    "get_active_business",
    "get_membership",
    "get_role",
    "is_manager",
    "is_agent",
    "is_owner",
    "get_role_display",
    "attach_role_to_request",
]

