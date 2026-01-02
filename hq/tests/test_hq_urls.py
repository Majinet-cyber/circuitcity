"""Tests for HQ URL namespace and routing."""
from django.test import TestCase
from django.urls import resolve, reverse, get_resolver
from django.contrib.auth import get_user_model
from tenants.models import Business

User = get_user_model()


class TestHQNamespace(TestCase):
    """Test that HQ namespace is properly registered and routes work."""

    def test_hq_namespace_in_resolver(self):
        """Verify hq namespace is registered in URL resolver."""
        resolver = get_resolver()
        self.assertIn("hq", resolver.namespace_dict)

    def test_hq_namespace_registered(self):
        """Verify hq:business_directory reverse works."""
        url = reverse("hq:business_directory")
        self.assertEqual(url, "/hq/businesses/")

    def test_hq_businesses_resolves_under_hq(self):
        """Verify /hq/businesses/ resolves with hq namespace."""
        match = resolve("/hq/businesses/")
        self.assertEqual(match.namespace, "hq")
        self.assertEqual(match.url_name, "business_directory")

    def test_hq_business_detail_reverse(self):
        """Verify hq:business_detail reverse works."""
        url = reverse("hq:business_detail", kwargs={"pk": 1})
        self.assertTrue(url.endswith("/hq/businesses/1/"))

    def test_hq_business_detail_reverse_with_business(self):
        """Verify hq:business_detail reverse works with actual Business instance."""
        biz = Business.objects.create(name="Test Business", slug="test-business")
        url = reverse("hq:business_detail", kwargs={"pk": biz.id})
        self.assertTrue(url.endswith(f"/hq/businesses/{biz.id}/"))

    def test_hq_business_detail_resolves_under_hq(self):
        """Verify /hq/businesses/<pk>/ resolves with hq namespace."""
        match = resolve("/hq/businesses/1/")
        self.assertEqual(match.namespace, "hq")
        self.assertEqual(match.url_name, "business_detail")

    def test_hq_businesses_does_not_hit_shim(self):
        """Regression test: Ensure /hq/businesses/ never resolves to a shim function."""
        match = resolve("/hq/businesses/")
        # Critical: The resolved function should NOT be a shim
        self.assertNotEqual(match.func.__name__, "_hq_businesses_shim")
        # Verify it's the actual view from hq.views_business_directory
        self.assertEqual(match.func.__module__, "hq.views_business_directory")
        self.assertEqual(match.func.__name__, "business_directory")
