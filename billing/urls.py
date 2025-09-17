# billing/urls.py
from django.urls import path

from . import views as v
from . import views_admin as va  # Super-admin dashboard & tools

app_name = "billing"

urlpatterns = [
    # ---------- Public / customer endpoints ----------
    path("subscribe/", v.subscribe, name="subscribe"),
    path("checkout/", v.checkout, name="checkout"),
    path("success/", v.success, name="success"),
    path("webhook/", v.webhook, name="webhook"),

    # Invoice utilities (inline preview/actions)
    path("invoice/<uuid:pk>/send/", v.invoice_send, name="invoice_send"),
    path("invoice/<uuid:pk>/download/", v.invoice_download, name="invoice_download"),

    # ---------- Super-admin tools ----------
    path("admin/", va.super_dashboard, name="admin_dashboard"),
    path("admin/webhooks/", va.webhook_logs, name="admin_webhook_logs"),
    path("admin/sub/<uuid:sub_id>/extend-trial/", va.extend_trial, name="admin_extend_trial"),
    path("admin/sub/<uuid:sub_id>/force-renew/", va.force_renew, name="admin_force_renew"),
    path("admin/invoice/<uuid:invoice_id>/resend/", va.resend_invoice, name="admin_resend_invoice"),
]
