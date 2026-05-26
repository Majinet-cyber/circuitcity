from django.urls import path
from . import views

urlpatterns = [
    path("", views.underwriter_dashboard, name="underwriter_dashboard"),
    path("", views.underwriter_dashboard, name="manager_home"),
    path("claim-next/", views.claim_next, name="underwriter_claim_next"),
    path("claim-next/", views.claim_next, name="claim_next"),
    path("queue/", views.queue, name="underwriter_queue"),
    path("review/<int:app_id>/", views.review_application, name="underwriter_review_application"),
    path("review/<int:app_id>/", views.review_application, name="review_application"),
    path("review/<int:app_id>/summary/", views.summary_review, name="underwriter_review_summary"),
    path("review/<int:app_id>/identity/", views.identity_check, name="underwriter_identity_check"),
    path("review/<int:app_id>/momo/", views.momo_check, name="underwriter_momo_check"),
    path("review/<int:app_id>/customer-call/", views.customer_call, name="underwriter_customer_call"),
    path("review/<int:app_id>/income/", views.income_check, name="underwriter_income_check"),
    path("review/<int:app_id>/location/", views.location_check, name="underwriter_location_check"),
    path("review/<int:app_id>/final/", views.final_review, name="underwriter_final_review"),
    path("review/<int:app_id>/correction/", views.correction_action, name="underwriter_correction_action"),
    path("review/<int:app_id>/address-check/", views.legacy_address_check, name="underwriter_address_check"),
    path("review/<int:app_id>/income-check/", views.legacy_income_check, name="underwriter_income_check_legacy"),
    path("review/<int:app_id>/confirm-approve/", views.confirm_approve, name="underwriter_confirm_approve"),
    path("active/", views.active_reviews, name="underwriter_active_reviews"),
    path("completed/", views.completed_reviews, name="underwriter_completed_reviews"),
]
