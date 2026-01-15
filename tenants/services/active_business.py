# tenants/services/active_business.py
"""
SINGLE SOURCE OF TRUTH for active business resolution.

This module provides canonical helpers for:
- Getting the active business from a request
- Ensuring an active business is set (auto-selecting when user has exactly one)
- Setting the active business in session and request

CRITICAL SECURITY: Only auto-select when user has exactly ONE business membership.
For multi-business users, maintain existing selection flow.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest
    from tenants.models import Business, Membership


def get_active_business(request: "HttpRequest") -> Optional["Business"]:
    """
    Get the currently active business from request or session.
    
    Resolution order:
    1. request.business (set by middleware)
    2. request.active_business (legacy attr)
    3. session['active_business_id'] -> lookup Business
    4. session['biz_id'] (legacy key) -> lookup Business
    
    Returns:
        Business object or None
    """
    # 1) Check request attributes (set by middleware)
    biz = getattr(request, "business", None)
    if biz is not None:
        return biz
    
    biz = getattr(request, "active_business", None)
    if biz is not None:
        return biz
    
    # 2) Check session keys
    bid = _read_session_business_id(request)
    if not bid:
        return None
    
    # 3) Resolve by ID
    biz = _resolve_business_by_id(bid)
    if biz:
        # Cache on request for this request lifecycle
        try:
            setattr(request, "business", biz)
        except Exception:
            pass
    
    return biz


def ensure_active_business(
    request: "HttpRequest",
    user=None,
    *,
    auto_select_single: bool = True,
) -> Optional["Business"]:
    """
    Ensure an active business is set for the request.
    
    This is the SSOT for middleware and views that need an active business.
    
    Logic:
    1. If business already set -> return it (and ensure location)
    2. If user has exactly ONE membership -> auto-select and persist it
    3. If user has multiple memberships -> return None (redirect to chooser)
    
    CRITICAL: When auto-selecting a business, also set default location to prevent
    location-scoped views from failing with 302/403 cascades.
    
    Args:
        request: HttpRequest
        user: User object (defaults to request.user)
        auto_select_single: Whether to auto-select when user has exactly one business
        
    Returns:
        Business object or None
    """
    # 1) Already set?
    biz = get_active_business(request)
    if biz is not None:
        # Ensure location is set for this business
        ensure_default_location(request, biz)
        return biz
    
    # 2) Auto-select if enabled and user has exactly one membership
    if not auto_select_single:
        return None
    
    if user is None:
        user = getattr(request, "user", None)
    
    if not user or not getattr(user, "is_authenticated", False):
        return None
    
    # Get the single active membership if it exists
    single_biz = _get_single_membership_business(user)
    if single_biz is None:
        return None
    
    # Set as active and persist to session
    set_active_business(request, single_biz)
    
    # CRITICAL: Also set default location to prevent location-scoped views from failing
    ensure_default_location(request, single_biz)
    
    return single_biz


def set_active_business(request: "HttpRequest", business: Optional["Business"]) -> None:
    """
    Set the active business on request and persist to session.
    
    This ensures all downstream code (views, templates, etc.) see the same business.
    Pass business=None to clear the selection.
    
    Args:
        request: HttpRequest
        business: Business object to set as active (or None to clear)
    """
    if business is None:
        # Clear selection
        try:
            request.session.pop("active_business_id", None)
            request.session.pop("biz_id", None)  # legacy
            request.session.modified = True
        except Exception:
            pass
        
        try:
            setattr(request, "business", None)
            setattr(request, "active_business", None)
            setattr(request, "active_business_id", None)
        except Exception:
            pass
        
        # Clear thread-local if available
        try:
            from tenants.models import set_current_business_id
            set_current_business_id(None)
        except Exception:
            pass
        
        return
    
    # Set business
    bid = getattr(business, "id", None) or getattr(business, "pk", None)
    
    # Persist to session (canonical + legacy keys)
    try:
        request.session["active_business_id"] = bid
        request.session["biz_id"] = bid  # legacy compatibility
        request.session.modified = True
    except Exception:
        pass
    
    # Set on request (multiple attrs for compatibility)
    try:
        setattr(request, "business", business)
        setattr(request, "active_business", business)
        setattr(request, "active_business_id", bid)
    except Exception:
        pass
    
    # Set thread-local if available
    try:
        from tenants.models import set_current_business_id
        set_current_business_id(bid)
    except Exception:
        pass


# ============================================================================
# Internal helpers
# ============================================================================

def _read_session_business_id(request: "HttpRequest") -> Optional[int]:
    """Read business ID from session (tries canonical + legacy keys)."""
    try:
        # Try canonical key first
        bid = request.session.get("active_business_id")
        if bid:
            return int(bid)
        
        # Try legacy key
        bid = request.session.get("biz_id")
        if bid:
            return int(bid)
    except Exception:
        pass
    
    return None


def _resolve_business_by_id(bid: int) -> Optional["Business"]:
    """Resolve a Business object by ID."""
    try:
        from tenants.models import Business
        return Business.objects.filter(pk=bid, status="ACTIVE").first()
    except Exception:
        return None


def _get_single_membership_business(user) -> Optional["Business"]:
    """
    Get the business if user has exactly ONE active membership.
    Returns None if user has 0 or >1 memberships.
    
    SECURITY: This is the gatekeeper that prevents auto-selection
    when users have multiple businesses (preserving selection flow).
    """
    try:
        from tenants.models import Membership
    except ImportError:
        return None
    
    if not user or not getattr(user, "is_authenticated", False):
        return None
    
    # Query active memberships
    qs = Membership.objects.filter(user=user).select_related("business")
    
    # Filter by status if field exists
    try:
        field_names = {f.name for f in Membership._meta.fields}
        if "status" in field_names:
            qs = qs.filter(status="ACTIVE")
        elif "is_active" in field_names:
            qs = qs.filter(is_active=True)
    except Exception:
        pass
    
    # Also filter by business status
    try:
        qs = qs.filter(business__status="ACTIVE")
    except Exception:
        pass
    
    # CRITICAL: Only return if exactly ONE membership
    count = qs.count()
    if count != 1:
        return None
    
    membership = qs.first()
    if not membership:
        return None
    
    return getattr(membership, "business", None)


def ensure_default_location(request: "HttpRequest", business: "Business") -> None:
    """
    Ensure a default location is set on the request and session if business has locations.
    This prevents location-scoped views from failing with 302/403 errors.
    
    CRITICAL: This is called by middleware and ensure_active_business to provide
    seamless location resolution for single-business users.
    
    Args:
        request: HttpRequest object
        business: Business object to resolve location for
    """
    # Skip if already set
    if getattr(request, "location_id", None) or getattr(request, "active_location_id", None):
        return
    
    # Check session too
    try:
        if request.session.get("default_location_id"):
            return
    except Exception:
        pass
    
    try:
        from inventory.models import Location
    except ImportError:
        try:
            from tenants.models import Location
        except ImportError:
            return
    
    try:
        # Get first location for this business
        # CRITICAL FIX: Don't filter by is_active - it's not a database field on Location
        # Location model only has is_default field. All locations are considered "active"
        # by design (see inventory/models.py Location.is_active property).
        qs = Location.objects.filter(business=business)
        
        # Prefer default location, fallback to first by name
        loc = (
            qs.filter(is_default=True).first()
            or qs.order_by("name").first()
        )
        
        if loc:
            loc_id = getattr(loc, "id", None) or getattr(loc, "pk", None)
            
            # Set on request (multiple attrs for compatibility)
            setattr(request, "location_id", loc_id)
            setattr(request, "active_location", loc)
            setattr(request, "active_location_id", loc_id)
            setattr(request, "default_location_id", loc_id)
            
            # Persist in session for downstream views
            try:
                request.session["location_id"] = loc_id
                request.session["active_location_id"] = loc_id
                request.session["default_location_id"] = loc_id
                request.session.modified = True
            except Exception:
                pass
    except Exception:
        # Never block request if location resolution fails
        pass

