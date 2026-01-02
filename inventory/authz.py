from __future__ import annotations

from functools import wraps
from typing import Callable, Iterable, Optional

from django.contrib import messages
from django.shortcuts import redirect

from tenants.utils import get_active_business

from .business_kinds import BusinessKind
from .helpers_core import business_vertical, product_mode_from_business

VerticalKey = Optional[str]

_VERTICAL_TO_KIND = {
    "phones": BusinessKind.PHONES,
    "liquor": BusinessKind.LIQUOR,
    "pharmacy": BusinessKind.PHARMACY,
    "clothing": BusinessKind.CLOTHING,
    "gym": BusinessKind.GYM,
    "grocery": BusinessKind.GROCERY,
}


def _normalize_kind(value: BusinessKind | str | None) -> str:
    if isinstance(value, BusinessKind):
        return value.value
    return (value or "").strip().lower()


def resolve_business_kind(business=None, request=None) -> str:
    """
    Determine a business kind value (BusinessKind.<...>.value).
    Prefers Business.business_kind, falls back to vertical inference.
    """
    if business and getattr(business, "business_kind", None):
        return getattr(business, "business_kind")

    vertical: VerticalKey = None
    if request is not None:
        try:
            vertical = business_vertical(request)
        except Exception:
            vertical = None

    if not vertical and business is not None:
        try:
            vertical = product_mode_from_business(business)
        except Exception:
            vertical = None

    vertical = (vertical or BusinessKind.PHONES.value).strip().lower()
    mapped = _VERTICAL_TO_KIND.get(vertical)
    return mapped.value if isinstance(mapped, BusinessKind) else BusinessKind.PHONES.value


def require_business_kind(
    *allowed_kinds: Iterable[BusinessKind | str],
) -> Callable:
    """
    Decorator to ensure the active business matches one of the allowed kinds.
    Redirects to the inventory dispatcher when mismatched.
    """
    allowed_values = {_normalize_kind(kind) for kind in allowed_kinds if kind}
    allowed_values = {val for val in allowed_values if val}

    def _decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            business = get_active_business(request)
            if business is None:
                messages.info(request, "Select a business to continue.")
                return redirect("tenants:activate_mine")

            current_kind = _normalize_kind(resolve_business_kind(business, request))
            if allowed_values and current_kind not in allowed_values:
                allowed_text = ", ".join(sorted(allowed_values))
                messages.warning(
                    request,
                    f"This page is only available for {allowed_text or 'specific'} businesses.",
                )
                return redirect("inventory:inventory_dashboard")

            return view_func(request, *args, **kwargs)

        return _wrapped

    return _decorator


__all__ = ["require_business_kind", "resolve_business_kind"]
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


def is_admin(user):
    return in_group(user, ADMIN)


def is_agent(user):
    return in_group(user, AGENT) and not is_admin(user)


def is_auditor(user):
    return in_group(user, AUDITOR) and not is_admin(user)


def forbid_writes_for_auditors(view_func):
    def _wrapped(request, *args, **kwargs):
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and is_auditor(request.user)
            and not is_admin(request.user)
        ):
            return HttpResponseForbidden("Auditors are read-only.")
        return view_func(request, *args, **kwargs)

    return _wrapped
