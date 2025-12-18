"""
Regression tests for sales rollback templates
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business

User = get_user_model()


class RollbackTemplateRenderingTests(TestCase):
    """
    Regression tests to ensure rollback templates render without errors.
    
    These tests prevent template syntax errors like:
    - Using {% else %} inside {% for %} (should use {% empty %})
    - Mismatched {% if %}/{% endif %} or {% for %}/{% endfor %} tags
    """
    
    def setUp(self):
        """Create test data"""
        # Create business
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            business_kind="PHONES"
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager",
            password="testpass123",
            email="manager@test.com"
        )
        self.manager.assigned_business = self.business
        self.manager.assigned_role = "MANAGER"
        self.manager.save()
        
        self.client = Client()
    
    
    def test_rollback_home_renders_without_error(self):
        """
        Test that /sales/rollback/ returns HTTP 200.
        
        This is a regression test for template syntax errors in rollback_home.html.
        """
        self.client.force_login(self.manager)
        
        # Set active business in session (required by middleware)
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('sales:rollback_home')
        response = self.client.get(url, HTTP_HOST='testserver')
        
        # Should return 200, not 500
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200, got {response.status_code}. "
            f"Response content: {response.content[:500] if hasattr(response, 'content') else 'N/A'}"
        )
        
        # Verify correct template is used
        self.assertTemplateUsed(response, 'sales/rollback_home.html')

