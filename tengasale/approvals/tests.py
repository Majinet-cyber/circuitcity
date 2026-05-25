from django.test import TestCase
from django.urls import reverse


class ApprovalUrlTests(TestCase):
    def test_manager_home_url_name_resolves(self):
        self.assertEqual(reverse("manager_home"), "/approvals/")
