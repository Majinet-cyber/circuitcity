from __future__ import annotations

import time
import uuid
import logging
from typing import Optional

from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("access")


class RequestIDMiddleware(MiddlewareMixin):
    HEADER_NAME = "HTTP_X_REQUEST_ID"

    def process_request(self, request: HttpRequest):
        rid = request.META.get(self.HEADER_NAME) or str(uuid.uuid4())
        request.request_id = rid


class AccessLogMiddleware(MiddlewareMixin):
    def process_request(self, request: HttpRequest):
        request._start_ts = time.perf_counter()

    def process_response(self, request: HttpRequest, response: HttpResponse):
        try:
            latency_ms = int(
                (time.perf_counter() - getattr(request, "_start_ts", time.perf_counter()))
                * 1000
            )
            user_id = getattr(getattr(request, "user", None), "id", None)
            logger.info(
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
