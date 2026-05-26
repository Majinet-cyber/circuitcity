from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_home_redirects_unauthenticated_users_to_login(self):
        response = self.client.get("/")

        self.assertRedirects(response, "/accounts/login/?next=/")

    def test_authenticated_user_can_access_home(self):
        user = get_user_model().objects.create_user(
            username="merchant",
            password="test-pass-123",
        )
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Hi, {user.username}")
        self.assertContains(response, "TengaSale")
        self.assertContains(response, "You are now earning more with TengaSale.")
        self.assertContains(response, "VIEW ALL EARNINGS")
        self.assertContains(response, "Spin & Win")
        self.assertContains(response, "SPIN NOW")
        self.assertContains(response, "NEW APPLICATION")
        self.assertContains(response, f'href="{settings.TENGASALE_WHATSAPP_LINK}"')
        self.assertContains(response, 'class="icon-button whatsapp-button"')
        self.assertContains(response, 'aria-label="WhatsApp support"')
        self.assertContains(response, "notification-button")
        self.assertContains(response, "logout-button")

        content = response.content.decode()
        self.assertLess(content.index("whatsapp-button"), content.index("notification-button"))
        self.assertLess(content.index("notification-button"), content.index("logout-button"))

    def test_home_template_uses_post_logout_form(self):
        get_user_model().objects.create_user(
            username="merchant",
            password="test-pass-123",
        )
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get("/")

        self.assertContains(response, 'method="post" action="/accounts/logout/"')
        self.assertNotContains(response, 'href="/accounts/logout/"')


class DashboardUrlTests(TestCase):
    def test_home_url_name_resolves(self):
        self.assertEqual(reverse("home"), "/")
