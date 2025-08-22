from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()

class PermissionsTests(TestCase):
    def test_admin_requires_login(self):
        resp = self.client.get("/admin/", follow=False)
        self.assertIn(resp.status_code, (301, 302))  # redirects to login

    def test_non_staff_cannot_access_admin(self):
        User.objects.create_user("user", password="pass12345", is_staff=False)
        self.client.login(username="user", password="pass12345")
        resp = self.client.get("/admin/", follow=False)
        self.assertIn(resp.status_code, (301, 302, 403))
