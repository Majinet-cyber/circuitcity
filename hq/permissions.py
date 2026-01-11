from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponseForbidden


def is_hq_admin(user):
    """Check if user is HQ admin (superuser or platform_admin group)."""
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="platform_admin").exists())


def is_staff_or_superuser(user):
    """Check if user is staff or superuser (for basic HQ access)."""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def hq_admin_required(view_func):
    """
    Decorator to require HQ admin access (superuser or platform_admin).
    
    CRITICAL FIX: For authenticated non-staff users, returns 403 instead of
    redirecting to login (which would cause redirect loops).
    
    For unauthenticated users, redirects to login.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, "user", None)
        
        # Unauthenticated -> redirect to login
        if not user or not getattr(user, "is_authenticated", False):
            from django.shortcuts import redirect
            from django.urls import reverse
            try:
                login_url = reverse("accounts:login")
            except Exception:
                login_url = "/accounts/login/"
            return redirect(f"{login_url}?next={request.path}")
        
        # Authenticated: check if HQ admin
        if is_hq_admin(user):
            return view_func(request, *args, **kwargs)
        
        # Authenticated but not HQ admin -> 403 Forbidden (NO redirect to prevent loops)
        return HttpResponseForbidden(
            "<h1>403 Forbidden</h1><p>You don't have permission to access HQ.</p>",
            content_type="text/html"
        )
    
    return wrapper


# Legacy alias for backwards compatibility
hq_staff_required = user_passes_test(is_staff_or_superuser, login_url="/accounts/login/")
