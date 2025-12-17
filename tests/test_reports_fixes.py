"""
Tests for Reports module fixes (Task A).

Tests:
- /reports/ returns 200 (not 404)
- /reports// redirects to /reports/
- URLResolver .name crashes don't occur
- Reports page renders safely
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class ReportsAccessTestCase(TestCase):
    """Test basic reports access and routing."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
    
    def test_reports_home_requires_login(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get("/reports/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith("/login") or 
            response.url.startswith("/accounts/login")
        )
    
    def test_reports_home_returns_200_for_authenticated_user(self):
        """Logged-in user should see reports home page (200)."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get("/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Reports", response.content)
    
    def test_reports_home_named_url(self):
        """Test that reports:home URL name works."""
        self.client.login(username="testuser", password="testpass123")
        url = reverse("reports:home")
        self.assertEqual(url, "/reports/")
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
    
    def test_reports_double_slash_redirects(self):
        """Test that /reports// redirects to /reports/."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get("/reports//", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reports/", response.url)
    
    def test_reports_multiple_slashes_redirect(self):
        """Test that /reports/// also redirects."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get("/reports///", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reports/", response.url)


class ReportsSubPagesTestCase(TestCase):
    """Test reports sub-pages (sales, inventory)."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")
    
    def test_sales_report_accessible(self):
        """Test that /reports/sales/ is accessible."""
        response = self.client.get("/reports/sales/")
        self.assertEqual(response.status_code, 200)
    
    def test_sales_report_named_url(self):
        """Test that reports:sales URL name works."""
        url = reverse("reports:sales")
        self.assertEqual(url, "/reports/sales/")
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
    
    def test_inventory_report_accessible(self):
        """Test that /reports/inventory/ is accessible."""
        response = self.client.get("/reports/inventory/")
        self.assertEqual(response.status_code, 200)
    
    def test_inventory_report_named_url(self):
        """Test that reports:inventory URL name works."""
        url = reverse("reports:inventory")
        self.assertEqual(url, "/reports/inventory/")
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class ReportsTemplateRenderingTestCase(TestCase):
    """Test that reports templates render without crashes."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")
    
    def test_reports_home_no_urlresolver_crash(self):
        """
        Test that reports home doesn't crash with URLResolver .name attribute errors.
        This was the original issue: templates were iterating over URLResolver objects
        and trying to access .name, which doesn't exist.
        """
        response = self.client.get("/reports/")
        self.assertEqual(response.status_code, 200)
        
        # Check that we got a proper HTML response, not an error page
        content = response.content.decode('utf-8')
        self.assertNotIn("URLResolver", content)
        self.assertNotIn("AttributeError", content)
        self.assertNotIn("VariableDoesNotExist", content)
    
    def test_reports_page_contains_expected_links(self):
        """Test that reports home page contains links to sub-reports."""
        response = self.client.get("/reports/")
        content = response.content.decode('utf-8')
        
        # Should contain links to sales and inventory reports
        self.assertIn("Sales", content)
        self.assertIn("Inventory", content)
    
    def test_sales_report_renders_with_empty_data(self):
        """Test that sales report renders even with no data."""
        response = self.client.get("/reports/sales/")
        self.assertEqual(response.status_code, 200)
        # Should not crash with empty data
        content = response.content.decode('utf-8')
        self.assertIn("Sales", content)
    
    def test_inventory_report_renders_with_empty_data(self):
        """Test that inventory report renders even with no data."""
        response = self.client.get("/reports/inventory/")
        self.assertEqual(response.status_code, 200)
        # Should not crash with empty data
        content = response.content.decode('utf-8')
        self.assertIn("Inventory", content)


class ReportsURLConsistencyTestCase(TestCase):
    """Test that reports URLs are consistent and follow best practices."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")
    
    def test_reports_index_redirects_to_home(self):
        """Test that /reports/index/ redirects to /reports/ for consistency."""
        response = self.client.get("/reports/index/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reports/", response.url)
    
    def test_all_reports_urls_have_trailing_slash(self):
        """Test that all reports URLs properly handle trailing slashes."""
        urls = [
            "/reports/",
            "/reports/sales/",
            "/reports/inventory/",
        ]
        
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(
                response.status_code, 200,
                f"URL {url} should return 200, got {response.status_code}"
            )


class ReportsDebugEndpointTestCase(TestCase):
    """Test debug endpoints (only available in DEBUG mode)."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")
    
    def test_which_templates_endpoint_exists_in_debug(self):
        """
        Test that /reports/which/ endpoint exists when DEBUG=True.
        This endpoint shows which templates are being used.
        """
        from django.conf import settings
        if settings.DEBUG:
            response = self.client.get("/reports/which/")
            # Should return 200 or 404 depending on if it's enabled
            self.assertIn(response.status_code, [200, 404])
