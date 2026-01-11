# cc/middleware.py
from __future__ import annotations

import time
import uuid
import logging
from importlib import import_module
from typing import Any, Optional

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.http import HttpRequest, HttpResponse, HttpResponseBase, Http404
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.shortcuts import render, redirect
from django.urls import reverse, NoReverseMatch


# ------------------------------------------------------------------
# Loggers
# ------------------------------------------------------------------
access_logger = logging.getLogger("access")
django_req_logger = logging.getLogger("django.request")


# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------
def _reverse_or(path_name: str, fallback: str) -> str:
    try:
        return reverse(path_name)
    except NoReverseMatch:
        return fallback


def _normalize_path(path: str) -> str:
    """Normalize path by removing duplicate slashes."""
    # Replace multiple slashes with single slash
    import re

    normalized = re.sub(r"/+", "/", path)
    # Ensure it starts with /
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


def _import_optional(path: str):
    try:
        return import_module(path)
    except Exception:
        return None


def _safe_is_authenticated(user: Any) -> bool:
    """
    Returns True iff the user is authenticated without boolean-casting the
    SimpleLazyObject. Any error while resolving the user/session -> False.
    """
    try:
        if user is None:
            return False
        attr = getattr(user, "is_authenticated", None)
        if callable(attr):
            return bool(attr())
        return bool(attr)
    except Exception:
        return False


def _safe_user_id(user: Any) -> Optional[int]:
    """Resolve user.id without forcing auth if it errors; return None on failure."""
    try:
        return getattr(user, "id", None)
    except Exception:
        return None


# ------------------------------------------------------------------
# Request ID
# ------------------------------------------------------------------
class RequestIDMiddleware(MiddlewareMixin):
    """
    Attaches a unique request ID to each request and response.

    • Reads incoming X-Request-ID (from proxies) if present,
      otherwise generates a UUID4.
    • Exposes request.request_id for views/templates.
    • Echoes back X-Request-ID on the response headers.
    """

    IN_HEADER = "HTTP_X_REQUEST_ID"
    OUT_HEADER = "X-Request-ID"

    def process_request(self, request: HttpRequest):
        rid = request.META.get(self.IN_HEADER) or str(uuid.uuid4())
        request.request_id = rid

    def process_response(self, request: HttpRequest, response: HttpResponse):
        try:
            rid = getattr(request, "request_id", None)
            if rid:
                response[self.OUT_HEADER] = rid
        except Exception:
            # Never block the response on header issues
            pass
        return response


# ------------------------------------------------------------------
# Access log
# ------------------------------------------------------------------
class AccessLogMiddleware(MiddlewareMixin):
    """
    Lightweight structured access logging with latency and user id.
    Safe: never blocks responses even if logging fails.
    """

    def process_request(self, request: HttpRequest):
        request._start_ts = time.perf_counter()

    def process_response(self, request: HttpRequest, response: HttpResponse):
        try:
            latency_ms = int((time.perf_counter() - getattr(request, "_start_ts", time.perf_counter())) * 1000)
            user = getattr(request, "user", None)
            user_id = _safe_user_id(user)

            access_logger.info(
                "http_request",
                extra={
                    "ts": timezone.now().isoformat(),
                    "request_id": getattr(request, "request_id", None),
                    "method": getattr(request, "method", None),
                    "path": request.get_full_path() if hasattr(request, "get_full_path") else None,
                    "status": getattr(response, "status_code", None),
                    "latency_ms": latency_ms,
                    "user_id": user_id,
                    "ip": request.META.get("REMOTE_ADDR") if hasattr(request, "META") else None,
                },
            )
        except Exception:
            # Never block the response on logging errors
            pass
        return response


# ------------------------------------------------------------------
# HQ guard — keep HQ admins out of tenant/store UIs
# Place this middleware in settings.py immediately AFTER
# AuthenticationMiddleware and BEFORE tenants middleware.
# ------------------------------------------------------------------
def _get_is_hq_admin():
    """
    Import canonical is_hq_admin(user) if present.
    Fallback: treat staff OR superuser as HQ admin.
    """
    for mp in ("circuitcity.hq.permissions", "hq.permissions"):
        try:
            mod = import_module(mp)
            fn = getattr(mod, "is_hq_admin", None)
            if callable(fn):
                return fn
        except Exception:
            continue
    return lambda u: bool(getattr(u, "is_staff", False) or getattr(u, "is_superuser", False))


_is_hq_admin = _get_is_hq_admin()

# Always allowed for HQ shell / admin / static
_HQ_ALLOW_PREFIXES = (
    "/hq",
    "/admin",
    "/accounts",
    "/static",
    "/media",
    "/favicon.ico",
    "/robots.txt",
    "/healthz",
    "/healthz/",
    "/api/global-search/",
)

# Client/tenant entry points we block for HQ admins
_BLOCK_PREFIXES = (
    "/tenants",
    "/inventory",
    "/dashboard",
    "/sell",
    "/scan",
    "/stock",
)


class PreventHQFromClientUI(MiddlewareMixin):
    """
    If user is an HQ admin, redirect any request to tenant/store UI
    back to the HQ shell. We redirect directly to **hq:subscriptions**
    (not hq:home) to avoid alias loops.

    CRITICAL LOOP GUARDS:
    - Never redirect when already on /hq/ paths
    - Never redirect if target equals current path
    """

    def __call__(self, request):
        # CRITICAL: Bypass HQ paths at the very top to prevent redirect loops
        path = request.path_info or request.path or "/"
        if path.startswith("/hq/"):
            return self.get_response(request)
        return super().__call__(request)

    def process_request(self, request: HttpRequest):
        # PART B: Rule 1 - HQ pages must never be redirected by tenant/business enforcement
        path = (request.path_info or request.path or "/").split("?")[0]
        if path.startswith("/hq/"):
            return None

        user = getattr(request, "user", None)
        # ⚠️ Never boolean-cast the lazy user; use the safe helper.
        if not _safe_is_authenticated(user):
            return None

        try:
            if not _is_hq_admin(user):
                return None  # non-HQ users are allowed through
        except Exception:
            # If role resolution fails (e.g., DB hiccup), treat as non-HQ and continue
            return None

        path = path.rstrip("/")

        # HQ/admin/static/etc. are always allowed
        for p in _HQ_ALLOW_PREFIXES:
            if path.startswith(p.rstrip("/")):
                return None

        # Block classic store/tenant entry points
        for p in _BLOCK_PREFIXES:
            if path.startswith(p):
                target = _reverse_or("hq:subscriptions", "/hq/subscriptions/")
                # Normalize target (remove query string if present)
                target = target.split("?")[0] if target else "/"
                target_normalized = target.rstrip("/")
                path_normalized = path.rstrip("/")

                # Anti-loop guard: Never redirect if target equals current path
                if target.rstrip("/") == path.rstrip("/"):
                    return None

                return redirect(target)

        return None


# ------------------------------------------------------------------
# Auto-select single business for tenant users
# ------------------------------------------------------------------
class AutoSelectBusinessMiddleware(MiddlewareMixin):
    """
    SSOT-based active business middleware.
    
    If an authenticated user has exactly one active membership, automatically set:
      - request.active_business / request.session['active_business_id']
      - request.active_location  (first active location for that business)

    This prevents 302 redirects to /tenants/ for single-business users.
    Multi-business users still see the tenant chooser (no behavior change).
    
    CRITICAL: This must run BEFORE any middleware that checks for active business
    and redirects to /tenants/ (e.g., require_business decorator logic).
    """

    def process_request(self, request: HttpRequest):
        try:
            user = getattr(request, "user", None)
            if not _safe_is_authenticated(user):
                return

            # Use SSOT service to ensure active business
            try:
                from tenants.services.active_business import ensure_active_business, _ensure_default_location
                
                biz = ensure_active_business(request, user, auto_select_single=True)
                
                # If business was set, ensure location too
                if biz:
                    _ensure_default_location(request, biz)
            except ImportError:
                # SSOT service not available, fall back to inline logic
                self._fallback_auto_select(request, user)
        except Exception:
            # Never break requests because of auto-select logic
            pass

    # ----------------- fallback for backwards compatibility -----------------

    def _fallback_auto_select(self, request: HttpRequest, user):
        """Fallback implementation if SSOT service is not available."""
        try:
            # If already set on request or session, do nothing.
            if getattr(request, "active_business", None) or request.session.get("active_business_id"):
                # Ensure a location is present if business exists but location isn't set.
                if getattr(request, "active_business", None) and not getattr(request, "active_location", None):
                    self._ensure_location(request)
                return

            # Try tenants models
            try:
                from tenants.models import Membership
            except ImportError:
                return

            qs = Membership.objects.filter(user=user).select_related("business")
            
            # Filter active memberships
            try:
                field_names = {f.name for f in Membership._meta.fields}
                if "status" in field_names:
                    qs = qs.filter(status="ACTIVE")
                elif "is_active" in field_names:
                    qs = qs.filter(is_active=True)
            except Exception:
                pass

            # Filter active businesses
            try:
                qs = qs.filter(business__status="ACTIVE")
            except Exception:
                pass

            # Only auto-select if exactly ONE
            count = qs.count()
            if count != 1:
                return

            membership = qs.first()
            if not membership:
                return

            biz = getattr(membership, "business", None)
            if not biz:
                return

            # Set business on request and session
            request.active_business = biz
            request.business = biz
            request.active_business_id = getattr(biz, "id", None)
            
            try:
                request.session["active_business_id"] = getattr(biz, "id", None)
                request.session["biz_id"] = getattr(biz, "id", None)
                request.session.modified = True
            except Exception:
                pass

            # Ensure a default location
            self._ensure_location(request)
        except Exception:
            pass

    def _ensure_location(self, request: HttpRequest):
        """Ensure a default location is set."""
        biz = getattr(request, "active_business", None) or getattr(request, "business", None)
        if not biz:
            return
        
        # Skip if already set
        if getattr(request, "active_location", None):
            return
        
        try:
            from tenants.models import Location
        except ImportError:
            return

        try:
            qs = Location.objects.filter(business=biz)
            
            # Prefer active locations
            try:
                if hasattr(Location, "is_active"):
                    qs = qs.filter(is_active=True)
            except Exception:
                pass
            
            # Prefer headquarters or default
            loc = (
                qs.filter(is_headquarters=True).first()
                or qs.filter(is_default=True).first()
                or qs.order_by("name").first()
            )
            
            if loc:
                request.active_location = loc
                request.active_location_id = getattr(loc, "id", None)
                try:
                    request.session["active_location_id"] = getattr(loc, "id", None)
                    request.session.modified = True
                except Exception:
                    pass
        except Exception:
            pass


# ------------------------------------------------------------------
# Friendly 500 page (production)
# ------------------------------------------------------------------
class FriendlyErrorsMiddleware(MiddlewareMixin):
    """
    Converts unexpected exceptions into a branded 500 page for users
    while keeping full tracebacks in logs. Has no effect when DEBUG=True.

    • Re-raises 404, PermissionDenied, SuspiciousOperation to let Django handle them.
    • For any other Exception, logs the traceback and renders templates/errors/500.html.
    • Includes X-Request-ID header (added by RequestIDMiddleware) for easier support.
    """

    def process_exception(self, request: HttpRequest, exc: Exception):
        # In development, let Django show the debug page
        if getattr(settings, "DEBUG", False):
            return None

        # Let Django handle these specifically (404/permission/security)
        if isinstance(exc, (Http404, PermissionDenied, SuspiciousOperation)):
            return None

        try:
            # Log full traceback for operators
            django_req_logger.exception("Unhandled exception at %s", request.get_full_path())
        except Exception:
            pass

        # Render friendly 500 page
        try:
            context = {"request_id": getattr(request, "request_id", None)}
            resp = render(request, "errors/500.html", context=context, status=500)
            # Ensure X-Request-ID header present (in case RequestIDMiddleware not installed)
            rid = getattr(request, "request_id", None)
            if rid:
                resp["X-Request-ID"] = rid
            return resp
        except Exception:
            # As a last resort, return a minimal safe response
            return HttpResponse("Sorry — something went wrong.", status=500)


# ------------------------------------------------------------------
# URL Normalization Middleware (fixes double slashes)
# ------------------------------------------------------------------
class NormalizeURLMiddleware(MiddlewareMixin):
    """
    Middleware to normalize URLs by removing duplicate slashes.
    Redirects /foo//bar/ to /foo/bar/ (permanent redirect).
    Prevents 404s caused by accidental double slashes.
    """

    def process_request(self, request: HttpRequest):
        """Normalize URL path by removing duplicate slashes."""
        original_path = request.path
        normalized_path = _normalize_path(original_path)

        # If path changed, redirect to normalized version
        if original_path != normalized_path:
            # Preserve query string
            query_string = request.META.get("QUERY_STRING", "")
            if query_string:
                normalized_url = f"{normalized_path}?{query_string}"
            else:
                normalized_url = normalized_path

            # 301 permanent redirect
            return redirect(normalized_url, permanent=True)

        return None
