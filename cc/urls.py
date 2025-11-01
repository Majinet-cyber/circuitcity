# cc/urls.py
from __future__ import annotations

import os
import re
import logging
from importlib import import_module

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views  # <- for login/logout fallbacks
from django.http import HttpResponse, JsonResponse, HttpResponseBase
from django.shortcuts import redirect, render
from django.template.loader import get_template
from django.urls import include, path, re_path, reverse, NoReverseMatch
from django.views.generic import RedirectView
from django.templatetags.static import static as static_build  # may raise with Manifest storage

from cc import views as core_views

log = logging.getLogger(__name__)

# ======================================================================================
# Helpers
# ======================================================================================
def robots_txt(_request):
    return HttpResponse("User-agent: *\nDisallow: /", content_type="text/plain")


def _try_import(modpath: str):
    try:
        return import_module(modpath)
    except Exception as e:
        log.error("Import failed for %s: %s", modpath, e)
        return None


def _try_from(modpath: str, attr: str):
    mod = _try_import(modpath)
    return getattr(mod, attr, None) if mod else None


def safe_include(prefix: str, module_path: str, namespace: str | None = None):
    """
    Include a child urlconf without taking the whole site down on import error.
    Logs errors and continues. Ensures proper app_name + namespace wiring.
    """
    try:
        mod = import_module(module_path)
        if not hasattr(mod, "urlpatterns"):
            log.error("URLConf %s has no urlpatterns; skipping include.", module_path)
            return []
        # choose an app_name (prefer module.app_name, else provided namespace, else last module segment)
        app_name = getattr(mod, "app_name", None) or namespace or module_path.rsplit(".", 1)[0].split(".")[-1]
        inc = include((mod.urlpatterns, app_name), namespace=namespace or app_name)
        return [path(prefix, inc)]
    except Exception as e:
        log.error("URL include failed for %s: %s", module_path, e)
        return []


def _safe_static(path_fragment: str) -> str:
    try:
        return static_build(path_fragment)
    except Exception:
        return settings.STATIC_URL.rstrip("/") + "/" + path_fragment.lstrip("/")


def _reverse_exists(name: str) -> bool:
    try:
        reverse(name)
        return True
    except NoReverseMatch:
        return False


def _first_working_reverse(names: tuple[str, ...]) -> str | None:
    """
    Returns the **URL path** of the first reversable name, not the name itself.
    """
    for n in names:
        try:
            return reverse(n)
        except NoReverseMatch:
            continue
    return None


def _safe_redirect_to(name: str, fallback: str = "/accounts/login/"):
    def _view(_request, *args, **kwargs):
        try:
            return redirect(reverse(name))
        except NoReverseMatch:
            return redirect(fallback)
    return _view


def _patterns_have_name(patterns, name: str) -> bool:
    """Pattern introspection (safe at import-time; no reverse())."""
    try:
        from django.urls.resolvers import URLPattern, URLResolver
    except Exception:
        return False

    for p in patterns:
        try:
            if isinstance(p, URLPattern):
                if p.name == name:
                    return True
            elif isinstance(p, URLResolver):
                if _patterns_have_name(p.url_patterns, name):
                    return True
        except Exception:
            continue
    return False


def _redirect_first(names: tuple[str, ...], fallback_path: str = "/accounts/login/"):
    """Redirect to first resolvable URL name or fallback_path."""
    target = _first_working_reverse(names)
    return redirect(target or fallback_path)


# ======================================================================================
# Smart root redirect
# ======================================================================================
is_hq_admin = _try_from("circuitcity.hq.permissions", "is_hq_admin") or (lambda _u: False)
get_active_business = _try_from("circuitcity.tenants.utils", "get_active_business") or (lambda _r: None)

_tenants_views = _try_import("tenants.views") or _try_import("circuitcity.tenants.views")
_activate_mine_view = getattr(_tenants_views, "activate_mine", None)


def root_redirect(request):
    # Anonymous -> login (prefer two_factor if present)
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return _redirect_first(("two_factor:login", "accounts:login", "login"), "/accounts/login/")

    # HQ admins -> HQ dashboard
    if is_hq_admin(request.user):
        target = _first_working_reverse(("hq:dashboard", "hq:home", "hq:subscriptions", "hq_subscriptions"))
        if target:
            return redirect(target)

    # No active business -> activation/chooser
    try:
        active = get_active_business(request)
    except Exception:
        active = None
    if not active:
        target = _first_working_reverse(("tenants:activate_mine", "tenants:choose_business", "tenants:join"))
        if target:
            return redirect(target)
        if _activate_mine_view:
            return redirect("/tenants/activate-mine/")

    # Store dashboards
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
    target = _first_working_reverse(candidates)
    if target:
        return redirect(target)

    return redirect("/inventory/")


# ======================================================================================
# Tiny debug probes
# ======================================================================================
def session_set(request):
    request.session["probe"] = "ok"
    return HttpResponse("set")


def session_get(request):
    return HttpResponse(request.session.get("probe", "missing"))


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

    for cand in data["REPORTS_TEMPLATES_CHECKED"] as list[str]:
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
        if "<body" in html.lower():
            body_start = html.lower().find("<body")
            if body_start != -1:
                gt = html.find(">", body_start)
                if gt != -1:
                    html = html[: gt + 1] + banner + html[gt + 1 :]
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
            if "<body" in html.lower():
                body_start = html.lower().find("<body")
                if body_start != -1:
                    gt = html.find(">", body_start)
                    if gt != -1:
                        html = html[: gt + 1] + banner + html[gt + 1 :]
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
                            hits.append({"file": os.path.relpath(fpath, root), "line_no": i, "line": line.strip()})
            except Exception:
                continue

    return JsonResponse({"root": root, "patterns": patterns, "hits": hits}, json_dumps_params={"indent": 2})


# ======================================================================================
# URL patterns
# ======================================================================================
urlpatterns: list = []

# Two-Factor (optional)
if getattr(settings, "ENABLE_2FA", False):
    urlpatterns += safe_include("", "two_factor.urls", "two_factor")

# Admin
admin_path = getattr(settings, "ADMIN_URL", "admin/")
if not admin_path.endswith("/"):
    admin_path += "/"
urlpatterns += [path(admin_path, admin.site.urls)]
if admin_path != "admin/":
    urlpatterns += [path("admin/", admin.site.urls)]

# Basics / health / robots / favicon / temporary
urlpatterns += [
    path("healthz", core_views.healthz, name="healthz_noslash"),
    path("healthz/", core_views.healthz, name="healthz"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("favicon.ico", RedirectView.as_view(url=f"{settings.STATIC_URL}favicon.ico", permanent=False)),
    path("temporary/", core_views.temporary_ok, name="temporary_ok"),
]

# Legacy static -> brand icons
urlpatterns += [
    path("static/icons/icon-192.png", RedirectView.as_view(url=_safe_static("brand/mjn-192.png"), permanent=False)),
    path("static/img/logo-32.png",  RedirectView.as_view(url=_safe_static("brand/mjn-32.png"), permanent=False)),
]

# Landing
urlpatterns += [path("", root_redirect, name="root")]

# ---------------- Accounts (ALWAYS NAMESPACED) ----------------
# Try to include the real app; otherwise provide a minimal namespaced fallback
_accounts_mod = _try_import("circuitcity.accounts.urls") or _try_import("accounts.urls")
if _accounts_mod and hasattr(_accounts_mod, "urlpatterns"):
    app_name = getattr(_accounts_mod, "app_name", "accounts")
    urlpatterns += [path("accounts/", include((_accounts_mod.urlpatterns, app_name), namespace="accounts"))]
else:
    # Minimal namespaced fallbacks so {% url 'accounts:*' %} never 500s
    accounts_fallback_patterns = [
        path("login/", auth_views.LoginView.as_view(template_name="registration/login_v11_fix.html"), name="login"),
        path("logout/", auth_views.LogoutView.as_view(next_page="/accounts/login/"), name="logout"),
        path("forgot/", core_views.feature_unavailable, name="forgot_password_request"),
        path("password/reset/", core_views.feature_unavailable, name="forgot_password_reset"),
    ]
    urlpatterns += [path("accounts/", include((accounts_fallback_patterns, "accounts"), namespace="accounts"))]

# Project-level convenient aliases
urlpatterns += [
    path("login/", _safe_redirect_to("accounts:login"), name="login"),
    path("logout/", _safe_redirect_to("accounts:logout"), name="logout"),
    path("accounts/logout/", _safe_redirect_to("accounts:logout"), name="accounts_logout"),
    path("password/forgot/", _safe_redirect_to("accounts:forgot_password_request"), name="password_forgot"),
    path("password/reset/", _safe_redirect_to("accounts:forgot_password_reset"), name="password_reset_flow"),
    path("password_reset/", _safe_redirect_to("accounts:forgot_password_reset"), name="password_reset"),
]

# Session probes
urlpatterns += [
    path("session-probe/set", session_set, name="session_probe_set"),
    path("session-probe/get", session_get, name="session_probe_get"),
]

# Time pages (updated to match inventory URL names)
urlpatterns += [
    path("time/check-in/", RedirectView.as_view(pattern_name="inventory:time_checkin", permanent=False)),
    path("time/logs/", RedirectView.as_view(pattern_name="inventory:time_logs", permanent=False)),
]

# CSV/Import hooks (if present)
export_inventory_csv = _try_from("circuitcity.inventory.views_export", "export_inventory_csv") or \
                       _try_from("inventory.views_export", "export_inventory_csv")
export_audits_csv = _try_from("circuitcity.inventory.views_export", "export_audits_csv") or \
                    _try_from("inventory.views_export", "export_audits_csv")
import_opening_stock = _try_from("circuitcity.inventory.views_import", "import_opening_stock") or \
                       _try_from("inventory.views_import", "import_opening_stock")
if export_inventory_csv:
    urlpatterns.append(path("exports/inventory.csv", export_inventory_csv, name="export_inventory_csv"))
if export_audits_csv:
    urlpatterns.append(path("exports/audits.csv", export_audits_csv, name="export_audits_csv"))
if import_opening_stock:
    urlpatterns.append(path("imports/opening-stock/", import_opening_stock, name="import_opening_stock"))

# ======================================================================================
# Response normalizer + auto-select helpers
# ======================================================================================
def _redirect_to_join():
    target = _first_working_reverse(("tenants:activate_mine", "tenants:choose_business", "tenants:join_business", "tenants:join"))
    if target:
        return redirect(target)
    return redirect("/tenants/activate-mine/")


def _looks_like_biz_loc_tuple(val):
    if not isinstance(val, tuple) or len(val) == 0:
        return False
    first = val[0]
    return not isinstance(first, (str, bytes)) and hasattr(first, "id")


def _set_active_on_request_and_session(request, biz, loc=None):
    try:
        request.active_business = biz
        request.active_business_id = getattr(biz, "id", None)
        request.session["active_business_id"] = getattr(biz, "id", None)
        request.session["biz_id"] = getattr(biz, "id", None)
        if loc:
            request.active_location = loc
            request.active_location_id = getattr(loc, "id", None)
    except Exception:
        pass


def _auto_select_single_membership(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return None
    try:
        TenantsModels = _try_import("tenants.models") or _try_import("circuitcity.tenants.models")
        if not TenantsModels:
            return None

        BM = getattr(TenantsModels, "BusinessMembership", None) or getattr(TenantsModels, "Membership", None)
        Business = getattr(TenantsModels, "Business", None)
        if not BM or not Business:
            return None

        qs = BM.objects.filter(user=request.user)
        for f in ("is_active", "active", "accepted"):
            if f in [fld.name for fld in BM._meta.fields]:
                try:
                    qs = qs.filter(**{f: True})
                except Exception:
                    pass

        count = qs.count()
        if count != 1:
            return None

        m = qs.first()
        biz = getattr(m, "business", None)
        if biz:
            _set_active_on_request_and_session(request, biz)
            return biz
        return None
    except Exception:
        return None


def _normalize_response(request, resp):
    if isinstance(resp, HttpResponseBase):
        return resp

    if isinstance(resp, tuple):
        if len(resp) >= 1 and (resp[0] is None or resp[0] == ""):
            return _redirect_to_join()

        template = resp[0]
        if isinstance(template, (str, bytes)):
            context = resp[1] if len(resp) > 1 and isinstance(resp[1], dict) else {}
            http = render(request, template, context)
            if len(resp) > 2 and isinstance(resp[2], int):
                http.status_code = resp[2]
            return http
        return HttpResponse(str(resp))

    return HttpResponse(str(resp))


def _call_inventory_view_with_legacy_guard(request, view_name, *args, **kwargs):
    from inventory import views as inv
    tenants_get_active = _try_from("circuitcity.tenants.utils", "get_active_business") or \
                         _try_from("tenants.utils", "get_active_business")

    biz = getattr(request, "active_business", None)
    if not biz and tenants_get_active:
        try:
            biz = tenants_get_active(request)
            if biz:
                _set_active_on_request_and_session(request, biz)
        except Exception:
            biz = None

    if not biz:
        auto = _auto_select_single_membership(request)
        if auto:
            biz = auto

    if hasattr(inv, "_require_active_business"):
        try:
            b, l = inv._require_active_business(request)
            if b and not getattr(request, "active_business", None):
                _set_active_on_request_and_session(request, b, l)
            elif l:
                _set_active_on_request_and_session(request, getattr(request, "active_business", None), l)
        except Exception:
            pass

    view = getattr(inv, view_name)
    resp = view(request, *args, **kwargs)

    if _looks_like_biz_loc_tuple(resp):
        b = resp[0]
        l = resp[1] if len(resp) > 1 else None
        _set_active_on_request_and_session(request, b, l)
        try:
            resp = view(request, *args, **kwargs)
        except Exception:
            return _redirect_to_join()

    if isinstance(resp, tuple) and len(resp) >= 1 and (resp[0] is None or resp[0] == ""):
        return _redirect_to_join()

    return _normalize_response(request, resp)


# ======================================================================================
# Hard-bind stock list & dashboard entries
# ======================================================================================
def _stock_list_entry(request, *args, **kwargs):
    try:
        return _call_inventory_view_with_legacy_guard(request, "stock_list", *args, **kwargs)
    except Exception:
        from inventory.views import stock_list
        return _normalize_response(request, stock_list(request, *args, **kwargs))


def _inventory_dashboard_entry(request, *args, **kwargs):
    try:
        return _call_inventory_view_with_legacy_guard(request, "inventory_dashboard", *args, **kwargs)
    except Exception:
        from inventory.views import inventory_dashboard
        return _normalize_response(request, inventory_dashboard(request, *args, **kwargs))


urlpatterns += [
    path("inventory/list/", _stock_list_entry, name="inventory_stock_list"),
    re_path(r"^inventory/list/$", _stock_list_entry, name="inventory_stock_list_re"),
    path("inventory/dashboard/", _inventory_dashboard_entry, name="inventory_dashboard"),
]

# Include app urlconfs (safe)
urlpatterns += safe_include("inventory/", "inventory.urls", "inventory")
urlpatterns += safe_include("tenants/",   "tenants.urls", "tenants")
urlpatterns += safe_include("dashboard/", "dashboard.urls", "dashboard")
urlpatterns += safe_include("layby/",     "layby.urls", "layby")

# >>> Simulator (namespaced; defensive import)
_sim_urls_mod = _try_import("simulator.urls") or _try_import("circuitcity.simulator.urls")
if _sim_urls_mod and hasattr(_sim_urls_mod, "urlpatterns"):
    app_name = getattr(_sim_urls_mod, "app_name", "simulator")
    urlpatterns += [path("simulator/", include((_sim_urls_mod.urlpatterns, app_name), namespace="simulator"))]

# --- Local fallback for activate-mine if tenants urls don’t expose it yet ---
if _activate_mine_view:
    urlpatterns += [
        path("tenants/activate-mine/", _activate_mine_view, name="tenants_activate_mine_fallback"),
        path("tenants/activate/", RedirectView.as_view(url="/tenants/activate-mine/", permanent=False)),
    ]

# -------- Wallet include (try both import paths) --------
_wallet_urls_mod = _try_import("wallet.urls") or _try_import("circuitcity.wallet.urls")
if _wallet_urls_mod and hasattr(_wallet_urls_mod, "urlpatterns"):
    app_name = getattr(_wallet_urls_mod, "app_name", "wallet")
    urlpatterns += [path("wallet/", include((_wallet_urls_mod.urlpatterns, app_name), namespace="wallet"))]

# -------- Robust shim for /wallet/admin/ with DIAGNOSTICS --------
def _wallet_admin_shim(request, *args, **kwargs):
    tried = []
    last_exc_repr = None
    exports = {}

    def _attempt(modpath: str, attr: str):
        nonlocal last_exc_repr
        tried.append(f"{modpath}.{attr}")
        try:
            mod = import_module(modpath)
            exports[modpath] = [n for n in dir(mod) if n.lower().startswith(("admin", "agent", "admin_"))]
            obj = getattr(mod, attr, None)
            if obj is None:
                return None
            view_callable = getattr(obj, "as_view", None)
            return view_callable() if callable(view_callable) else obj
        except Exception as e:
            last_exc_repr = f"{e.__class__.__name__}: {e}"
            return None

    for mp, at in [
        ("wallet.views", "admin_home"),
        ("wallet.views", "AdminWalletHome"),
        ("circuitcity.wallet.views", "admin_home"),
        ("circuitcity.wallet.views", "AdminWalletHome"),
    ]:
        vc = _attempt(mp, at)
        if callable(vc):
            return vc(request, *args, **kwargs)

    details = [
        "Wallet admin is unavailable.",
        f"Tried: {', '.join(tried)}",
        f"Last import error: {last_exc_repr or '(none — modules imported but attributes missing)'}",
        f"Exports wallet.views: {', '.join(exports.get('wallet.views', [])) or '(module not importable)'}",
        f"Exports circuitcity.wallet.views: {', '.join(exports.get('circuitcity.wallet.views', [])) or '(module not importable)'}",
        "",
        "Hints:",
        "• Ensure wallet/ is on PYTHONPATH and has __init__.py",
        "• Confirm wallet/views.py defines either `AdminWalletHome` (class) or `admin_home = AdminWalletHome.as_view()`",
        "• If wallet.urls imports models that crash, fix that import so wallet.urls can be included.",
    ]
    return HttpResponse("<br>".join(details), status=404)

urlpatterns += [
    path("wallet/admin/", _wallet_admin_shim, name="wallet_admin_shim"),
    path("wallet/admin", RedirectView.as_view(url="/wallet/admin/", permanent=False)),
]

# If wallet.urls NOT included above, add a minimal namespaced fallback so `{% url 'wallet:admin_home' %}` doesn’t 500
if not _wallet_urls_mod:
    wallet_fallback_patterns = [
        path("admin/", _wallet_admin_shim, name="admin_home"),
    ]
    urlpatterns += [path("wallet/", include((wallet_fallback_patterns, "wallet"), namespace="wallet"))]

# >>> Global alias for `{% url 'wallet' %}` (legacy templates)
def _wallet_home_shim(_request):
    target = _first_working_reverse((
        "wallet:admin_home",
        "wallet:agent_wallet",
        "hq:wallet",
        "dashboard:agent_dashboard",
        "inventory:inventory_dashboard",
        "admin:index",
    ))
    return redirect(target or "/")

urlpatterns += [path("wallet/home-alias/", _wallet_home_shim, name="wallet")]

# =========================
# BILLING — ALWAYS NAMESPACED
# =========================
_billing_urls_mod = _try_import("billing.urls") or _try_import("circuitcity.billing.urls")
billing_admin_views = _try_import("billing.views_admin") or _try_import("circuitcity.billing.views_admin")

if _billing_urls_mod and hasattr(_billing_urls_mod, "urlpatterns"):
    app_name = getattr(_billing_urls_mod, "app_name", "billing")
    urlpatterns += [
        path("billing/", include((_billing_urls_mod.urlpatterns, app_name), namespace="billing"))
    ]
else:
    subs_view = getattr(billing_admin_views, "hq_subscriptions", None) if billing_admin_views else None
    if subs_view is None:
        subs_view = _wallet_home_shim  # reuse shim as generic target
    urlpatterns += [
        path(
            "billing/",
            include((
                [
                    path("hq/wallet/", _wallet_home_shim, name="wallet"),
                    path("hq/subscriptions/", subs_view, name="subscriptions"),
                    path("invoices/", lambda r: redirect("/hq/subscriptions/"), name="invoices"),
                ],
                "billing",
            ), namespace="billing"),
        )
    ]

# ---- HQ include or minimal fallback (stay strictly in HQ shell) ----
def _hq_businesses_shim(request):
    target = _first_working_reverse(("hq:businesses", "hq:subscriptions", "hq_subscriptions"))
    return redirect(target or "/hq/subscriptions/")

def _hq_invoices_shim(_request):
    target = _first_working_reverse(("hq:invoices", "hq:subscriptions", "hq_subscriptions"))
    return redirect(target or "/hq/subscriptions/")

def _hq_agents_shim(_request):
    target = _first_working_reverse(("hq:agents", "hq:subscriptions", "hq_subscriptions"))
    return redirect(target or "/hq/subscriptions/")

def _hq_home_fallback(_request):
    target = _first_working_reverse(("hq:home", "hq:subscriptions", "hq_subscriptions"))
    return redirect(target or "/hq/subscriptions/")

# Prefer the real HQ urls if present
if _try_import("hq.urls") or _try_import("circuitcity.hq.urls"):
    urlpatterns += safe_include("hq/", "hq.urls", "hq")
else:
    urlpatterns += [
        path(
            "hq/",
            include((
                [
                    path("subscriptions/", getattr(billing_admin_views, "hq_subscriptions", _hq_home_fallback), name="subscriptions"),
                    path("businesses/", _hq_businesses_shim, name="businesses"),
                    path("invoices/", _hq_invoices_shim, name="invoices"),
                    path("agents/", _hq_agents_shim, name="agents"),
                    path("", _hq_home_fallback, name="home"),
                    path("home/", _hq_home_fallback, name="home"),
                ],
                "hq",
            ), namespace="hq"),
        ),
    ]

# Optional explicit alias (kept; harmless since 'hq/' include matches earlier)
if billing_admin_views and hasattr(billing_admin_views, "hq_subscriptions"):
    urlpatterns += [path("hq/subscriptions/", billing_admin_views.hq_subscriptions, name="hq_subscriptions")]

# Global Search + Saved Views
core_search = _try_import("circuitcity.core.views_search") or _try_import("core.views_search")
core_savedview = _try_import("circuitcity.core.views_savedview") or _try_import("core.views_savedview")

def _empty_search(_req):
    return JsonResponse({"skus": [], "agents": [], "invoices": [], "transactions": []})

if core_search and hasattr(core_search, "api_global_search"):
    urlpatterns += [path("api/global-search/", core_search.api_global_search, name="api_global_search")]
else:
    urlpatterns += [path("api/global-search/", _empty_search, name="api_global_search")]

if core_savedview and hasattr(core_savedview, "api_saved_views"):
    urlpatterns += [path("api/saved-views/<str:scope>/", core_savedview.api_saved_views, name="api_saved_views")]

# DEBUG-only probes
if settings.DEBUG:
    urlpatterns += [
        path("__whoami__", __whoami__, name="__whoami__"),
        path("__render_login__", __render_login__, name="__render_login__"),
        path("__render_reports__", __render_reports__, name="__render_reports__"),
        path("__grep_soon__", __grep_soon__, name="__grep_soon__"),
    ]

# Back-compat URL names expected by older templates
urlpatterns += [
    path("stock/in/",  RedirectView.as_view(pattern_name="inventory:scan_in",  permanent=False), name="stock_in"),
    path("stock/out/", RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="stock_out"),
    path("stock/list/", RedirectView.as_view(pattern_name="inventory:stock_list", permanent=False), name="stock_list"),
]

# Back-compat for 'stock_trends'
def _stock_trends_shim(_request):
    target = _first_working_reverse((
        "inventory:stock_trends",
        "inventory:restock_heatmap",
        "inventory:inventory_dashboard",
        "inventory:stock_list",
        "dashboard:home",
    ))
    return redirect(target or "/inventory/")

urlpatterns += [path("stock/trends/", _stock_trends_shim, name="stock_trends")]

# Convenience short paths
urlpatterns += [
    path("sell/",        RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="sell_short"),
    path("sell/quick/",  RedirectView.as_view(pattern_name="inventory:sell_quick", permanent=False), name="sell_quick_short"),
    path("scan/",        RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="scan_short"),
    path("stock/",       RedirectView.as_view(pattern_name="inventory:stock_list", permanent=False), name="stock_short"),
]

# Legacy API path aliases for restock heatmap
urlpatterns += [
    path("inventory/restock-heatmap/", RedirectView.as_view(url="/inventory/api/restock-heatmap/", permanent=False)),
    path("inventory/api/restock_heatmap/", RedirectView.as_view(url="/inventory/api/restock-heatmap/", permanent=False)),
]

# Legacy API path alias for stock status (underscore -> hyphen)
urlpatterns += [
    path("inventory/api/stock_status/", RedirectView.as_view(url="/inventory/api/stock-status/", permanent=False)),
]

# ===== Product API aliases & fallbacks =====
urlpatterns += [
    path(
        "inventory/api/product/update_price/",
        RedirectView.as_view(url="/inventory/api/product/update-price/", permanent=False),
    ),
]

# Friendly fallbacks for unfinished endpoints if app route is missing
try:
    inv_urls_mod = _try_import("inventory.urls") or _try_import("circuitcity.inventory.urls")
    has_heatmap = has_stock_status = False
    has_prod_create = has_prod_update = False
    if inv_urls_mod and hasattr(inv_urls_mod, "urlpatterns"):
        has_heatmap = _patterns_have_name(inv_urls_mod.urlpatterns, "restock_heatmap_api")
        has_stock_status = _patterns_have_name(inv_urls_mod.urlpatterns, "api_stock_status")
        has_prod_create = _patterns_have_name(inv_urls_mod.urlpatterns, "api_product_create")
        has_prod_update = _patterns_have_name(inv_urls_mod.urlpatterns, "api_product_update_price")

    if not has_heatmap:
        urlpatterns += [path("inventory/api/restock-heatmap/", core_views.feature_unavailable, name="restock_heatmap_api")]
    if not has_stock_status:
        urlpatterns += [path("inventory/api/stock-status/", core_views.feature_unavailable, name="api_stock_status")]

    if not has_prod_create:
        _prod_create_view = _try_from("inventory.api_views", "api_product_create") or \
                            _try_from("circuitcity.inventory.api_views", "api_product_create")
        urlpatterns += [
            path("inventory/api/product/create/", _prod_create_view or core_views.feature_unavailable, name="api_product_create")
        ]
    if not has_prod_update:
        _prod_update_view = _try_from("inventory.api_views", "api_product_update_price") or \
                            _try_from("circuitcity.inventory.api_views", "api_product_update_price")
        urlpatterns += [
            path("inventory/api/product/update-price/", _prod_update_view or core_views.feature_unavailable, name="api_product_update_price")
        ]
except Exception:
    urlpatterns += [path("inventory/api/restock-heatmap/", core_views.feature_unavailable, name="restock_heatmap_api")]
    urlpatterns += [path("inventory/api/stock-status/", core_views.feature_unavailable, name="api_stock_status")]
    _prod_create_view = _try_from("inventory.api_views", "api_product_create") or \
                        _try_from("circuitcity.inventory.api_views", "api_product_create")
    _prod_update_view = _try_from("inventory.api_views", "api_product_update_price") or \
                        _try_from("circuitcity.inventory.api_views", "api_product_update_price")
    urlpatterns += [
        path("inventory/api/product/create/", _prod_create_view or core_views.feature_unavailable, name="api_product_create"),
        path("inventory/api/product/update-price/", _prod_update_view or core_views.feature_unavailable, name="api_product_update_price"),
    ]

# Static / media in DEBUG
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# --- Final safety: flatten any accidental nested lists to avoid resolver crashes ---
def _flatten_urlpatterns(items):
    flat = []
    for it in items:
        if isinstance(it, (list, tuple)):
            flat.extend(_flatten_urlpatterns(list(it)))
        else:
            flat.append(it)
    return flat

urlpatterns = _flatten_urlpatterns(urlpatterns)

# ======================================================================================
# Error handlers
# ======================================================================================
handler404 = "cc.views.page_not_found"
handler500 = "cc.views.server_error"
