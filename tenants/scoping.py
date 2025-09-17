# tenants/scoping.py
from __future__ import annotations
from typing import Optional
from django.db.models import QuerySet

def apply_tenant_scope(qs: QuerySet, business: Optional[object]) -> QuerySet:
    """
    Best-effort filter:
      - Model has `business`           -> .filter(business=biz)
      - Model has `store` w/ business  -> .filter(store__business=biz)
      - Model has `warehouse` w/ biz   -> .filter(warehouse__business=biz)
      - Model has `created_by` and Memberships -> .filter(created_by__memberships__business=biz)
    If none match, returns qs unchanged (so it won't explode).
    """
    if not business:
        return qs

    model = qs.model
    # direct FK
    if hasattr(model, "business_id"):
        return qs.filter(business=business)

    # common indirect pivots
    if hasattr(model, "store_id"):
        try:
            return qs.filter(store__business=business)
        except Exception:
            pass

    if hasattr(model, "warehouse_id"):
        try:
            return qs.filter(warehouse__business=business)
        except Exception:
            pass

    if hasattr(model, "created_by_id"):
        try:
            # Membership model: user -> memberships -> business
            return qs.filter(created_by__memberships__business=business)
        except Exception:
            pass

    return qs
