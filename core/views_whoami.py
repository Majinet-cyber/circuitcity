"""
Whoami endpoint for Cypress E2E tests and debugging.
Returns current user information as JSON.
"""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from tenants.utils import get_active_business

User = get_user_model()
logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def whoami(request: HttpRequest) -> JsonResponse:
    """
    Return current user information as JSON.

    Returns:
    - 401 if not authenticated: {ok: false, error: "UNAUTHENTICATED"}
    - 200 if authenticated: {ok: true, email, username, user_id, business_id (if any), role (if any)}

    Must never raise exceptions; wrap in try/except and return safe error JSON.
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse(
                {"ok": False, "error": "UNAUTHENTICATED", "is_authenticated": False},
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
            {"ok": False, "error": "INTERNAL_ERROR", "is_authenticated": False},
            status=500,
        )
