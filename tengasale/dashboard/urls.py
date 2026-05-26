from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("home/", views.home, name="home_redirect"),
    path("merchant/", RedirectView.as_view(pattern_name="merchant_dashboard", permanent=False), name="merchant_shortcut"),
    path("underwriter/", RedirectView.as_view(pattern_name="underwriter_dashboard", permanent=False), name="underwriter_shortcut"),
    path("hq/", RedirectView.as_view(pattern_name="hq_dashboard", permanent=False), name="hq_shortcut"),
    path("tengasale/merchant/", views.merchant_dashboard, name="merchant_dashboard"),
    path("tengasale/hq/", views.hq_dashboard, name="hq_dashboard"),
    path("tengasale/hq/users/", views.hq_users, name="hq_users"),
    path("tengasale/hq/users/<int:user_id>/", views.hq_user_edit, name="hq_user_edit"),
    path("tengasale/hq/deals/", views.hq_deals, name="hq_deals"),
    path("tengasale/hq/applications/", views.hq_applications, name="hq_applications"),
    path("tengasale/hq/underwriter-queue/", views.hq_underwriter_queue, name="hq_underwriter_queue"),
    path("tengasale/hq/commissions/", views.hq_commissions, name="hq_commissions"),
    path("tengasale/hq/reports/", views.hq_reports, name="hq_reports"),
    path("tengasale/hq/preview/merchant/", views.hq_merchant_preview, name="hq_merchant_preview"),
    path("tengasale/hq/preview/underwriter/", views.hq_underwriter_preview, name="hq_underwriter_preview"),
]
