# cc/middleware.py
from __future__ import annotations

import time
import uuid
import logging
from typing import Optional

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.http import HttpRequest, HttpResponse
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.shortcuts import render

# ------------------------------------------------------------------
# Loggers
# ------------------------------------------------------------------
access_logger = logging.getLogger("access")
django_req_logger = logging.getLogger("django.request")


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
                (time.perf_counter() - getattr(request, "_start_ts", time.perf_counter()))
                * 1000
            )
            user_id = getattr(getattr(request, "user", None), "id", None)
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
            if not (user and user.is_authenticated):
                return

            # If already set on request or session, do nothing.
            if getattr(request, "active_business", None) or request.session.get("active_business_id"):
                # Ensure a location is present if business exists but location isn't set.
                if getattr(request, "active_business", None) and not getattr(request, "active_location", None):
                    self._ensure_location(request)
                return

            # Try tenants models (prefer un-namespaced, then circuitcity.*)
            BM = self._import_membership_model()
            if not BM:
                return

            qs = BM.objects.filter(user=user)
            # Be defensive about flags
            for f in ("is_active", "active", "accepted"):
                if f in [fld.name for fld in BM._meta.fields]:
                    try:
                        qs = qs.filter(**{f: True})
                    except Exception:
                        pass

            if qs.count() != 1:
                return

            membership = qs.first()
            biz = getattr(membership, "business", None)
            if not biz:
                return

            # Set business on request and session
            request.active_business = biz
            request.active_business_id = getattr(biz, "id", None)
            request.session["active_business_id"] = getattr(biz, "id", None)
            # legacy keys some old code might read
            request.session["biz_id"] = getattr(biz, "id", None)

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
            loc = (
                Location.objects.filter(business=biz)
                .filter(**({"is_active": True} if "is_active" in [f.name for f in Location._meta.fields] else {}))
                .order_by("name")
                .first()
            )
            if loc:
                request.active_location = loc
                request.active_location_id = getattr(loc, "id", None)
        except Exception:
            pass


class FriendlyErrorsMiddleware(MiddlewareMixin):
    """
    Converts unexpected exceptions into a branded 500 page for users
    while keeping full tracebacks in logs. Has no effect when DEBUG=True.

    • Re-raises 404, PermissionDenied, SuspiciousOperation to let Django handle them.
    • For any other Exception, logs the traceback and renders templates/errors/500.html.
    • Includes X-Request-ID header (added by RequestIDMiddleware) for easier support.

    Add to settings.MIDDLEWARE near the end, e.g.:

        MIDDLEWARE = [
            # ... Django defaults ...
            "cc.middleware.RequestIDMiddleware",
            "cc.middleware.AccessLogMiddleware",
            "cc.middleware.AutoSelectBusinessMiddleware",
            "cc.middleware.FriendlyErrorsMiddleware",  # ← keep near the end
        ]

        DEBUG_PROPAGATE_EXCEPTIONS = False
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
