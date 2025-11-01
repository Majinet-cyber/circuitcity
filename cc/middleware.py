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
            latency_ms = int(
                (time.perf_counter() - getattr(request, "_start_ts", time.perf_counter())) * 1000
            )
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
    "/hq", "/admin", "/accounts", "/static", "/media",
    "/favicon.ico", "/robots.txt", "/healthz", "/healthz/",
    "/api/global-search/",
)

# Client/tenant entry points we block for HQ admins
_BLOCK_PREFIXES = (
    "/tenants", "/inventory", "/dashboard", "/sell", "/scan", "/stock",
)


class PreventHQFromClientUI(MiddlewareMixin):
    """
    If user is an HQ admin, redirect any request to tenant/store UI
    back to the HQ shell. We redirect directly to **hq:subscriptions**
    (not hq:home) to avoid alias loops.
    """

    def process_request(self, request: HttpRequest):
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

        path = (request.path or "")

        # HQ/admin/static/etc. are always allowed
        for p in _HQ_ALLOW_PREFIXES:
            if path.startswith(p.rstrip("/")):
                return None

        # Block classic store/tenant entry points
        for p in _BLOCK_PREFIXES:
            if path.startswith(p):
                return redirect(_reverse_or("hq:subscriptions", "/hq/subscriptions/"))

        return None


# ------------------------------------------------------------------
# Auto-select single business for tenant users
# ------------------------------------------------------------------
class AutoSelectBusinessMiddleware(MiddlewareMixin):
    """
    If an authenticated user has exactly one active membership, automatically set:
      - request.active_business / request.session['active_business_id']
      - request.active_location  (first active location for that business)

    This makes pages like stock list / scan-in work without the user manually
    choosing a business each time.
    """

    def process_request(self, request: HttpRequest):
        try:
            user = getattr(request, "user", None)
            if not _safe_is_authenticated(user):
                return

            # If already set on request or session, do nothing.
            try:
                if getattr(request, "active_business", None) or request.session.get("active_business_id"):
                    # Ensure a location is present if business exists but location isn't set.
                    if getattr(request, "active_business", None) and not getattr(request, "active_location", None):
                        self._ensure_location(request)
                    return
            except Exception:
                # If session access explodes due to DB, quietly skip auto-select
                return

            # Try tenants models (prefer un-namespaced, then circuitcity.*)
            BM = self._import_membership_model()
            if not BM:
                return

            qs = BM.objects.filter(user=user)
            # Be defensive about flags
            try:
                field_names = [fld.name for fld in BM._meta.fields]
            except Exception:
                field_names = []

            for f in ("is_active", "active", "accepted"):
                if f in field_names:
                    try:
                        qs = qs.filter(**{f: True})
                    except Exception:
                        pass

            # Avoid expensive count() if DB is unhappy
            try:
                count = qs.count()
            except Exception:
                return

            if count != 1:
                return

            try:
                membership = qs.first()
            except Exception:
                return

            biz = getattr(membership, "business", None)
            if not biz:
                return

            # Set business on request and session
            request.active_business = biz
            request.active_business_id = getattr(biz, "id", None)
            try:
                request.session["active_business_id"] = getattr(biz, "id", None)
                # legacy keys some old code might read
                request.session["biz_id"] = getattr(biz, "id", None)
            except Exception:
                # If session write fails, still keep request-scoped values
                pass

            # Ensure a default location
            self._ensure_location(request)
        except Exception:
            # Never break requests because of auto-select logic
            pass

    # ----------------- helpers -----------------

    def _import_membership_model(self):
        try:
            from tenants.models import BusinessMembership  # type: ignore
            return BusinessMembership
        except Exception:
            try:
                from circuitcity.tenants.models import BusinessMembership  # type: ignore
                return BusinessMembership
            except Exception:
                return None

    def _import_location_model(self):
        try:
            from tenants.models import Location  # type: ignore
            return Location
        except Exception:
            try:
                from circuitcity.tenants.models import Location  # type: ignore
                return Location
            except Exception:
                return None

    def _ensure_location(self, request: HttpRequest):
        biz = getattr(request, "active_business", None)
        if not biz:
            return
        Location = self._import_location_model()
        if not Location:
            return
        try:
            field_names = [f.name for f in Location._meta.fields]
        except Exception:
            field_names = []

        try:
            qs = Location.objects.filter(business=biz)
            if "is_active" in field_names:
                qs = qs.filter(is_active=True)
            loc = qs.order_by("name").first()
            if loc:
                request.active_location = loc
                request.active_location_id = getattr(loc, "id", None)
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
