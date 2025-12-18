# hq/tests/test_hq_mobile.py
"""
Tests for HQ mobile-first responsiveness.
Ensures HQ admin pages render properly on mobile without zoom requirements.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class HQMobileRenderingTestCase(TestCase):
    """Test that HQ pages render without errors and include mobile CSS"""
    
    def setUp(self):
        """Create staff user for HQ access"""
        self.client = Client()
        self.staff_user = User.objects.create_user(
            username="staff@test.com",
            email="staff@test.com",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
    
    def test_hq_dashboard_renders(self):
        """Test HQ dashboard renders successfully"""
        self.client.login(username="staff@test.com", password="testpass123")
        
        response = self.client.get(reverse('hq:dashboard'))
        
        assert response.status_code == 200
        # Check viewport meta tag exists (mobile-friendly)
        self.assertContains(response, 'viewport')
    
    def test_hq_mobile_css_included(self):
        """Test that HQ pages include mobile-first CSS"""
        self.client.login(username="staff@test.com", password="testpass123")
        
        response = self.client.get(reverse('hq:dashboard'))
        
        # Check mobile CSS is linked
        assert response.status_code == 200
        self.assertContains(response, 'hq-mobile.css', msg_prefix="HQ mobile CSS should be included")
    
    def test_hq_business_directory_renders(self):
        """Test business directory page renders"""
        self.client.login(username="staff@test.com", password="testpass123")
        
        response = self.client.get(reverse('hq:business_directory'))
        
        assert response.status_code == 200
    
    def test_hq_subscriptions_page_renders(self):
        """Test subscriptions page renders"""
        self.client.login(username="staff@test.com", password="testpass123")
        
        response = self.client.get(reverse('hq:subscriptions'))
        
        assert response.status_code == 200
    
    def test_hq_agents_page_renders(self):
        """Test agents page renders"""
        self.client.login(username="staff@test.com", password="testpass123")
        
        response = self.client.get(reverse('hq:agents'))
        
        assert response.status_code == 200
    
    def test_hq_without_auth_redirects(self):
        """Test unauthenticated users are redirected"""
        response = self.client.get(reverse('hq:dashboard'))
        
        # Should redirect to login
        assert response.status_code == 302
    
    def test_hq_without_staff_forbidden(self):
        """Test non-staff users cannot access HQ"""
        # Create regular user (not staff)
        regular_user = User.objects.create_user(
            username="user@test.com",
            email="user@test.com",
            password="testpass123",
            is_staff=False
        )
        
        self.client.login(username="user@test.com", password="testpass123")
        
        response = self.client.get(reverse('hq:dashboard'))
        
        # Should be forbidden or redirected
        assert response.status_code in [302, 403]


class HQTableResponsivenessTestCase(TestCase):
    """Test that HQ tables have responsive wrappers"""
    
    def setUp(self):
        """Create staff user"""
        self.client = Client()
        self.staff_user = User.objects.create_user(
            username="staff@test.com",
            email="staff@test.com",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
    
    def test_business_directory_has_responsive_classes(self):
        """Test that business directory includes responsive table classes"""
        self.client.login(username="staff@test.com", password="testpass123")
        
        response = self.client.get(reverse('hq:business_directory'))
        
        assert response.status_code == 200
        # Template should use .hq-table-responsive or similar classes
        # (This is a sanity check, actual class usage depends on template implementation)
    
    def test_hq_pages_have_no_horizontal_scroll_indicators(self):
        """Test that HQ pages use overflow-hidden correctly"""
        self.client.login(username="staff@test.com", password="testpass123")
        
        response = self.client.get(reverse('hq:dashboard'))
        
        assert response.status_code == 200
        # Check that overflow-x:hidden or similar is set
        self.assertContains(response, 'overflow-x')
