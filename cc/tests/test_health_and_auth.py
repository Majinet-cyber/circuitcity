from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import Location
from tenants.models import Business, Membership

User = get_user_model()


class HealthAndAuthTests(TestCase):
    def test_healthz_ok(self):
        resp = self.client.get("/healthz/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertJSONEqual(resp.content, {"ok": True})

    def test_login_and_agent_dashboard(self):
        agent = User.objects.create_user(username="agent1", password="pass12345")
        biz = Business.objects.create(name="Agent Biz", slug="agent-biz", status="ACTIVE")
        location = Location.objects.create(name="Front Desk", business=biz)
        Membership.objects.create(user=agent, business=biz, role="AGENT", status="ACTIVE", location=location)
        self.client.login(username="agent1", password="pass12345")
        session = self.client.session
        session["active_business_id"] = biz.id
        session.save()
        resp = self.client.get(reverse("dashboard:agent_dashboard"))
        self.assertEqual(resp.status_code, 200)
