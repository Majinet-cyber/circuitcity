from django.urls import path
from . import views

app_name = "staticpages"

urlpatterns = [
    path("", views.home, name="home"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("data-deletion/", views.data_deletion, name="data_deletion"),
    path("about/", views.about, name="about"),
    path("pricing/", views.pricing, name="pricing"),
    path("contact/", views.contact, name="contact"),
    path("simulator/", views.simulator, name="simulator"),
    path("join/", views.join_team, name="join_team"),
    # Public API endpoints
    path("api/stats/", views.platform_stats_api, name="platform_stats_api"),
    path("api/landing-metrics/", views.landing_metrics_api, name="landing_metrics_api"),
    # Onboarding guides
    path("onboarding/manager/", views.onboarding_manager, name="onboarding_manager"),
    path("onboarding/hq/", views.onboarding_hq, name="onboarding_hq"),
    path("onboarding/hq/pdf/", views.hq_onboarding_pdf, name="hq_onboarding_pdf"),
]
