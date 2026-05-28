"""Support utilities — safe error metadata handling."""

SENSITIVE_KEYS = {
    "password",
    "token",
    "secret",
    "api_key",
    "authorization",
    "webhook_secret",
    "private_key",
    "access_token",
    "refresh_token",
    "auth",
    "bearer",
    "credentials",
    "passwd",
    "pwd",
}

_REDACTED = "[REDACTED]"


def sanitize_error_metadata(data, _depth=0):
    """
    Recursively sanitize a dict so that any key matching a sensitive pattern
    has its value replaced with '[REDACTED]'.  Handles nested dicts and lists.
    Returns a new dict (does not mutate the original).
    """
    if _depth > 10:
        return _REDACTED
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if any(sensitive in str(k).lower() for sensitive in SENSITIVE_KEYS):
                out[k] = _REDACTED
            else:
                out[k] = sanitize_error_metadata(v, _depth + 1)
        return out
    if isinstance(data, list):
        return [sanitize_error_metadata(item, _depth + 1) for item in data]
    return data
