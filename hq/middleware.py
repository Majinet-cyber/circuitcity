# hq/middleware.py
"""
BugCaptureMiddleware — captures unhandled exceptions into SystemIssue / SystemIssueOccurrence.

CRITICAL DESIGN RULES:
1. NEVER returns a response — always returns None so Django's normal error handling continues.
2. NEVER raises — any internal error is swallowed silently to avoid masking the original exception.
3. Privacy-safe — payloads are sanitized before storage; no passwords/tokens/cookies stored.
4. Idempotent — recurring errors increment occurrence_count, not create endless rows.
"""
from __future__ import annotations

import logging
import traceback
from typing import Optional

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("hq.bugmonitor")

# Status codes below this threshold don't need bug monitor entries (except 500+)
_CAPTURE_STATUS_CODES = frozenset([400, 403, 404, 500])


class BugCaptureMiddleware(MiddlewareMixin):
    """
    Intercepts exceptions, logs them to SystemIssue/SystemIssueOccurrence,
    then returns None so normal Django error handling proceeds.
    """

    def process_exception(self, request, exception):
        try:
            self._capture(request, exception)
        except Exception:
            # Silently swallow — never let bug monitor cause a user-facing failure
            pass
        return None  # Always let Django continue its normal error handling

    # ------------------------------------------------------------------

    def _capture(self, request, exception):
        from hq.models_bugmonitor import SystemIssue, SystemIssueOccurrence, IssueStatus, IssueSeverity
        from hq.sanitizer import sanitize_querydict, sanitize_request_body, normalize_path_for_fingerprint

        # Determine status code and severity from exception type
        status_code, severity = self._classify_exception(exception)

        # Extract stack trace
        stack_str = traceback.format_exc() or ""
        top_frame = self._get_top_frame(stack_str)

        # Extract request context
        path = getattr(request, "path", "/") or "/"
        if status_code == 404 and path.startswith("/media/"):
            return
        method = getattr(request, "method", "GET") or "GET"
        view_name = self._get_view_name(request)
        user_agent = (request.META.get("HTTP_USER_AGENT", "") or "")[:1000]
        ip = self._get_client_ip(request)

        # Resolve user and business (if available)
        user = self._get_request_user(request)
        business = self._get_request_business(request)

        # Error classification
        error_type = type(exception).__name__
        message = str(exception)[:2000]
        title = f"{error_type}: {message[:200]}" if message else error_type

        # Build fingerprint
        fingerprint = SystemIssue.build_fingerprint(
            error_type=error_type,
            status_code=status_code,
            path=path,
            view_name=view_name,
            top_frame=top_frame,
        )

        # Sanitize payloads
        san_get = sanitize_querydict(getattr(request, "GET", None))
        san_post = sanitize_querydict(getattr(request, "POST", None))
        san_body = sanitize_request_body(request)

        # Parse UA for device/browser/os
        device_family, browser_family, os_family = self._parse_ua(user_agent)

        # Env / version
        from django.conf import settings as djsettings
        environment = getattr(djsettings, "ENVIRONMENT", "") or ("development" if getattr(djsettings, "DEBUG", False) else "production")
        release_version = getattr(djsettings, "RELEASE_VERSION", "") or getattr(djsettings, "BUILD_ID", "") or ""

        # Upsert SystemIssue
        try:
            issue = SystemIssue.objects.get(fingerprint=fingerprint)
            # Existing issue: increment count, update last-seen, refresh payload snapshot
            issue.occurrence_count += 1
            issue.last_seen_at = _now()
            issue.sanitized_get_params = san_get
            issue.sanitized_post_data = san_post
            issue.sanitized_payload = san_body
            issue.stack_trace = stack_str[:50000]
            # If issue was cleared/ignored, reopen it as NEW when it recurs
            if issue.status in (IssueStatus.CLEARED, IssueStatus.IGNORED):
                issue.status = IssueStatus.NEW
            issue.save(update_fields=[
                "occurrence_count", "last_seen_at",
                "sanitized_get_params", "sanitized_post_data", "sanitized_payload",
                "stack_trace", "status", "updated_at",
            ])
        except SystemIssue.DoesNotExist:
            issue = SystemIssue.objects.create(
                fingerprint=fingerprint,
                title=title,
                error_type=error_type,
                message=message,
                status_code=status_code,
                severity=severity,
                status=IssueStatus.NEW,
                path=path[:2048],
                method=method[:16],
                view_name=view_name[:255],
                user=user,
                business=business,
                user_agent=user_agent,
                device_family=device_family[:128],
                browser_family=browser_family[:128],
                os_family=os_family[:128],
                ip_address=ip,
                sanitized_get_params=san_get,
                sanitized_post_data=san_post,
                sanitized_payload=san_body,
                stack_trace=stack_str[:50000],
                environment=environment[:64],
                release_version=release_version[:128],
            )

        # Always create a child occurrence
        SystemIssueOccurrence.objects.create(
            issue=issue,
            path=path[:2048],
            method=method[:16],
            user=user,
            business=business,
            user_agent=user_agent,
            ip_address=ip,
            stack_trace=stack_str[:50000],
            sanitized_get_params=san_get,
            sanitized_post_data=san_post,
            sanitized_payload=san_body,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_exception(exception) -> tuple[Optional[int], str]:
        from hq.models_bugmonitor import IssueSeverity
        if isinstance(exception, Http404):
            return 404, IssueSeverity.LOW
        if isinstance(exception, PermissionDenied):
            return 403, IssueSeverity.LOW
        if isinstance(exception, SuspiciousOperation):
            return 400, IssueSeverity.LOW
        return 500, IssueSeverity.HIGH

    @staticmethod
    def _get_top_frame(stack_str: str) -> str:
        """Return the last meaningful frame from the traceback."""
        if not stack_str:
            return ""
        lines = [ln.strip() for ln in stack_str.splitlines() if ln.strip().startswith("File ")]
        return lines[-1][:200] if lines else ""

    @staticmethod
    def _get_view_name(request) -> str:
        try:
            resolver_match = getattr(request, "resolver_match", None)
            if resolver_match:
                return resolver_match.view_name or ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _get_client_ip(request) -> Optional[str]:
        try:
            xff = request.META.get("HTTP_X_FORWARDED_FOR")
            if xff:
                return xff.split(",")[0].strip()
            return request.META.get("REMOTE_ADDR")
        except Exception:
            return None

    @staticmethod
    def _get_request_user(request):
        try:
            user = getattr(request, "user", None)
            if user and getattr(user, "is_authenticated", False):
                return user
        except Exception:
            pass
        return None

    @staticmethod
    def _get_request_business(request):
        try:
            return (
                getattr(request, "active_business", None)
                or getattr(request, "business", None)
            )
        except Exception:
            return None

    @staticmethod
    def _parse_ua(user_agent: str) -> tuple[str, str, str]:
        """Parse UA string into (device, browser, os). Gracefully degrades."""
        try:
            from ua_parser import user_agent_parser
            parsed = user_agent_parser.Parse(user_agent)
            device  = parsed.get("device", {}).get("family", "") or ""
            browser = parsed.get("user_agent", {}).get("family", "") or ""
            os_     = parsed.get("os", {}).get("family", "") or ""
            return device, browser, os_
        except ImportError:
            pass
        except Exception:
            pass
        # Fallback: simple heuristics
        ua = user_agent.lower()
        browser = "Chrome" if "chrome" in ua else "Firefox" if "firefox" in ua else "Safari" if "safari" in ua else ""
        device = "Mobile" if any(x in ua for x in ("mobile", "android", "iphone")) else "Desktop"
        os_ = "Android" if "android" in ua else "iOS" if "iphone" in ua or "ipad" in ua else "Windows" if "windows" in ua else "macOS" if "mac os" in ua else "Linux" if "linux" in ua else ""
        return device, browser, os_


def _now():
    from django.utils import timezone
    return timezone.now()
