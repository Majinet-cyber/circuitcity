# core/tests/test_404_template_safe.py
"""
Tests to ensure 404 error pages render without crashing.

Guards against template errors like:
    django.template.base.VariableDoesNotExist: Failed lookup for key [name] in <URLResolver ...>
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

User = get_user_model()


@pytest.mark.django_db
class Test404TemplateSafe(TestCase):
    """Ensure 404 pages render successfully without template errors."""

    def setUp(self):
        """Create test user for authenticated tests."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.client = Client()

    @override_settings(DEBUG=False)
    def test_404_unauthenticated(self):
        """Test 1: Request a missing URL (unauthenticated) => clean 404 page."""
        # Generate a guaranteed non-existent URL
        missing_url = "/this-url-definitely-does-not-exist-12345/"

        response = self.client.get(missing_url)

        # Should return 404 status
        self.assertEqual(response.status_code, 404, "Should return 404 for missing URL")

        # Should render successfully (no template exceptions)
        # If template had errors, Django would return 500 or raise exception
        self.assertIsNotNone(response.content, "Response should have content (not crash)")

        # Content should be non-empty HTML
        content = response.content.decode("utf-8")
        self.assertGreater(len(content), 0, "404 page should render content")

        # Should contain some indication it's a 404 page
        content_lower = content.lower()
        self.assertTrue(
            "404" in content_lower or "not found" in content_lower or "page" in content_lower,
            "404 page should indicate error",
        )

    @override_settings(DEBUG=False)
    def test_404_authenticated(self):
        """Test 2: Request a missing URL (authenticated) => clean 404 page."""
        self.client.login(username="testuser", password="testpass123")

        missing_url = "/authenticated/missing/endpoint/"

        response = self.client.get(missing_url)

        self.assertEqual(response.status_code, 404)
        self.assertIsNotNone(response.content)

        content = response.content.decode("utf-8")
        self.assertGreater(len(content), 0)

    @override_settings(DEBUG=False)
    def test_404_api_endpoint(self):
        """Test 3: Request a missing API endpoint => JSON 404 (if configured)."""
        missing_api_url = "/api/this-does-not-exist/"

        response = self.client.get(missing_api_url)

        # Should return 404
        self.assertEqual(response.status_code, 404)

        # Should not crash (content exists)
        self.assertIsNotNone(response.content)

    @override_settings(DEBUG=False)
    def test_404_with_special_characters(self):
        """Test 4: Missing URL with special chars => clean 404."""
        # Test URL with special characters that might break template rendering
        special_urls = [
            "/test/<script>alert('xss')</script>/",
            "/test/{'key': 'value'}/",
            "/test/%00null-byte/",
        ]

        for url in special_urls:
            with self.subTest(url=url):
                response = self.client.get(url)

                # Should return 404 (or redirect, but not 500)
                self.assertIn(
                    response.status_code,
                    [404, 302, 400],
                    f"URL {url} should return safe status (not 500)",
                )

                # Should render without crashing
                self.assertIsNotNone(response.content)

    @override_settings(DEBUG=True)
    def test_404_debug_mode(self):
        """Test 5: In DEBUG mode, 404 shows Django's helpful debug page."""
        missing_url = "/debug-test-missing-url/"

        response = self.client.get(missing_url)

        # Should return 404
        self.assertEqual(response.status_code, 404)

        # In DEBUG mode, Django shows a detailed 404 page with URL patterns
        # This should still not crash
        self.assertIsNotNone(response.content)

        content = response.content.decode("utf-8")
        self.assertGreater(len(content), 0)

        # Debug page typically shows "Using the URLconf"
        # But we're mainly ensuring it doesn't crash with template errors

    def test_404_handler_exists(self):
        """Test 6: Ensure custom 404 handler is configured."""
        from django.conf import settings

        # Check if handler404 is set in urls
        try:
            from cc import urls as cc_urls

            self.assertTrue(
                hasattr(cc_urls, "handler404"),
                "cc/urls.py should define handler404",
            )
        except ImportError:
            # If cc.urls doesn't exist, check settings
            self.assertIsNotNone(
                getattr(settings, "ROOT_URLCONF", None),
                "ROOT_URLCONF should be configured",
            )


# Run with: pytest core/tests/test_404_template_safe.py -v
# Or: python manage.py test core.tests.test_404_template_safe

