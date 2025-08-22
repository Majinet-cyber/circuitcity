from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class HealthAndAuthTests(TestCase):
    def test_healthz_ok(self):
        resp = self.client.get("/healthz/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertJSONEqual(resp.content, {"ok": True})

    def test_login_and_agent_dashboard(self):
        User.objects.create_user(username="agent1", password="pass12345")
        self.client.login(username="agent1", password="pass12345")
        resp = self.client.get(reverse("dashboard:agent_dashboard"))
        self.assertEqual(resp.status_code, 200)
