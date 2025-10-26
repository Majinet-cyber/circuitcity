# cc/middleware/security.py
from django.shortcuts import redirect
from importlib import import_module

def _get_is_hq_admin():
    """
    Try to import your canonical is_hq_admin(user) check from HQ.
    Fallbacks keep HQ locked to staff/superusers if the helper is missing.
    """
    for mp in ("circuitcity.hq.permissions", "hq.permissions"):
        try:
            mod = import_module(mp)
            fn = getattr(mod, "is_hq_admin", None)
            if callable(fn):
                return fn
        except Exception:
            continue

    # Conservative fallback: staff OR superuser is considered HQ
    return lambda u: bool(getattr(u, "is_staff", False) or getattr(u, "is_superuser", False))

_is_hq_admin = _get_is_hq_admin()

# Paths HQ admins are allowed to hit without being bounced
_HQ_ALLOW_PREFIXES = (
    "/hq", "/admin", "/accounts", "/static", "/media", "/favicon.ico", "/robots.txt",
    "/healthz", "/healthz/", "/api/global-search/",
)

# Store/tenant UI entry points we want to keep HQ admins out of
_BLOCK_PREFIXES = ("/tenants", "/inventory", "/dashboard", "/sell", "/scan", "/stock")


class PreventHQFromClientUI:
    """
    HQ admins must NOT browse tenant/store UIs.
    If an HQ admin requests a blocked path, redirect to hq:home.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        path = (request.path or "").rstrip("/")

        # Not logged in / anonymous -> ignore
        if not user or not user.is_authenticated:
            return self.get_response(request)

        # Non-HQ users -> ignore (they are supposed to use store UI)
        if not _is_hq_admin(user):
            return self.get_response(request)

        # HQ admin: always allowed on HQ/admin/static/etc.
        for p in _HQ_ALLOW_PREFIXES:
            if path.startswith(p.rstrip("/")):
                return self.get_response(request)

        # Block classic store/tenant entry points
        for p in _BLOCK_PREFIXES:
            if path.startswith(p):
                return redirect("hq:home")

        return self.get_response(request)


