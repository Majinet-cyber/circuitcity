# inventory/urls_router.py
"""
URL patterns for business-aware router endpoints.
These routes prevent vertical leakage by redirecting to the correct vertical-specific URLs.
"""
from django.urls import path

try:
    from . import views_router
except ImportError:
    views_router = None

app_name = "app_router"

urlpatterns = []

if views_router:
    urlpatterns = [
        path("home/", views_router.app_home, name="home"),
        path("scan/", views_router.app_scan, name="scan"),
        path("sell/", views_router.app_sell, name="sell"),
        path("stock/", views_router.app_stock, name="stock"),
        path("wallet/", views_router.app_wallet, name="wallet"),
        path("sim/", views_router.app_sim, name="sim"),
        path("analytics/", views_router.app_analytics, name="analytics"),
    ]

# ======================================================================================
# URL COMPATIBILITY ALIASES (SSOT)
# Import compatibility URL patterns from cc.urls_compat to ensure consistent naming
# across all URLConfs. This allows tests using reverse('stock'), reverse('sell'), etc.
# to work correctly when router URLConf is loaded.
# ======================================================================================
try:
    from cc.urls_compat import get_compat_urlpatterns
    urlpatterns += get_compat_urlpatterns()
except ImportError:
    pass  # If cc.urls_compat not available, skip (shouldn't happen in normal operation)