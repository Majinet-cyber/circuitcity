from __future__ import annotations
from typing import Optional

# Allowed template keys (match your template filenames suffixes)
ALLOWED_KEYS = {
    "phones": "phones",
    "clothing": "clothing",
    "pharmacy": "pharmacy",
    "liquor": "liquor",
    "generic": "generic",  # optional fallback if you have one
}

# Map a business â€œindustryâ€ to a template key
INDUSTRY_TO_KEY = {
    "phones": "phones",
    "electronics": "phones",
    "clothing": "clothing",
    "fashion": "clothing",
    "pharmacy": "pharmacy",
    "liquor": "liquor",
}

DEFAULT_KEY = "phones"   # preserves current behaviour for everyone else

def _coerce_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().lower()
    return ALLOWED_KEYS.get(v)  # returns None if not in allowed list

def _guess_from_name(name: str) -> Optional[str]:
    n = name.lower()
    if any(w in n for w in ("boutique", "apparel", "fashion", "cloth", "wear")):
        return "clothing"
    if any(w in n for w in ("pharma", "drug", "chemist")):
        return "pharmacy"
    if any(w in n for w in ("liquor", "bar", "bottle")):
        return "liquor"
    if any(w in n for w in ("phone", "mobile", "electronics", "imei")):
        return "phones"
    return None

def resolve_template_key(request) -> str:
    """
    Order of precedence (first hit wins):
      1) ?template=... (handy for quick testing; stored into session)
      2) session["template_key"]
      3) business.template_key (custom attr you can set in admin/shell)
      4) business.industry / business.category (common field names)
      5) guess from business.name (keyword heuristic)
      6) DEFAULT_KEY
    """
    # 1) URL override for quick checks (safe; no deploys needed)
    q = _coerce_key(request.GET.get("template"))
    if q:
        request.session["template_key"] = q
        return q

    # 2) Session sticky
    q = _coerce_key(request.session.get("template_key"))
    if q:
        return q

    # 3,4) Business-derived
    biz = getattr(request, "business", None) or getattr(request, "active_business", None)
    if biz:
        for attr in ("template_key", "industry", "category", "sector"):
            q = _coerce_key(getattr(biz, attr, None))
            if q:
                return q
        # 5) Heuristic from name
        name = getattr(biz, "name", "") or getattr(biz, "title", "")
        q = _guess_from_name(name) or DEFAULT_KEY
        return q

    # 6) Total fallback
    return DEFAULT_KEY

def tpl(page: str, key: str) -> str:
    """
    Build the template path for a page.
      page: 'add_product', 'list_products', 'edit_product', etc.
      key: resolved template key (e.g., 'clothing')
    Your filenames already follow this style: add_product_clothing.html etc.
    """
    return f"inventory/{page}_{key}.html"


