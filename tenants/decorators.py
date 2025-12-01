# tenants/decorators.py
"""
Decorators for enforcing tenant isolation and role-based access control.
"""
from functools import wraps
from django.http import HttpResponseForbidden, Http404
from django.shortcuts import redirect
from django.contrib import messages
from .models import Business, Membership
from .utils import get_active_business, get_manager_bound_business, require_business as _legacy_require_business

# Re-export for backward compatibility
require_business = _legacy_require_business


def enforce_single_business(view_func):
    """
    Decorator that ensures managers can ONLY access their own business.
    Redirects to their bound business if they try to access another.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        
        # Superusers bypass this check
        if user.is_superuser or user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Get the manager's bound business
        bound_business = get_manager_bound_business(user)
        if not bound_business:
            # Not a manager, proceed normally
            return view_func(request, *args, **kwargs)
        
        # Check if they're trying to access their own business
        current_business = get_active_business(request)
        if current_business and current_business.id != bound_business.id:
            messages.error(request, "You can only access your own business.")
            return redirect('dashboard:home')
        
        # Ensure their business is active
        if not current_business or current_business.id != bound_business.id:
            from .utils import set_active_business
            set_active_business(request, bound_business)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped


def check_business_param_access(view_func):
    """
    Decorator for views that accept a business_id or pk parameter.
    Ensures non-superusers can only access businesses they belong to.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        
        # Superusers bypass this check
        if user.is_superuser or user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Extract business_id from URL kwargs
        business_id = kwargs.get('business_id') or kwargs.get('pk') or kwargs.get('business_pk')
        
        if business_id:
            # Check if user has membership in this business
            has_access = Membership.objects.filter(
                user=user,
                business_id=business_id,
                status='ACTIVE'
            ).exists()
            
            if not has_access:
                # Try to find if it's their bound business
                bound = get_manager_bound_business(user)
                if not bound or bound.id != int(business_id):
                    raise Http404("Business not found")
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped


def manager_only(view_func):
    """
    Decorator that only allows managers and staff to access a view.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        
        if not user.is_authenticated:
            return redirect('login')
        
        # Staff/superuser always allowed
        if user.is_superuser or user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Check if user is a manager
        is_manager = Membership.objects.filter(
            user=user,
            role='MANAGER',
            status='ACTIVE'
        ).exists()
        
        if not is_manager:
            return HttpResponseForbidden("Only managers can access this page.")
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped


def hq_only(view_func):
    """
    Decorator that only allows HQ staff (staff/superuser) to access a view.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        
        if not user.is_authenticated:
            return redirect('login')
        
        if not (user.is_superuser or user.is_staff):
            return HttpResponseForbidden("Only HQ staff can access this page.")
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped
