from __future__ import annotations

from typing import Any

from django.db import models
from django.utils import timezone

try:
    from tenants.models import Membership
except Exception:  # pragma: no cover
    Membership = None  # type: ignore

try:
    from tenants.utils import get_active_business
except Exception:  # pragma: no cover
    def get_active_business(_request):  # type: ignore
        return None


def _wants_json(request) -> bool:
    headers = getattr(request, "headers", {})
    return (
        request.GET.get("as") == "json"
        or headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (headers.get("Accept") or "")
        or "application/json" in (headers.get("Content-Type") or "")
    )


def _is_admin(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and (user.is_staff or user.is_superuser))


def _has_group(user, names: set[str]) -> bool:
    try:
        return user.groups.filter(name__in=names).exists()
    except Exception:
        return False


def _can_edit_inventory(user) -> bool:
    if _is_admin(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _has_group(user, {"Owner", "Admin", "Manager", "Inventory Manager", "Supervisor"}):
        return True
    try:
        if user.has_perm("inventory.change_inventoryitem") or user.has_perm("inventory.change_stock"):
            return True
    except Exception:
        pass
    if Membership is not None:
        try:
            role = (
                Membership.objects.filter(user=user, status="ACTIVE")
                .values_list("role", flat=True)
                .first()
            )
            return str(role or "").strip().upper() in {"OWNER", "ADMIN", "MANAGER", "SUPERVISOR", "FINANCE"}
        except Exception:
            return False
    return False


def _is_agent_user(user) -> bool:
    if _is_admin(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _has_group(user, {"Agent", "Sales Agent", "Manager", "Inventory Manager", "Supervisor"}):
        return True
    if Membership is not None:
        try:
            role = (
                Membership.objects.filter(user=user, status="ACTIVE")
                .values_list("role", flat=True)
                .first()
            )
            return str(role or "").strip().upper() in {"AGENT", "BAR_MANAGER", "MANAGER", "SUPERVISOR", "OWNER", "ADMIN"}
        except Exception:
            pass
    try:
        return hasattr(user, "agentprofile")
    except Exception:
        return False


def _model_field_names(model) -> set[str]:
    try:
        return {getattr(f, "name", "") for f in model._meta.get_fields()}
    except Exception:
        return set()


def _scoped(qs_or_manager, request):
    """
    Scope a queryset/manager to the active business when the model supports it.
    Kept as a small compatibility module for legacy inventory views.
    """
    qs = qs_or_manager.all() if hasattr(qs_or_manager, "all") else qs_or_manager
    business = get_active_business(request)
    if not business:
        return qs

    model = getattr(qs, "model", None)
    fields = _model_field_names(model) if model is not None else set()
    if "business" in fields or "business_id" in fields:
        try:
            return qs.filter(models.Q(business=business) | models.Q(business_id=getattr(business, "id", None)))
        except Exception:
            try:
                return qs.filter(business=business)
            except Exception:
                return qs
    return qs


def _audit(item: Any, user, action: str, details: str = "") -> None:
    try:
        from inventory.models import AuditLog
    except Exception:
        AuditLog = None  # type: ignore
    if AuditLog is None:
        return
    try:
        kwargs = {
            "actor": user if getattr(user, "is_authenticated", False) else None,
            "action": action,
            "details": details,
        }
        fields = _model_field_names(AuditLog)
        if "item" in fields:
            kwargs["item"] = item
        elif "object_repr" in fields:
            kwargs["object_repr"] = str(item)
        if "created_at" in fields:
            kwargs["created_at"] = timezone.now()
        AuditLog.objects.create(**{k: v for k, v in kwargs.items() if k in fields})
    except Exception:
        pass
