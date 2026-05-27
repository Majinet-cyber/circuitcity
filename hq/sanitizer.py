# hq/sanitizer.py
"""
Privacy-safe payload sanitization for Bug Monitor.

All-seeing without snooping: captures operational context while
scrubbing passwords, tokens, OTPs, payment secrets, and auth headers.
"""
from __future__ import annotations

import re
from typing import Any

# Keys containing any of these substrings (case-insensitive) will be redacted.
_SENSITIVE_SUBSTRINGS = (
    "password",
    "passwd",
    "token",
    "secret",
    "otp",
    "authorization",
    "cookie",
    "csrf",
    "card",
    "pin",
    "api_key",
    "apikey",
    "access",
    "refresh",
    "private",
    "credential",
    "auth",
    "cvv",
    "ssn",
    "pii",
    "account_number",
    "billing",
)

_REDACTED = "[REDACTED]"
_MAX_DEPTH = 5
_MAX_STRING_LEN = 2000


def _is_sensitive_key(key: str) -> bool:
    """Return True if key name matches any sensitive substring."""
    lk = key.lower()
    return any(sub in lk for sub in _SENSITIVE_SUBSTRINGS)


def sanitize_value(value: Any, depth: int = 0) -> Any:
    """Recursively sanitize a value, redacting sensitive strings."""
    if depth > _MAX_DEPTH:
        return "[TRUNCATED]"

    if isinstance(value, dict):
        return {k: (_REDACTED if _is_sensitive_key(str(k)) else sanitize_value(v, depth + 1)) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        sanitized = [sanitize_value(item, depth + 1) for item in value]
        return type(value)(sanitized) if isinstance(value, tuple) else sanitized

    if isinstance(value, str):
        if len(value) > _MAX_STRING_LEN:
            return value[:_MAX_STRING_LEN] + "...[TRUNCATED]"
        return value

    return value


def sanitize_dict(data: dict | None) -> dict:
    """Sanitize a dict, redacting sensitive keys and values."""
    if not data:
        return {}
    try:
        return sanitize_value(dict(data))
    except Exception:
        return {"error": "Could not sanitize payload"}


def sanitize_querydict(qd) -> dict:
    """Sanitize a Django QueryDict (GET/POST params)."""
    if qd is None:
        return {}
    try:
        result = {}
        for key in qd.keys():
            if _is_sensitive_key(key):
                result[key] = _REDACTED
            else:
                vals = qd.getlist(key)
                result[key] = vals[0] if len(vals) == 1 else vals
        return result
    except Exception:
        return {"error": "Could not sanitize querydict"}


def sanitize_headers(meta: dict) -> dict:
    """Extract and sanitize relevant HTTP headers from request.META."""
    safe = {}
    _HEADER_MAP = {
        "HTTP_HOST": "Host",
        "HTTP_REFERER": "Referer",
        "HTTP_ACCEPT": "Accept",
        "HTTP_ACCEPT_LANGUAGE": "Accept-Language",
        "HTTP_X_FORWARDED_FOR": "X-Forwarded-For",
        "HTTP_X_REQUEST_ID": "X-Request-ID",
        "REQUEST_METHOD": "Method",
        "SERVER_NAME": "Server-Name",
        "CONTENT_TYPE": "Content-Type",
    }
    for meta_key, header_name in _HEADER_MAP.items():
        val = meta.get(meta_key)
        if val:
            safe[header_name] = str(val)[:500]
    return safe


def sanitize_request_body(request) -> dict:
    """
    Attempt to parse and sanitize the request body as JSON or form data.
    Returns empty dict if body cannot be safely read.
    """
    try:
        import json
        body = getattr(request, "body", b"")
        if not body:
            return {}
        ct = request.META.get("CONTENT_TYPE", "")
        if "application/json" in ct:
            raw = json.loads(body.decode("utf-8", errors="replace"))
            if isinstance(raw, dict):
                return sanitize_dict(raw)
            return {"body": "[non-dict JSON]"}
    except Exception:
        pass
    return {}


def normalize_path_for_fingerprint(path: str) -> str:
    """
    Normalize a URL path for fingerprinting by collapsing numeric/UUID segments
    so that /items/123/ and /items/456/ produce the same fingerprint.
    """
    path = re.sub(r"/\d+/", "/<int>/", path)
    path = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/", "/<uuid>/", path)
    path = re.sub(r"/{2,}", "/", path)
    return path.rstrip("/") or "/"
