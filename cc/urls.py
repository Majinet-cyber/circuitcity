# cc/urls.py
from importlib import import_module
import os
import re

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.loader import get_template
from django.urls import include, path, re_path, reverse, NoReverseMatch
from django.views.generic import RedirectView

# --- Core views (project-level)
from cc import views as core_views  # keep as-is (project module is "cc")


# ---------- Safe import helpers (prefer fully-qualified circuitcity.* then fallback) ----------
def _try_import(path_fq: str, path_short: str | None = None):
    """
    Import a module by its fully-qualified path, with an optional short fallback.
    Returns the imported module or None.
    """
    try:
        return import_module(path_fq)
    except Exception:
        if path_short:
            try:
                return import_module(path_short)
            except Exception:
                return None
        return None


def _try_from(module_fq: str, attr: str, module_short: str | None = None):
    mod = _try_import(module_fq, module_short)
    return getattr(mod, attr, None) if mod else None


# ---------- Inventory exports/imports (prefer fqdn) ----------
export_inventory_csv = _try_from(
    "circuitcity.inventory.views_export", "export_inventory_csv", "inventory.views_export"
)
export_audits_csv = _try_from(
    "circuitcity.inventory.views_export", "export_audits_csv", "inventory.views_export"
)
import_opening_stock = _try_from(
    "circuitcity.inventory.views_import", "import_opening_stock", "inventory.views_import"
)

# Legacy inventory fallbacks (for some APIs)
inv_views_mod = _try_import("circuitcity.inventory.views", "inventory.views")

# Accounts views (optional custom)
accounts_views = _try_import("circuitcity.accounts.views", "accounts.views")

# --- HQ (platform admin) permission check
is_hq_admin = _try_from("circuitcity.hq.permissions", "is_hq_admin", "hq.permissions") or (lambda _u: False)

# --- Tenants helpers (for active-business detection)
get_active_business = _try_from("circuitcity.tenants.utils", "get_active_business", "tenants.utils") or (lambda _r: None)

# Optional polish APIs (guarded imports)
core_search = _try_import("circuitcity.core.views_search", "core.views_search")
core_savedview = _try_import("circuitcity.core.views_savedview", "core.views_savedview")


# ---------------------------------------------------------------------
# Basics / utility endpoints
# ---------------------------------------------------------------------
def robots_txt(_request):
    return HttpResponse("User-agent: *\nDisallow: /", content_type="text/plain")


def root_redirect(request):
    """
    Home router:
    - Anonymous -> login
    - HQ admin  -> HQ (if present)
    - No active business -> tenants chooser/join
    - Else -> first available tenant dashboard
    """
    # Anonymous -> login (prefer two_factor if enabled)
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        for name in ("two_factor:login", "accounts:login", "login"):
            try:
                reverse(name)
                return redirect(name)
            except NoReverseMatch:
                continue
        return redirect("/accounts/login/")

    # HQ admins first
    if is_hq_admin(request.user):
        try:
            return redirect("hq:home")
        except NoReverseMatch:
            pass

    # If no active business, push chooser/join
    try:
        active = get_active_business(request)
    except Exception:
        active = None
    if not active:
        for name in ("tenants:choose_business", "tenants:join"):
            try:
                reverse(name)
                return redirect(name)
            except NoReverseMatch:
                continue

    # Active business present -> try likely dashboards
    candidates = (
        "dashboard:home",
        "inventory:inventory_dashboard",
        "inventory:dashboard",
        "inventory:stock_list",
        "dashboard:agent_dashboard",
        "wallet:agent_wallet",
        "reports:home",
        "admin:index",
    )
    for name in candidates:
        try:
            reverse(name)
            return redirect(name)
        except NoReverseMatch:
            continue

    return redirect("/inventory/")  # last resort


# --- Tiny session probe (useful for debugging cookies)
def session_set(request):
    request.session["probe"] = "ok"
    return HttpResponse("set")


def session_get(request):
    return HttpResponse(request.session.get("probe", "missing"))


# --- DEBUG helpers (template origins etc.)
def __whoami__(request):
    data = {
        "DEBUG": settings.DEBUG,
        "BASE_DIR": str(settings.BASE_DIR),
        "TEMPLATE_DIRS": [str(p) for p in settings.TEMPLATES[0].get("DIRS", [])],
        "APP_DIRS": settings.TEMPLATES[0].get("APP_DIRS", False),
        "INSTALLED_APPS_contains_accounts": any(a.endswith("accounts") for a in settings.INSTALLED_APPS),
        "INSTALLED_APPS_contains_ccreports": any(a.endswith("ccreports") for a in settings.INSTALLED_APPS),
        "LOGIN_URL": settings.LOGIN_URL,
        "LOGIN_REDIRECT_URL": getattr(settings, "LOGIN_REDIRECT_URL", "/"),
        "LOGIN_TEMPLATE_PROBED": "registration/login_v11_fix.html",
        "LOGIN_TEMPLATE_ORIGIN": None,
        "REPORTS_TEMPLATES_CHECKED": ["reports/home.html", "ccreports/home.html", "reports/index.html"],
        "REPORTS_TEMPLATE_FOUND": None,
    }
    try:
        t = get_template("registration/login_v11_fix.html")
        data["LOGIN_TEMPLATE_ORIGIN"] = getattr(getattr(t, "origin", None), "name", None)
    except Exception as e:
        data["LOGIN_TEMPLATE_ORIGIN"] = f"(not found) {e.__class__.__name__}: {e}"

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
    try:
        t = get_template("registration/login_v11_fix.html")
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
            f"<pre>registration/login_v11_fix.html could not be loaded:\n{e.__class__.__name__}: {e}</pre>",
            status=500,
            content_type="text/html",
        )


def __render_reports__(request):
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
                            hits.append(
                                {
                                    "file": os.path.relpath(fpath, root),
                                    "line_no": i,
                                    "line": line.strip(),
                                }
                            )
            except Exception:
                continue

    return JsonResponse({"root": root, "patterns": patterns, "hits": hits}, json_dumps_params={"indent": 2})


urlpatterns = []

# ---------------- Two-Factor (optional)
_enable_2fa = getattr(settings, "ENABLE_2FA", False)
if _enable_2fa:
    try:
        import two_factor.urls  # noqa: F401
        urlpatterns.append(path("", include(("two_factor.urls", "two_factor"), namespace="two_factor")))
    except Exception:
        pass

# ---------------- Admin (use configurable ADMIN_URL)
admin_path = getattr(settings, "ADMIN_URL", "__admin__/")
urlpatterns += [path(admin_path, admin.site.urls)]

# ---------------- Health / robots / favicon / temporary
urlpatterns += [
    path("healthz", core_views.healthz, name="healthz_noslash"),
    path("healthz/", core_views.healthz, name="healthz"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("favicon.ico", RedirectView.as_view(url=f"{settings.STATIC_URL}favicon.ico", permanent=False)),
    path("temporary/", core_views.temporary_ok, name="temporary_ok"),
]

# ---------------- Landing
urlpatterns += [path("", root_redirect, name="root")]

# ---------------- Settings alias → Inventory settings
def _settings_redirect(_request):
    try:
        return redirect("inventory:settings")
    except NoReverseMatch:
        try:
            return redirect("inventory:inventory_dashboard")
        except NoReverseMatch:
            return redirect("/inventory/")


urlpatterns += [
    path("settings/", _settings_redirect, name="settings_root"),
    path("settings", _settings_redirect),
]

# ---------------- CSV export & imports
if export_inventory_csv:
    urlpatterns.append(path("exports/inventory.csv", export_inventory_csv, name="export_inventory_csv"))
if export_audits_csv:
    urlpatterns.append(path("exports/audits.csv", export_audits_csv, name="export_audits_csv"))
if import_opening_stock:
    urlpatterns.append(path("imports/opening-stock/", import_opening_stock, name="import_opening_stock"))

# ---------------- Accounts include (robust): prefer real urlconf; else fallback patterns
_accounts_urlconf_fq = _try_import("circuitcity.accounts.urls")
_accounts_urlconf_short = None if _accounts_urlconf_fq else _try_import("accounts.urls")

if _accounts_urlconf_fq or _accounts_urlconf_short:
    # Include whichever import succeeded, namespaced as 'accounts'
    urlpatterns += [
        path(
            "accounts/",
            include(((_accounts_urlconf_fq or _accounts_urlconf_short), "accounts"), namespace="accounts"),
        )
    ]
else:
    # Fallback: provide a minimal accounts namespace so {% url 'accounts:login' %} works
    def _accounts_fallback_patterns():
        return [
            path(
                "login/",
                auth_views.LoginView.as_view(
                    template_name="accounts/login.html", redirect_authenticated_user=True
                ),
                name="login",
            ),
            path("logout/", auth_views.LogoutView.as_view(next_page="/"), name="logout"),
            # Provide password reset so {% url 'password_reset' %} resolves
            path("password_reset/", auth_views.PasswordResetView.as_view(), name="password_reset"),
        ]

    urlpatterns += [path("accounts/", include((_accounts_fallback_patterns(), "accounts"), namespace="accounts"))]

# Direct password helpers (call the real views if import succeeded)
if accounts_views:
    urlpatterns += [
        path(
            "accounts/password/forgot/",
            accounts_views.forgot_password_request_view,
            name="forgot_password_request_direct",
        ),
        path(
            "accounts/password/reset/",
            accounts_views.forgot_password_verify_view,
            name="forgot_password_reset_direct",
        ),
        # Alias so templates using {% url 'password_reset' %} always resolve to your flow
        path(
            "accounts/password_reset/",
            RedirectView.as_view(pattern_name="forgot_password_request_direct", permanent=False),
            name="password_reset",
        ),
    ]

# ---------------- Session probes
urlpatterns += [
    path("session-probe/set", session_set, name="session_probe_set"),
    path("session-probe/get", session_get, name="session_probe_get"),
]

# ---------------- Convenience top-level redirects for Time pages
urlpatterns += [
    path("time/check-in/", RedirectView.as_view(pattern_name="inventory:time_checkin_page", permanent=False)),
    path("time/logs/", RedirectView.as_view(pattern_name="inventory:time_logs", permanent=False)),
]

# ---------------- Optional sales CSV export
export_sales_csv = _try_from("circuitcity.sales.views_export", "export_sales_csv", "sales.views_export")
if export_sales_csv:
    urlpatterns.append(path("exports/sales.csv", export_sales_csv, name="export_sales_csv"))

# ---------------------------------------------------------------------
# Preferred Inventory API endpoints (use inventory.api when present)
# ---------------------------------------------------------------------
api_mod = _try_import("circuitcity.inventory.api", "inventory.api")


def _choose(pref_mod, name, fallback):
    if pref_mod:
        try:
            fn = getattr(pref_mod, name, None)
            if callable(fn):
                return fn
        except Exception:
            pass
    return getattr(inv_views_mod, fallback) if inv_views_mod else None


predictions_view = _choose(api_mod, "predictions_summary", "api_predictions")
value_trend_view = _choose(api_mod, "api_value_trend", "api_sales_trend")
sales_trend_view = _choose(api_mod, "api_sales_trend", "api_sales_trend")
top_models_view = _choose(api_mod, "api_top_models", "api_top_models")
alerts_view = _choose(api_mod, "alerts_feed", "api_alerts")
stock_health_view = _choose(api_mod, "api_stock_health", "restock_heatmap_api")
profit_bar_view = getattr(api_mod, "api_profit_bar", None) if api_mod else None

api_task_submit = getattr(api_mod, "api_task_submit", None) if api_mod else None
api_task_status = getattr(api_mod, "api_task_status", None) if api_mod else None
api_audit_verify = getattr(api_mod, "api_audit_verify", None) if api_mod else None


def _add_api(pattern, view, **kwargs):
    if view:
        urlpatterns.append(re_path(pattern, view, **kwargs))


# Primary API paths (+ aliases)
_add_api(r"^inventory/api/predictions/?$", predictions_view, name="api_predictions")

# Sales trend (new + legacy)
_add_api(r"^inventory/api/sales[-_]trend/?$", sales_trend_view, name="api_sales_trend")
_add_api(r"^inventory/api_sales_trend/?$", sales_trend_view)

# Value trend (underscore + hyphen aliases)
_add_api(r"^inventory/api/value[_-]trend/?$", value_trend_view, name="api_value_trend")

# Top models (aliases)
_add_api(r"^inventory/api/top[_-]models/?$", top_models_view, name="api_top_models")
_add_api(r"^inventory/api_top_models/?$", top_models_view)

# Alerts
_add_api(r"^inventory/api/alerts/?$", alerts_view, name="api_alerts")

# Stock health (aliases)
_add_api(r"^inventory/api/stock[-_]health/?$", stock_health_view)
_add_api(r"^inventory/api/stock_health/?$", stock_health_view)

# Optional: profit bar (aliases) if available
_add_api(r"^inventory/api/profit[-_]bar/?$", profit_bar_view) if profit_bar_view else None
_add_api(r"^inventory/api_profit_bar/?$", profit_bar_view) if profit_bar_view else None

# Optional: async task submit/status + audit verify if provided
if api_task_submit:
    urlpatterns.append(path("inventory/api/task/submit/", api_task_submit))
if api_task_status:
    urlpatterns.append(path("inventory/api/task/status/", api_task_status))
if api_audit_verify:
    urlpatterns.append(path("inventory/api/audit-verify/", api_audit_verify))

# Heatmap aliases (restock)
restock_heatmap_view = stock_health_view
_add_api(r"^inventory/api/restock[_-]heatmap/?$", restock_heatmap_view)
_Add = _add_api  # alias
_Add(r"^inventory/restock[_-]heatmap_api/?$", restock_heatmap_view)
_Add(r"^inventory/restock[_-]heatmap/?$", restock_heatmap_view)


# ---------------------------------------------------------------------
# App URLConfs (namespaced includes) — ALWAYS present via stubs
# ---------------------------------------------------------------------
def _wallet_stub_urls():
    def _j(name):
        return lambda r, *a, **k: JsonResponse({"ok": True, "ns": "wallet", "name": name, "stub": True})

    return [
        path("", _j("agent_wallet"), name="agent_wallet"),
        path("transactions/", _j("agent_txns"), name="agent_txns"),
        path("admin/", _j("admin_home"), name="admin_home"),
    ]


def _inventory_stub_urls():
    def _j(name):
        return lambda r, *a, **k: JsonResponse({"ok": True, "ns": "inventory", "name": name, "stub": True})

    return [
        path("", _j("inventory_dashboard"), name="inventory_dashboard"),
        path("list/", _j("stock_list"), name="stock_list"),
        path("settings/", _j("settings"), name="settings"),
        path("time/check-in/", _j("time_checkin_page"), name="time_checkin_page"),
        path("time/logs/", _j("time_logs"), name="time_logs"),
        path("scan-sold/", _j("scan_sold"), name="scan_sold"),
        path("scan-in/", _j("scan_in"), name="scan_in"),
    ]


def _reports_stub_urls():
    def _j(name):
        return lambda r, *a, **k: JsonResponse({"ok": True, "ns": "reports", "name": name, "stub": True})

    return [
        path("", _j("home"), name="home"),
        path("sales/", _j("sales"), name="sales"),
        path("stock/", _j("stock"), name="stock"),
        path("agents/", _j("agents"), name="agents"),
    ]


def _tenants_stub_urls():
    def _j(name):
        return lambda r, *a, **k: JsonResponse({"ok": True, "ns": "tenants", "name": name, "stub": True})

    return [
        path("", _j("home"), name="home"),
        path("choose/", _j("choose_business"), name="choose_business"),
        path("join/", _j("join"), name="join"),
        path("create/", _j("create_business"), name="create_business"),
    ]


def _billing_stub_urls():
    def _j(name):
        return lambda r, *a, **k: JsonResponse({"ok": True, "ns": "billing", "name": name, "stub": True})

    return [path("", _j("home"), name="home")]


def _notifications_stub_urls():
    def _j(name):
        return lambda r, *a, **k: JsonResponse({"ok": True, "ns": "notifications", "name": name, "stub": True})

    return [path("", _j("home"), name="home")]


def _patterns_for(modpath_fq: str, modpath_short: str, fallback_patterns: list, ns: str):
    """
    Always return a concrete list of URL patterns.
    If importing the real module fails (during autoreload etc.), use stubs.
    """
    mod = _try_import(modpath_fq, modpath_short)
    if mod:
        try:
            patterns = getattr(mod, "urlpatterns", None)
            if isinstance(patterns, (list, tuple)) and patterns:
                return list(patterns)
        except Exception:
            pass
    print(f"[cc.urls] {ns} real urlconf unavailable -> using stub")
    return list(fallback_patterns)


urlpatterns += [
    path("dashboard/", include(("circuitcity.dashboard.urls", "dashboard"), namespace="dashboard")),
    # ✅ Namespaces are ALWAYS registered (stubs used if real modules fail)
    path(
        "inventory/",
        include(
            (
                _patterns_for("circuitcity.inventory.urls", "inventory.urls", _inventory_stub_urls(), "inventory"),
                "inventory",
            ),
            namespace="inventory",
        ),
    ),
    path(
        "wallet/",
        include(
            (_patterns_for("circuitcity.wallet.urls", "wallet.urls", _wallet_stub_urls(), "wallet"), "wallet"),
            namespace="wallet",
        ),
    ),
    path(
        "reports/",
        include(
            (_patterns_for("circuitcity.ccreports.urls", "ccreports.urls", _reports_stub_urls(), "reports"), "reports"),
            namespace="reports",
        ),
    ),
    # ✅ Tenants robust include (supports top-level `tenants` or package `circuitcity.tenants`)
    path(
        "tenants/",
        include(
            (_patterns_for("circuitcity.tenants.urls", "tenants.urls", _tenants_stub_urls(), "tenants"), "tenants"),
            namespace="tenants",
        ),
    ),
    # ✅ Billing and Notifications robust includes
    path(
        "billing/",
        include(
            (_patterns_for("circuitcity.billing.urls", "billing.urls", _billing_stub_urls(), "billing"), "billing"),
            namespace="billing",
        ),
    ),
    path(
        "notifications/",
        include(
            (
                _patterns_for(
                    "circuitcity.notifications.urls", "notifications.urls", _notifications_stub_urls(), "notifications"
                ),
                "notifications",
            ),
            namespace="notifications",
        ),
    ),
]

# ---------------- HQ (platform admin) include — robust (fq + short)
if _try_import("circuitcity.hq.urls", "hq.urls"):
    urlpatterns.append(path("hq/", include(("hq.urls", "hq"), namespace="hq")))

# ---------------- Onboarding include (guarded)
if _try_import("circuitcity.onboarding.urls", "onboarding.urls"):
    urlpatterns.append(
        path("onboarding/", include(("circuitcity.onboarding.urls", "onboarding"), namespace="onboarding"))
    )
    urlpatterns.append(
        path("get-started/", RedirectView.as_view(pattern_name="onboarding:start", permanent=False), name="get_started")
    )
else:

    def _onboarding_placeholder(_req, *args, **kwargs):
        html = """
        <main style="max-width:840px;margin:2rem auto;padding:1.25rem;font-family:system-ui,Segoe UI,Inter,Roboto,Arial">
          <h1>Getting started</h1>
          <p>The onboarding module isn't installed yet.</p>
          <ol>
            <li>Sign up / create an account</li>
            <li>Verify OTP</li>
            <li>Create your business</li>
            <li>Add your first product</li>
          </ol>
          <p style="color:#6b7280">Add an <code>onboarding</code> app with <code>onboarding/urls.py</code> to enable the guided flow.</p>
          <p><a href="/accounts/login/">Go to login</a></p>
        </main>
        """.strip()
        return HttpResponse(html)

    urlpatterns += [
        path("onboarding/", _onboarding_placeholder, name="onboarding_placeholder"),
        path("get-started/", _onboarding_placeholder, name="get_started"),
    ]

# ---------------- Optional sales app include — robust (fq + short)
if _try_import("circuitcity.sales.urls", "sales.urls"):
    urlpatterns.append(path("sales/", include(("sales.urls", "sales"), namespace="sales")))

# ---------------- AI-CFO API include (guarded)
if _try_import("circuitcity.cfo.urls", "cfo.urls"):
    urlpatterns.append(path("api/v1/", include(("circuitcity.cfo.urls", "cfo"), namespace="cfo_api")))
else:

    def _stub_view(payload, status=200):
        def _view(_req, *args, **kwargs):
            return JsonResponse(payload, status=status, safe=False)

        return _view

    urlpatterns += [
        re_path(r"^api/v1/cfo/forecast/?$", _stub_view([])),
        re_path(r"^api/v1/cfo/forecast/compute/?$", _stub_view({"ok": True})),
        re_path(r"^api/v1/cfo/alerts/?$", _stub_view([])),
        re_path(r"^api/v1/cfo/recommendations/?$", _stub_view([])),
        re_path(r"^api/v1/payouts/?$", _stub_view([])),
    ]

# ---------------- Simulator include (guarded + feature-flag aware)
_SIM_ENABLED = getattr(settings, "FEATURES", {}).get("SIMULATOR", True)
if _SIM_ENABLED and _try_import("circuitcity.simulator.urls", "simulator.urls"):
    urlpatterns.append(path("simulator/", include(("simulator.urls", "simulator"), namespace="simulator")))
elif _SIM_ENABLED:

    def _sim_placeholder(_req, *args, **kwargs):
        html = """
        <main style="max-width:860px;margin:2rem auto;padding:1rem;font-family:system-ui,Segoe UI,Inter,Roboto,Arial">
          <h1 style="margin:.2rem 0 1rem">Simulator (placeholder)</h1>
          <p>This is a lightweight placeholder because the <code>simulator</code> app isn't installed.</p>
          <ul>
            <li><a href="/simulator/new/">Create a new simulation</a></li>
          </ul>
          <p style="color:#6b7280">To enable the full experience, add <code>simulator</code> to <strong>INSTALLED_APPS</strong> and provide <code>simulator/urls.py</code>.</p>
        </main>
        """.strip()
        return HttpResponse(html)

    def _sim_new_placeholder(_req, *args, **kwargs):
        html = """
        <main style="max-width:860px;margin:2rem auto;padding:1rem;font-family:system-ui,Segoe UI,Inter,Roboto,Arial">
          <h1 style="margin:.2rem 0 1rem">New Simulation (placeholder)</h1>
          <p>Define parameters like demand growth %, price changes, lead times, and stock policies here.</p>
          <p style="color:#6b7280">This page is a placeholder until the full simulator app is installed.</p>
          <p><a href="/simulator/">Back to Simulator</a></p>
        </main>
        """.strip()
        return HttpResponse(html)

    urlpatterns += [
        path("simulator/", _sim_placeholder, name="simulator_placeholder_home"),
        path("simulator/new/", _sim_new_placeholder, name="simulator_placeholder_new"),
    ]
else:

    def _sim_disabled(_req, *args, **kwargs):
        return HttpResponse(
            "<main style='max-width:860px;margin:2rem auto;padding:1rem;font-family:system-ui,Segoe UI,Inter,Roboto,Arial'>"
            "<h1>Simulator disabled</h1>"
            "<p>The Simulator feature is currently turned off. Set <code>FEATURE_SIMULATOR=1</code> and restart to enable.</p>"
            "</main>"
        )

    urlpatterns += [
        path("simulator/", _sim_disabled, name="simulator_disabled"),
        path("simulator/new/", _sim_disabled),
    ]

# ---------------- Layby include (feature-flag aware, robust)
_LAYBY_ENABLED = getattr(settings, "FEATURES", {}).get("LAYBY", True)
if _LAYBY_ENABLED:
    urlpatterns += [path("layby/", include(("layby.urls", "layby"), namespace="layby"))]
else:

    def _layby_disabled(_req, *args, **kwargs):
        return HttpResponse(
            "<main style='max-width:860px;margin:2rem auto;padding:1rem;font-family:system-ui,Segoe UI,Inter,Roboto,Arial'>"
            "<h1>Layby disabled</h1>"
            "<p>The Layby feature is turned off. Set <code>FEATURE_LAYBY=1</code> and restart to enable.</p>"
            "</main>"
        )

    urlpatterns += [
        path("layby/", _layby_disabled, name="layby_disabled"),
        path("layby/agent/", _layby_disabled),
        path("layby/agent/new/", _layby_disabled),
        path("layby/admin/", _layby_disabled),
        path("layby/customer/", _layby_disabled),
    ]

# ---------------- Global Search + Saved Views (polish APIs)
def _empty_search(_req):
    return JsonResponse({"skus": [], "agents": [], "invoices": [], "transactions": []})


if core_search and hasattr(core_search, "api_global_search"):
    urlpatterns += [path("api/global-search/", core_search.api_global_search, name="api_global_search")]
else:
    urlpatterns += [path("api/global-search/", _empty_search, name="api_global_search")]

if core_savedview and hasattr(core_savedview, "api_saved_views"):
    urlpatterns += [path("api/saved-views/<str:scope>/", core_savedview.api_saved_views, name="api_saved_views")]

# ---------------- DEBUG-only probes
if settings.DEBUG:
    urlpatterns += [
        path("__whoami__", __whoami__, name="__whoami__"),
        path("__render_login__", __render_login__, name="__render_login__"),
        path("__render_reports__", __render_reports__, name="__render_reports__"),
        path("__grep_soon__", __grep_soon__, name="__grep_soon__"),
    ]

# ---------------- Back-compat URL names expected by older templates
urlpatterns += [
    path(
        "stock/in/",
        RedirectView.as_view(pattern_name="inventory:scan_in", permanent=False),
        name="stock_in",
    ),
    path(
        "stock/out/",
        RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False),
        name="stock_out",
    ),
    path(
        "stock/list/",
        RedirectView.as_view(pattern_name="inventory:stock_list", permanent=False),
        name="stock_list",
    ),
]

# ---------------- Convenience short paths (nice aliases)
urlpatterns += [
    path("sell/", RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="sell_short"),
    path("scan/", RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="scan_short"),
    path("stock/", RedirectView.as_view(pattern_name="inventory:stock_list", permanent=False), name="stock_short"),
]

# ---------------- Static / media in DEBUG
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
