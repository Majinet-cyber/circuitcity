from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.utils import assign_role


class HomePageTests(TestCase):
    def setUp(self):
        call_command("seed_roles")

    def create_user(self, username, group_name=None, **kwargs):
        user = get_user_model().objects.create_user(username=username, password="test-pass-123", **kwargs)
        if group_name:
            role = {"Merchant": "merchant", "Underwriter": "underwriter", "HQ": "hq"}[group_name]
            assign_role(user, role)
        return user

    def test_home_redirects_unauthenticated_users_to_login(self):
        response = self.client.get("/")

        self.assertRedirects(response, "/accounts/login/?next=/")

    def test_root_redirects_merchant_to_merchant_portal(self):
        self.create_user("merchant", "Merchant")
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get("/")

        self.assertRedirects(response, reverse("merchant_dashboard"))

    def test_root_redirects_underwriter_to_underwriter_portal(self):
        self.create_user("underwriter", "Underwriter")
        self.client.login(username="underwriter", password="test-pass-123")

        response = self.client.get("/")

        self.assertRedirects(response, reverse("underwriter_dashboard"))

    def test_root_redirects_hq_to_hq_portal(self):
        self.create_user("hq", "HQ")
        self.client.login(username="hq", password="test-pass-123")

        response = self.client.get("/")

        self.assertRedirects(response, reverse("hq_dashboard"))

    def test_merchant_can_access_merchant_dashboard(self):
        user = self.create_user("merchant", "Merchant")
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get(reverse("merchant_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Hi, {user.username}")
        self.assertContains(response, "TengaSale")
        self.assertContains(response, "You are now earning more with TengaSale.")
        self.assertContains(response, "VIEW ALL EARNINGS")
        self.assertContains(response, "Spin & Win")
        self.assertContains(response, "0 SPINS AVAILABLE")
        self.assertContains(response, "NEW APPLICATION")
        self.assertContains(response, f'href="{settings.TENGASALE_WHATSAPP_LINK}"')
        self.assertContains(response, 'class="icon-button whatsapp-button"')
        self.assertContains(response, 'aria-label="WhatsApp support"')
        self.assertContains(response, "notification-button")
        self.assertContains(response, "logout-button")
        self.assertNotContains(response, "Claim Next")

        content = response.content.decode()
        self.assertLess(content.index("whatsapp-button"), content.index("notification-button"))
        self.assertLess(content.index("notification-button"), content.index("logout-button"))

    def test_underwriter_visiting_merchant_dashboard_redirects_to_underwriter(self):
        self.create_user("underwriter", "Underwriter")
        self.client.login(username="underwriter", password="test-pass-123")

        response = self.client.get(reverse("merchant_dashboard"))

        self.assertRedirects(response, reverse("underwriter_dashboard"))

    def test_hq_can_access_hq_dashboard_only(self):
        self.create_user("hq", "HQ")
        self.client.login(username="hq", password="test-pass-123")

        hq_response = self.client.get(reverse("hq_dashboard"))
        merchant_response = self.client.get(reverse("merchant_dashboard"))

        self.assertEqual(hq_response.status_code, 200)
        self.assertContains(hq_response, "HQ")
        self.assertRedirects(merchant_response, reverse("hq_dashboard"))

    def test_hq_dashboard_does_not_show_preview_links_for_normal_hq_user(self):
        self.create_user("hq", "HQ")
        self.client.login(username="hq", password="test-pass-123")

        response = self.client.get(reverse("hq_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Developer Preview")
        self.assertNotContains(response, "Merchant Portal Preview")
        self.assertNotContains(response, "Underwriter Portal Preview")

    def test_hq_dashboard_shows_only_hq_links(self):
        self.create_user("hq-staff", "HQ", is_staff=True)
        self.client.login(username="hq-staff", password="test-pass-123")

        response = self.client.get(reverse("hq_dashboard"))

        self.assertContains(response, "Django Admin")
        self.assertContains(response, "Deals Management")
        self.assertContains(response, "Users")
        self.assertContains(response, "Applications")
        self.assertContains(response, "Underwriter Queue")
        self.assertContains(response, "Monitor submitted, claimed, and reviewed applications.")
        self.assertContains(response, "Commissions")
        self.assertContains(response, "Reports / Analytics")
        self.assertNotContains(response, "New Application")
        self.assertNotContains(response, "Claim Next")
        self.assertNotContains(response, "Merchant Portal Preview")
        self.assertNotContains(response, "Underwriter Portal Preview")

    @override_settings(DEBUG=True)
    def test_debug_superuser_can_see_developer_preview_section(self):
        user = get_user_model().objects.create_superuser(username="super-debug", password="test-pass-123")
        assign_role(user, "hq")
        self.client.login(username="super-debug", password="test-pass-123")

        response = self.client.get(reverse("hq_dashboard"))

        self.assertContains(response, "Developer Preview")
        self.assertContains(response, "Merchant Portal Preview")
        self.assertContains(response, "Underwriter Portal Preview")

    @override_settings(DEBUG=False)
    def test_superuser_cannot_see_developer_preview_when_debug_is_false(self):
        user = get_user_model().objects.create_superuser(username="super-prod", password="test-pass-123")
        assign_role(user, "hq")
        self.client.login(username="super-prod", password="test-pass-123")

        response = self.client.get(reverse("hq_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Developer Preview")
        self.assertNotContains(response, "Merchant Portal Preview")
        self.assertNotContains(response, "Underwriter Portal Preview")

    def test_merchant_cannot_access_hq_dashboard(self):
        self.create_user("merchant", "Merchant")
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get(reverse("hq_dashboard"))

        self.assertRedirects(response, reverse("merchant_dashboard"))

    def test_underwriter_cannot_open_merchant_application_creation(self):
        self.create_user("underwriter", "Underwriter")
        self.client.login(username="underwriter", password="test-pass-123")

        response = self.client.get(reverse("new_application"))

        self.assertRedirects(response, reverse("underwriter_dashboard"))

    def test_underwriter_cannot_access_hq_dashboard(self):
        self.create_user("underwriter", "Underwriter")
        self.client.login(username="underwriter", password="test-pass-123")

        response = self.client.get(reverse("hq_dashboard"))

        self.assertRedirects(response, reverse("underwriter_dashboard"))

    def test_superuser_can_access_hq_dashboard(self):
        user = get_user_model().objects.create_superuser(username="super", password="test-pass-123")
        assign_role(user, "hq")
        self.client.login(username="super", password="test-pass-123")

        response = self.client.get(reverse("hq_dashboard"))

        self.assertEqual(response.status_code, 200)

    def test_hq_cannot_access_worker_portals_or_developer_preview(self):
        self.create_user("hq-normal", "HQ")
        self.client.login(username="hq-normal", password="test-pass-123")

        merchant_response = self.client.get(reverse("merchant_dashboard"))
        underwriter_response = self.client.get(reverse("underwriter_dashboard"))
        preview_response = self.client.get(reverse("hq_merchant_preview"))

        self.assertRedirects(merchant_response, reverse("hq_dashboard"))
        self.assertRedirects(underwriter_response, reverse("hq_dashboard"))
        self.assertRedirects(preview_response, reverse("hq_dashboard"))

    def test_hq_can_create_user_with_role(self):
        self.create_user("hq", "HQ")
        self.client.login(username="hq", password="test-pass-123")

        response = self.client.post(
            reverse("hq_users"),
            {
                "username": "new-underwriter",
                "email": "underwriter@example.com",
                "password": "test-pass-123",
                "full_name": "New Underwriter",
                "role": "underwriter",
                "is_active": "on",
            },
        )

        created = get_user_model().objects.get(username="new-underwriter")
        self.assertRedirects(response, reverse("hq_users"))
        self.assertTrue(created.groups.filter(name="Underwriter").exists())
        self.assertEqual(created.userprofile.role, "underwriter")

    def test_home_path_redirects_to_role_portal(self):
        self.create_user("merchant", "Merchant")
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get("/home/")

        self.assertRedirects(response, reverse("merchant_dashboard"))

    def test_home_template_uses_post_logout_form(self):
        self.create_user("merchant", "Merchant")
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get(reverse("merchant_dashboard"))

        self.assertContains(response, 'method="post" action="/accounts/logout/"')
        self.assertNotContains(response, 'href="/accounts/logout/"')


class DashboardUrlTests(TestCase):
    def test_home_url_name_resolves(self):
        self.assertEqual(reverse("home"), "/")

    def test_portal_url_names_resolve(self):
        self.assertEqual(reverse("merchant_dashboard"), "/tengasale/merchant/")
        self.assertEqual(reverse("underwriter_dashboard"), "/tengasale/underwriter/")
        self.assertEqual(reverse("hq_dashboard"), "/tengasale/hq/")
        self.assertEqual(reverse("hq_users"), "/tengasale/hq/users/")
        self.assertEqual(reverse("hq_underwriter_queue"), "/tengasale/hq/underwriter-queue/")
        self.assertEqual(reverse("hq_reports"), "/tengasale/hq/reports/")

    def test_short_portal_urls_redirect_to_tengasale_urls(self):
        self.assertRedirects(self.client.get("/merchant/"), "/tengasale/merchant/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/underwriter/"), "/tengasale/underwriter/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/hq/"), "/tengasale/hq/", fetch_redirect_response=False)
