from django.core.exceptions import PermissionDenied

def forbid_superuser_in_tenant(view_func):
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            raise PermissionDenied("Superusers cannot access tenant dashboards.")
        return view_func(request, *args, **kwargs)
    return _wrapped


