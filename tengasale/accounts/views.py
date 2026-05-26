from django.contrib.auth.views import LoginView, LogoutView

from .utils import is_hq, is_underwriter, role_redirect_url


class UserLoginView(LoginView):
    template_name = "accounts/login.html"

    def get_success_url(self):
        redirect_url = self.get_redirect_url()
        if redirect_url and self._redirect_matches_role(redirect_url):
            return redirect_url
        return role_redirect_url(self.request.user)

    def _redirect_matches_role(self, redirect_url):
        if is_hq(self.request.user):
            return True
        if is_underwriter(self.request.user):
            return redirect_url.startswith("/tengasale/underwriter/") or redirect_url.startswith("/approvals/")
        return not redirect_url.startswith("/tengasale/underwriter/") and not redirect_url.startswith("/tengasale/hq/")


class UserLogoutView(LogoutView):
    pass
