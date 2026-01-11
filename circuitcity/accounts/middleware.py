# accounts/middleware.py
"""
Middleware for account-related functionality:
- Force password change for users with temp passwords
"""
from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

# Import shared bypass prefixes for consistent middleware behavior
try:
    from cc.middleware_constants import BYPASS_PREFIXES as SHARED_BYPASS_PREFIXES
except ImportError:
    # Fallback if import fails
    SHARED_BYPASS_PREFIXES = (
        "/sw.js",
        "/manifest.json",
        "/favicon.ico",
        "/static/",
        "/media/",
    )

# Paths that should always be accessible (no force password change check)
# Combine shared bypass prefixes with password-change-specific exemptions
FORCE_PWD_EXEMPT_PREFIXES = list(SHARED_BYPASS_PREFIXES) + [
    "/accounts/logout/",
    "/accounts/password/change/",
    "/accounts/password/set/",
    "/accounts/set-new-password/",
    "/admin/",
]


class ForcePasswordChangeMiddleware(MiddlewareMixin):
    """
    Middleware to enforce password change for users with force_password_change=True.

    After agent invite acceptance with temp password, users must change their password
    before accessing any other part of the application.
    """

    def process_request(self, request):
        # Skip if not authenticated
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None

        # Skip exempt paths
        path = request.path or "/"
        if any(path.startswith(prefix) for prefix in FORCE_PWD_EXEMPT_PREFIXES if prefix):
            return None

        # Check if user needs to change password
        try:
            profile = user.profile
            if getattr(profile, "force_password_change", False):
                # Redirect to password change page
                try:
                    change_url = reverse("accounts:password_change")
                except Exception:
                    change_url = "/accounts/password/change/"

                # Avoid redirect loop
                if path.startswith(change_url.rstrip("/")):
                    return None

                return redirect(f"{change_url}?force=1")
        except Exception:
            # No profile or error - skip
            pass

        return None
