from functools import wraps
from django.http import HttpResponseForbidden

def user_in_group(user, name: str) -> bool:
    return bool(user and user.is_authenticated and user.groups.filter(name__iexact=name).exists())

def is_manager(u):  # NOT staff
    return bool(u and u.is_authenticated and (user_in_group(u, "Manager")))

def is_agent(u):
    return bool(u and u.is_authenticated and (user_in_group(u, "Agent")))

def is_admin(u):  # internal app admin (optionally same as staff)
    return bool(u and u.is_authenticated and (u.is_staff or user_in_group(u, "Admin")))

def require_role(*allowed):
    def deco(view):
        @wraps(view)
        def _w(request, *a, **kw):
            u = request.user
            role_ok = any([
                ("Manager" in allowed and is_manager(u)),
                ("Agent" in allowed and is_agent(u)),
                ("Admin" in allowed and is_admin(u)),
            ])
            if not role_ok:
                return HttpResponseForbidden("You do not have permission.")
            return view(request, *a, **kw)
        return _w
    return deco


