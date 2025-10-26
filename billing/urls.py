# billing/urls.py
from django.urls import path
from django.views.generic import RedirectView

from . import views as v
from . import views_admin as va  # Keep import in case you still use parts of it.

app_name = "billing"

urlpatterns = [
    # ------------------------------------------------------------------
    # Public / customer endpoints
    # ------------------------------------------------------------------
    path("subscribe/", v.subscribe, name="subscribe"),
    path("checkout/",  v.checkout,  name="checkout"),
    path("success/",   v.success,   name="success"),
    path("webhook/",   v.webhook,   name="webhook"),

    # NEW: one-click plan selection + per-plan page
    path("select-plan/", v.select_plan, name="select_plan"),
    path("plan/<slug:slug>/", v.plan_detail, name="plan_detail"),

    # Invoice utilities (inline preview/actions)
    path("invoice/<uuid:pk>/send/",     v.invoice_send,     name="invoice_send"),
    path("invoice/<uuid:pk>/download/", v.invoice_download, name="invoice_download"),
    # Compatibility for projects that used INT primary keys on invoices
    path("invoice/<int:pk>/send/",      v.invoice_send,     name="invoice_send_int"),
    path("invoice/<int:pk>/download/",  v.invoice_download, name="invoice_download_int"),

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
]


