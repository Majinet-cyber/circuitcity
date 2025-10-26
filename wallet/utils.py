from typing import Any
from django.db.models import QuerySet

def scope_qs_to_user(qs: QuerySet, request: Any) -> QuerySet:
    """
    Superusers: full queryset.
    Others: restricted to active business (and store if model supports it).
    Works with models having business_id and/or store_id (or store__business_id).
    """
    user = getattr(request, "user", None)
    if getattr(user, "is_superuser", False):
        return qs

    biz = getattr(request, "business", None)
    biz_id = getattr(biz, "id", None)

    if biz_id is None:
        # No business context; safest is to return nothing for non-superusers
        return qs.none()

    Model = qs.model

    # Prefer direct business FK
    if hasattr(Model, "business_id"):
        qs = qs.filter(business_id=biz_id)
    elif hasattr(Model, "store") and hasattr(Model, "store_id"):
        # If model links to store, try store->business
        try:
            qs = qs.filter(store__business_id=biz_id)
        except Exception:
            pass

    # Optional store scoping (if you later add request.store or ?store=)
    store_id = getattr(getattr(request, "store", None), "id", None) or request.GET.get("store")
    if store_id and hasattr(Model, "store_id"):
        qs = qs.filter(store_id=store_id)

    return qs


