# inventory/utils_status.py
from django.db import models
from django.utils import timezone

def _choice_value(model: type[models.Model], field: str, human: str, default: str):
    """
    Return the internal DB value for a human label from a Choices field.
    Falls back to `default` if we can't resolve.
    """
    f = model._meta.get_field(field)
    choices = getattr(f, "choices", None) or ()
    for val, label in choices:
        if str(label).lower() == str(human).lower():
            return val
    return default

def sold_choice_for(model):
    """
    What should `status` be when an item is SOLD?
    """
    # Adjust the last argument to your usual default if not in choices
    return _choice_value(model, "status", "SOLD", "SOLD")

def in_stock_choice_for(model):
    """
    What should `status` be when an item is IN_STOCK?
    """
    return _choice_value(model, "status", "IN_STOCK", "IN_STOCK")

def mark_item_sold(item, *, price=None, sold_date=None, user=None, loc_id=None):
    """
    Mutate a single InventoryItem into SOLD state using every relevant field
    that might exist. Returns a dict of updates actually applied.
    """
    from .models import InventoryItem  # local import in case of app wiring

    updates = {}
    sold_val = sold_choice_for(type(item))
    today = sold_date or getattr(item, "sold_at", None) or timezone.localdate()

    # Primary flags
    if hasattr(item, "status"):
        item.status = sold_val
        updates["status"] = item.status

    if hasattr(item, "is_sold"):
        item.is_sold = True
        updates["is_sold"] = True

    if hasattr(item, "in_stock"):
        try:
            item.in_stock = False
            updates["in_stock"] = False
        except Exception:
            pass

    # Dates/people/price
    if hasattr(item, "sold_at"):
        item.sold_at = today
        updates["sold_at"] = item.sold_at

    if price is not None and hasattr(item, "selling_price"):
        item.selling_price = price
        updates["selling_price"] = item.selling_price

    if user and hasattr(item, "sold_by") and getattr(item, "sold_by", None) is None:
        try:
            item.sold_by = user
            updates["sold_by_id"] = user.id
        except Exception:
            pass

    # Location
    if loc_id is not None:
        if hasattr(item, "current_location_id"):
            item.current_location_id = loc_id
            updates["current_location_id"] = loc_id
        elif hasattr(item, "location_id"):
            item.location_id = loc_id
            updates["location_id"] = loc_id

    return updates

def is_item_sold(obj) -> bool:
    """
    Canonical read predicate used everywhere.
    """
    try:
        # Status choice
        if hasattr(obj, "status"):
            if str(getattr(obj, "status")) == str(sold_choice_for(type(obj))):
                return True
        # Booleans
        if getattr(obj, "is_sold", False):
            return True
        if hasattr(obj, "in_stock") and obj.in_stock is False:
            return True
        # Date as last resort
        if getattr(obj, "sold_at", None):
            return True
    except Exception:
        pass
    return False


