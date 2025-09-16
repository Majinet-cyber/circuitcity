# layby/urls.py
from django.urls import path
from . import views

app_name = "layby"

urlpatterns = [
    # Default: /layby/ → Agent dashboard
    path("", views.agent_dashboard, name="home"),

    # Agent area
    path("agent/", views.agent_dashboard, name="agent_dashboard"),
    path("agent/new/", views.agent_new, name="agent_new"),
    # Legacy alias some templates may reference: {% url 'agent_create' %}
    path("agent/create/", views.agent_new, name="agent_create"),

    # Agent: add payment for an order
    path("agent/<int:order_id>/add-payment/", views.agent_add_payment, name="agent_add_payment"),

    # Admin dashboard (customers + alerts + colors)
    path("admin/dashboard/", views.admin_dashboard, name="admin_dashboard"),

    # Admin: customer detail page (click from dashboard)
    path("admin/customer/", views.admin_customer, name="admin_customer"),
    # Back-compat alias (old name used in some templates)
    path("admin/customer/detail/", views.admin_customer, name="admin_customer_detail"),

    # Customer OTP flow
    path("customer/login/", views.customer_login, name="customer_login"),
    path("customer/send-otp/", views.customer_send_otp, name="customer_send_otp"),
    path("customer/verify-otp/", views.customer_verify_otp, name="customer_verify_otp"),
    path("portal/", views.customer_portal, name="customer_portal"),

    # Pay Now / QR
    path("pay/<int:order_id>/", views.pay_now, name="pay_now"),
    path("qr/<int:order_id>.png", views.qr_png, name="qr_png"),
]
