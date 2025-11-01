# circuitcity/inventory/views_dashboard.py
from __future__ import annotations
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, JsonResponse


def inventory_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Inventory dashboard view.

    - If Accept header asks for JSON → return a small JSON stub.
    - Otherwise render a template (inventory/dashboard.html).
    - Falls back to a plain HttpResponse if the template is missing.
    """
    if request.headers.get("accept", "").startswith("application/json"):
        return JsonResponse({"ok": True, "message": "Inventory dashboard ready"})
    # circuitcity/inventory/views_dashboard.py

    from typing import Any, Dict
    import logging

    from django.contrib.auth.decorators import login_required
    from django.http import HttpRequest, HttpResponse, JsonResponse
    from django.shortcuts import render
    from django.views.decorators.cache import never_cache

    log = logging.getLogger(__name__)

    def _try_import(modpath: str, attr: str | None = None):
        """Import helper that never explodes."""
        try:
            mod = __import__(modpath, fromlist=[attr] if attr else [])
            return getattr(mod, attr) if attr else mod
        except Exception:
            return None

    # Prefer the single-source-of-truth helpers if present
    _dashboard_counts = _try_import("inventory.query", "dashboard_counts")
    _sales_in_range = _try_import("inventory.query", "sales_in_range")

    @login_required
    @never_cache
    def inventory_dashboard(request: HttpRequest) -> HttpResponse:
        """
        Inventory dashboard view (single source of truth).

        - Reads counts from inventory.query.{dashboard_counts,sales_in_range} if available.
        - Accepts `?days=7|30` for the "Sales (last N days)" card.
        - JSON if: `?format=json` or Accept: application/json (for widgets/AJAX).
        - Otherwise renders `inventory/dashboard.html` with a compact context.
        """
        # ------------ filters ------------
        try:
            last_days = int(request.GET.get("days") or 7)
            last_days = max(1, min(90, last_days))
        except Exception:
            last_days = 7

        # Optional toggle (if you want "Products" = SKUs that are currently in stock)
        products_in_stock_only = (request.GET.get("products_in_stock_only") or "").lower() in {
            "1", "true", "on"
        }

        wants_json = (
                (request.GET.get("format") or "").lower() == "json"
                or request.headers.get("x-requested-with") == "XMLHttpRequest"
                or "application/json" in (request.headers.get("Accept") or request.headers.get("accept") or "")
        )

        # ------------ compute metrics ------------
        products = items_in_stock = sales_mtd = 0
        sales_last = 0

        if callable(_dashboard_counts):
            try:
                counts = _dashboard_counts(request, products_in_stock_only=products_in_stock_only)
                products = int(counts.get("products") or 0)
                items_in_stock = int(counts.get("items_in_stock") or 0)
                sales_mtd = float(counts.get("sales_mtd") or 0)
            except Exception as e:
                log.exception("dashboard_counts failed: %s", e)

        if callable(_sales_in_range):
            try:
                sales_last = float(_sales_in_range(request, days=last_days) or 0)
            except Exception as e:
                log.exception("sales_in_range failed: %s", e)

        # ------------ JSON short-circuit ------------
        if wants_json:
            return JsonResponse(
                {
                    "ok": True,
                    "metrics": {
                        "products": products,
                        "items_in_stock": items_in_stock,
                        "sales_mtd": sales_mtd,
                        "sales_last": sales_last,
                    },
                    "filters": {
                        "days": last_days,
                        "products_in_stock_only": products_in_stock_only,
                    },
                },
                status=200,
            )

        # ------------ HTML ------------
        ctx: Dict[str, Any] = {
            "products": products,
            "items_in_stock": items_in_stock,
            "sales_mtd": sales_mtd,
            "sales_last": sales_last,
            "last_days": last_days,
            "products_in_stock_only": products_in_stock_only,
        }

        try:
            return render(request, "inventory/dashboard.html", ctx)
        except Exception:
            # Gentle fallback if the template isn't ready yet.
            html = f"""
            <section style="max-width:720px;margin:24px auto;font-family:system-ui, -apple-system, Segoe UI, Roboto, sans-serif">
              <h1 style="margin:0 0 8px">Inventory Dashboard</h1>
              <p style="margin:0 0 18px;color:#475569">Template <code>inventory/dashboard.html</code> not found. Showing fallback.</p>
              <ul style="line-height:1.7">
                <li><strong>Products</strong>: {products}</li>
                <li><strong>Items in stock</strong>: {items_in_stock}</li>
                <li><strong>Sales (MTD)</strong>: {sales_mtd:,.0f}</li>
                <li><strong>Sales (last {last_days} days)</strong>: {sales_last:,.0f}</li>
              </ul>
            </section>
            """.strip()
            return HttpResponse(html, content_type="text/html")

    try:
        return render(request, "inventory/dashboard.html")
    except Exception:
        return HttpResponse(
            "<h1>Inventory Dashboard</h1><p>Coming soon.</p>"
        )


