from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.contrib.staticfiles import finders
from django.conf import settings
from django.test import TestCase
from django.urls import resolve, reverse

from .utils import is_hq, is_merchant, is_underwriter, primary_role


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


class RoleHelperTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        for group_name in ["Merchant", "Underwriter", "Manager", "HQ"]:
            Group.objects.create(name=group_name)

    def user_with_group(self, username, group_name, **kwargs):
        user = self.User.objects.create_user(username=username, password="test-pass-123", **kwargs)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    def test_merchant_group_user_is_merchant(self):
        user = self.user_with_group("merchant-role", "Merchant")

        self.assertTrue(is_merchant(user))
        self.assertEqual(primary_role(user), "merchant")

    def test_underwriter_group_user_is_underwriter(self):
        user = self.user_with_group("underwriter-role", "Underwriter")

        self.assertTrue(is_underwriter(user))
        self.assertEqual(primary_role(user), "underwriter")

    def test_manager_group_user_is_underwriter_for_compatibility(self):
        user = self.user_with_group("manager-role", "Manager")

        self.assertTrue(is_underwriter(user))
        self.assertEqual(primary_role(user), "underwriter")

    def test_staff_non_superuser_is_underwriter(self):
        user = self.User.objects.create_user(username="staff-role", password="test-pass-123", is_staff=True)

        self.assertTrue(is_underwriter(user))
        self.assertEqual(primary_role(user), "underwriter")

    def test_hq_group_user_is_hq(self):
        user = self.user_with_group("hq-role", "HQ")

        self.assertTrue(is_hq(user))
        self.assertEqual(primary_role(user), "hq")

    def test_superuser_is_hq(self):
        user = self.User.objects.create_superuser(username="super-role", password="test-pass-123")

        self.assertTrue(is_hq(user))
        self.assertEqual(primary_role(user), "hq")

    def test_no_group_user_defaults_to_merchant_role(self):
        user = self.User.objects.create_user(username="no-group", password="test-pass-123")

        self.assertFalse(is_merchant(user))
        self.assertEqual(primary_role(user), "merchant")


class LoginRedirectTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        call_command("seed_roles")

    def make_user(self, username, group_name=None, **kwargs):
        user = self.User.objects.create_user(username=username, password="test-pass-123", **kwargs)
        if group_name:
            user.groups.add(Group.objects.get(name=group_name))
        return user

    def assert_login_redirects(self, username, expected_url):
        response = self.client.post(
            reverse("login"),
            {"username": username, "password": "test-pass-123"},
        )

        self.assertRedirects(response, expected_url, fetch_redirect_response=False)

    def test_merchant_login_redirects_to_merchant_portal(self):
        self.make_user("merchant-login", "Merchant")

        self.assert_login_redirects("merchant-login", reverse("merchant_dashboard"))

    def test_underwriter_login_redirects_to_underwriter_portal(self):
        self.make_user("underwriter-login", "Underwriter")

        self.assert_login_redirects("underwriter-login", reverse("underwriter_dashboard"))

    def test_staff_login_redirects_to_underwriter_portal(self):
        self.make_user("staff-login", is_staff=True)

        self.assert_login_redirects("staff-login", reverse("underwriter_dashboard"))

    def test_hq_login_redirects_to_hq_portal(self):
        self.make_user("hq-login", "HQ")

        self.assert_login_redirects("hq-login", reverse("hq_dashboard"))

    def test_superuser_login_redirects_to_hq_portal(self):
        self.User.objects.create_superuser(username="super-login", password="test-pass-123")

        self.assert_login_redirects("super-login", reverse("hq_dashboard"))


class SeedRolesCommandTests(TestCase):
    def test_seed_roles_creates_required_groups_idempotently(self):
        call_command("seed_roles")
        call_command("seed_roles")

        for group_name in ["Merchant", "Underwriter", "HQ"]:
            self.assertTrue(Group.objects.filter(name=group_name).exists())


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
