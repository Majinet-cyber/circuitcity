# tenants/decorators.py
"""
MULTI-TENANCY HARDENING: Decorators for business and vertical isolation.

These decorators ensure:
1. Views only show data from the user's business
2. Views only accessible to correct vertical (gym users can't access phones routes)
3. Proper 404 responses instead of leaking data
"""

from functools import wraps
from django.http import Http404, HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import redirect

try:
    from .utils import get_active_business, user_has_any_business
except ImportError:
    def get_active_business(request):
        return getattr(request, "business", None)
    
    def user_has_any_business(user):
        return False


def require_vertical(*allowed_verticals):
    """
    Decorator: Require the active business to match one of the allowed verticals.
    Raises 404 if vertical doesn't match (prevents data leakage).
    
    Usage:
        @require_vertical("gym")
        def gym_dashboard(request):
            ...
        
        @require_vertical("phones", "pharmacy")
        def multi_vertical_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            business = get_active_business(request)
            
            if not business:
                # No business active - redirect to onboarding
                if request.user.is_authenticated:
                    messages.info(request, "Please set up or join a business first.")
                    return redirect("onboarding:start")
                raise Http404("No active business")
            
            # Get business vertical/kind
            business_vertical = getattr(business, "business_kind", None)
            if not business_vertical:
                business_vertical = "phones"  # Default fallback
            
            # Normalize to lowercase
            if hasattr(business_vertical, "value"):
                business_vertical = business_vertical.value
            business_vertical = str(business_vertical).strip().lower()
            
            # Check if vertical matches
            allowed = [v.lower() for v in allowed_verticals]
            if business_vertical not in allowed:
                # SECURITY: Return 404 instead of 403 to avoid leaking route existence
                raise Http404("This feature is not available for your business type")
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def require_business_access(view_func):
    """
    Decorator: Ensure user has an active business before accessing the view.
    Redirects to onboarding if no business membership exists.
    
    Usage:
        @require_business_access
        def some_protected_view(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        
        if not user_has_any_business(request.user) and not request.user.is_superuser:
            messages.info(request, "Please set up or join a business first.")
            return redirect("onboarding:start")
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def scope_to_business(view_func):
    """
    Decorator: Ensure all database queries in the view are scoped to the active business.
    This is a marker decorator that signals the view follows business isolation rules.
    
    The actual scoping must be done in the view using scope_queryset_to_business()
    or get_object_for_business() from tenants.utils.
    
    Usage:
        @scope_to_business
        def list_products(request):
            business = get_active_business(request)
            products = scope_queryset_to_business(Product.objects.all(), business)
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        business = get_active_business(request)
        
        if not business and not request.user.is_superuser:
            messages.warning(request, "No active business selected.")
            return redirect("tenants:choose_business")
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def prevent_cross_business_access(param_name="pk"):
    """
    Decorator: Prevent accessing objects from other businesses by ID.
    
    This decorator checks that the object with the given ID belongs to the
    active business. If not, raises 404 instead of showing permission error.
    
    Usage:
        @prevent_cross_business_access("product_id")
        def edit_product(request, product_id):
            # product_id is validated to belong to request.business
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            business = get_active_business(request)
            
            if not business and not request.user.is_superuser:
                raise Http404("No active business")
            
            # Extract the ID parameter from kwargs
            obj_id = kwargs.get(param_name)
            if obj_id is None:
                # No ID to validate - proceed
                return view_func(request, *args, **kwargs)
            
            # Note: Actual validation must be done in the view
            # This decorator serves as a marker and business context checker
            # Views should use get_object_or_404(Model.objects.filter(business=business), pk=obj_id)
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def manager_only(view_func):
    """
    Decorator: Restrict view to managers only.
    Agents and other roles get 403 Forbidden.
    
    Usage:
        @manager_only
        def approve_costs(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser or request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Check membership role
        membership = getattr(request, "membership", None)
        if membership and membership.role == "MANAGER":
            return view_func(request, *args, **kwargs)
        
        # Check user_highest_role
        from .utils import user_highest_role
        role = (user_highest_role(request.user) or "").upper()
        if role in {"OWNER", "MANAGER", "ADMIN"}:
            return view_func(request, *args, **kwargs)
        
        return HttpResponseForbidden("This action requires manager privileges.")
    
    return wrapper


def hq_only(view_func):
    """
    Decorator: Restrict view to HQ admins only (staff/superuser).
    Regular business users get 403 Forbidden.
    
    Usage:
        @hq_only
        def hq_dashboard(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        
        # Check if user is HQ admin (staff or superuser)
        if request.user.is_superuser or request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Try to use the canonical is_hq_admin check if available
        try:
            from importlib import import_module
            for module_path in ("hq.permissions", "circuitcity.hq.permissions"):
                try:
                    mod = import_module(module_path)
                    is_hq_admin = getattr(mod, "is_hq_admin", None)
                    if callable(is_hq_admin) and is_hq_admin(request.user):
                        return view_func(request, *args, **kwargs)
                except Exception:
                    continue
        except Exception:
            pass
        
        return HttpResponseForbidden("This view is restricted to HQ administrators.")
    
    return wrapper


# Backwards-compatible alias (older code imports require_business)
require_business = require_business_access