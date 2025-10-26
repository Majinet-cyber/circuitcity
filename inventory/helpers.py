# inventory/helpers.py
from __future__ import annotations

from typing import Optional, Dict, Iterable
from django.urls import reverse, NoReverseMatch

# ------------------------------------------------------------------
# Canonical vertical keys
# ------------------------------------------------------------------
PHONES   = "phones"
PHARMACY = "pharmacy"
CLOTHING = "clothing"
LIQUOR   = "liquor"
GROCERY  = "grocery"
GENERIC  = "generic"

# Synonyms / legacy labels -> canonical keys
_ALIASES: Dict[str, str] = {
    # phones / electronics
    "phone": PHONES, "phones": PHONES, "mobile": PHONES, "mobiles": PHONES,
    "electronics": PHONES, "phones & electronics": PHONES, "merch": PHONES,
    # pharmacy
    "pharmacy": PHARMACY, "chemist": PHARMACY, "medicine": PHARMACY, "drugstore": PHARMACY,
    # clothing / fashion
    "clothing": CLOTHING, "clothes": CLOTHING, "apparel": CLOTHING,
    "fashion": CLOTHING, "fashion & clothing": CLOTHING,
    # liquor
    "liquor": LIQUOR, "alcohol": LIQUOR, "bar": LIQUOR, "bottle-store": LIQUOR, "bottle store": LIQUOR,
    # grocery / retail
    "grocery": GROCERY, "groceries": GROCERY, "supermarket": GROCERY, "retail": GROCERY,
    "supermarket & groceries": GROCERY,
}

# Which fields on Business we will probe to determine vertical
_BIZ_FIELDS: tuple[str, ...] = (
    "template_key", "vertical", "category", "industry", "type", "kind", "sector", "business_type"
)

# Session keys that might carry a business id or a vertical override
_SESS_BIZ_IDS = ("active_business_id", "business_id", "tenant_id", "current_business_id")
_SESS_VERTICAL_KEY = "active_business_vertical"


# ------------------------------------------------------------------
# Internal utils
# ------------------------------------------------------------------
def _norm_label(v: Optional[str]) -> str:
    """
    Normalize any string label to a canonical vertical key.
    Default to PHONES because the app is phones-first and this
    avoids landing users on the generic form.
    """
    key = (v or "").strip().lower()
    return _ALIASES.get(key, PHONES)

def _try_reverse(names: Iterable[str]) -> str:
    """
    Try a list of url names and return the first that reverses successfully.
    Falls back to the generic add-product page.
    """
    for name in names:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    try:
        return reverse("inventory:product_create")  # legacy generic
    except NoReverseMatch:
        return "/inventory/products/new/generic/"


# ------------------------------------------------------------------
# Public: business / request resolvers
# ------------------------------------------------------------------
def get_active_business(request):
    """
    Best-effort way to get the active Business from the request.
    Looks on request/user/tenant; falls back to session id lookup.
    """
    biz = (
        getattr(request, "business", None)
        or getattr(request, "active_business", None)
        or getattr(getattr(request, "user", None), "business", None)
        or getattr(getattr(request, "tenant", None), "business", None)
    )
    if biz:
        return biz

    # Optional session id fallback
    bid = None
    try:
        sess = getattr(request, "session", {}) or {}
        for k in _SESS_BIZ_IDS:
            v = sess.get(k)
            if v:
                bid = v
                break
    except Exception:
        bid = None

    if bid:
        try:
            from tenants.models import Business
            return Business.objects.filter(id=bid).first()
        except Exception:
            return None

    return None


def normalize_category(raw: Optional[str]) -> str:
    """
    Backwards-compatible alias that returns the normalized vertical key.
    """
    return _norm_label(raw)


def product_mode_from_business(business) -> str:
    """
    Inspect multiple Business attributes to infer the active vertical.
    Defaults to PHONES (phones-first product).
    """
    if not business:
        return PHONES

    for field in _BIZ_FIELDS:
        # direct value
        try:
            val = getattr(business, field, None)
            if isinstance(val, str) and val.strip():
                return _norm_label(val)
        except Exception:
            pass

        # support choice fields with get_FOO_display()
        disp_fn = getattr(business, f"get_{field}_display", None)
        if callable(disp_fn):
            try:
                disp = disp_fn()
                if isinstance(disp, str) and disp.strip():
                    return _norm_label(disp)
            except Exception:
                pass

    return PHONES


def business_vertical(request) -> str:
    """
    Single source of truth for vertical from a request:
      1) Session override (active_business_vertical)
      2) Active business fields
      3) Default PHONES
    """
    try:
        sess = getattr(request, "session", {}) or {}
        sess_v = sess.get(_SESS_VERTICAL_KEY)
        if isinstance(sess_v, str) and sess_v.strip():
            return _norm_label(sess_v)
    except Exception:
        pass

    biz = get_active_business(request)
    return product_mode_from_business(biz)


def is_phone_business(obj) -> bool:
    """
    Accepts a request or a Business object and returns True if vertical is PHONES.
    """
    if hasattr(obj, "META"):  # request-like
        return business_vertical(obj) == PHONES
    return product_mode_from_business(obj) == PHONES


# ------------------------------------------------------------------
# Public: URL helpers (single truth)
# ------------------------------------------------------------------
def product_new_url_for_business(business) -> str:
    """
    Return the correct 'Add Product' URL for a given business vertical.
    Prefers polished v2 pages, with graceful fallbacks if a route is missing.
    """
    mode = product_mode_from_business(business)

    if mode == PHONES:
        return _try_reverse(("inventory:merch_product_new",))  # phones v2 router

    if mode == PHARMACY:
        # Add your pharmacy v2 route here when available
        return _try_reverse(("inventory:pharmacy_product_new",))

    if mode == CLOTHING:
        return _try_reverse((
            "inventory:clothing_product_new_v2",  # v2 (preferred)
            "inventory:clothing_product_new",     # legacy
        ))

    if mode == LIQUOR:
        return _try_reverse((
            "inventory:liquor_product_new_v2",    # v2 (preferred)
            "inventory:liquor_product_new",       # legacy
        ))

    if mode == GROCERY:
        return _try_reverse(("inventory:product_create_grocery",))

    # generic / unknown
    return _try_reverse(("inventory:product_create",))


def add_product_url_for_request(request) -> str:
    """
    Request-aware Add Product target (used by product_new_entry view or templates).
    """
    mode = business_vertical(request)

    if mode == CLOTHING:
        return _try_reverse(("inventory:clothing_product_new_v2",))
    if mode == LIQUOR:
        return _try_reverse(("inventory:liquor_product_new_v2",))
    if mode == PHARMACY:
        return _try_reverse(("inventory:pharmacy_product_new",))

    # phones default
    return _try_reverse(("inventory:merch_product_new",))


def add_product_entry_url() -> str:
    """
    Canonical dispatcher URL used in templates:
        <a href="{% url 'inventory:product_new_entry' %}">Add Product</a>
    """
    try:
        return reverse("inventory:product_new_entry")
    except NoReverseMatch:
        return "/inventory/products/new/"


