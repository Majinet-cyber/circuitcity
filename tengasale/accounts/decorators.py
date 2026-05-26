from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render

from .utils import is_hq, is_merchant, is_underwriter, role_redirect_url


def role_required(test_func, sensitive=False):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if test_func(request.user):
                return view_func(request, *args, **kwargs)
            return render(
                request,
                "accounts/role_forbidden.html",
                {"dashboard_url": role_redirect_url(request.user)},
                status=403,
            )

        return wrapped

    return decorator


def merchant_required(view_func=None, *, sensitive=False):
    decorator = role_required(is_merchant, sensitive=sensitive)
    return decorator(view_func) if view_func else decorator


def underwriter_required(view_func=None, *, sensitive=False):
    decorator = role_required(is_underwriter, sensitive=sensitive)
    return decorator(view_func) if view_func else decorator


def hq_required(view_func=None, *, sensitive=False):
    decorator = role_required(is_hq, sensitive=sensitive)
    return decorator(view_func) if view_func else decorator
