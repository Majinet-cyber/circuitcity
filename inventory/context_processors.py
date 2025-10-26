# inventory/context_processor.py
from __future__ import annotations

from typing import Dict, Tuple, Any
from django.http import HttpRequest

# Import the single-source-of-truth helpers
from .helpers import (
    get_active_business,
    business_vertical,
    add_product_url_for_request,
)


def resolve_active_context(request: HttpRequest) -> Tuple[object | None, Dict[str, Any]]:
    """
    Central place to compute commonly needed, stable UI context.
    Never raise: always returns (business, ctx_dict).
    """
    biz = None
    try:
        biz = get_active_business(request)
    except Exception:
        biz = None

    try:
        vertical = business_vertical(request)
    except Exception:
        vertical = "phones"  # sensible default for your app

    try:
        add_product_url = add_product_url_for_request(request)
    except Exception:
        add_product_url = "/inventory/products/new/generic/"

    ctx: Dict[str, Any] = {
        # Business + vertical
        "ACTIVE_BUSINESS": biz,
        "ACTIVE_BUSINESS_ID": getattr(biz, "id", None) if biz else None,
        "BUSINESS_VERTICAL": vertical,

        # One canonical target for all â€œAdd Productâ€ buttons
        "ADD_PRODUCT_URL": add_product_url,
    }
    return biz, ctx


def active_scope_ctx(request: HttpRequest) -> Dict[str, Any]:
    """
    Context processor entrypoint.
    Returns a compact, stable set of values for templates.
    """
    try:
        _, ctx = resolve_active_context(request)
        return ctx
    except Exception:
        # Never break template rendering
        return {
            "ACTIVE_BUSINESS": None,
            "ACTIVE_BUSINESS_ID": None,
            "BUSINESS_VERTICAL": "phones",
            "ADD_PRODUCT_URL": "/inventory/products/new/generic/",
        }


