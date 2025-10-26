# core/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.urls import include, path, re_path
from django.views.generic import RedirectView

# Staff-only admin site (superusers/staff only)
try:
    from core.admin_site import staff_admin_site
except Exception:  # pragma: no cover
    staff_admin_site = None  # type: ignore


def healthz(_request):
    return HttpResponse("ok", content_type="text/plain")


# Normalize ADMIN_URL and keep it non-obvious
_admin_url = getattr(settings, "ADMIN_URL", "__admin__/")
if not _admin_url.endswith("/"):
    _admin_url = f"{_admin_url}/"


urlpatterns = [
    # Health & favicon
    path("healthz", healthz, name="healthz"),
    re_path(r"^favicon\.ico$", RedirectView.as_view(url=f"{settings.STATIC_URL}favicon.ico", permanent=False)),

    # Core app routes
    path("", include("dashboard.urls")),            # / â†’ dashboard home
    path("accounts/", include("accounts.urls")),
    path("tenants/", include("tenants.urls")),
    path("inventory/", include("inventory.urls")),
    path("sales/", include("sales.urls")),
    path("reports/", include("ccreports.urls")),
    path("insights/", include("insights.urls")),
    path("wallet/", include("wallet.urls")),
    path("notifications/", include("notifications.urls")),
    path("cfo/", include("cfo.urls")),
    path("simulator/", include("simulator.urls")),
    path("layby/", include("layby.urls")),
    path("billing/", include("billing.urls")),
]

# ðŸ”’ Staff-only Django admin; managers/agents cannot access
if staff_admin_site is not None:
    urlpatterns.append(path(_admin_url, staff_admin_site.urls))

# Optional: Two-Factor URLs if enabled/installed
if "two_factor" in settings.INSTALLED_APPS:
    urlpatterns.insert(
        0,
        path("", include(("two_factor.urls", "two_factor"), namespace="two_factor")),
    )

# Optional: Debug Toolbar
if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar  # type: ignore
    urlpatterns.append(path("__debug__/", include(debug_toolbar.urls)))

# Serve static/media in dev
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


