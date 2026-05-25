from django.test import TestCase
from django.urls import reverse


class EarningsUrlTests(TestCase):
    def test_earnings_home_url_name_resolves(self):
        self.assertEqual(reverse("earnings_home"), "/earnings/")
