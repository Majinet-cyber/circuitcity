from django.contrib.auth.views import LoginView, LogoutView


class UserLoginView(LoginView):
    template_name = "accounts/login.html"


class UserLogoutView(LogoutView):
    pass