# tenants/mixins.py
"""
Workspace-scoping mixins for Django views and Django REST Framework viewsets.

Usage (DRF):
    class ProductViewSet(WorkspaceScopedQuerysetMixin, WorkspaceAssignOnCreateMixin, viewsets.ModelViewSet):
        queryset = Product.objects.all()
        serializer_class = ProductSerializer

Usage (CBV):
    class ProductListView(WorkspaceScopedQuerysetMixin, ListView):
        model = Product
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Generic (works with Django CBVs and DRF ViewSets)
# ---------------------------------------------------------------------------

class BusinessQuerysetMixin:
    """
    Original mixin — filters queryset to the active business.
    Kept for backwards-compatibility. Prefer WorkspaceScopedQuerysetMixin.
    """
    business_field = "business"

    def get_queryset(self):
        qs = super().get_queryset()
        biz = getattr(self.request, "business", None)
        return qs.filter(**{self.business_field: biz}) if biz else qs.none()


# ---------------------------------------------------------------------------
# Canonical workspace-scoped mixins (new, spec-compliant names)
# ---------------------------------------------------------------------------

class WorkspaceScopedQuerysetMixin:
    """
    Mixin that automatically scopes list/detail querysets to the active workspace.

    Works with both Django class-based views and DRF ViewSets.

    Attributes:
        workspace_field (str): Model field name for the business FK. Default: "business".

    Security:
        - Returns qs.none() when no business is active (no data leakage).
        - Detail endpoints inherit the filtered queryset, preventing cross-tenant access.
    """

    workspace_field: str = "business"

    def get_queryset(self):
        qs = super().get_queryset()  # type: ignore[misc]
        biz = getattr(self.request, "business", None)  # type: ignore[attr-defined]
        if biz is None:
            return qs.none()
        return qs.filter(**{self.workspace_field: biz})


class WorkspaceAssignOnCreateMixin:
    """
    Mixin that automatically assigns the active workspace when creating objects.

    Works with DRF ViewSets (overrides perform_create).

    Security:
        - Ignores any business value provided in the request payload.
        - Uses the resolved request.business (set by TenantResolutionMiddleware).
    """

    workspace_field: str = "business"

    def perform_create(self, serializer):  # type: ignore[override]
        biz = getattr(self.request, "business", None)  # type: ignore[attr-defined]
        if biz is None:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("No active workspace. Cannot create resource.")
        serializer.save(**{self.workspace_field: biz})


class WorkspaceScopedMixin(WorkspaceScopedQuerysetMixin, WorkspaceAssignOnCreateMixin):
    """
    Convenience combo: scope queryset AND assign on create.
    Equivalent to inheriting both mixins individually.
    """
