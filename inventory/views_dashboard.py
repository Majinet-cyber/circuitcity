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
    _compute_agent_ranking = _try_import("inventory.services.agent_ranking", "compute_agent_ranking")
    _format_rank = _try_import("inventory.services.agent_ranking", "format_rank")

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

        # ------------ Agent Ranking (for agents only) ------------
        ranking_data = None
        user = getattr(request, "user", None)
        business = getattr(request, "business", None)
        
        # Check if user is an agent (not manager/staff)
        is_agent = False
        if user and user.is_authenticated and business:
            try:
                from tenants.models import Membership
                membership = Membership.objects.filter(
                    user=user, business=business, role="AGENT", status="ACTIVE"
                ).first()
                is_agent = membership is not None
            except Exception:
                pass
        
        if is_agent and callable(_compute_agent_ranking) and business:
            try:
                # Default to last 30 days for agent ranking
                ranking_days = 30
                ranking_data = _compute_agent_ranking(business, days=ranking_days, agent_user=user)
                if _format_rank and ranking_data.get("agent_rank"):
                    ranking_data["agent_rank_formatted"] = _format_rank(ranking_data["agent_rank"])
            except Exception as e:
                log.exception("Agent ranking failed: %s", e)
        
        # ------------ Profit & Payment Mix (MTD) ------------
        # Import helpers locally to avoid circular imports
        try:
            from dashboard.dashboard_metrics import (
                add_profit_context,
                add_payment_mix_context,
                get_mtd_dates,
            )
            from sales.models import Sale
            from decimal import Decimal
            
            # Get MTD date range
            start_date, end_date = get_mtd_dates()
            business = getattr(request, "business", None)
            
            # Build sales queryset for MTD
            sales_qs = None
            if business and Sale is not None:
                sales_qs = Sale.objects.filter(
                    location__business=business,
                    sold_at__gte=start_date,
                    sold_at__lte=end_date,
                )
            
            # Revenue is already calculated as sales_mtd
            revenue_total = Decimal(str(sales_mtd))
            
            # Create initial context
            ctx: Dict[str, Any] = {
                "products": products,
                "items_in_stock": items_in_stock,
                "sales_mtd": sales_mtd,
                "sales_last": sales_last,
                "last_days": last_days,
                "products_in_stock_only": products_in_stock_only,
                "agent_ranking": ranking_data,
                "is_agent": is_agent,
            }
            
            # Add profit context
            if business:
                ctx = add_profit_context(
                    ctx,
                    business=business,
                    revenue=revenue_total,
                    start_date=start_date,
                    end_date=end_date,
                    period_label="MTD",
                )
            
            # Add payment mix context
            if sales_qs is not None:
                ctx = add_payment_mix_context(
                    ctx,
                    sales_queryset=sales_qs,
                    period_label="MTD",
                )
        except Exception as e:
            # If profit/payment mix fails, continue with basic context
            log.exception("Failed to add profit/payment mix context: %s", e)
            ctx: Dict[str, Any] = {
                "products": products,
                "items_in_stock": items_in_stock,
                "sales_mtd": sales_mtd,
                "sales_last": sales_last,
                "last_days": last_days,
                "products_in_stock_only": products_in_stock_only,
                "agent_ranking": ranking_data,
                "is_agent": is_agent,
            }

        # ------------ HTML ------------
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


