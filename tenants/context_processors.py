# tenants/context_processors.py
from __future__ import annotations

from typing import Dict, Any

# Defensive/lazy imports so templates never crash if utilities are missing
try:
    from tenants.utils import get_active_business
except Exception:  # pragma: no cover
    def get_active_business(_request):  # type: ignore
        return None


# Keep aliases in sync with TenantResolutionMiddleware
_VERTICAL_ALIASES = {
    # Phones / Electronics
    "phones & electronics": "phones",
    "electronics": "phones",
    "phone": "phones",
    "phones": "phones",
    "mobile": "phones",
    "mobiles": "phones",

    # Pharmacy
    "pharmacy": "pharmacy",
    "chemist": "pharmacy",
    "medicine": "pharmacy",
    "drugstore": "pharmacy",

    # Liquor
    "liquor": "liquor",
    "bar": "liquor",
    "alcohol": "liquor",
    "pub": "liquor",
    "bottle-store": "liquor",
    "bottle store": "liquor",

    # Grocery / Supermarket / Retail
    "grocery": "grocery",
    "groceries": "grocery",
    "supermarket": "grocery",
    "supermarket & groceries": "grocery",
    "retail": "grocery",
}

PRODUCT_MODE_SESSION_KEY = "product_mode"


def _normalize_vertical(v: str | None) -> str:
    key = (v or "").strip().lower()
    return _VERTICAL_ALIASES.get(key, "generic")


def _derive_mode_from_business(biz) -> str:
    if not biz:
        return "generic"
    # Check a few common attributes (plus their display())
    for attr in ("vertical", "category", "industry", "type", "kind", "sector", "business_type"):
        val = getattr(biz, attr, None)
        if isinstance(val, str) and val.strip():
            return _normalize_vertical(val)
        disp = getattr(biz, f"get_{attr}_display", None)
        if callable(disp):
            try:
                dv = disp()
                if isinstance(dv, str) and dv.strip():
                    return _normalize_vertical(dv)
            except Exception:
                pass
    return "generic"


def _resolve_business(request):
    """
    Prefer request.business set by middleware; fall back to utils helper.
    Never raises.
    """
    biz = getattr(request, "business", None)
    if biz is not None:
        return biz
    try:
        return get_active_business(request)
    except Exception:
        return None


def active_business(request) -> Dict[str, Any]:
    """
    Minimal context processor that matches settings reference:
    exposes both 'active_business' and 'active_business_id' for templates.
    Kept small on purpose; product mode is handled by tenant_context().
    """
    biz = _resolve_business(request)
    bid = getattr(biz, "pk", None) if biz is not None else None
    return {
        "active_business": biz,
        "active_business_id": bid,
    }


def tenant_context(request) -> Dict[str, Any]:
    """
    Adds to every template:
      - business / business_id (new keys)
      - active_business / active_business_id (legacy-friendly mirror)
      - PRODUCT_MODE ∈ {'phones','pharmacy','liquor','grocery','generic'}

    Priority for PRODUCT_MODE:
      1) request.product_mode (set by middleware)
      2) ?mode= override (dev/testing)
      3) derived from active business
      4) session fallback
      5) 'generic'
    """
    biz = _resolve_business(request)
    bid = getattr(request, "business_id", None) or (getattr(biz, "pk", None) if biz else None)

    # 1) middleware (single source of truth if present)
    mode = getattr(request, "product_mode", None)

    # 2) explicit override (useful in dev)
    if not mode:
        override = request.GET.get("mode")
        if override:
            mode = _normalize_vertical(override)

    # 3) derive from business
    if not mode or mode == "generic":
        mode = _derive_mode_from_business(biz)

    # 4) session fallback
    if mode == "generic":
        try:
            sess_mode = request.session.get(PRODUCT_MODE_SESSION_KEY)
            if isinstance(sess_mode, str) and sess_mode:
                mode = _normalize_vertical(sess_mode)
        except Exception:
            pass

    # 5) final default
    if not mode:
        mode = "generic"

    # Persist for consistency with middleware (best effort)
    try:
        request.session[PRODUCT_MODE_SESSION_KEY] = mode
    except Exception:
        pass

    # Expose both new and legacy keys so no template breaks
    return {
        # New names
        "business": biz,
        "business_id": bid,
        "PRODUCT_MODE": mode,

        # Legacy-friendly mirrors
        "active_business": biz,
        "active_business_id": bid,
    }


__all__ = ["active_business", "tenant_context"]
