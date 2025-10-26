# circuitcity/inventory/views_scan.py
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional

from django.urls import reverse_lazy
from django.views.generic import TemplateView


# ---------------------------------------------------------------------
# Safe dynamic imports (works if your models live in different apps)
# ---------------------------------------------------------------------
def _safe_import(*candidates: str):
    """
    Try a list of 'app.Model' dotted names and return the first model that imports.
    This lets us work even if your model is named Product vs CatalogProduct, etc.
    """
    import importlib
    for dotted in candidates:
        try:
            app_label, model_name = dotted.split(".", 1)
            m = importlib.import_module(f"{app_label}.models")
            return getattr(m, model_name)
        except Exception:
            continue
    return None


# Try common names from your codebase
Product = _safe_import("inventory.Product", "inventory.ModelsProduct", "sales.Product", "core.Product")
Location = _safe_import("inventory.Location", "tenants.Location", "tenants.Store", "tenants.Branch")

# Optional tenant/business resolver
def _get_active_business(request):
    try:
        from tenants.utils import get_active_business  # type: ignore
        return get_active_business(request)
    except Exception:
        # Fallback: some codebases attach .business on the request
        return getattr(request, "business", None)


# ---------------------------------------------------------------------
# Small field/meta helpers
# ---------------------------------------------------------------------
def _model_has_field(model, field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in model._meta.get_fields())
    except Exception:
        return hasattr(model, field_name)  # very defensive fallback


def _safe_order_by(qs, model, preferred_field: str) -> Any:
    if _model_has_field(model, preferred_field):
        return qs.order_by(preferred_field)
    return qs.order_by("id")


# ---------------------------------------------------------------------
# Query helpers used by both ScanIn and ScanSold pages
# ---------------------------------------------------------------------
def _query_products(request) -> list[dict[str, Any]]:
    if not Product:
        return []

    try:
        business = _get_active_business(request)
        qs = Product.objects.all()

        # If the Product model is tenant-scoped, prefer filtering to the active business
        for tenant_field in ("business", "tenant", "organization"):
            if _model_has_field(Product, tenant_field) and business is not None:
                qs = qs.filter(**{tenant_field: business})
                break

        # Prefer 'active' filter if present
        if _model_has_field(Product, "active"):
            qs = qs.filter(active=True)

        qs = _safe_order_by(qs, Product, "name")[:500]

        items: list[dict[str, Any]] = []
        for p in qs:
            items.append(
                {
                    "id": getattr(p, "id", None),
                    "name": getattr(p, "name", str(p)),
                    # Provide a default order price if your model has it
                    "default_order_price": (
                        getattr(p, "order_price", None)
                        or getattr(p, "default_cost", None)
                        or getattr(p, "cost", None)
                        or getattr(p, "price", None)
                    ),
                }
            )
        return items
    except Exception:
        return []


def _query_locations(request) -> list[dict[str, Any]]:
    if not Location:
        return []

    try:
        business = _get_active_business(request)
        qs = Location.objects.all()

        # If Location is tenant-scoped, filter to active business
        for tenant_field in ("business", "tenant", "organization"):
            if _model_has_field(Location, tenant_field) and business is not None:
                qs = qs.filter(**{tenant_field: business})
                break

        qs = _safe_order_by(qs, Location, "name")[:200]

        items: list[dict[str, Any]] = []
        for l in qs:
            items.append(
                {
                    "id": getattr(l, "id", None),
                    "name": getattr(l, "name", str(l)),
                }
            )
        return items
    except Exception:
        return []


# ---------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------
class ScanInView(TemplateView):
    template_name = "inventory/scan_in.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request

        ctx.update(
            {
                "post_url": reverse_lazy("inventory:api_scan_in"),
                "products": _query_products(request),     # for Product select
                "locations": _query_locations(request),   # optional Location select
                "received_date_default": date.today(),    # default date â€œtodayâ€
                "rules": {
                    "imei_length": 15,
                    "require_product": True,
                    "order_price_autofill": True,          # template can use this to auto-fill from product
                },
            }
        )
        return ctx


class ScanSoldView(TemplateView):
    template_name = "inventory/scan_sold.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request

        ctx.update(
            {
                "post_url": reverse_lazy("inventory:api_scan_sold"),
                "products": _query_products(request),
                "locations": _query_locations(request),
                "rules": {
                    "imei_length": 15,
                    "require_product": True,
                },
            }
        )
        return ctx


