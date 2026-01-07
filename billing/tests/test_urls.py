# billing/tests/test_urls.py
"""
Tests for billing URL routing.
"""
from django.test import TestCase
from django.urls import NoReverseMatch, resolve, reverse


class BillingURLTests(TestCase):
    """Test billing URL patterns resolve correctly."""

    def test_checkout_url_resolves(self):
        """Test /billing/checkout/ resolves with correct namespace and name."""
        resolved = resolve("/billing/checkout/")
        self.assertEqual(resolved.namespace, "billing")
        self.assertEqual(resolved.url_name, "checkout")

    def test_checkout_url_reverses(self):
        """Test billing:checkout reverses to /billing/checkout/."""
        url = reverse("billing:checkout")
        self.assertEqual(url, "/billing/checkout/")

    def test_plans_url_resolves(self):
        """Test /billing/plans/ resolves with correct namespace and name."""
        resolved = resolve("/billing/plans/")
        self.assertEqual(resolved.namespace, "billing")
        self.assertEqual(resolved.url_name, "plans")

    def test_plans_url_reverses(self):
        """Test billing:plans reverses to /billing/plans/."""
        url = reverse("billing:plans")
        self.assertEqual(url, "/billing/plans/")

    def test_billing_hub_url_resolves(self):
        """Test /billing/hub/ resolves with correct namespace and name."""
        resolved = resolve("/billing/hub/")
        self.assertEqual(resolved.namespace, "billing")
        self.assertEqual(resolved.url_name, "billing_hub")

    def test_billing_hub_url_reverses(self):
        """Test billing:billing_hub reverses to /billing/hub/."""
        url = reverse("billing:billing_hub")
        self.assertEqual(url, "/billing/hub/")
