from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def setUp(self):
        call_command("seed_roles")

    def create_user(self, username, group_name=None, **kwargs):
        user = get_user_model().objects.create_user(username=username, password="test-pass-123", **kwargs)
        if group_name:
            user.groups.add(Group.objects.get(name=group_name))
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

    def test_hq_can_access_hq_and_merchant_dashboards(self):
        self.create_user("hq", "HQ")
        self.client.login(username="hq", password="test-pass-123")

        hq_response = self.client.get(reverse("hq_dashboard"))
        merchant_response = self.client.get(reverse("merchant_dashboard"))

        self.assertEqual(hq_response.status_code, 200)
        self.assertContains(hq_response, "HQ")
        self.assertEqual(merchant_response.status_code, 200)

    def test_merchant_cannot_access_hq_dashboard(self):
        self.create_user("merchant", "Merchant")
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get(reverse("hq_dashboard"))

        self.assertRedirects(response, reverse("merchant_dashboard"))

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
