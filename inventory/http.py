# inventory/utils/http.py (or at top of views.py)
def _int(request, key, default, min_=1, max_=200):
    try:
        v = int(request.GET.get(key, default))
        return max(min_, min(v, max_))
    except (TypeError, ValueError):
        return default

def _choice(request, key, allowed, default):
    v = (request.GET.get(key) or "").lower()
    return v if v in allowed else default
