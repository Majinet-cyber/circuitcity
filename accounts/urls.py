# circuitcity/accounts/urls.py
from django.conf import settings
from django.urls import path, reverse_lazy
from django.contrib.auth.views import LoginView, LogoutView
from . import views

app_name = "accounts"

LOGIN_URL_LAZY = reverse_lazy("accounts:login")

urlpatterns = [
    # Auth
    path("login/", LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("signup/manager/", views.signup_manager, name="signup_manager"),

    # Logout (GET/POST)
    path("logout/", views.logout_get_or_post, name="logout"),
    path("logout/post/", LogoutView.as_view(next_page=LOGIN_URL_LAZY), name="logout_post"),

    # OTP
    path("otp/", views.otp_challenge, name="otp_challenge"),

    # Password
    path("password/forgot/", views.forgot_password_request_view, name="forgot_password_request"),
    path("password/reset/",  views.forgot_password_verify_view,  name="forgot_password_reset"),

    # Legacy shims
    path("password/change/",       views.settings_security, name="password_change_shim"),
    path("password/change/done/",  views.settings_security, name="password_change_done_shim"),

    # Avatars
    path("avatar/me/", views.upload_my_avatar, name="upload_my_avatar"),
    path("avatar/<int:agent_id>/", views.upload_agent_avatar, name="upload_agent_avatar"),

    # Admin
    path("admin/unblock/", views.admin_unblock_user_view, name="admin_unblock_user"),

    # Settings
    path("settings/",             views.settings_unified,  name="settings_unified"),
    path("settings/home/",        views.settings_home,     name="settings_home"),
    path("settings/profile/",     views.settings_profile,  name="settings_profile"),
    path("settings/security/",    views.settings_security, name="settings_security"),
    path("settings/sessions/",    views.settings_sessions, name="settings_sessions"),
    path("settings/sessions/terminate-others/", views.terminate_other_sessions, name="terminate_other_sessions"),
]

# Optional short aliases
urlpatterns += [
    path("signin/",  LoginView.as_view(template_name="accounts/login.html"), name="signin_alias"),
    path("signout/", views.logout_get_or_post, name="signout_alias"),
]

# Debug-only template probe
if settings.DEBUG:
    urlpatterns += [
        path("login/_which/", views.login_template_probe, name="login_template_probe"),
    ]
