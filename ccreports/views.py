# ccreports/views.py
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Tuple

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.template import TemplateDoesNotExist
from django.template.loader import get_template

__all__ = ["home", "sales_report", "inventory_report", "which_templates"]

log = logging.getLogger(__name__)


# --------------------------------------------------
# Internal helpers
# --------------------------------------------------
def _resolve_first(names: Iterable[str]) -> Tuple[str | None, str | None, List[str]]:
    """
    Try each template name until one resolves.
    Returns (chosen_name, origin_path, errors).
    """
    errors: List[str] = []
    for name in names:
        try:
            t = get_template(name)
            origin = getattr(getattr(t, "origin", None), "name", None)
            return name, origin, errors
        except TemplateDoesNotExist as e:
            errors.append(f"{name}: {e}")
        except Exception as e:
            errors.append(f"{name}: {e.__class__.__name__}: {e}")
    return None, None, errors


def _render_with_candidates(
    request: HttpRequest,
    candidates: Iterable[str],
    context: Dict[str, Any],
) -> HttpResponse:
    """
    Render the first template that exists from `candidates`.
    Also prints/logs which template/origin was used and sets response headers.
    """
    chosen, origin, errs = _resolve_first(candidates)

    if chosen:
        msg = f">> REPORTS USING TEMPLATE {chosen}: {origin or '(unknown origin)'}"
        print(msg)
        log.debug(msg)

        resp = render(request, chosen, context)
        resp["X-Reports-Template"] = chosen
        if origin:
            resp["X-Template-Origin"] = origin
        return resp

    # Nothing found â†’ return a helpful error page (keeps you out of a raw 500)
    pretty = "\n".join(f"- {e}" for e in errs) or "(no details)"
    html = f"""
      <h1>Reports template not found</h1>
      <p>None of the candidate templates could be located. Looked for:</p>
      <pre style="white-space:pre-wrap">{pretty}</pre>
      <p>Create one of these files and refresh:</p>
      <ul>
        <li><code>templates/ccreports/â€¦</code></li>
        <li><code>templates/reports/â€¦</code></li>
      </ul>
    """.strip()
    print(">> REPORTS TEMPLATE RESOLVE FAILED\n" + pretty)
    log.error("REPORTS TEMPLATE RESOLVE FAILED: %s", pretty)
    return HttpResponse(html, status=500)


# --------------------------------------------------
# Views
# --------------------------------------------------
@login_required
def home(request: HttpRequest) -> HttpResponse:
    """
    Reports dashboard landing page.
    """
    ctx: Dict[str, Any] = {
        "title": "Reports",
        "subtitle": "Overview",
    }
    # Try app-specific first, then generic folder for compatibility
    return _render_with_candidates(
        request,
        candidates=("ccreports/home.html", "reports/home.html"),
        context=ctx,
    )


@login_required
def sales_report(request: HttpRequest) -> HttpResponse:
    """
    Sales report view (safe defaults).
    """
    ctx: Dict[str, Any] = {
        "title": "Reports Â· Sales",
        "top_models": [],
        "agents": [],
        "recent_sales": [],
        "page_obj": None,
    }
    return _render_with_candidates(
        request,
        candidates=("ccreports/sales.html", "reports/sales.html"),
        context=ctx,
    )


@login_required
def inventory_report(request: HttpRequest) -> HttpResponse:
    """
    Inventory report view (safe defaults).
    """
    ctx: Dict[str, Any] = {
        "title": "Reports Â· Inventory",
        "low_stock": [],
        "ageing": [],
        "turnover": [],
        "groups": [],
        "snapshot": [],
        "page_obj": None,
    }
    return _render_with_candidates(
        request,
        candidates=("ccreports/inventory.html", "reports/inventory.html"),
        context=ctx,
    )


# --------------------------------------------------
# Debug endpoint
# --------------------------------------------------
@login_required
def which_templates(request: HttpRequest) -> HttpResponse:
    """
    Show where each reports template is being resolved from.
    """
    def origin_for(cands: Iterable[str]) -> Dict[str, Any]:
        chosen, origin, errs = _resolve_first(cands)
        return {
            "candidates": list(cands),
            "chosen": chosen,
            "origin": origin,
            "errors": errs,
        }

    data = {
        "home": origin_for(("ccreports/home.html", "reports/home.html")),
        "sales": origin_for(("ccreports/sales.html", "reports/sales.html")),
        "inventory": origin_for(("ccreports/inventory.html", "reports/inventory.html")),
    }
    return JsonResponse(data, json_dumps_params={"indent": 2})


