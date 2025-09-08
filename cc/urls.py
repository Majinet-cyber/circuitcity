# circuitcity/cc/urls.py
from importlib import import_module
import os
import re

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.loader import get_template
from django.urls import include, path, re_path, reverse, NoReverseMatch
from django.views.generic import RedirectView

from cc import views as core_views
from inventory.views_export import export_inventory_csv, export_audits_csv
from inventory.views_import import import_opening_stock
from inventory import views as inv_views  # used for fallbacks
from accounts import views as accounts_views


# ---------------- Basics / utility endpoints ----------------
def robots_txt(_request):
    return HttpResponse("User-agent: *\nDisallow: /", content_type="text/plain")


def root_redirect(_request):
    """
    Try a few likely dashboards; fall back to login.
    Order tweaked to prefer inventory stock list if dashboard not ready.
    """
    candidates = (
        "inventory:inventory_dashboard",  # full dashboard if present
        "inventory:dashboard",            # legacy name, safely ignored if missing
        "inventory:stock_list",           # stock list (safe fallback w/ built-in HTML)
        "dashboard:agent_dashboard",
        "wallet:agent_wallet",
        "reports:home",
        "admin:index",
        "accounts:login",
    )
    for name in candidates:
        try:
            reverse(name)
            return redirect(name)
        except NoReverseMatch:
            continue
    return redirect("/accounts/login/")


# --- Tiny session probe (useful for debugging cookies) -----------------
def session_set(request):
    request.session["probe"] = "ok"
    return HttpResponse("set")


def session_get(request):
    return HttpResponse(request.session.get("probe", "missing"))


# --- DEBUG ENDPOINTS (prove which templates are used) ------------------
def __whoami__(request):
    """
    Return settings + template origin paths for key templates.
    Visit: /__whoami__
    """
    data = {
        "DEBUG": settings.DEBUG,
        "BASE_DIR": str(settings.BASE_DIR),
        "TEMPLATE_DIRS": [str(p) for p in settings.TEMPLATES[0].get("DIRS", [])],
        "APP_DIRS": settings.TEMPLATES[0].get("APP_DIRS", False),
        "INSTALLED_APPS_contains_accounts": any(a.endswith("accounts") for a in settings.INSTALLED_APPS),
        "INSTALLED_APPS_contains_ccreports": any(a.endswith("ccreports") for a in settings.INSTALLED_APPS),
        "LOGIN_URL": settings.LOGIN_URL,
        "LOGIN_REDIRECT_URL": getattr(settings, "LOGIN_REDIRECT_URL", "/"),
        "LOGIN_TEMPLATE_PROBED": "accounts/login.html",
        "LOGIN_TEMPLATE_ORIGIN": None,
        "REPORTS_TEMPLATES_CHECKED": ["reports/home.html", "ccreports/home.html", "reports/index.html"],
        "REPORTS_TEMPLATE_FOUND": None,
        "NOTE": "If a *_ORIGIN is None, Django cannot locate that template under current settings.",
    }
    # Login template
    try:
        t = get_template("accounts/login.html")
        data["LOGIN_TEMPLATE_ORIGIN"] = getattr(getattr(t, "origin", None), "name", None)
    except Exception as e:
        data["LOGIN_TEMPLATE_ORIGIN"] = f"(not found) {e.__class__.__name__}: {e}"

    # Reports templates (try common candidates)
    for cand in data["REPORTS_TEMPLATES_CHECKED"]:
        try:
            rt = get_template(cand)
            data["REPORTS_TEMPLATE_FOUND"] = {
                "template": cand,
                "origin": getattr(getattr(rt, "origin", None), "name", None),
            }
            break
        except Exception:
            continue

    return JsonResponse(data, json_dumps_params={"indent": 2})


def __render_login__(request):
    """
    Render accounts/login.html directly and inject a banner showing its origin.
    Visit: /__render_login__
    """
    try:
        t = get_template("accounts/login.html")
        origin = getattr(getattr(t, "origin", None), "name", "(unknown origin)")
        html = t.render({"form": None, "_debug_note": "Rendered by __render_login__ (no auth flow)."})
        banner = f"""
        <div style="margin:10px 0;padding:10px 12px;border-radius:10px;
                    background:#ecfeff;border:1px solid #bae6fd;color:#0c4a6e;
                    font-family:system-ui,Segoe UI,Inter,Roboto,Arial,sans-serif;">
          <strong>Rendered at /__render_login__</strong><br>
          Template origin: <code>{origin}</code>
        </div>
        """
        if "<body" in html:
            html = html.replace("<body", "<body data-render-probe='1' ", 1)
            idx = html.find(">")
            if idx != -1:
                html = html[: idx + 1] + banner + html[idx + 1 :]
        else:
            html = banner + html
        return HttpResponse(html)
    except Exception as e:
        return HttpResponse(
            f"<pre>accounts/login.html could not be loaded:\n{e.__class__.__name__}: {e}</pre>",
            status=500,
            content_type="text/html",
        )


def __render_reports__(request):
    """
    Try rendering a plausible Reports template and inject its origin.
    Visit: /__render_reports__
    """
    candidates = ["reports/home.html", "ccreports/home.html", "reports/index.html"]
    last_err = None
    for cand in candidates:
        try:
            t = get_template(cand)
            origin = getattr(getattr(t, "origin", None), "name", "(unknown origin)")
            html = t.render({"_debug_note": f"Rendered by __render_reports__ using {cand}"})
            banner = f"""
            <div style="margin:10px 0;padding:10px 12px;border-radius:10px;
                        background:#ecfeff;border:1px solid #bae6fd;color:#0c4a6e;
                        font-family:system-ui,Segoe UI,Inter,Roboto,Arial,sans-serif;">
              <strong>Rendered at /__render_reports__</strong><br>
              Template: <code>{cand}</code><br>
              Origin: <code>{origin}</code>
            </div>
            """
            if "<body" in html:
                html = html.replace("<body", "<body data-render-probe='1' ", 1)
                idx = html.find(">")
                if idx != -1:
                    html = html[: idx + 1] + banner + html[idx + 1 :]
            else:
                html = banner + html
            return HttpResponse(html)
        except Exception as e:
            last_err = e
            continue
    return HttpResponse(
        f"<pre>No reports template could be rendered.\nLast error: {last_err.__class__.__name__}: {last_err}</pre>",
        status=500,
        content_type="text/html",
    )


def __grep_soon__(request):
    """
    DEBUG helper: grep the project tree for 'Soon' / 'Reports (soon)' in *.html/*.py).
    Visit: /__grep_soon__
    """
    if not settings.DEBUG:
        return HttpResponse("Not available when DEBUG=False.", status=404)

    patterns = [r"\bSoon\b", r"Reports\s*\(soon\)"]
    rx = re.compile("|".join(patterns), re.IGNORECASE)
    root = str(settings.BASE_DIR)
    hits = []

    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if not (fn.endswith(".html") or fn.endswith(".py")):
                continue
            fpath = os.path.join(dirpath, fn)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, start=1):
                        if rx.search(line):
                            hits.append({
                                "file": os.path.relpath(fpath, root),
                                "line_no": i,
                                "line": line.strip(),
                            })
            except Exception:
                continue

    return JsonResponse({"root": root, "patterns": patterns, "hits": hits}, json_dumps_params={"indent": 2})


urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # Health / robots / favicon / temporary
    path("healthz/", core_views.healthz, name="healthz"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("favicon.ico", RedirectView.as_view(url=f"{settings.STATIC_URL}favicon.ico", permanent=False)),
    path("temporary/", core_views.temporary_ok, name="temporary_ok"),

    # Landing
    path("", root_redirect, name="root"),

    # CSV export & imports
    path("exports/inventory.csv", export_inventory_csv, name="export_inventory_csv"),
    path("exports/audits.csv", export_audits_csv, name="export_audits_csv"),
    path("imports/opening-stock/", import_opening_stock, name="import_opening_stock"),

    # Forgot / Reset (direct endpoints)
    path("accounts/password/forgot/", accounts_views.forgot_password_request_view, name="forgot_password_request_direct"),
    path("accounts/password/reset/", accounts_views.forgot_password_verify_view, name="forgot_password_reset_direct"),

    # Session probe helpers
    path("session-probe/set", session_set, name="session_probe_set"),
    path("session-probe/get", session_get, name="session_probe_get"),

    # Debug template probes
    path("__whoami__", __whoami__, name="__whoami__"),
    path("__render_login__", __render_login__, name="__render_login__"),
    path("__render_reports__", __render_reports__, name="__render_reports__"),

    # Convenience top-level redirects for Time pages (map to inventory app)
    path("time/check-in/", RedirectView.as_view(pattern_name="inventory:time_checkin_page", permanent=False)),
    path("time/logs/",    RedirectView.as_view(pattern_name="inventory:time_logs",         permanent=False)),
]

# Optional sales CSV export (if available)
try:
    from sales.views_export import export_sales_csv  # type: ignore
except Exception:
    export_sales_csv = None

if export_sales_csv:
    urlpatterns.append(path("exports/sales.csv", export_sales_csv, name="export_sales_csv"))

# ---------------- Inventory API fallbacks (prefer inventory.api if available)
# We resolve each endpoint carefully, falling back to views.* where available.
def _resolve_from(mod, name, fallback=None):
    try:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    except Exception:
        pass
    return fallback

try:
    api_mod = import_module("inventory.api")
except Exception:
    api_mod = None

# Baseline: pull from views.py (all these exist in your views)
predictions_view   = getattr(inv_views, "api_predictions", None)
cash_overview_view = getattr(inv_views, "api_cash_overview", None)
sales_trend_view   = getattr(inv_views, "api_sales_trend", None)
top_models_view    = getattr(inv_views, "api_top_models", None)
alerts_view        = getattr(inv_views, "api_alerts", None)
# There is no api_value_trend in views; we can alias to sales trend for compatibility
value_trend_view   = sales_trend_view
# Stock health isn't a separate view; use the heatmap if present
stock_health_view  = getattr(inv_views, "restock_heatmap_api", alerts_view)

# Prefer inventory.api where provided
if api_mod:
    predictions_view  = _resolve_from(api_mod, "predictions_summary", predictions_view)
    value_trend_view  = _resolve_from(api_mod, "api_value_trend",     value_trend_view)
    sales_trend_view  = _resolve_from(api_mod, "api_sales_trend",     sales_trend_view)
    top_models_view   = _resolve_from(api_mod, "api_top_models",      top_models_view)
    alerts_view       = _resolve_from(api_mod, "alerts_feed",         alerts_view)
    stock_health_view = _resolve_from(api_mod, "api_stock_health",    stock_health_view)

# Only add these routes if we have a baseline predictions_view to anchor the group
if predictions_view:
    urlpatterns += [
        re_path(r"^inventory/api/predictions/?$",        predictions_view),
        re_path(r"^inventory/api/predictions/v2/?$",     getattr(inv_views, "api_predictions", predictions_view)),
        re_path(r"^inventory/api/cash[-_]overview/?$",   cash_overview_view or predictions_view),
        re_path(r"^inventory/api/value[_-]trend/?$",     value_trend_view or predictions_view),
        re_path(r"^inventory/api_sales_trend/?$",        sales_trend_view or predictions_view),
        re_path(r"^inventory/api/top_models/?$",         top_models_view or predictions_view),
        re_path(r"^inventory/api/alerts/?$",             alerts_view or predictions_view),
        re_path(r"^inventory/api/stock[_-]health/?$",    stock_health_view or alerts_view or predictions_view),
    ]

# ---------------- App URLConfs (namespaced includes)
urlpatterns += [
    path("dashboard/", include(("dashboard.urls", "dashboard"), namespace="dashboard")),
    path("inventory/", include(("inventory.urls", "inventory"), namespace="inventory")),
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("wallet/", include(("wallet.urls", "wallet"), namespace="wallet")),
    # Reports include with explicit namespace (NOTE: NO separate 'reports/' redirect above).
    path("reports/", include(("ccreports.urls", "reports"), namespace="reports")),
]

# ---------------- Optional sales app include
try:
    urlpatterns.append(path("sales/", include(("sales.urls", "sales"), namespace="sales")))
except Exception:
    pass

# ---------------- DEBUG-only helpers that touch the filesystem
if settings.DEBUG:
    urlpatterns += [
        path("__grep_soon__", __grep_soon__, name="__grep_soon__"),
    ]

# ---------------- Static / media in DEBUG
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
