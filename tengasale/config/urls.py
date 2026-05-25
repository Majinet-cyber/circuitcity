from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    path("", include("dashboard.urls")),
    path("accounts/", include("accounts.urls")),
    path("applications/", include("applications.urls")),
    path("deals/", include("deals.urls")),
    path("earnings/", include("earnings.urls")),
    path("approvals/", include("approvals.urls")),
    path("contracts/", include("contracts.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
