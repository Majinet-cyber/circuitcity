# inventory/middleware.py
from django.conf import settings
from django.http import HttpResponseForbidden

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class AuditorReadOnlyMiddleware:
    """
    Enforce read-only for auditors on mutating requests, without breaking admin.

    Rules:
    - If FEATURES['ROLE_ENFORCEMENT'] is false -> no enforcement.
    - Always allow Django admin URLs (/admin/...) so staff can use the admin UI.
    - Always allow SAFE_METHODS (GET/HEAD/OPTIONS/TRACE).
    - If user is not authenticated -> let normal auth/CSRF handle it.
    - Superusers are never blocked.
    - A user is considered an 'auditor' if any of:
        * Member of group named 'Auditors' (case-insensitive)
        * Has custom perm 'inventory.read_only' (optional)
        * user.agentprofile.role == 'AUDITOR' (if AgentProfile exists)
    - If auditor attempts POST/PUT/PATCH/DELETE -> 403.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 0) Feature flag gate
        if not getattr(settings, "FEATURES", {}).get("ROLE_ENFORCEMENT", True):
            return self.get_response(request)

        path = request.path_info or request.path

        # 1) Never intercept Django admin actions
        if path.startswith("/admin/"):
            return self.get_response(request)

        # 2) Allow safe methods
        if request.method in SAFE_METHODS:
            return self.get_response(request)

        user = getattr(request, "user", None)

        # 3) If anonymous, let auth/CSRF handle it
        if not getattr(user, "is_authenticated", False):
            return self.get_response(request)

        # 4) Superusers are fully allowed
        if getattr(user, "is_superuser", False):
            return self.get_response(request)

        # 5) Determine if this user is an auditor
        is_auditor = False

        # Group: "Auditors"
        try:
            if user.groups.filter(name__iexact="Auditors").exists():
                is_auditor = True
        except Exception:
            pass

        # Optional custom perm
        try:
            if user.has_perm("inventory.read_only"):
                is_auditor = True
        except Exception:
            pass

        # Optional AgentProfile.role == "AUDITOR"
        try:
            role = getattr(getattr(user, "agentprofile", None), "role", "")
            if isinstance(role, str) and role.strip().upper() == "AUDITOR":
                is_auditor = True
        except Exception:
            pass

        # 6) Block mutating requests from auditors
        if is_auditor:
            return HttpResponseForbidden("Auditors are read-only")

        # Otherwise proceed
        return self.get_response(request)
