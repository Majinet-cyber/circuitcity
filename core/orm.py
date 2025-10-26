# core/orm.py
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence, Tuple, Type, TypeVar

from django.db import models
from django.core.exceptions import FieldDoesNotExist

T = TypeVar("T", bound=models.Model)


# -------------------------------------------------------------------
# Safe attribute access
# -------------------------------------------------------------------
def safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


# -------------------------------------------------------------------
# Model metadata helpers
# -------------------------------------------------------------------
def get_field(model: Type[T], name: str) -> Optional[models.Field]:
    """Return a model field or None if it doesn't exist."""
    try:
        return model._meta.get_field(name)  # type: ignore[attr-defined]
    except (FieldDoesNotExist, Exception):
        return None


def model_has_field(model: Type[T], name: str) -> bool:
    """Fast check if a model has a given field name."""
    return get_field(model, name) is not None


def model_field_names(model: Type[T]) -> set[str]:
    """All concrete field names on a model."""
    try:
        return {
            f.name
            for f in model._meta.get_fields()  # type: ignore[attr-defined]
            if hasattr(f, "attname") or getattr(f, "concrete", False)
        }
    except Exception:
        return set()


def get_fk_model(model: Type[T], field_name: str) -> Optional[Type[models.Model]]:
    """
    Return the related model class for a FK/OneToOne field,
    or None if not resolvable.
    """
    f = get_field(model, field_name)
    try:
        rel = getattr(f, "remote_field", None)
        return getattr(rel, "model", None)
    except Exception:
        return None


# -------------------------------------------------------------------
# Business/tenant helpers (non-breaking)
# -------------------------------------------------------------------
def biz_field_name(model: Type[T]) -> Optional[str]:
    """
    Return the field name to use for tenant filtering on this model.
    Preference: 'business_id' (fast), then 'business' (FK),
    otherwise None if the model isn't tenant-scoped.
    """
    if model_has_field(model, "business_id"):
        return "business_id"
    if model_has_field(model, "business"):
        # We still filter by 'business_id' for consistency/perf
        return "business_id"
    return None


def biz_filter_kwargs(model: Type[T], business_id: Any) -> Dict[str, Any]:
    """
    Build the correct kwargs for filtering a queryset by business.
    Returns {} if the model is not tenant-scoped.
    """
    field = biz_field_name(model)
    if field and business_id is not None:
        return {field: business_id}
    return {}


def attach_business_kwargs(model: Type[T], business_or_id: Any) -> Dict[str, Any]:
    """
    Build kwargs suitable for object creation with a bound business.
    Accepts a Business instance or an id. Returns {} if model is not tenant-scoped.
    """
    field = biz_field_name(model)
    if not field or business_or_id is None:
        return {}
    bid = getattr(business_or_id, "id", business_or_id)
    return {field: bid}


def obj_belongs_to_business(obj: Any, business_id: Any) -> bool:
    """
    Best-effort check that an object is attached to the given business id.
    If the object is not tenant-scoped, returns True (non-blocking).
    """
    try:
        if hasattr(obj, "business_id"):
            return obj.business_id == business_id
        if hasattr(obj, "business") and getattr(obj, "business", None) is not None:
            return getattr(obj.business, "id", None) == business_id
    except Exception:
        return False
    return True


def qs_for_tenant(qs: models.QuerySet[T], business_id: Any) -> models.QuerySet[T]:
    """
    Apply tenant filter to a queryset if its model supports it.
    No-op when the model is not tenant-scoped.
    """
    try:
        model = qs.model  # type: ignore[attr-defined]
        kwargs = biz_filter_kwargs(model, business_id)
        return qs.filter(**kwargs) if kwargs else qs
    except Exception:
        return qs


# -------------------------------------------------------------------
# Small queryset/instance conveniences
# -------------------------------------------------------------------
def safe_first(qs: models.QuerySet[T]) -> Optional[T]:
    """Return qs.first() with broad exception safety."""
    try:
        return qs.first()
    except Exception:
        return None


def exists_fast(qs: models.QuerySet[T]) -> bool:
    """Return qs.exists() with broad exception safety."""
    try:
        return qs.exists()
    except Exception:
        return False


def save_update_fields(
    instance: T,
    update_fields: Optional[Sequence[str]] = None,
) -> None:
    """
    Save an instance using update_fields when provided.
    Silently falls back to a regular save() if update_fields can't be honored.
    """
    try:
        if update_fields:
            instance.save(update_fields=list(update_fields))
        else:
            instance.save()
    except Exception:
        # Last-resort: unconditional save
        try:
            instance.save()
        except Exception:
            # swallowâ€”the caller should handle/log if needed
            pass


