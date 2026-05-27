"""
Two-Factor Authentication Decorators

Decorators for enforcing 2FA step-up authentication on sensitive actions.
"""
from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required


def require_recent_2fa(max_age_seconds=1800):
    """
    Decorator that requires a RECENT 2FA verification for sensitive actions.

    This implements "step-up authentication" - even if the user is logged in
    and has passed 2FA, certain sensitive actions require a RECENT 2FA verification.

    Args:
        max_age_seconds: Maximum age of the 2FA verification in seconds (default: 1800 = 30 minutes)

    Usage:
        @require_recent_2fa()  # Default 30 minutes
        def sensitive_view(request):
            ...

        @require_recent_2fa(max_age_seconds=600)  # 10 minutes
        def very_sensitive_view(request):
            ...

    Apply this to views that handle:
    - Password changes
    - Profile/email updates
    - Payout/billing changes
    - Wallet withdrawals
    - Destructive operations (delete, export)
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped_view(request, *args, **kwargs):
            from .models import is_twofa_enabled, is_twofa_recent

            # Check if user has 2FA enabled
            if not is_twofa_enabled(request.user):
                # No 2FA required, proceed normally
                return view_func(request, *args, **kwargs)

            # User has 2FA - check if it's recent
            if is_twofa_recent(request, max_age_seconds):
                # Recent 2FA verification, allow access
                return view_func(request, *args, **kwargs)

            # 2FA is not recent enough, require re-verification
            challenge_url = reverse("accounts:twofa_challenge")
            next_url = request.get_full_path()

            if next_url != challenge_url:
                challenge_url += f"?next={next_url}"

            return redirect(challenge_url)

        return wrapped_view

    return decorator


# Convenience alias for common use case
require_recent_twofa = require_recent_2fa
