# inventory/authz.py
from django.contrib.auth.models import Group
from django.http import HttpResponseForbidden

ADMIN = "Admin"
AGENT = "Agent"
AUDITOR = "Auditor"

def in_group(user, name: str) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=name).exists()

def is_admin(user): return in_group(user, ADMIN)
def is_agent(user): return in_group(user, AGENT) and not is_admin(user)
def is_auditor(user): return in_group(user, AUDITOR) and not is_admin(user)

def forbid_writes_for_auditors(view_func):
    def _wrapped(request, *args, **kwargs):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and is_auditor(request.user) and not is_admin(request.user):
            return HttpResponseForbidden("Auditors are read-only.")
        return view_func(request, *args, **kwargs)
    return _wrapped
