"""
Data scoping utilities for role-based visibility.

This module provides helpers to determine what data a user can see:
- Managers see GLOBAL numbers (all stock, all sales)
- Agents see ONLY their own numbers (their stock, their sales)

CRITICAL: This module now uses the centralized role resolution from
tenants.utils_roles via middleware-set request attributes. This ensures
managers NEVER downgrade to agent scope.

Usage:
    from inventory.utils_scope import get_visible_actor, scope_sales_qs, scope_stock_qs
    
    is_manager, is_agent, actor = get_visible_actor(request)
    sales_qs = scope_sales_qs(Sale.objects.all(), request)
    stock_qs = scope_stock_qs(InventoryItem.objects.all(), request)
"""
from django.db.models import Q, QuerySet
from django.contrib.auth import get_user_model
from typing import Tuple, Optional

User = get_user_model()


def get_visible_actor(request) -> Tuple[bool, bool, Optional[User]]:
    """
    Determine the visibility scope for the current user.

    Returns:
        tuple: (is_manager, is_agent, actor_user)
            - is_manager: True if user can see all data
            - is_agent: True if user can only see their own data
            - actor_user: The User object for filtering

    CRITICAL: Uses middleware-set role flags (request.is_manager_plus, request.is_agent_only)
    which are computed by RoleResolutionMiddleware using tenants.utils_roles.

    This ensures manager precedence - managers are NEVER treated as agents,
    even if they have location memberships or agent assignments.

    Fallback: If middleware flags are not present, checks is_staff/is_superuser.
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return False, False, None

    user = request.user

    # ✅ PRIMARY: Use middleware-set role flags (set by RoleResolutionMiddleware)
    # These flags are computed using the centralized tenants.utils_roles logic
    # which implements proper manager precedence
    if hasattr(request, "is_manager_plus") and hasattr(request, "is_agent_only"):
        is_manager = request.is_manager_plus
        is_agent = request.is_agent_only

        # Safety check: manager cannot be agent (middleware should prevent this, but belt & suspenders)
        if is_manager and is_agent:
            is_agent = False

        return is_manager, is_agent, user

    # ✅ FALLBACK: If middleware didn't run (shouldn't happen in production),
    # use simple checks to avoid breaking the app
    is_manager = user.is_staff or user.is_superuser or user.has_perm("inventory.can_view_all_sales")

    # If not a manager, they're an agent
    is_agent = not is_manager

    return is_manager, is_agent, user


def scope_sales_qs(base_qs: QuerySet, request) -> QuerySet:
    """
    Filter sales queryset based on user's role.

    Args:
        base_qs: Base queryset of Sale or InventoryItem (sold) objects
        request: HttpRequest object

    Returns:
        QuerySet: Filtered to the user's visible scope

    Managers: See all sales
    Agents: See only sales where they are the agent

    The function automatically detects the model and uses the appropriate
    ownership field (assigned_agent, agent, created_by, etc.)
    """
    is_manager, is_agent, user = get_visible_actor(request)

    if not user:
        # No authenticated user - return empty queryset
        return base_qs.none()

    if is_manager:
        # Managers see everything
        return base_qs

    # Agents see only their own sales
    model = base_qs.model

    # Build query for agent ownership
    # Try multiple possible field names (in order of preference)
    ownership_q = Q(pk__in=[])  # Start with empty Q

    # Check which fields exist on the model
    if hasattr(model, "assigned_agent"):
        ownership_q |= Q(assigned_agent=user)

    if hasattr(model, "agent"):
        ownership_q |= Q(agent=user)

    if hasattr(model, "created_by"):
        ownership_q |= Q(created_by=user)

    if hasattr(model, "recorded_by"):
        ownership_q |= Q(recorded_by=user)

    if hasattr(model, "seller"):
        ownership_q |= Q(seller=user)

    # Apply the ownership filter
    return base_qs.filter(ownership_q)


def scope_stock_qs(base_qs: QuerySet, request) -> QuerySet:
    """
    Filter stock queryset based on user's role.

    Args:
        base_qs: Base queryset of InventoryItem objects
        request: HttpRequest object

    Returns:
        QuerySet: Filtered to the user's visible scope

    Managers: See all stock
    Agents: See only stock assigned to them

    For InventoryItem, the primary ownership field is 'assigned_agent'.
    """
    is_manager, is_agent, user = get_visible_actor(request)

    if not user:
        # No authenticated user - return empty queryset
        return base_qs.none()

    if is_manager:
        # Managers see everything
        return base_qs

    # Agents see only their own stock
    model = base_qs.model

    # Build query for agent ownership
    ownership_q = Q(pk__in=[])  # Start with empty Q

    # Check which fields exist on the model
    if hasattr(model, "assigned_agent"):
        ownership_q |= Q(assigned_agent=user)

    if hasattr(model, "created_by"):
        ownership_q |= Q(created_by=user)

    if hasattr(model, "owner"):
        ownership_q |= Q(owner=user)

    # Apply the ownership filter
    return base_qs.filter(ownership_q)


def scope_costs_qs(base_qs: QuerySet, request) -> QuerySet:
    """
    Filter business costs based on user's role.

    Args:
        base_qs: Base queryset of WalletTransaction (costs) objects
        request: HttpRequest object

    Returns:
        QuerySet: Filtered to the user's visible scope

    Managers: See all business costs
    Agents: See NO business costs (or only costs assigned to them if supported)

    For most businesses, operational costs are manager-level data.
    If your WalletTransaction model has assigned_to/agent fields, we filter by those.
    Otherwise, agents see zero costs.
    """
    is_manager, is_agent, user = get_visible_actor(request)

    if not user:
        # No authenticated user - return empty queryset
        return base_qs.none()

    if is_manager:
        # Managers see all costs
        return base_qs

    # Agents: Check if costs can be attributed to an agent
    model = base_qs.model

    # If the model has agent-assignment fields, filter by them
    ownership_q = Q(pk__in=[])  # Start with empty Q

    if hasattr(model, "assigned_to"):
        ownership_q |= Q(assigned_to=user)

    if hasattr(model, "agent"):
        ownership_q |= Q(agent=user)

    if hasattr(model, "created_by"):
        ownership_q |= Q(created_by=user)

    # If no ownership fields exist, return empty queryset (agents don't see costs)
    if ownership_q == Q(pk__in=[]):
        return base_qs.none()

    return base_qs.filter(ownership_q)


def can_view_all_data(request) -> bool:
    """
    Quick check if the current user can view all data.

    Returns:
        bool: True if user is a manager, False if agent
    """
    is_manager, _, _ = get_visible_actor(request)
    return is_manager
