# circuitcity/accounts/urls.py
from django.conf import settings
from django.urls import path, reverse_lazy
from django.contrib.auth.views import LogoutView
from django.views.generic import RedirectView

from . import views

app_name = "accounts"

# Default landing after logout (used if ?next= isnâ€™t provided)
LOGIN_URL_LAZY = reverse_lazy("accounts:login")

urlpatterns = [
    # -------------------------------
    # Authentication
    # -------------------------------
    path("login/", views.login_view, name="login"),
    path("signup/manager/", views.signup_manager, name="signup_manager"),

    # Logout (supports GET or POST), plus a vanilla CBV option
    path("logout/", views.logout_get_or_post, name="logout"),
    path("logout/post/", LogoutView.as_view(next_page=LOGIN_URL_LAZY), name="logout_post"),

    # -------------------------------
    # OTP (One-Time Password)
    # -------------------------------
    path("otp/", views.otp_challenge, name="otp_challenge"),

    # -------------------------------
    # Password Management
    # -------------------------------
    # Step 1: enter identifier (email/username) â†’ email a code (if user exists)
    path("password/forgot/", views.forgot_password_request_view, name="forgot_password_request"),
    # Step 2: verify code + set the new password
    path("password/reset/", views.forgot_password_verify_view, name="forgot_password_reset"),

    # âœ… Aliases expected by templates / legacy Django auth URLs
    path(
        "password_reset/",
        RedirectView.as_view(pattern_name="accounts:forgot_password_reset", permanent=False),
        name="password_reset",
    ),
    path(
        "password_change/",
        RedirectView.as_view(pattern_name="accounts:settings_security", permanent=False),
        name="password_change",
    ),
    path(
        "password_change/done/",
        RedirectView.as_view(pattern_name="accounts:settings_security", permanent=False),
        name="password_change_done",
    ),
    path(
        "password_reset/done/",
        RedirectView.as_view(pattern_name="accounts:forgot_password_request", permanent=False),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        RedirectView.as_view(pattern_name="accounts:forgot_password_reset", permanent=False),
        name="password_reset_confirm",
    ),

    # -------------------------------
    # Avatar Uploads
    # -------------------------------
    path("avatar/me/", views.upload_my_avatar, name="upload_my_avatar"),
    path("avatar/<int:agent_id>/", views.upload_agent_avatar, name="upload_agent_avatar"),

    # -------------------------------
    # Admin Actions
    # -------------------------------
    path("admin/unblock/", views.admin_unblock_user_view, name="admin_unblock_user"),

    # -------------------------------
    # User Settings
    # -------------------------------
    path("settings/", views.settings_unified, name="settings_unified"),
    path("settings/home/", views.settings_home, name="settings_home"),
    path("settings/profile/", views.settings_profile, name="settings_profile"),
    path("settings/security/", views.settings_security, name="settings_security"),
    path("settings/sessions/", views.settings_sessions, name="settings_sessions"),
    path(
        "settings/sessions/terminate-others/",
        views.terminate_other_sessions,
        name="terminate_other_sessions",
    ),
]

# -------------------------------
# Optional Short Aliases
# -------------------------------
urlpatterns += [
    path("signin/", views.login_view, name="signin_alias"),
    path("signout/", views.logout_get_or_post, name="signout_alias"),
]

# -------------------------------
# Debug-only helpers
# -------------------------------
if settings.DEBUG:
    urlpatterns += [
        path("login/_which/", views.login_template_probe, name="login_template_probe"),
    ]


