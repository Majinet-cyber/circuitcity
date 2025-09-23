# circuitcity/inventory/views_scan.py
from __future__ import annotations

from datetime import date
from typing import Any

from django.urls import reverse_lazy
from django.views.generic import TemplateView

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

def _query_products() -> list[dict[str, Any]]:
    if not Product:
        return []
    try:
        qs = getattr(Product.objects, "filter", Product.objects.all)()
        # Prefer 'active' filter if present
        if hasattr(qs, "filter") and hasattr(Product, "active"):
            qs = qs.filter(active=True)
        items = []
        for p in qs.order_by(getattr("name", "id"))[:500]:
            items.append({
                "id": getattr(p, "id", None),
                "name": getattr(p, "name", str(p)),
                # provide a default order price if your model has it (cost, order_price, default_cost)
                "default_order_price": (
                    getattr(p, "order_price", None)
                    or getattr(p, "default_cost", None)
                    or getattr(p, "cost", None)
                ),
            })
        return items
    except Exception:
        return []

def _query_locations() -> list[dict[str, Any]]:
    if not Location:
        return []
    try:
        qs = getattr(Location.objects, "filter", Location.objects.all)()
        # keep it small
        items = []
        for l in qs.order_by(getattr("name", "id"))[:200]:
            items.append({
                "id": getattr(l, "id", None),
                "name": getattr(l, "name", str(l)),
            })
        return items
    except Exception:
        return []

class ScanInView(TemplateView):
    template_name = "inventory/scan_in.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx.update({
            "post_url": reverse_lazy("inventory:api_scan_in"),
            "products": _query_products(),         # for your Product select
            "locations": _query_locations(),       # optional Location select
            "received_date_default": date.today(), # default date “today”
            "rules": {
                "imei_length": 15,
                "require_product": True,
                "order_price_autofill": True,      # template can use this to auto-fill from product
            },
        })
        return ctx

class ScanSoldView(TemplateView):
    template_name = "inventory/scan_sold.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "post_url": reverse_lazy("inventory:api_scan_sold"),
            "products": _query_products(),
            "locations": _query_locations(),
            "rules": {
                "imei_length": 15,
                "require_product": True,
            },
        })
        return ctx
