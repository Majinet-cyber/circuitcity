from django.urls import path

from . import views


urlpatterns = [
    path("", views.legacy_underwriter_dashboard, name="legacy_approvals_home"),
    path("claim-next/", views.legacy_claim_next, name="legacy_claim_next"),
    path("review/<int:app_id>/", views.legacy_review_application, name="legacy_review_application"),
]
