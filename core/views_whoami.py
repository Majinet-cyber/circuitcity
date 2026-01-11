"""
Whoami endpoint for Cypress E2E tests and debugging.
Returns current user information as JSON.

Also provides build/debug info for diagnosing template caching issues.
"""
from __future__ import annotations

import logging
import os
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from tenants.utils import get_active_business

User = get_user_model()
logger = logging.getLogger(__name__)


def _get_git_sha() -> str:
    """
    Get current git commit SHA (short).
    """
    for key in ("RENDER_GIT_COMMIT", "GIT_SHA", "GIT_COMMIT"):
        value = os.environ.get(key, "").strip()
        if value:
            return value[:7]
    
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=getattr(settings, "BASE_DIR", None),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    
    return "unknown"


def _get_template_dirs() -> list:
    """
    Get the effective TEMPLATE_DIRS from settings.
    """
    try:
        templates_config = settings.TEMPLATES
        if templates_config and len(templates_config) > 0:
            dirs = templates_config[0].get("DIRS", [])
            return [str(d) for d in dirs]
    except Exception:
        pass
    return []


@require_http_methods(["GET"])
def whoami(request: HttpRequest) -> JsonResponse:
    """
    Return current user information and build diagnostics as JSON.

    Returns:
    - 401 if not authenticated: {ok: false, error: "UNAUTHENTICATED", build_sha, debug, template_dirs}
    - 200 if authenticated: {ok: true, email, username, user_id, business_id (if any), role (if any), build_sha, debug, template_dirs}

    Always includes build info for debugging template/caching issues:
    - build_sha: Current git commit SHA (short)
    - debug: Whether DEBUG is True
    - template_dirs: Effective TEMPLATE_DIRS order

    Must never raise exceptions; wrap in try/except and return safe error JSON.
    """
    # Always include build info for debugging
    build_info = {
        "build_sha": _get_git_sha(),
        "debug": settings.DEBUG,
        "template_dirs": _get_template_dirs(),
    }
    
    try:
        if not request.user.is_authenticated:
            return JsonResponse(
                {"ok": False, "error": "UNAUTHENTICATED", "is_authenticated": False, **build_info},
                status=401,
            )

        # Get user info
        user = request.user
        response_data = {
            "ok": True,
            "is_authenticated": True,
            "email": user.email or user.username,
            "username": user.username,
            "user_id": user.id,
            **build_info,
        }

        # Try to get business info (may not exist)
        try:
            business = get_active_business(request)
            if business:
                response_data["business_id"] = business.id
                response_data["business_name"] = business.name
                response_data["business_kind"] = business.business_kind or None
        except Exception as e:
            # Business lookup failed - that's ok, just don't include it
            logger.debug(f"whoami: Could not get business for user {user.id}: {e}")

        # Try to get role from membership (may not exist)
        try:
            from tenants.models import Membership

            membership = Membership.objects.filter(user=user, status="ACTIVE").select_related("business").first()

            if membership:
                response_data["role"] = membership.role
                if not response_data.get("business_id") and membership.business_id:
                    response_data["business_id"] = membership.business_id
        except Exception as e:
            # Membership lookup failed - that's ok
            logger.debug(f"whoami: Could not get membership for user {user.id}: {e}")

        return JsonResponse(response_data, status=200)

    except Exception as e:
        # Never crash - return safe error
        logger.error(f"whoami endpoint error: {e}", exc_info=True)
        return JsonResponse(
            {"ok": False, "error": "INTERNAL_ERROR", "is_authenticated": False, **build_info},
            status=500,
        )
