"""
Test HQ Command Center template rendering (Fix A)
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestHQCommandCenterTemplateRendering(TestCase):
    """Test that the HQ Command Center template renders without 500 errors"""
    
    def setUp(self):
        """Create HQ admin user and business for testing"""
        self.client = Client()
        
        # Create HQ admin (superuser)
        self.hq_user = User.objects.create_user(
            username='hqadmin',
            email='hqadmin@test.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        
        # Create a test business
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business'
        )
    
    def test_command_center_renders_successfully(self):
        """Test that command center page returns 200 (not 500) for HQ admin"""
        # Login as HQ admin
        self.client.login(username='hqadmin', password='testpass123')
        
        # Hit the command center URL
        url = f'/hq/businesses/{self.business.id}/command-center/'
        response = self.client.get(url)
        
        # Should return 200, not 500 (template syntax error)
        self.assertEqual(
            response.status_code, 
            200, 
            f"Expected 200 but got {response.status_code}. Template should compile without errors."
        )
        
        # Verify we got the right page (contains business name)
        self.assertContains(response, self.business.name)
    
    def test_command_center_tabs_render(self):
        """Test that all tabs render without errors"""
        self.client.login(username='hqadmin', password='testpass123')
        
        tabs = ['overview', 'subscription', 'users', 'data', 'sales', 'health', 'tickets', 'audit']
        
        for tab in tabs:
            url = f'/hq/businesses/{self.business.id}/command-center/?tab={tab}'
            response = self.client.get(url)
            
            self.assertEqual(
                response.status_code, 
                200, 
                f"Tab '{tab}' should render successfully"
            )
    
    def test_non_hq_user_cannot_access(self):
        """Test that regular users cannot access command center"""
        # Create regular user
        regular_user = User.objects.create_user(
            username='regular',
            email='regular@test.com',
            password='testpass123'
        )
        
        self.client.login(username='regular', password='testpass123')
        
        url = f'/hq/businesses/{self.business.id}/command-center/'
        response = self.client.get(url)
        
        # Should redirect or return 403, not 200
        self.assertIn(
            response.status_code, 
            [302, 403], 
            "Regular users should not access HQ command center"
        )
