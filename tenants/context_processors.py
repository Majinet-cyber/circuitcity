# tenants/context_processors.py
from __future__ import annotations

from typing import Dict, Any

# Defensive/lazy imports so templates never crash if models/utilities are missing
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


def tenant_context(request) -> Dict[str, Any]:
    """
    Adds to every template:
      - business: the active Business (or None)
      - business_id: its id (or None)
      - PRODUCT_MODE: one of {'phones','pharmacy','liquor','grocery','generic'}
    Priority for PRODUCT_MODE:
      1) request.product_mode (set by middleware)
      2) ?mode= override (dev/testing)
      3) derived from active business
      4) session fallback
      5) 'generic'
    """
    biz = getattr(request, "business", None) or get_active_business(request)
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

    # Persist for consistency with middleware
    try:
        request.session[PRODUCT_MODE_SESSION_KEY] = mode
    except Exception:
        pass

    return {
        "business": biz,
        "business_id": bid,
        "PRODUCT_MODE": mode,
    }


