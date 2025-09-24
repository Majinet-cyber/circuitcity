from django.urls import path
from . import views

app_name = "layby"

urlpatterns = [
    # Default: /layby/ → Agent dashboard (list / overview)
    path("", views.agent_dashboard, name="home"),

    # Canonical "create" endpoint used by sidebar/templates
    path("new/", views.agent_new, name="new"),

    # Agent area (explicit)
    path("agent/", views.agent_dashboard, name="agent_dashboard"),
    path("agent/new/", views.agent_new, name="agent_new"),
    # Legacy alias some templates may reference
    path("agent/create/", views.agent_new, name="agent_create"),

    # Agent: add payment for an order
    path("agent/<int:order_id>/add-payment/", views.agent_add_payment, name="agent_add_payment"),

    # Optional list pages (map to your current dashboard/list until dedicated views exist)
    path("agreements/", views.agent_dashboard, name="agreements"),
    path("payments/",   views.agent_dashboard, name="payments"),

    # Admin dashboard (customers + alerts + colors)
    path("admin/dashboard/", views.admin_dashboard, name="admin_dashboard"),

    # Admin: customer detail page (click from dashboard)
    path("admin/customer/",          views.admin_customer, name="admin_customer"),
    path("admin/customer/detail/",   views.admin_customer, name="admin_customer_detail"),  # back-compat

    # Customer OTP flow / portal
    path("customer/login/",      views.customer_login,      name="customer_login"),
    path("customer/send-otp/",   views.customer_send_otp,   name="customer_send_otp"),
    path("customer/verify-otp/", views.customer_verify_otp, name="customer_verify_otp"),
    path("portal/",              views.customer_portal,     name="customer_portal"),

    # Pay Now / QR
    path("pay/<int:order_id>/",    views.pay_now, name="pay_now"),
    path("qr/<int:order_id>.png",  views.qr_png,  name="qr_png"),
]
