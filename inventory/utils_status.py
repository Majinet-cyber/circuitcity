# inventory/utils_status.py
from __future__ import annotations

from typing import Any, Dict, Iterable

from django.db import models
from django.utils import timezone


# ----------------------------
# Choice helpers (safe + robust)
# ----------------------------

def _get_field(model: type[models.Model], field: str):
    try:
        return model._meta.get_field(field)
    except Exception:
        return None

def _field_is_datetime(f) -> bool:
    try:
        return isinstance(f, models.DateTimeField)
    except Exception:
        return False

def _choice_value(model: type[models.Model], field: str, human_or_value: str, default: str) -> str:
    """
    Return the internal DB *value* for a human label OR value from a Choices field.
    Falls back to `default` if we can't resolve or the field/choices don't exist.
    """
    f = _get_field(model, field)
    if not f:
        return default

    choices: Iterable = getattr(f, "choices", None) or ()
    want = str(human_or_value).strip().lower()

    # Try both (value, label) match, case-insensitive.
    for val, label in choices:
        if str(val).strip().lower() == want:
            return val
        if str(label).strip().lower() == want:
            return val

    return default


def sold_choice_for(model: type[models.Model]) -> str:
    """
    What should `status` be when an item is SOLD?
    If there are no choices, "SOLD" is returned.
    """
    return _choice_value(model, "status", "SOLD", "SOLD")


def in_stock_choice_for(model: type[models.Model]) -> str:
    """
    What should `status` be when an item is IN_STOCK?
    """
    return _choice_value(model, "status", "IN_STOCK", "IN_STOCK")


# ----------------------------
# Canonical mutators / predicates
# ----------------------------

def _set_if_has(obj: Any, field: str, value: Any, updates: Dict[str, Any]) -> None:
    if hasattr(obj, field):
        try:
            setattr(obj, field, value)
            updates[field] = value
        except Exception:
            pass

def _first_existing_field(obj: Any, *names: str) -> str | None:
    for n in names:
        if hasattr(obj, n):
            return n
    return None


def mark_item_sold(item: models.Model, *, price=None, sold_date=None, user=None, loc_id=None) -> Dict[str, Any]:
    """
    Mutate a single InventoryItem into SOLD state using every relevant field
    that might exist. **This function SAVES the item** and returns a dict of
    the updates that were applied (field -> value).

    Optional kwargs:
      - price: set selling/sale price if your schema supports it
      - sold_date: datetime/date to persist (defaults to now)
      - user: set sold_by/agent if available (doesn't overwrite if already set)
      - loc_id: set current_location_id/location_id when provided
    """
    Model = type(item)
    updates: Dict[str, Any] = {}

    # ---------- Status/flags ----------
    sold_val = sold_choice_for(Model)
    _set_if_has(item, "status", sold_val, updates)
    _set_if_has(item, "is_sold", True, updates)

    # Some schemas use "in_stock" or availability flags
    if hasattr(item, "in_stock"):
        try:
            item.in_stock = False
            updates["in_stock"] = False
        except Exception:
            pass
    if hasattr(item, "available"):
        try:
            item.available = False
            updates["available"] = False
        except Exception:
            pass
    if hasattr(item, "availability"):
        try:
            item.availability = False
            updates["availability"] = False
        except Exception:
            pass

    # ---------- Dates ----------
    now = timezone.now()
    when = sold_date or getattr(item, "sold_at", None) or now

    # If the model's sold_at is a DateField, store date; if DateTimeField, store aware datetime
    sold_at_field = _get_field(Model, "sold_at")
    if sold_at_field:
        if _field_is_datetime(sold_at_field):
            # ensure aware datetime
            if timezone.is_naive(when):
                when = timezone.make_aware(when, timezone.get_current_timezone()) if hasattr(when, "tzinfo") else now
            _set_if_has(item, "sold_at", when, updates)
        else:
            # DateField
            try:
                _set_if_has(item, "sold_at", when.date() if hasattr(when, "date") else when, updates)
            except Exception:
                pass

    # Common "updated_at" timestamp (best-effort)
    if hasattr(item, "updated_at"):
        try:
            item.updated_at = now
            updates["updated_at"] = now
        except Exception:
            pass

    # ---------- Price ----------
    if price is not None:
        price_fields = ("selling_price", "sale_price", "price", "sell_price", "order_price")
        pf = _first_existing_field(item, *price_fields)
        if pf:
            _set_if_has(item, pf, price, updates)

    # ---------- Agent / ownership ----------
    if user:
        for agent_field in ("sold_by", "agent", "assigned_agent", "assigned_to", "assignee", "owner", "user", "created_by", "added_by"):
            if hasattr(item, agent_field) and getattr(item, agent_field, None) in (None, "", 0):
                try:
                    setattr(item, agent_field, user)
                    updates[f"{agent_field}_id"] = getattr(user, "id", None)
                    break
                except Exception:
                    pass

    # ---------- Location ----------
    if loc_id is not None:
        # Prefer the field your UI reads (current_location_id), fallback to location_id
        if hasattr(item, "current_location_id"):
            try:
                item.current_location_id = int(loc_id)
                updates["current_location_id"] = int(loc_id)
            except Exception:
                pass
        elif hasattr(item, "location_id"):
            try:
                item.location_id = int(loc_id)
                updates["location_id"] = int(loc_id)
            except Exception:
                pass

    # ---------- Persist (tight update_fields) ----------
    update_fields = sorted(updates.keys())
    try:
        if update_fields:
            item.save(update_fields=update_fields)
        else:
            # No discovered fields -> still try save (noop if nothing changed)
            item.save()
    except Exception:
        # As a last resort, try a full save
        try:
            item.save()
        except Exception:
            pass

    return updates


def is_item_sold(obj: Any) -> bool:
    """
    Canonical read predicate:
      - status equals SOLD choice
      - or is_sold True
      - or in_stock/available/availability indicate "not available"
      - or sold_at set
    """
    try:
        # 1) status
        if hasattr(obj, "status"):
            sval = str(getattr(obj, "status"))
            if sval == str(sold_choice_for(type(obj))):
                return True
            # be tolerant with common variants if choices aren't configured
            if sval.strip().lower().startswith("sold"):
                return True

        # 2) booleans
        if getattr(obj, "is_sold", False):
            return True
        if hasattr(obj, "in_stock") and obj.in_stock is False:
            return True
        if hasattr(obj, "available") and obj.available is False:
            return True
        if hasattr(obj, "availability") and obj.availability is False:
            return True

        # 3) date/datetime
        if getattr(obj, "sold_at", None):
            return True
    except Exception:
        pass
    return False
