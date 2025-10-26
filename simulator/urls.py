# circuitcity/simulator/urls.py
from django.urls import path
from django.http import JsonResponse
from types import SimpleNamespace

# ---- Role guard (admin/manager only) ----
try:
    from core.decorators import manager_required
except Exception:
    def manager_required(view_func):
        return view_func

# Import views defensively
try:
    from . import views as _views
except Exception:
    _views = SimpleNamespace()

try:
    from . import views_api as _api
except Exception:
    _api = SimpleNamespace()

app_name = "simulator"

# ---------- helpers ----------
def _stub(msg):
    def _fn(request, *args, **kwargs):
        return JsonResponse({"ok": False, "error": msg}, status=501)
    return _fn

def _get(src, name, msg=None):
    fn = getattr(src, name, None)
    return fn if callable(fn) else _stub(msg or f"{name} not implemented")

# ---------- resolve views safely ----------
_sim_home        = _get(_views, "sim_home",        "sim_home view missing")
_sim_new         = _get(_views, "sim_new",         "sim_new view missing")
_sim_detail      = _get(_views, "sim_detail",      "sim_detail view missing")
_sim_run         = _get(_views, "sim_run",         "sim_run view missing")
_sim_compare     = _get(_views, "sim_compare",     "sim_compare view missing")
_sim_results_api = _get(_views, "sim_results_api", "results API missing")

_api_run         = _get(_api,   "run_simulation",  "api_run missing")
_api_forecast    = _get(_api,   "ai_forecast_api", "ai_forecast missing")
_api_monte       = _get(_api,   "monte_carlo_api", "monte_carlo missing")

urlpatterns = [
    # ----------------------
    # Core scenario pages  (ADMIN/MANAGER ONLY)
    # ----------------------
    path("",                 manager_required(_sim_home),    name="home"),
    path("new/",             manager_required(_sim_new),     name="new"),
    path("<int:pk>/",        manager_required(_sim_detail),  name="detail"),
    path("<int:pk>/run/",    manager_required(_sim_run),     name="run"),
    # legacy aliases expected by older templates
    path("<int:pk>/run/",    manager_required(_sim_run),     name="sim_run"),
    path("new/",             manager_required(_sim_new),     name="sim_new"),
    path("<int:pk>/",        manager_required(_sim_detail),  name="sim_detail"),

    # ----------------------
    # Comparison & latest-results API (ADMIN/MANAGER ONLY)
    # ----------------------
    path("compare/",                  manager_required(_sim_compare),     name="compare"),
    path("compare/",                  manager_required(_sim_compare),     name="sim_compare"),  # alias
    path("api/<int:pk>/results.json", manager_required(_sim_results_api), name="results_api"),

    # ----------------------
    # Programmatic APIs for JS frontends (ADMIN/MANAGER ONLY)
    # ----------------------
    path("api/run/",   manager_required(_api_run),      name="api_run"),
    path("api/runs/",  manager_required(_api_run),      name="api_runs"),  # alias used by some templates
    path("api/<int:pk>/forecast/", manager_required(_api_forecast), name="ai_forecast"),
    path("api/monte-carlo/",       manager_required(_api_monte),    name="monte_carlo"),
]


