from django.core.cache import cache

_VER_KEY = "dash:ver"

def _get_ver() -> int:
    v = cache.get(_VER_KEY)
    return int(v or 1)

def bump_dashboard_cache_version() -> None:
    """Increment a global version so all cached dashboard keys invalidate at once."""
    v = _get_ver()
    cache.set(_VER_KEY, v + 1, None)  # None = no expiry for the version stamp

def dash_key(*parts: str) -> str:
    """Build a versioned cache key for dashboard/metrics."""
    v = _get_ver()
    safe = [str(p if p not in (None, "") else "-") for p in parts]
    return "dash:v{}:{}".format(v, ":".join(safe))
