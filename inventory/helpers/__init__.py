# inventory/helpers/__init__.py
from __future__ import annotations
from typing import Dict
from django.http import HttpRequest

def default_location_for_request(request: HttpRequest):
    """
    Return the user's default store/location object or None.
    Replace with your real lookup. Safe no-op by default.
    """
    try:
        from inventory.models import Location  # type: ignore
        # Example: first location in the active business
        biz = getattr(request, "business", None)
        if biz:
            qs = Location.objects.filter(business=biz).order_by("id")
            return qs.first()
        return Location.objects.order_by("id").first()
    except Exception:
        return None

def _attach_business_kwargs(model, business_id) -> Dict[str, object]:
    """Return kwargs to set the active business on creates."""
    try:
        if business_id and any(f.name == "business" for f in model._meta.get_fields()):
            return {"business_id": business_id}
    except Exception:
        pass
    return {}

def _biz_filter_kwargs(model, business_id) -> Dict[str, object]:
    """Return kwargs to scope queries by business."""
    try:
        if business_id and any(f.name == "business" for f in model._meta.get_fields()):
            return {"business_id": business_id}
    except Exception:
        pass
    return {}

def _limit_form_querysets(form, request: HttpRequest) -> None:
    """Clamp form querysets (Products, Locations) to active business."""
    biz = getattr(request, "business", None)
    biz_id = getattr(biz, "id", None)
    if not biz_id:
        return
    try:
        if "product" in form.fields:
            qs = getattr(form.fields["product"], "queryset", None)
            if qs is not None and hasattr(qs.model, "_meta"):
                if any(f.name == "business" for f in qs.model._meta.get_fields()):
                    form.fields["product"].queryset = qs.filter(business_id=biz_id)
    except Exception:
        pass
    try:
        for name in ("location", "current_location", "store", "branch"):
            if name in form.fields:
                qs = getattr(form.fields[name], "queryset", None)
                if qs is not None and hasattr(qs.model, "_meta"):
                    if any(f.name == "business" for f in qs.model._meta.get_fields()):
                        form.fields[name].queryset = qs.filter(business_id=biz_id)
    except Exception:
        pass

def _obj_belongs_to_active_business(obj, request: HttpRequest) -> bool:
    """True if obj.business == active business (or model has no business field)."""
    try:
        biz = getattr(request, "business", None)
        if not biz:
            return True
        obiz = getattr(obj, "business", None)
        return (obiz is None) or (getattr(obiz, "id", None) == getattr(biz, "id", None))
    except Exception:
        return True
