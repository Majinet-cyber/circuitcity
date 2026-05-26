from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render

from .utils import is_hq, is_merchant, is_underwriter, role_redirect_url


class UserLoginView(LoginView):
    template_name = "accounts/login.html"

    def get_success_url(self):
        redirect_url = self.get_redirect_url()
        if redirect_url and self._redirect_matches_role(redirect_url):
            return redirect_url
        return role_redirect_url(self.request.user)

    def _redirect_matches_role(self, redirect_url):
        if is_hq(self.request.user):
            return redirect_url.startswith("/tengasale/hq/") or redirect_url.startswith("/admin/")
        if is_underwriter(self.request.user):
            return redirect_url.startswith("/tengasale/underwriter/")
        if is_merchant(self.request.user):
            return (
                redirect_url.startswith("/tengasale/merchant/")
                or redirect_url.startswith("/applications/")
                or redirect_url.startswith("/earnings/")
                or redirect_url.startswith("/payments/")
                or redirect_url.startswith("/deals/")
                or redirect_url.startswith("/contracts/")
            )
        return False


class UserLogoutView(LogoutView):
    pass


def no_role(request):
    return render(request, "accounts/no_role.html", status=403)
