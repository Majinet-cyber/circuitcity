# dashboard/scope.py
"""
DASHBOARD SCOPING - SINGLE SOURCE OF TRUTH

This module provides authoritative scoping for dashboard data queries.
All dashboard views and JSON endpoints MUST use these helpers.

CRITICAL RULES:
1. Managers see business-wide data (all locations, all agents)
2. Agents see only their own data (their location, their sales)
3. Never downgrade managers to agent scope
4. Stock, sales, and agent lists must be scoped consistently

Usage:
    from dashboard.scope import (
        get_sales_qs_for_dashboard,
        get_stock_qs_for_dashboard,
        get_agents_for_dashboard,
        should_show_agents_section,
    )
    
    # In any dashboard view or API
    def my_dashboard_view(request):
        sales = get_sales_qs_for_dashboard(request, request.business)
        stock = get_stock_qs_for_dashboard(request, request.business)
        agents = get_agents_for_dashboard(request, request.business)
        show_agents = should_show_agents_section(request)
        ...
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.db.models import QuerySet


def _get_user(request) -> Optional[object]:
    """Safely get user from request."""
    return getattr(request, "user", None)


def _get_business(request) -> Optional[object]:
    """Safely get business from request."""
    return getattr(request, "business", None) or getattr(request, "cc_business", None)


def _is_manager_plus(request) -> bool:
    """
    Check if user is manager/owner/admin.
    Uses request flags set by RoleResolutionMiddleware.
    """
    # First check request flags (set by middleware)
    if hasattr(request, "is_manager_plus"):
        return bool(request.is_manager_plus)
    
    # Fallback to canonical role determination
    try:
        from tenants.utils_roles import is_manager
        user = _get_user(request)
        business = _get_business(request)
        return is_manager(user, business)
    except Exception:
        return False


def _is_agent_only(request) -> bool:
    """
    Check if user is agent (and NOT manager).
    Uses request flags set by RoleResolutionMiddleware.
    """
    # First check request flags (set by middleware)
    if hasattr(request, "is_agent_only"):
        return bool(request.is_agent_only)
    
    # Fallback to canonical role determination
    try:
        from tenants.utils_roles import is_agent
        user = _get_user(request)
        business = _get_business(request)
        return is_agent(user, business)
    except Exception:
        return False


def _get_agent_profile(request) -> Optional[object]:
    """Get AgentProfile for the current user."""
    user = _get_user(request)
    if not user:
        return None
    
    try:
        from accounts.models import AgentProfile
        return AgentProfile.objects.filter(user=user).first()
    except Exception:
        return None


def _get_primary_location(request) -> Optional[object]:
    """Get primary location for agent."""
    profile = _get_agent_profile(request)
    if not profile:
        return None
    
    return getattr(profile, "primary_location", None)


def get_sales_qs_for_dashboard(request: "HttpRequest", business) -> "QuerySet":
    """
    Get sales queryset scoped for dashboard display.
    
    - Managers: ALL business sales (all locations, all agents)
    - Agents: Only their own sales
    
    Args:
        request: HttpRequest with role flags attached
        business: Business instance
    
    Returns:
        QuerySet of Sale objects
    """
    try:
        from sales.models import Sale
    except Exception:
        # Return empty queryset-like object
        from django.db.models import QuerySet
        from django.db.models import Model as DummyModel
        return QuerySet(model=DummyModel).none()
    
    if not business:
        return Sale.objects.none()
    
    # Base queryset: all sales for this business
    qs = Sale.objects.filter(business=business)
    
    # CRITICAL: Managers see ALL business sales
    if _is_manager_plus(request):
        return qs
    
    # Agents see only their own sales
    if _is_agent_only(request):
        user = _get_user(request)
        if user:
            # Filter by agent (sold_by or created_by depending on model)
            if hasattr(Sale, "sold_by"):
                qs = qs.filter(sold_by=user)
            elif hasattr(Sale, "agent"):
                qs = qs.filter(agent=user)
            elif hasattr(Sale, "created_by"):
                qs = qs.filter(created_by=user)
            else:
                # Fallback: filter by location if available
                location = _get_primary_location(request)
                if location and hasattr(Sale, "location"):
                    qs = qs.filter(location=location)
        
        return qs
    
    # Default: no sales (shouldn't reach here normally)
    return Sale.objects.none()


def get_stock_qs_for_dashboard(request: "HttpRequest", business) -> "QuerySet":
    """
    Get stock/inventory queryset scoped for dashboard display.
    
    - Managers: ALL business stock (all locations)
    - Agents: Only their location's stock
    
    Args:
        request: HttpRequest with role flags attached
        business: Business instance
    
    Returns:
        QuerySet of InventoryItem objects
    """
    try:
        from inventory.models import InventoryItem
    except Exception:
        from django.db.models import QuerySet
        from django.db.models import Model as DummyModel
        return QuerySet(model=DummyModel).none()
    
    if not business:
        return InventoryItem.objects.none()
    
    # Base queryset: all stock for this business
    qs = InventoryItem.objects.filter(business=business)
    
    # CRITICAL: Managers see ALL business stock
    if _is_manager_plus(request):
        return qs
    
    # Agents see only their location's stock
    if _is_agent_only(request):
        location = _get_primary_location(request)
        if location and hasattr(InventoryItem, "location"):
            qs = qs.filter(location=location)
        else:
            # If no location, agent sees nothing
            return InventoryItem.objects.none()
        
        return qs
    
    # Default: no stock
    return InventoryItem.objects.none()


def get_agents_for_dashboard(request: "HttpRequest", business) -> "QuerySet":
    """
    Get list of agents to display on dashboard.
    
    - Managers: ALL business agents (clickable links)
    - Agents: Empty list (don't show other agents)
    
    Args:
        request: HttpRequest with role flags attached
        business: Business instance
    
    Returns:
        QuerySet of AgentProfile objects
    """
    try:
        from accounts.models import AgentProfile
    except Exception:
        from django.db.models import QuerySet
        from django.db.models import Model as DummyModel
        return QuerySet(model=DummyModel).none()
    
    if not business:
        return AgentProfile.objects.none()
    
    # CRITICAL: Only managers see agent list
    if not _is_manager_plus(request):
        return AgentProfile.objects.none()
    
    # Managers see all agents in the business
    # Note: AgentProfile doesn't have direct business FK,
    # so we need to filter via user memberships
    try:
        from tenants.models import Membership
        
        # Get all active memberships for this business
        memberships = Membership.objects.filter(
            business=business,
        )
        
        # Filter to ACTIVE status if field exists
        if hasattr(Membership, "status"):
            memberships = memberships.filter(status__iexact="ACTIVE")
        
        # Get user IDs
        user_ids = memberships.values_list("user_id", flat=True)
        
        # Get agent profiles for these users
        agents = AgentProfile.objects.filter(user_id__in=user_ids).select_related("user")
        
        return agents
    except Exception:
        return AgentProfile.objects.none()


def should_show_agents_section(request: "HttpRequest") -> bool:
    """
    Determine if agents section should be visible on dashboard.
    
    - Managers: Yes (with clickable agent names)
    - Agents: No
    
    Args:
        request: HttpRequest with role flags attached
    
    Returns:
        bool: True if agents section should be shown
    """
    return _is_manager_plus(request)


def get_agent_detail_url(agent_profile) -> Optional[str]:
    """
    Get URL for agent detail/drilldown page.
    
    Args:
        agent_profile: AgentProfile instance
    
    Returns:
        str: URL path or None
    """
    try:
        from django.urls import reverse
        
        # Try multiple possible URL patterns
        patterns = [
            ("dashboard:admin_agent_detail", {"pk": agent_profile.pk}),
            ("timelogs:agent_detail", {"agent_id": agent_profile.user_id}),
            ("dashboard:agent_detail", {"pk": agent_profile.pk}),
        ]
        
        for pattern_name, kwargs in patterns:
            try:
                return reverse(pattern_name, kwargs=kwargs)
            except Exception:
                continue
        
        # Fallback: construct URL manually
        return f"/dashboard/agents/{agent_profile.pk}/"
    except Exception:
        return None


__all__ = [
    "get_sales_qs_for_dashboard",
    "get_stock_qs_for_dashboard",
    "get_agents_for_dashboard",
    "should_show_agents_section",
    "get_agent_detail_url",
]

