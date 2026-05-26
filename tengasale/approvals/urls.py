from django.urls import path
from . import views

urlpatterns = [
    path("", views.underwriter_dashboard, name="underwriter_dashboard"),
    path("", views.underwriter_dashboard, name="manager_home"),
    path("claim-next/", views.claim_next, name="underwriter_claim_next"),
    path("claim-next/", views.claim_next, name="claim_next"),
    path("review/<int:app_id>/", views.review_application, name="underwriter_review_application"),
    path("review/<int:app_id>/", views.review_application, name="review_application"),
    path("review/<int:app_id>/address-check/", views.address_check, name="underwriter_address_check"),
    path("review/<int:app_id>/income-check/", views.income_check, name="underwriter_income_check"),
    path("review/<int:app_id>/confirm-approve/", views.confirm_approve, name="underwriter_confirm_approve"),
    path("active/", views.active_reviews, name="underwriter_active_reviews"),
    path("completed/", views.completed_reviews, name="underwriter_completed_reviews"),
]
