# circuitcity/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from importlib import import_module

# Import inventory views for fallbacks
from inventory import views as inv_views

# Prefer inventory.api.predictions_summary if present; otherwise use views.api_predictions
try:
    api_mod = import_module("inventory.api")
    prediction_view = getattr(api_mod, "predictions_summary", inv_views.api_predictions)
except Exception:
    prediction_view = inv_views.api_predictions

urlpatterns = [
    path("admin/", admin.site.urls),

    # App
    path("inventory/", include(("inventory.urls", "inventory"), namespace="inventory")),

    # ---- Hard aliases so these NEVER 404 even if the app's urls module differs ----
    re_path(r"^inventory/api/predictions/?$",    prediction_view),
    re_path(r"^inventory/api/predictions/v2/?$", inv_views.api_predictions),
    re_path(r"^inventory/api/cash[-_]overview/?$", inv_views.api_cash_overview),
]
