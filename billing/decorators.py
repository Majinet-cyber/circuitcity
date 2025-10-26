from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse

def requires_active_subscription(view):
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        tenant = getattr(request, 'tenant', None)
        sub = getattr(tenant, 'subscription', None) if tenant else None
        if not sub or not sub.is_active:
            return redirect(reverse('billing_paywall'))
        return view(request, *args, **kwargs)
    return _wrapped


