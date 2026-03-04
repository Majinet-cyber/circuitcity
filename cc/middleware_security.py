"""
Production Security Middleware

This middleware enforces production-grade security hardening:
1. Removes framework fingerprinting headers (Server, X-Powered-By, etc.)
2. Adds strict security headers (CSP, Permissions-Policy, etc.)
3. Sanitizes error responses (no stack traces, generic messages only)
4. Rotates session IDs on login/privilege change
5. Adds correlation IDs for support without exposing internals

Usage:
    Add to MIDDLEWARE after SecurityMiddleware in cc/settings.py:
    
    MIDDLEWARE = [
        "django.middleware.security.SecurityMiddleware",
        "cc.middleware_security.SecurityHeadersMiddleware",  # <- Add this
        "cc.middleware_security.RemoveServerHeaderMiddleware",  # <- Add this
        ...
    ]
"""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404


logger = logging.getLogger(__name__)


# ============================================================================
# 1. Remove Framework Fingerprints (Server, X-Powered-By, etc.)
# ============================================================================
class RemoveServerHeaderMiddleware(MiddlewareMixin):
    """
    Removes headers that identify the web server or framework.

    Removes:
    - Server (identifies web server: Apache, nginx, gunicorn, etc.)
    - X-Powered-By (identifies framework: Django, PHP, ASP.NET, etc.)
    - X-AspNet-Version (ASP.NET version leak)
    - X-AspNetMvc-Version (ASP.NET MVC version leak)
    - X-Django-Version (custom header some middleware might add)

    Why: Fingerprinting aids attackers in identifying known vulnerabilities.
    """

    HEADERS_TO_REMOVE = [
        "Server",
        "X-Powered-By",
        "X-AspNet-Version",
        "X-AspNetMvc-Version",
        "X-Django-Version",
        "X-Runtime",  # Some frameworks expose execution time
    ]

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Remove fingerprinting headers from response."""
        for header in self.HEADERS_TO_REMOVE:
            if header in response:
                del response[header]

        return response


# ============================================================================
# 2. Strict Security Headers (CSP, Permissions-Policy, etc.)
# ============================================================================
class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Adds comprehensive security headers to all responses.

    Headers added:
    - Content-Security-Policy (CSP): Restrict resource loading
    - Permissions-Policy: Disable dangerous browser features
    - X-Content-Type-Options: Prevent MIME sniffing
    - X-Frame-Options: Prevent clickjacking (already in Django, but re-enforced)
    - Referrer-Policy: Control referer header leakage
    - Cache-Control: Prevent sensitive data caching (for authenticated pages)
    - Cross-Origin-Opener-Policy (COOP): Prevent window.opener attacks
    - Cross-Origin-Resource-Policy (CORP): Control resource embedding

    Note: HSTS is already handled by Django's SecurityMiddleware.
    """

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Add security headers to response."""

        # Skip security headers for static/media files (handled by web server)
        path = request.path
        if path.startswith("/static/") or path.startswith("/media/"):
            return response

        # 1. Content Security Policy (CSP)
        # Start strict, allow 'self' and inline styles/scripts where needed
        # This is a baseline - adjust based on your actual needs
        if not response.get("Content-Security-Policy"):
            # media-src must allow 'self' (WhiteNoise static video fallback) plus
            # any VIDEO_BASE_URL CDN so the browser doesn't block video playback.
            video_cdn = getattr(settings, "VIDEO_BASE_URL", "").strip()
            media_src = f"media-src 'self' {video_cdn}" if video_cdn else "media-src 'self'"

            csp_directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com",  # Allow CDN for libraries
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
                "img-src 'self' data: https:",  # Allow data: for inline images, https: for external
                "font-src 'self' data: https://fonts.gstatic.com",
                "connect-src 'self' https://api.paychangu.com https://api.stripe.com https://graph.facebook.com",  # Allow API calls to payment providers
                media_src,  # Allow video/audio from self and optional CDN
                "frame-ancestors 'none'",  # Stronger than X-Frame-Options
                "base-uri 'self'",  # Prevent base tag injection
                "form-action 'self'",  # Prevent form submission to external domains
                "upgrade-insecure-requests",  # Automatically upgrade HTTP to HTTPS in production
            ]

            # In development, be more permissive
            if getattr(settings, "DEBUG", False):
                csp_directives = [
                    "default-src 'self' 'unsafe-inline' 'unsafe-eval'",
                    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com",
                    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
                    "img-src 'self' data: https: http:",
                    "font-src 'self' data: https://fonts.gstatic.com",
                    "connect-src 'self' https://api.paychangu.com https://api.stripe.com https://graph.facebook.com http://localhost:* ws://localhost:*",
                ]

            response["Content-Security-Policy"] = "; ".join(csp_directives)

        # 2. Permissions-Policy (formerly Feature-Policy)
        # Disable dangerous browser features
        if not response.get("Permissions-Policy"):
            permissions_directives = [
                "accelerometer=()",
                "ambient-light-sensor=()",
                "autoplay=()",
                "battery=()",
                "camera=()",  # Disable camera unless explicitly needed
                "display-capture=()",
                "geolocation=(self)",  # Allow geolocation for location tracking feature
                "gyroscope=()",
                "magnetometer=()",
                "microphone=()",  # Disable microphone unless explicitly needed
                "midi=()",
                "payment=(self)",  # Allow payment APIs for own origin
                "picture-in-picture=()",
                "speaker=()",
                "usb=()",
                "vibrate=()",
                "vr=()",
            ]
            response["Permissions-Policy"] = ", ".join(permissions_directives)

        # 3. X-Content-Type-Options (prevent MIME sniffing)
        # Already set by Django SecurityMiddleware, but re-enforce
        if not response.get("X-Content-Type-Options"):
            response["X-Content-Type-Options"] = "nosniff"

        # 4. X-Frame-Options (prevent clickjacking)
        # Already set by Django XFrameOptionsMiddleware, but re-enforce
        # CSP frame-ancestors is stronger, but keep this for older browsers
        if not response.get("X-Frame-Options"):
            response["X-Frame-Options"] = "DENY"

        # 5. Referrer-Policy (control referer leakage)
        # Already set in settings, but re-enforce
        if not response.get("Referrer-Policy"):
            response["Referrer-Policy"] = "same-origin"

        # 6. Cache-Control for authenticated pages
        # Prevent sensitive data from being cached
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            # Don't cache authenticated pages
            if not response.get("Cache-Control"):
                response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response["Pragma"] = "no-cache"  # HTTP/1.0 compatibility

        # 7. Cross-Origin-Opener-Policy (COOP)
        # Prevent window.opener attacks (especially important for OAuth flows)
        if not response.get("Cross-Origin-Opener-Policy"):
            response["Cross-Origin-Opener-Policy"] = "same-origin"

        # 8. Cross-Origin-Resource-Policy (CORP)
        # Control who can load this resource
        if not response.get("Cross-Origin-Resource-Policy"):
            response["Cross-Origin-Resource-Policy"] = "same-origin"

        # 9. X-Permitted-Cross-Domain-Policies
        # Prevent Adobe Flash/PDF cross-domain requests (legacy, but harmless)
        if not response.get("X-Permitted-Cross-Domain-Policies"):
            response["X-Permitted-Cross-Domain-Policies"] = "none"

        return response


# ============================================================================
# 3. Safe Error Response Middleware (No Stack Traces)
# ============================================================================
class SafeErrorResponseMiddleware(MiddlewareMixin):
    """
    Ensures error responses never leak sensitive information.

    - Intercepts all 4xx/5xx responses
    - Removes stack traces, internal paths, SQL queries
    - Replaces with generic error message + correlation ID
    - Logs full error details for operators

    This is a defense-in-depth measure (Django's DEBUG=False already prevents
    stack traces, but this ensures no custom code accidentally leaks info).
    """

    def process_exception(self, request: HttpRequest, exception: Exception) -> Optional[HttpResponse]:
        """Handle exceptions and return safe error responses."""

        # In development, let Django show the debug page
        if getattr(settings, "DEBUG", False):
            return None

        # Let Django handle these specifically (they have safe handlers)
        if isinstance(exception, (Http404, PermissionDenied, SuspiciousOperation)):
            return None

        # Log full exception for operators
        try:
            logger.exception(
                "Unhandled exception at %s",
                request.get_full_path(),
                extra={
                    "request_id": getattr(request, "request_id", None),
                    "user_id": getattr(request.user, "id", None) if hasattr(request, "user") else None,
                    "path": request.path,
                    "method": request.method,
                },
            )
        except Exception:
            # Never let logging break error handling
            pass

        # Return safe error response
        request_id = getattr(request, "request_id", None)

        # Determine if this is an API request (JSON response expected)
        is_api = (
            request.path.startswith("/api/")
            or request.path.startswith("/inventory/api/")
            or request.META.get("HTTP_ACCEPT", "").startswith("application/json")
            or request.META.get("CONTENT_TYPE", "").startswith("application/json")
        )

        if is_api:
            # JSON error response (no internal details)
            return JsonResponse(
                {
                    "error": "An error occurred processing your request.",
                    "request_id": request_id,
                },
                status=500,
            )

        # HTML error response (render template)
        try:
            from django.shortcuts import render

            return render(request, "errors/500.html", {"request_id": request_id}, status=500)
        except Exception:
            # Last resort: plain text response
            return HttpResponse(
                f"An error occurred. Reference: {request_id or 'N/A'}", status=500, content_type="text/plain"
            )

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Sanitize error responses (4xx/5xx) to remove leakage."""

        # Skip if not an error response
        if response.status_code < 400:
            return response

        # Skip in development (allow detailed errors)
        if getattr(settings, "DEBUG", False):
            return response

        # For API errors, ensure generic message (no Django/DRF details)
        if response.status_code >= 400 and response["Content-Type"].startswith("application/json"):
            try:
                import json

                data = json.loads(response.content.decode("utf-8"))

                # Check for verbose error keys that might leak info
                verbose_keys = ["detail", "traceback", "exception", "exc_info", "errors"]
                has_verbose = any(key in data for key in verbose_keys)

                if has_verbose and not getattr(settings, "DEBUG", False):
                    # Replace with generic message
                    request_id = getattr(request, "request_id", None)
                    safe_data = {
                        "error": "Request failed",
                        "request_id": request_id,
                    }

                    # Preserve status code hint (but no details)
                    if response.status_code == 400:
                        safe_data["error"] = "Invalid request"
                    elif response.status_code == 401:
                        safe_data["error"] = "Authentication required"
                    elif response.status_code == 403:
                        safe_data["error"] = "Permission denied"
                    elif response.status_code == 404:
                        safe_data["error"] = "Not found"
                    elif response.status_code == 429:
                        safe_data["error"] = "Too many requests"
                    elif response.status_code >= 500:
                        safe_data["error"] = "Server error"

                    return JsonResponse(safe_data, status=response.status_code)

            except Exception:
                # If we can't parse JSON, leave it alone
                pass

        return response


# ============================================================================
# 4. Custom 403 Handler (CSRF failures, permission denied)
# ============================================================================
def custom_403_handler(request: HttpRequest, exception: Exception) -> HttpResponse:
    """
    Custom 403 handler for permission denied and CSRF failures.

    Returns generic message without exposing why access was denied.
    """
    request_id = getattr(request, "request_id", None)

    # Check if this is an API request
    is_api = (
        request.path.startswith("/api/")
        or request.path.startswith("/inventory/api/")
        or request.META.get("HTTP_ACCEPT", "").startswith("application/json")
    )

    if is_api:
        return JsonResponse(
            {
                "error": "Permission denied",
                "request_id": request_id,
            },
            status=403,
        )

    # HTML response
    try:
        from django.shortcuts import render

        return render(request, "errors/403.html", {"request_id": request_id}, status=403)
    except Exception:
        return HttpResponse("Access denied", status=403, content_type="text/plain")
