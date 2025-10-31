# inventory/constants.py
from __future__ import annotations

from typing import Type, Optional
from django.db import models
from django.db.models import Q

# Optional default model so callers can omit the class
try:
    from .models import InventoryItem as _DefaultItem
except Exception:  # pragma: no cover
    _DefaultItem = None  # type: ignore

# Choice resolvers (fallbacks are safe if helpers aren't present)
try:
    from .utils_status import sold_choice_for, in_stock_choice_for
except Exception:  # pragma: no cover
    def sold_choice_for(model): return "SOLD"        # type: ignore
    def in_stock_choice_for(model): return "IN_STOCK"  # type: ignore


def _has(model: Optional[Type[models.Model]], field: str) -> bool:
    if model is None:
        return False
    try:
        model._meta.get_field(field)
        return True
    except Exception:
        return False


# ---------------------------------------------
# Canonical stock predicates (InventoryItem-first)
# ---------------------------------------------
def SOLD_Q(model: Optional[Type[models.Model]] = None) -> Q:
    """
    'Sold' is true if the row is explicitly marked SOLD or has a sale timestamp.
    We intentionally DO NOT treat archived (is_active=False) as 'sold'.
    """
    m = model or _DefaultItem
    q = Q()
    if _has(m, "status"):
        q |= Q(status=sold_choice_for(m))
    if _has(m, "sold_at"):
        q |= Q(sold_at__isnull=False)
    return q


def IN_STOCK_Q(model: Optional[Type[models.Model]] = None) -> Q:
    """
    'In stock' is active inventory available for sale:
      - status == IN_STOCK (when field exists)
      - sold_at IS NULL (when field exists)
      - is_active == True (when field exists)
    """
    m = model or _DefaultItem
    q = Q()
    if _has(m, "status"):
        q &= Q(status=in_stock_choice_for(m))
    if _has(m, "sold_at"):
        q &= Q(sold_at__isnull=True)
    if _has(m, "is_active"):
        q &= Q(is_active=True)
    return q
