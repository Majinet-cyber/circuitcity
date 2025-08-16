from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class SmokeTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("staff", password="pass12345", is_staff=True)
        self.agent = User.objects.create_user("agent", password="pass12345", is_staff=False)

    def test_home_redirects_for_agent(self):
        self.client.login(username="agent", password="pass12345")
        resp = self.client.get(reverse("home"))
        self.assertIn(resp.status_code, (301, 302))

        self.client.login(username="staff", password="pass12345")
        resp = self.client.get(reverse("home"))
        self.assertIn(resp.status_code, (301, 302))
