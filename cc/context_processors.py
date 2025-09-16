# circuitcity/cc/context_processors.py
from __future__ import annotations

def brand(request):
    """
    Provides `brand_name` and `active_business` to all templates.
    """
    biz = getattr(request, "business", None)
    name = getattr(biz, "name", None) or "Circuit City"
    return {
        "brand_name": name,
        "active_business": biz,
    }
