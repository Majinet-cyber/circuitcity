# accounts/urls.py
from django.urls import path
from django.http import JsonResponse
from . import views as V

app_name = "accounts"

def _stub(msg):
    def _fn(request, *args, **kwargs):
        return JsonResponse({"ok": False, "error": msg}, status=501)
    return _fn

def pick(name, alt=None, msg=None):
    fn = getattr(V, name, None)
    if callable(fn):
        return fn
    if alt and callable(alt):
        return alt
    return _stub(msg or f"{name} not implemented")

urlpatterns = [
    # Auth
    path("login/",  pick("login_view",  getattr(V, "login",  None), "login_view not implemented"),  name="login"),
    path("logout/", pick("logout_view", getattr(V, "logout", None), "logout_view not implemented"), name="logout"),
    path("register/", pick("register_view", None, "register_view not implemented"), name="register"),

    # Avatars
    path("me/avatar/",                 pick("upload_my_avatar",     None, "upload_my_avatar not implemented"),     name="upload_my_avatar"),
    path("agents/<int:agent_id>/avatar/", pick("upload_agent_avatar", None, "upload_agent_avatar not implemented"), name="upload_agent_avatar"),

    # Password reset (optional; won’t break if missing)
    path("password/forgot/", pick("forgot_password_request_view", None, "forgot_password_request_view not implemented"), name="forgot_password_request"),
    path("password/reset/",  pick("forgot_password_verify_view",  None, "forgot_password_verify_view not implemented"),  name="forgot_password_reset"),
]
