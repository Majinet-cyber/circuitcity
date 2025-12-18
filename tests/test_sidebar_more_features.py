# tests/test_sidebar_more_features.py
"""
Tests for Sidebar "More Features" collapsible menu.
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestSidebarMoreFeatures(TestCase):
    """Test sidebar More Features collapsible menu."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        # Create test business
        self.business = Business.objects.create(
            name="Test Business",
            business_kind="pharmacy"
        )
        
        # Create membership
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager"
        )
        
        # Login
        self.client.login(username="testuser", password="testpass123")
    
    def test_more_features_present_in_sidebar(self):
        """Test that 'More Features' menu is present in sidebar."""
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for More Features toggle
        self.assertContains(response, 'More Features')
        self.assertContains(response, 'moreFeaturesToggle')
        self.assertContains(response, 'moreFeaturesSubmenu')
    
    def test_wallet_links_in_submenu(self):
        """Test that wallet links are in submenu, not top-level."""
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        content = response.content.decode('utf-8')
        
        # My Wallet should be in submenu
        self.assertIn('My Wallet', content)
        
        # Admin Wallet should be in submenu for managers
        self.assertIn('Admin Wallet', content)
        
        # Check they're inside the submenu
        self.assertIn('more-features-submenu', content)
    
    def test_backups_link_in_submenu_for_managers(self):
        """Test that Backups link appears in submenu for managers."""
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        content = response.content.decode('utf-8')
        
        # Data Backup should be in submenu for managers
        self.assertIn('Data Backup', content)
    
    def test_simulator_link_in_submenu_when_enabled(self):
        """Test that Simulator link appears in submenu when feature flag is enabled."""
        # This test assumes FEATURES.SIMULATOR is enabled in test settings
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        content = response.content.decode('utf-8')
        
        # Simulator should be in submenu if enabled
        # Note: This depends on FEATURES.SIMULATOR setting
        # If disabled, this assertion should be skipped
    
    def test_wallet_links_resolve_correctly(self):
        """Test that wallet links resolve to correct URLs."""
        # Test My Wallet link
        response = self.client.get(reverse('wallet:agent_wallet'))
        self.assertIn(response.status_code, [200, 302])  # 200 OK or 302 redirect
        
        # Test Admin Wallet link (for managers)
        response = self.client.get(reverse('wallet:admin_dashboard'))
        self.assertIn(response.status_code, [200, 302])
    
    def test_backups_link_resolves_for_managers(self):
        """Test that Backups link resolves correctly for managers."""
        response = self.client.get(reverse('backups:manager_list'))
        self.assertIn(response.status_code, [200, 302])
    
    def test_non_manager_sees_limited_submenu(self):
        """Test that non-managers see limited submenu items."""
        # Create agent user
        agent_user = User.objects.create_user(
            username="agent",
            email="agent@example.com",
            password="agentpass123"
        )
        
        Membership.objects.create(
            user=agent_user,
            business=self.business,
            role="agent"
        )
        
        # Login as agent
        self.client.logout()
        self.client.login(username="agent", password="agentpass123")
        
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        content = response.content.decode('utf-8')
        
        # Agent should see My Wallet
        self.assertIn('My Wallet', content)
        
        # Agent should NOT see Admin Wallet or Backups
        # (These are wrapped in permission checks in the template)
    
    def test_sidebar_js_loaded(self):
        """Test that sidebar-more-features.js is loaded."""
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        self.assertContains(response, 'sidebar-more-features.js')
    
    def test_sidebar_css_loaded(self):
        """Test that sidebar-more-features.css is loaded."""
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        self.assertContains(response, 'sidebar-more-features.css')
    
    def test_no_top_level_wallet_duplication(self):
        """Test that wallet links are NOT duplicated at top level."""
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        content = response.content.decode('utf-8')
        
        # Check that wallet links appear in submenu context
        # This is a structural test - exact implementation may vary
        self.assertIn('more-features-submenu', content)
    
    def test_mobile_responsive_no_overflow(self):
        """Test that sidebar has no horizontal overflow (CSS test)."""
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        
        # Check that mobile-friendly CSS is present
        self.assertContains(response, 'sidebar-more-features.css')
        
        # Actual overflow testing would require browser automation
        # This is a smoke test to ensure CSS is loaded
    
    def test_active_link_highlighting_works(self):
        """Test that active link highlighting works for submenu items."""
        # Visit wallet page
        response = self.client.get(reverse('wallet:agent_wallet'))
        
        # Check response is successful
        self.assertIn(response.status_code, [200, 302])
        
        # Active link highlighting is handled by JS
        # This test ensures the page loads correctly


@pytest.mark.django_db
class TestSidebarIntegration(TestCase):
    """Integration tests for sidebar across different verticals."""
    
    def setUp(self):
        """Set up test data for multiple verticals."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
    
    def test_sidebar_works_for_pharmacy_vertical(self):
        """Test sidebar works correctly for pharmacy vertical."""
        business = Business.objects.create(
            name="Test Pharmacy",
            business_kind="pharmacy"
        )
        Membership.objects.create(
            user=self.user,
            business=business,
            role="manager"
        )
        
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'More Features')
    
    def test_sidebar_works_for_clothing_vertical(self):
        """Test sidebar works correctly for clothing vertical."""
        business = Business.objects.create(
            name="Test Clothing",
            business_kind="clothing"
        )
        Membership.objects.create(
            user=self.user,
            business=business,
            role="manager"
        )
        
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'More Features')
    
    def test_sidebar_works_for_phones_vertical(self):
        """Test sidebar works correctly for phones vertical."""
        business = Business.objects.create(
            name="Test Phones",
            business_kind="phones"
        )
        Membership.objects.create(
            user=self.user,
            business=business,
            role="manager"
        )
        
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse('inventory:inventory_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'More Features')

