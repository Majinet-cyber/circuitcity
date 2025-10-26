# hq/urls.py
from django.urls import path
from django.views.generic import RedirectView
from . import views

# All URLs are namespaced as 'hq:<name>'
app_name = "hq"

urlpatterns = [
    # =========================
    # Canonical HQ Dashboard
    # =========================
    # /hq/ -> /hq/dashboard/
    path("", RedirectView.as_view(pattern_name="hq:dashboard", permanent=False)),
    path("dashboard/", views.dashboard, name="dashboard"),
    # Alias (same view)
    path("home/", views.dashboard, name="home"),

    # =========================
    # Lists
    # =========================
    path("businesses/",    views.businesses,    name="businesses"),
    path("subscriptions/", views.subscriptions, name="subscriptions"),
    path("invoices/",      views.invoices,      name="invoices"),
    path("agents/",        views.agents,        name="agents"),
    path("stock-trends/",  views.stock_trends,  name="stock_trends"),

    # =========================
    # Details
    # =========================
    path("businesses/<int:pk>/", views.business_detail, name="business_detail"),

    # =========================
    # Wallet (HQ shell)
    # =========================
    path("wallet/", views.wallet_home, name="wallet"),

    # ==================================================================
    # Subscription Admin Actions (used by HQ Subscriptions table buttons)
    #  - Provide endpoints for both UUID and INT primary keys.
    #  - Provide short aliases so templates can use stable names.
    # ==================================================================

    # ---- Extend trial / dates ----
    path("subscriptions/<uuid:pk>/extend/", views.sub_extend, name="sub_extend"),
    path("subscriptions/<int:pk>/extend/",  views.sub_extend, name="sub_extend_int"),

    # ---- Revoke trial (or pause) ----
    path("subscriptions/<uuid:pk>/revoke/", views.sub_revoke_trial, name="sub_revoke_trial"),
    path("subscriptions/<int:pk>/revoke/",  views.sub_revoke_trial, name="sub_revoke_trial_int"),
    # Friendly alias (same view) for templates that expect 'sub_revoke'
    path("subscriptions/<uuid:pk>/revoke-now/", views.sub_revoke_trial, name="sub_revoke"),
    path("subscriptions/<int:pk>/revoke-now/",  views.sub_revoke_trial, name="sub_revoke_int"),

    # ---- Activate immediately ----
    path("subscriptions/<uuid:pk>/activate-now/", views.sub_activate_now, name="sub_activate_now"),
    path("subscriptions/<int:pk>/activate-now/",  views.sub_activate_now, name="sub_activate_now_int"),
    # Friendly alias
    path("subscriptions/<uuid:pk>/activate/", views.sub_activate_now, name="sub_activate"),
    path("subscriptions/<int:pk>/activate/",  views.sub_activate_now, name="sub_activate_int"),

    # ---- Change / set plan ----
    path("subscriptions/<uuid:pk>/set-plan/", views.sub_set_plan, name="sub_set_plan"),
    path("subscriptions/<int:pk>/set-plan/",  views.sub_set_plan, name="sub_set_plan_int"),

    # =========================
    # Invoice actions
    # =========================
    path("invoices/<int:pk>/refund/", views.invoice_refund, name="invoice_refund"),

    # =========================
    # Trial adjustment / cancel (INT pk in your codebase)
    # =========================
    path("subscriptions/<int:pk>/adjust-trial/", views.sub_adjust_trial, name="sub_adjust_trial"),
    path("subscriptions/<int:pk>/cancel/",       views.sub_cancel,       name="sub_cancel"),
]

# ---------------------------------------------------------------------
# Optional: legacy â€œunnamespacedâ€ names for old templates doing {% url 'businesses' %}
# Only include if your project expects these globals under /hq/.
# ---------------------------------------------------------------------
legacy_urlpatterns = [
    path("",      RedirectView.as_view(pattern_name="hq:dashboard", permanent=False), name="dashboard"),
    path("home/", RedirectView.as_view(pattern_name="hq:home",      permanent=False), name="home"),

    path("businesses/",    views.businesses,    name="businesses"),
    path("subscriptions/", views.subscriptions, name="subscriptions"),
    path("invoices/",      views.invoices,      name="invoices"),
    path("agents/",        views.agents,        name="agents"),
    path("stock-trends/",  views.stock_trends,  name="stock_trends"),
    path("businesses/<int:pk>/", views.business_detail, name="business_detail"),
    path("wallet/", views.wallet_home, name="wallet"),
]

# Enable legacy globals by default; remove the next line if you don't need them.
urlpatterns += legacy_urlpatterns


