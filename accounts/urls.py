# accounts/urls.py
from django.conf import settings
from django.urls import path, reverse_lazy
from django.contrib.auth.views import LogoutView

from . import views

app_name = "accounts"

# Default landing after logout (used if ?next= isn’t provided)
LOGIN_URL_LAZY = reverse_lazy("accounts:login")

urlpatterns = [
    # -------------------------------
    # Authentication
    # -------------------------------
    # Our custom login view (renders accounts/login.html, redirects if already authenticated)
    path("login/", views.login_view, name="login"),

    # Logout that accepts GET or POST (implemented in views.logout_get_or_post)
    path("logout/", views.logout_get_or_post, name="logout"),

    # Fallback POST-only endpoint (Django’s built-in) in case anything still posts here explicitly
    path("logout/post/", LogoutView.as_view(next_page=LOGIN_URL_LAZY), name="logout_post"),

    # -------------------------------
    # Password Management
    # -------------------------------
    path("password/forgot/", views.forgot_password_request_view, name="forgot_password_request"),
    path("password/reset/",  views.forgot_password_verify_view,  name="forgot_password_reset"),

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
    # User Settings (Profile, Security, Sessions)
    # -------------------------------
    path("settings/",                            views.settings_home,          name="settings_home"),
    path("settings/profile/",                    views.settings_profile,       name="settings_profile"),
    path("settings/security/",                   views.settings_security,      name="settings_security"),
    path("settings/sessions/",                   views.settings_sessions,      name="settings_sessions"),
    path("settings/sessions/terminate-others/",  views.terminate_other_sessions, name="terminate_other_sessions"),
]

# Optional short aliases some links might use
urlpatterns += [
    path("signin/",  views.login_view,                   name="signin_alias"),
    path("signout/", views.logout_get_or_post,           name="signout_alias"),
]

# 🔎 Debug-only endpoint to confirm which login template is rendering
if settings.DEBUG:
    urlpatterns += [
        path("login/_which/", views.login_template_probe, name="login_template_probe"),
    ]
