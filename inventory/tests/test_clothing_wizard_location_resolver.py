"""
Regression tests for clothing wizard location resolver.

Tests that resolve_active_location() never crashes with FieldError
when querying Location by is_active (which doesn't exist).

Ensures:
- GET /inventory/wizard/clothing/ returns 200 (no FieldError)
- Session active_location_id is set properly
- Bogus session location_id doesn't crash
- Resolver falls back to default/first location correctly
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Location, Membership

User = get_user_model()


class ClothingWizardLocationResolverTests(TestCase):
    """Test that clothing wizard location resolver doesn't query Location.is_active."""

    def setUp(self):
        """Set up test fixtures."""
        # Create user
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@example.com',
            password='managerpass123'
        )
        
        # Create business
        self.business = Business.objects.create(
            name='Test Clothing Business',
            business_kind='CLOTHING',
            status='ACTIVE'
        )
        
        # Create membership (manager role) - using correct field names
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create client and login
        self.client = Client()
        self.client.login(username='testmanager', password='managerpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_clothing_wizard_page_loads_with_one_location(self):
        """
        Test that GET /inventory/wizard/clothing/ returns 200 (no FieldError)
        when business has one location.
        """
        # Create a location with is_default=True
        location = Location.objects.create(
            name='Main Store',
            business=self.business,
            is_default=True
        )
        
        # Hit the clothing wizard page
        url = reverse('inventory:clothing_wizard')
        response = self.client.get(url)
        
        # Should succeed with 200, not crash with FieldError
        self.assertEqual(response.status_code, 200)
        
        # Check context has location_id
        self.assertIsNotNone(response.context.get('location_id'))
        self.assertEqual(response.context['location_id'], location.id)

    def test_clothing_wizard_page_loads_with_no_location(self):
        """
        Test that GET /inventory/wizard/clothing/ returns 200 even when
        business has no locations (resolver returns None gracefully).
        """
        # Delete any auto-created locations
        Location.objects.filter(business=self.business).delete()
        
        # Hit the clothing wizard page
        url = reverse('inventory:clothing_wizard')
        response = self.client.get(url)
        
        # Should still return 200 (not crash)
        self.assertEqual(response.status_code, 200)
        
        # Context should have location_id=None
        self.assertIsNone(response.context.get('location_id'))

    def test_clothing_wizard_with_bogus_session_location_id(self):
        """
        Test that a bogus session active_location_id doesn't crash.
        Resolver should detect DoesNotExist, clear session, and fall back.
        """
        # Create a valid location
        location = Location.objects.create(
            name='Valid Store',
            business=self.business,
            is_default=True
        )
        
        # Set bogus session location_id (non-existent)
        session = self.client.session
        session['active_location_id'] = 99999
        session.save()
        
        # Hit the clothing wizard page
        url = reverse('inventory:clothing_wizard')
        response = self.client.get(url)
        
        # Should succeed (no crash)
        self.assertEqual(response.status_code, 200)
        
        # Should fall back to the valid location
        self.assertIsNotNone(response.context.get('location_id'))
        self.assertEqual(response.context['location_id'], location.id)
        
        # Session should be updated to the valid location
        updated_session = self.client.session
        self.assertEqual(updated_session.get('active_location_id'), location.id)

    def test_clothing_wizard_prefers_default_location(self):
        """
        Test that when multiple locations exist, the resolver prefers is_default=True.
        """
        # Delete any auto-created locations to avoid unique constraint issues
        Location.objects.filter(business=self.business).delete()
        
        # Create two locations
        location1 = Location.objects.create(
            name='Store A',
            business=self.business,
            is_default=False
        )
        location2 = Location.objects.create(
            name='Store B (Default)',
            business=self.business,
            is_default=True
        )
        
        # Hit the clothing wizard page
        url = reverse('inventory:clothing_wizard')
        response = self.client.get(url)
        
        # Should succeed
        self.assertEqual(response.status_code, 200)
        
        # Should select the default location (location2)
        self.assertIsNotNone(response.context.get('location_id'))
        self.assertEqual(response.context['location_id'], location2.id)
        
        # Session should reflect this
        session = self.client.session
        self.assertEqual(session.get('active_location_id'), location2.id)

    def test_clothing_wizard_resolver_sets_session(self):
        """
        Test that resolve_active_location sets active_location_id in session
        for subsequent API calls to reuse.
        """
        # Create location
        location = Location.objects.create(
            name='Test Store',
            business=self.business,
            is_default=True
        )
        
        # Initially no session location
        session = self.client.session
        self.assertIsNone(session.get('active_location_id'))
        
        # Hit the clothing wizard page
        url = reverse('inventory:clothing_wizard')
        response = self.client.get(url)
        
        # Should succeed
        self.assertEqual(response.status_code, 200)
        
        # Session should now have active_location_id set
        updated_session = self.client.session
        self.assertEqual(updated_session.get('active_location_id'), location.id)
        
        # Verify response context
        self.assertEqual(response.context['location_id'], location.id)

