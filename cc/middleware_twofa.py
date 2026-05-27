"""
Two-Factor Authentication Enforcement Middleware

This middleware enforces SMS OTP 2FA for users who have it enabled.
After successful password login, users with 2FA enabled must complete
the OTP challenge before accessing protected pages.

SECURITY REQUIREMENTS:
- Block all non-allowlisted pages until 2FA challenge is passed
- Allow access to 2FA-related pages, logout, and public pages
- Do not break tenant scoping or other security boundaries
- Handle Twilio outages gracefully (don't lock users out permanently)
"""
from django.conf import settings
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse

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


class TwoFactorAuthMiddleware:
    """
    Enforce 2FA challenge for users with SMS 2FA enabled.

    Flow:
    1. After password login, login view sets session["twofa_required"] = True
    2. This middleware checks every request:
       - If user has 2FA enabled AND hasn't passed challenge -> redirect to challenge
       - If user is on allowlisted path -> allow
       - If user has passed challenge recently -> allow
    3. Challenge view sets session["twofa_passed"] = True on success
    """

    # Paths that are always allowed (even without passing 2FA)
    # Combine shared bypass prefixes with 2FA-specific allowlist
    ALLOWLIST = list(SHARED_BYPASS_PREFIXES) + [
        # 2FA-related pages
        "/accounts/2fa/challenge/",
        "/accounts/2fa/resend/",
        "/accounts/2fa/sms/enable/start/",
        "/accounts/2fa/sms/enable/verify/",
        "/accounts/2fa/sms/disable/start/",
        "/accounts/2fa/sms/disable/verify/",
        # Authentication pages
        "/accounts/login/",
        "/accounts/logout/",
        # Admin (prevent staff lockout)
        "/admin/",
        # Health checks (for load balancers)
        "/health/",
        "/ping/",
        # API version check (used by app)
        "/api/version/",
        # Public gym QR code endpoints (no auth required)
        "/gym/qr/",
    ]

    # URL patterns that are public (no auth required)
    PUBLIC_PATTERNS = [
        "accounts:login",
        "accounts:signup",
        "accounts:signup_wizard_step",
        "accounts:signup_verify_email",
        "accounts:signup_manager",
        "accounts:forgot_password_request",
        "accounts:forgot_password_reset",
        "staticpages:home",  # Public landing page
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip middleware for non-authenticated users
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Skip if path is in allowlist
        if self._is_allowlisted(request.path):
            return self.get_response(request)

        # Skip if this is a public page
        if self._is_public_page(request):
            return self.get_response(request)

        # Check if user has 2FA enabled
        from circuitcity.accounts.models import is_twofa_enabled

        if not is_twofa_enabled(request.user):
            # No 2FA required, proceed normally
            return self.get_response(request)

        # User has 2FA enabled - check if they've passed the challenge
        twofa_passed = request.session.get("twofa_passed", False)

        if not twofa_passed:
            # Redirect to 2FA challenge
            challenge_url = reverse("accounts:twofa_challenge")

            # Preserve the intended destination
            next_url = request.get_full_path()
            if next_url != challenge_url:
                challenge_url += f"?next={next_url}"

            return redirect(challenge_url)

        # 2FA passed, allow access
        return self.get_response(request)

    def _is_allowlisted(self, path: str) -> bool:
        """Check if path is in the allowlist."""
        for allowed in self.ALLOWLIST:
            if path.startswith(allowed):
                return True
        return False

    def _is_public_page(self, request) -> bool:
        """Check if current URL pattern is a public page."""
        try:
            match = resolve(request.path)
            url_name = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
            return url_name in self.PUBLIC_PATTERNS
        except Resolver404:
            return False
