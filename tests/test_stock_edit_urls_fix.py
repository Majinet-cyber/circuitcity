"""
Unit tests for stock_edit URL fix.

Tests that:
1. inventory:stock_edit and inventory:stock_delete URL names resolve correctly
2. /inventory/list/ page loads without NoReverseMatch errors
3. URLs follow the expected pattern stock/<pk>/edit/ and stock/<pk>/delete/

This prevents regression of the NoReverseMatch error that occurred when
templates referenced non-existent URL names.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import NoReverseMatch, reverse

User = get_user_model()


class StockEditURLTestCase(TestCase):
    """Test stock_edit and stock_delete URL patterns are correctly wired."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@example.com",
            password="testpass123",
            is_staff=False,
        )

    def test_stock_edit_url_resolves(self):
        """Test that reverse('inventory:stock_edit', kwargs={'pk': 1}) resolves."""
        try:
            url = reverse("inventory:stock_edit", kwargs={"pk": 1})
            # Should resolve to /inventory/stock/1/edit/
            assert url == "/inventory/stock/1/edit/"
        except NoReverseMatch:
            pytest.fail("inventory:stock_edit URL name does not resolve")

    def test_stock_delete_url_resolves(self):
        """Test that reverse('inventory:stock_delete', kwargs={'pk': 1}) resolves."""
        try:
            url = reverse("inventory:stock_delete", kwargs={"pk": 1})
            # Should resolve to /inventory/stock/1/delete/
            assert url == "/inventory/stock/1/delete/"
        except NoReverseMatch:
            pytest.fail("inventory:stock_delete URL name does not resolve")

    def test_stock_list_page_loads_for_authenticated_user(self):
        """Test that GET /inventory/list/ returns 200 for authenticated user."""
        # Log in
        self.client.force_login(self.user)

        # GET /inventory/list/
        response = self.client.get("/inventory/list/")

        # Should not crash with NoReverseMatch
        # May return 200 (success) or 302 (redirect to activate business)
        # Both are acceptable — the key is NO 500 error
        assert response.status_code in [200, 302], (
            f"Expected 200 or 302, got {response.status_code}. "
            f"If 500, check for NoReverseMatch in template rendering."
        )

    def test_stock_list_page_renders_without_reverse_error(self):
        """Test that stock_list template can be rendered without NoReverseMatch."""
        from django.template import Context, Template
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/inventory/list/")
        request.user = self.user
        request.session = {}

        # Simulate the template tag usage
        template_string = """
        {% load static %}
        {% url 'inventory:stock_edit' 1 as edit_url %}
        {% url 'inventory:stock_delete' 1 as delete_url %}
        Edit: {{ edit_url }}
        Delete: {{ delete_url }}
        """

        try:
            template = Template(template_string)
            context = Context({"request": request})
            rendered = template.render(context)
            
            # Should contain the resolved URLs
            assert "/inventory/stock/1/edit/" in rendered
            assert "/inventory/stock/1/delete/" in rendered
        except NoReverseMatch as e:
            pytest.fail(f"Template rendering failed with NoReverseMatch: {e}")

    def test_stock_edit_requires_pk_argument(self):
        """Test that stock_edit URL requires a pk argument."""
        with pytest.raises(NoReverseMatch):
            # Should fail without pk
            reverse("inventory:stock_edit")

    def test_stock_delete_requires_pk_argument(self):
        """Test that stock_delete URL requires a pk argument."""
        with pytest.raises(NoReverseMatch):
            # Should fail without pk
            reverse("inventory:stock_delete")


class StockEditIntegrationTestCase(TestCase):
    """Integration tests for stock edit/delete functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="testmanager",
            email="manager@example.com",
            password="testpass123",
            is_staff=True,  # Managers typically need staff flag
        )
        
        # Create regular user (agent)
        self.agent = User.objects.create_user(
            username="testagent",
            email="agent@example.com",
            password="testpass123",
            is_staff=False,
        )

    def test_stock_list_page_does_not_500_for_manager(self):
        """Test that managers can load stock list without errors."""
        self.client.force_login(self.manager)
        response = self.client.get("/inventory/list/")
        
        # Should not return 500
        assert response.status_code != 500, (
            f"Stock list page returned 500 for manager. "
            f"This likely indicates a NoReverseMatch error in the template."
        )

    def test_stock_list_page_does_not_500_for_agent(self):
        """Test that agents can load stock list without errors."""
        self.client.force_login(self.agent)
        response = self.client.get("/inventory/list/")
        
        # Should not return 500
        assert response.status_code != 500, (
            f"Stock list page returned 500 for agent. "
            f"This likely indicates a NoReverseMatch error in the template."
        )

    def test_stock_list_uses_correct_url_namespace(self):
        """Test that stock list template uses inventory: namespace."""
        # Ensure the URLs are registered under the 'inventory' namespace
        url_edit = reverse("inventory:stock_edit", kwargs={"pk": 1})
        url_delete = reverse("inventory:stock_delete", kwargs={"pk": 1})
        
        assert url_edit.startswith("/inventory/")
        assert url_delete.startswith("/inventory/")

    def test_stock_edit_url_pattern_matches_convention(self):
        """Test that edit URL follows REST convention."""
        url = reverse("inventory:stock_edit", kwargs={"pk": 123})
        
        # Should follow pattern: /inventory/stock/<pk>/edit/
        assert "/stock/123/edit/" in url

    def test_stock_delete_url_pattern_matches_convention(self):
        """Test that delete URL follows REST convention."""
        url = reverse("inventory:stock_delete", kwargs={"pk": 456})
        
        # Should follow pattern: /inventory/stock/<pk>/delete/
        assert "/stock/456/delete/" in url

