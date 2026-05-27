# core/views_csrf.py
"""
Branded CSRF failure view to replace Django's default CSRF 403 page.
Shows a user-friendly recovery screen instead of raw debug info.
"""
from django.conf import settings
from django.shortcuts import render


def csrf_failure(request, reason=""):
    """
    Custom CSRF failure view.

    Shows a branded, user-friendly page when CSRF validation fails.
    Provides clear recovery actions (reload/login) without leaking technical details.

    Args:
        request: HttpRequest that failed CSRF validation
        reason: Technical reason for failure (only shown if DEBUG=True)

    Returns:
        HttpResponse with 403 status and branded error page
    """
    # Prepare context
    ctx = {
        "page_title": "Security Check Failed",
        "show_reason": settings.DEBUG,  # Only show technical reason in DEBUG mode
        "reason": reason if settings.DEBUG else "",
        "login_url": settings.LOGIN_URL,
    }

    response = render(request, "core/csrf_failure.html", ctx)
    response.status_code = 403

    return response
