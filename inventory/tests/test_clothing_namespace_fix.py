"""
Regression test for clothing namespace registration.

This test ensures that the 'clothing' URL namespace is properly registered
and that URLs can be reversed correctly, preventing NoReverseMatch errors
in templates that use {% url 'clothing:...' %}.

Issue: django.urls.exceptions.NoReverseMatch: 'clothing' is not a registered namespace
Fixed by: Ensuring cc/urls.py includes inventory.urls_clothing with proper namespace
"""
from django.test import TestCase
from django.urls import reverse, NoReverseMatch


class ClothingNamespaceTest(TestCase):
    """Test that the clothing namespace is properly registered."""

    def test_clothing_namespace_exists(self):
        """Test that the 'clothing' namespace can be resolved."""
        try:
            # This should not raise NoReverseMatch
            url = reverse('clothing:dashboard')
            self.assertIsNotNone(url)
            self.assertEqual(url, '/clothing/')
        except NoReverseMatch as e:
            self.fail(f"'clothing' namespace not registered: {e}")

    def test_clothing_barcode_batch_step1_url(self):
        """Test that clothing:barcode_batch_step1 URL can be reversed."""
        try:
            url = reverse('clothing:barcode_batch_step1')
            self.assertIsNotNone(url)
            self.assertEqual(url, '/clothing/api/barcode-batch/step1/')
        except NoReverseMatch as e:
            self.fail(f"clothing:barcode_batch_step1 URL not found: {e}")

    def test_clothing_barcode_batch_scan_url(self):
        """Test that clothing:barcode_batch_scan URL can be reversed."""
        try:
            url = reverse('clothing:barcode_batch_scan')
            self.assertIsNotNone(url)
            self.assertEqual(url, '/clothing/api/barcode-batch/scan/')
        except NoReverseMatch as e:
            self.fail(f"clothing:barcode_batch_scan URL not found: {e}")

    def test_clothing_stock_list_url(self):
        """Test that clothing:stock_list URL can be reversed."""
        try:
            url = reverse('clothing:stock_list')
            self.assertIsNotNone(url)
            self.assertEqual(url, '/clothing/stock/')
        except NoReverseMatch as e:
            self.fail(f"clothing:stock_list URL not found: {e}")

    def test_clothing_fast_sell_urls(self):
        """Test that clothing fast sell API URLs can be reversed."""
        urls_to_test = [
            ('clothing:fast_sell_lookup', '/clothing/api/fast-sell/lookup/'),
            ('clothing:fast_sell_create', '/clothing/api/fast-sell/create/'),
        ]
        
        for url_name, expected_path in urls_to_test:
            with self.subTest(url_name=url_name):
                try:
                    url = reverse(url_name)
                    self.assertIsNotNone(url)
                    self.assertEqual(url, expected_path)
                except NoReverseMatch as e:
                    self.fail(f"{url_name} URL not found: {e}")

