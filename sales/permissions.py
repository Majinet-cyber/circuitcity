# sales/permissions.py
"""
Sales Permissions
=================
Helper functions for checking sales-related permissions.
"""
from __future__ import annotations
from typing import Optional

from django.contrib.auth import get_user_model
from django.http import HttpRequest

from sales.models import Sale
from tenants.models import Business

User = get_user_model()


def can_rollback_sale(user, sale: Sale, request: Optional[HttpRequest] = None) -> bool:
    """
    Check if a user can rollback a sale.

    Rules:
    - Superuser/HQ can always rollback
    - Managers can rollback any sale in their business
    - Agents cannot rollback (even their own sales)

    Args:
        user: User instance
        sale: Sale instance
        request: Optional HttpRequest (used to get business if not provided)

    Returns:
        bool: True if user can rollback, False otherwise
    """
    from sales.services.rollback import RollbackService

    # Get business from sale or request
    business = None
    if hasattr(sale, "item") and hasattr(sale.item, "business"):
        business = sale.item.business
    elif request and hasattr(request, "business"):
        business = request.business
    elif request and hasattr(request, "active_business"):
        business = request.active_business

    if not business:
        return False

    # Use RollbackService for consistent permission checking
    can_rollback, _ = RollbackService.can_rollback(sale, user, business)
    return can_rollback


__all__ = ["can_rollback_sale"]
