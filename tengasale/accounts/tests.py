from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.conf import settings
from django.test import TestCase
from django.urls import resolve, reverse


class LoginTemplateTests(TestCase):
    def test_login_url_returns_200(self):
        response = self.client.get("/accounts/login/")

        self.assertEqual(response.status_code, 200)

    def test_login_page_renders_expected_template(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_login_page_contains_forgot_password_link(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, "Forgot password?")
        self.assertContains(response, reverse("password_reset"))


class AccountUrlTests(TestCase):
    def test_login_url_name_resolves(self):
        self.assertEqual(reverse("login"), "/accounts/login/")

    def test_password_reset_resolves_and_returns_200(self):
        response = self.client.get(reverse("password_reset"))

        self.assertEqual(resolve(reverse("password_reset")).url_name, "password_reset")
        self.assertEqual(response.status_code, 200)

    def test_password_reset_done_resolves(self):
        self.assertEqual(
            resolve(reverse("password_reset_done")).url_name,
            "password_reset_done",
        )

    def test_password_reset_complete_resolves(self):
        self.assertEqual(
            resolve(reverse("password_reset_complete")).url_name,
            "password_reset_complete",
        )


class LogoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="merchant",
            password="test-pass-123",
        )

    def test_logout_via_post_redirects_to_login(self):
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"))

    def test_logout_via_get_returns_method_not_allowed(self):
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get(reverse("logout"))

        self.assertEqual(response.status_code, 405)


class StaticFileTests(TestCase):
    def test_local_css_is_configured_and_findable(self):
        static_dir = settings.BASE_DIR / "static"

        self.assertIn(static_dir, settings.STATICFILES_DIRS)
        self.assertTrue((static_dir / "css" / "style.css").exists())
        self.assertIsNotNone(finders.find("css/style.css"))
