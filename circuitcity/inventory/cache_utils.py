# inventory/cache_utils.py
from django.core.cache import cache

_KEY = "dash:ver"

def get_dashboard_cache_version() -> int:
    v = cache.get(_KEY)
    if not v:
        v = 1
        cache.set(_KEY, v, None)  # no TTL; bumping controls invalidation
    return int(v)

def bump_dashboard_cache_version() -> int:
    v = get_dashboard_cache_version() + 1
    cache.set(_KEY, v, None)
    return v
