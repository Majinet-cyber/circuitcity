# circuitcity/inventory/queries.py
from __future__ import annotations
from django.db.models import QuerySet
from typing import Iterable

from tenants.utils import scoped, user_is_agent, user_is_manager

# Prefer these actor fields in order when narrowing to an agent
_AGENT_FIELD_CANDIDATES: Iterable[str] = (
    "agent",
    "sold_by",
    "created_by",
    "user",
    "owner",
    "checked_in_by",
)

def _model_has_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False

def limit_to_actor(qs: QuerySet, user) -> QuerySet:
    """
    If the current user is an 'agent' (non-manager), limit to rows that belong to them.
    We try a series of common foreign-key/user fields. If none exist, we return qs.none()
    to avoid accidental data exposure.
    """
    if not user_is_agent(user):
        return qs  # managers/staff/superusers see tenant-wide

    model = getattr(qs, "model", None)
    if not model:
        return qs.none()

    for field in _AGENT_FIELD_CANDIDATES:
        if _model_has_field(model, field):
            try:
                return qs.filter(**{field: user})
            except Exception:
                # If a field exists but isn’t a direct FK to user, try field_id
                try:
                    return qs.filter(**{f"{field}_id": getattr(user, "id", None)})
                except Exception:
                    continue
    # No recognizable actor field → safest behavior is "no rows"
    return qs.none()

def scoped_for_user(qs_or_manager, request) -> QuerySet:
    """
    Tenant-scope first, then (if agent) limit to their own rows.
    """
    qs = scoped(qs_or_manager, request)
    return limit_to_actor(qs, getattr(request, "user", None))
