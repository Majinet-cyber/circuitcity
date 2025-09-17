# circuitcity/tenants/decorators.py
from django.shortcuts import redirect
from functools import wraps

def require_business(view):
    @wraps(view)
    def _wrap(request, *a, **kw):
        if not getattr(request, "business", None):
            return redirect("tenants:setup")  # or your business chooser
        return view(request, *a, **kw)
    return _wrap
