# billing/urls.py
from django.urls import path
from django.views.generic import RedirectView

from . import views as v
from . import views_admin as va  # Keep import in case you still use parts of it.
from . import views_billing_hub as vbh  # Premium billing hub
from . import views_invoice as vi  # Invoice management
from . import views_paychangu as vpc  # PayChangu
from . import views_providers as vp  # Stripe + Pesapal
from . import views_receipt as vreceipt  # Receipt PDFs
from . import views_reconciliation as vr  # Reconciliation (staff-only)

app_name = "billing"

urlpatterns = [
    # ------------------------------------------------------------------
    # Public / customer endpoints
    # ------------------------------------------------------------------
    path("plans/", v.subscribe, name="plans"),  # Alias for sidebar navigation
    path("subscribe/", v.subscribe, name="subscribe"),
    path("manage/", v.manage, name="manage"),  # Manage subscription (legacy)
    path("hub/", vbh.billing_hub, name="billing_hub"),  # Premium billing hub
    path("checkout/", v.checkout, name="checkout"),
    path("success/", v.success, name="success"),
    path("webhook/", v.webhook, name="webhook"),
    path("trial-expired/", v.trial_expired, name="trial_expired"),
    path("invoices/", vi.invoice_list, name="invoices"),
    # NEW: one-click plan selection + per-plan page
    path("select-plan/", v.select_plan, name="select_plan"),
    path("plan/<slug:slug>/", v.plan_detail, name="plan_detail"),
    # Subscription upgrade flow
    path("upgrade/start/<slug:to_plan_code>/", v.upgrade_start, name="upgrade_start"),
    # ------------------------------------------------------------------
    # Stripe checkout & webhooks
    # ------------------------------------------------------------------
    path("stripe/checkout/", vp.stripe_checkout, name="stripe_checkout"),
    path("stripe/success/", vp.stripe_success, name="stripe_success"),
    path("stripe/webhook/", vp.stripe_webhook, name="stripe_webhook"),
    # ------------------------------------------------------------------
    # Pesapal checkout, callback & IPN
    # ------------------------------------------------------------------
    path("pesapal/checkout/", vp.pesapal_checkout, name="pesapal_checkout"),
    path("pesapal/callback/", vp.pesapal_callback, name="pesapal_callback"),
    path("pesapal/ipn/", vp.pesapal_ipn, name="pesapal_ipn"),
    # ------------------------------------------------------------------
    # PayChangu checkout, webhook & return
    # ------------------------------------------------------------------
    path("paychangu/initiate/", vpc.paychangu_initiate, name="paychangu_initiate"),
    path("paychangu/webhook/", vpc.paychangu_webhook, name="paychangu_webhook"),
    path("paychangu/return/", vpc.paychangu_return, name="paychangu_return"),
    path("paychangu/callback/", vpc.paychangu_callback, name="paychangu_callback"),
    path("paychangu/payment-status/", vpc.paychangu_payment_status, name="paychangu_payment_status"),
    path("api/payment-status/", v.payment_status_api, name="payment_status_api"),
    # Invoice utilities (inline preview/actions)
    path("invoice/<uuid:pk>/send/", vi.invoice_send, name="invoice_send"),
    path("invoice/<uuid:pk>/download/", vi.invoice_download, name="invoice_download"),
    # Receipt PDFs
    path("payments/<uuid:payment_id>/receipt/pdf/", vreceipt.payment_receipt_pdf, name="payment_receipt_pdf"),
    path(
        "transactions/<uuid:transaction_id>/receipt/pdf/",
        vreceipt.transaction_receipt_pdf,
        name="transaction_receipt_pdf",
    ),
    # Compatibility for projects that used INT primary keys on invoices
    path("invoice/<int:pk>/send/", vi.invoice_send, name="invoice_send_int"),
    path("invoice/<int:pk>/download/", vi.invoice_download, name="invoice_download_int"),
    # ------------------------------------------------------------------
    # HQ subscriptions (shortcuts / backward compatibility)
    # We now rely on the canonical views under the `hq` app.
    # These routes simply redirect to the new namespaced endpoints.
    # ------------------------------------------------------------------
    # List page
    path(
        "hq/subscriptions/",
        RedirectView.as_view(pattern_name="hq:subscriptions", permanent=False),
        name="hq_subscriptions",
    ),
    # Trial / lifecycle actions (UUID pk)
    path(
        "hq/sub/<uuid:pk>/extend-trial/",
        RedirectView.as_view(pattern_name="hq:sub_extend", permanent=False),
        name="hq_extend_trial",
    ),
    path(
        "hq/sub/<uuid:pk>/revoke-trial/",
        RedirectView.as_view(pattern_name="hq:sub_revoke_trial", permanent=False),
        name="hq_revoke_trial",
    ),
    path(
        "hq/sub/<uuid:pk>/activate-now/",
        RedirectView.as_view(pattern_name="hq:sub_activate_now", permanent=False),
        name="hq_activate_now",
    ),
    path(
        "hq/sub/<uuid:pk>/set-plan/",
        RedirectView.as_view(pattern_name="hq:sub_set_plan", permanent=False),
        name="hq_set_plan",
    ),
    # Same actions (INT pk) â€” preserves older links
    path(
        "hq/sub/<int:pk>/extend-trial/",
        RedirectView.as_view(pattern_name="hq:sub_extend", permanent=False),
        name="hq_extend_trial_int",
    ),
    path(
        "hq/sub/<int:pk>/revoke-trial/",
        RedirectView.as_view(pattern_name="hq:sub_revoke_trial", permanent=False),
        name="hq_revoke_trial_int",
    ),
    path(
        "hq/sub/<int:pk>/activate-now/",
        RedirectView.as_view(pattern_name="hq:sub_activate_now", permanent=False),
        name="hq_activate_now_int",
    ),
    path(
        "hq/sub/<int:pk>/set-plan/",
        RedirectView.as_view(pattern_name="hq:sub_set_plan", permanent=False),
        name="hq_set_plan_int",
    ),
    # ------------------------------------------------------------------
    # Legacy "admin" shortcuts â€” keep for compatibility, redirect to HQ
    # ------------------------------------------------------------------
    path(
        "admin/",
        RedirectView.as_view(pattern_name="hq:subscriptions", permanent=False),
        name="admin_dashboard",
    ),
    path(
        "admin/sub/<uuid:pk>/extend-trial/",
        RedirectView.as_view(pattern_name="hq:sub_extend", permanent=False),
        name="admin_extend_trial",
    ),
    path(
        "admin/sub/<uuid:pk>/revoke-trial/",
        RedirectView.as_view(pattern_name="hq:sub_revoke_trial", permanent=False),
        name="admin_revoke_trial",
    ),
    # INT variants for very old links
    path(
        "admin/sub/<int:pk>/extend-trial/",
        RedirectView.as_view(pattern_name="hq:sub_extend", permanent=False),
        name="admin_extend_trial_int",
    ),
    path(
        "admin/sub/<int:pk>/revoke-trial/",
        RedirectView.as_view(pattern_name="hq:sub_revoke_trial", permanent=False),
        name="admin_revoke_trial_int",
    ),
    # Reconciliation dashboard (staff-only)
    path("admin/reconciliation/", vr.reconciliation_dashboard, name="reconciliation_dashboard"),
]
