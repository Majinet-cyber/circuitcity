from django.urls import path
from . import views

urlpatterns = [
    path("", views.sales_home, name="sales_home"),
    path("api/queue-status/", views.sales_queue_status, name="sales_queue_status"),
    path("claim/", views.sales_claim_next, name="sales_claim_next"),
    path("applications/", views.sales_applications, name="sales_applications"),
    path("queue-rules/", views.sales_queue_rules, name="sales_queue_rules"),
    path("wallet/", views.sales_wallet, name="sales_wallet"),

    # Review steps
    path("applications/<int:app_id>/", views.sales_review_summary, name="sales_review_summary"),
    path("applications/<int:app_id>/identity/", views.sales_identity_check, name="sales_identity_check"),
    path("applications/<int:app_id>/address/", views.sales_address_check, name="sales_address_check"),
    path("applications/<int:app_id>/customer-call/", views.sales_customer_call, name="sales_customer_call"),
    path("applications/<int:app_id>/income/", views.sales_income_check, name="sales_income_check"),
    path("applications/<int:app_id>/review/", views.sales_final_review, name="sales_final_review"),
    path("applications/<int:app_id>/confirm-approve/", views.sales_confirm_approve, name="sales_confirm_approve"),
]
