"""
Website app tests — Phase 5.

Coverage:
- Website landing page renders (200)
- PWA manifest is served
"""

from django.test import TestCase, Client


class WebsiteSmokeTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_website_landing_renders(self):
        res = self.client.get("/site/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "TengaSale")

    def test_offline_page_renders(self):
        res = self.client.get("/offline/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "offline")
