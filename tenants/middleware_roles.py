# tenants/middleware_roles.py
"""
Role Resolution Middleware - SINGLE SOURCE OF TRUTH for request.role

This middleware attaches authoritative role flags to every request
AFTER business resolution but BEFORE view execution.

Attaches to request:
    - request.effective_role: str ("MANAGER", "AGENT", "OWNER", etc.)
    - request.is_manager_plus: bool (True if MANAGER/OWNER/ADMIN)
    - request.is_agent_only: bool (True if AGENT and NOT manager)
    - request.cc_business: Business object (alias for request.business)
    - request.cc_role: str (alias for request.effective_role)

CRITICAL: This ensures managers never downgrade to agent scope.
"""
from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

from tenants.utils_roles import (
    get_role,
    is_manager,
    is_agent,
    is_owner,
    get_active_business,
)


class RoleResolutionMiddleware(MiddlewareMixin):
    """
    Middleware to attach canonical role information to request.
    
    MUST be placed after:
        - AuthenticationMiddleware
        - TenantResolutionMiddleware / ActiveBusinessMiddleware
    
    Usage in MIDDLEWARE setting:
        MIDDLEWARE = [
            ...
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "tenants.middleware.TenantResolutionMiddleware",
            "tenants.middleware.ActiveBusinessMiddleware",
            "tenants.middleware_roles.RoleResolutionMiddleware",  # <-- Add this
            ...
        ]
    """
    
    def process_request(self, request):
        """
        Attach role flags to request before view execution.
        """
        user = getattr(request, "user", None)
        
        # Get business from request (set by tenant middleware)
        business = get_active_business(request)
        
        # Get canonical role
        role = get_role(user, business)
        
        # Attach to request
        request.effective_role = role
        request.is_manager_plus = is_manager(user, business)
        request.is_agent_only = is_agent(user, business)
        request.is_owner = is_owner(user, business)
        
        # Aliases for backward compatibility
        request.cc_business = business
        request.cc_role = role
        request.cc_is_manager = request.is_manager_plus
        request.cc_is_agent = request.is_agent_only
        request.cc_is_owner = request.is_owner
        
        # CRITICAL: Manager precedence check
        # If user has ANY manager indicator, ensure agent flags are False
        if request.is_manager_plus and request.is_agent_only:
            # This should never happen if utils_roles is working correctly,
            # but we guard against it here as a safety
            request.is_agent_only = False
            request.cc_is_agent = False
        
        return None  # Continue processing
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Called just before view execution - final safety check.
        """
        # Final validation: manager cannot be agent
        if getattr(request, "is_manager_plus", False) and getattr(request, "is_agent_only", False):
            # Force agent flags to False if manager
            request.is_agent_only = False
            request.cc_is_agent = False
        
        return None  # Continue to view

