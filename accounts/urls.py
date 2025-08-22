from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # Avatar uploads
    path("me/avatar/", views.upload_my_avatar, name="upload_my_avatar"),
    path("agents/<int:agent_id>/avatar/", views.upload_agent_avatar, name="upload_agent_avatar"),

    # Password reset (OTP code via email)
    path("password/forgot/", views.forgot_password_request, name="forgot_password_request"),
    path("password/reset/", views.forgot_password_reset, name="forgot_password_reset"),
]
