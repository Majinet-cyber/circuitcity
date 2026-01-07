# cc/api_utils.py
"""
Centralized API Response Utilities
===================================

Provides consistent JSON response envelopes for all API endpoints.

Usage:
    from cc.api_utils import api_success, api_error, api_unauthorized, api_forbidden

    @login_required
    def my_api_view(request):
        try:
            data = {"result": "something"}
            return api_success(data)
        except ValueError as e:
            return api_error(str(e), status=400)

Response Format:
    Success: {"ok": true, "data": {...}, "request_id": "..."}
    Error: {"ok": false, "error": "message", "request_id": "..."}
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from django.http import JsonResponse, HttpRequest
import logging

logger = logging.getLogger(__name__)


def _get_request_id(request: Optional[HttpRequest] = None) -> Optional[str]:
    """Extract request ID from request object if available."""
    if request:
        return getattr(request, "request_id", None)
    return None


def api_success(
    data: Dict[str, Any] | List[Any] | None = None,
    message: Optional[str] = None,
    status: int = 200,
    request: Optional[HttpRequest] = None,
    **extra,
) -> JsonResponse:
    """
    Return a success JSON response with consistent envelope.

    Args:
        data: Response payload (dict, list, or None)
        message: Optional success message
        status: HTTP status code (default 200)
        request: Optional HttpRequest (for request_id)
        **extra: Additional fields to include in response

    Returns:
        JsonResponse with {"ok": true, "data": ..., ...}
    """
    payload = {
        "ok": True,
    }

    if data is not None:
        payload["data"] = data

    if message:
        payload["message"] = message

    # Add request ID for traceability
    request_id = _get_request_id(request)
    if request_id:
        payload["request_id"] = request_id

    # Merge any extra fields
    if extra:
        payload.update(extra)

    return JsonResponse(payload, status=status)


def api_error(
    error: str, status: int = 400, request: Optional[HttpRequest] = None, code: Optional[str] = None, **extra
) -> JsonResponse:
    """
    Return an error JSON response with consistent envelope.

    Args:
        error: Error message (user-friendly, NO internal details)
        status: HTTP status code (default 400)
        request: Optional HttpRequest (for request_id)
        code: Optional error code (e.g., "INVALID_INPUT", "RESOURCE_NOT_FOUND")
        **extra: Additional fields to include in error response

    Returns:
        JsonResponse with {"ok": false, "error": ..., ...}

    Security Note:
        NEVER include stack traces, exception types, or internal paths in error messages.
        Use generic messages for production. Log detailed errors server-side.
    """
    payload = {
        "ok": False,
        "error": error,
    }

    if code:
        payload["code"] = code

    # Add request ID for traceability
    request_id = _get_request_id(request)
    if request_id:
        payload["request_id"] = request_id

    # Merge any extra fields (be careful not to leak sensitive info)
    if extra:
        payload.update(extra)

    return JsonResponse(payload, status=status)


def api_unauthorized(
    error: str = "Authentication required", request: Optional[HttpRequest] = None, **extra
) -> JsonResponse:
    """Return a 401 Unauthorized response."""
    return api_error(error, status=401, request=request, code="UNAUTHORIZED", **extra)


def api_forbidden(error: str = "Permission denied", request: Optional[HttpRequest] = None, **extra) -> JsonResponse:
    """Return a 403 Forbidden response."""
    return api_error(error, status=403, request=request, code="FORBIDDEN", **extra)


def api_not_found(error: str = "Resource not found", request: Optional[HttpRequest] = None, **extra) -> JsonResponse:
    """Return a 404 Not Found response."""
    return api_error(error, status=404, request=request, code="NOT_FOUND", **extra)


def api_conflict(error: str = "Resource conflict", request: Optional[HttpRequest] = None, **extra) -> JsonResponse:
    """Return a 409 Conflict response."""
    return api_error(error, status=409, request=request, code="CONFLICT", **extra)


def api_rate_limited(
    error: str = "Too many requests. Please try again later.",
    request: Optional[HttpRequest] = None,
    retry_after: Optional[int] = None,
    **extra,
) -> JsonResponse:
    """
    Return a 429 Too Many Requests response.

    Args:
        error: Error message
        request: Optional HttpRequest
        retry_after: Optional retry-after value in seconds
        **extra: Additional fields
    """
    response = api_error(error, status=429, request=request, code="RATE_LIMITED", **extra)

    if retry_after:
        response["Retry-After"] = str(retry_after)

    return response


def api_validation_error(
    errors: Dict[str, List[str]] | List[str] | str,
    message: str = "Validation failed",
    request: Optional[HttpRequest] = None,
) -> JsonResponse:
    """
    Return a 400 Bad Request response for validation errors.

    Args:
        errors: Validation errors (field -> error list mapping, or single message)
        message: General error message
        request: Optional HttpRequest

    Returns:
        JsonResponse with {"ok": false, "error": ..., "errors": {...}}

    Example:
        errors = {
            "email": ["Invalid email format"],
            "password": ["Too short", "Must contain a number"]
        }
        return api_validation_error(errors)
    """
    payload = {
        "ok": False,
        "error": message,
        "code": "VALIDATION_ERROR",
    }

    # Normalize errors to dict format
    if isinstance(errors, dict):
        payload["errors"] = errors
    elif isinstance(errors, list):
        payload["errors"] = {"_general": errors}
    elif isinstance(errors, str):
        payload["errors"] = {"_general": [errors]}

    request_id = _get_request_id(request)
    if request_id:
        payload["request_id"] = request_id

    return JsonResponse(payload, status=400)


def api_exception_handler(request: HttpRequest, exception: Exception, log_exception: bool = True) -> JsonResponse:
    """
    Centralized exception handler for API views.

    Usage:
        try:
            # ... API logic ...
        except Exception as e:
            return api_exception_handler(request, e)

    Args:
        request: HttpRequest object
        exception: Caught exception
        log_exception: Whether to log the exception (default True)

    Returns:
        JsonResponse with generic error message (NO stack trace)

    Security Note:
        This function NEVER returns internal exception details to the client.
        All exceptions are logged server-side for debugging.
    """
    if log_exception:
        logger.error(
            f"API exception in {request.path}: {type(exception).__name__}: {exception}",
            exc_info=True,
            extra={
                "request_id": getattr(request, "request_id", None),
                "user": getattr(request, "user", None),
                "path": request.path,
            },
        )

    # Return generic error (no internal details)
    return api_error("An error occurred processing your request.", status=500, request=request, code="INTERNAL_ERROR")


# Backwards compatibility aliases (for gradual migration)
json_ok = api_success
json_error = api_error

__all__ = [
    "api_success",
    "api_error",
    "api_unauthorized",
    "api_forbidden",
    "api_not_found",
    "api_conflict",
    "api_rate_limited",
    "api_validation_error",
    "api_exception_handler",
    # Backwards compatibility
    "json_ok",
    "json_error",
]
