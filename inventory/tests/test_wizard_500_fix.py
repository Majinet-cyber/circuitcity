"""
Regression tests for wizard 500 errors (clothing wizard crash).

This test reproduces the production bug where /inventory/wizard/clothing/
returns 500 error due to querying Location.is_active (which doesn't exist).

Root cause: resolve_active_location() in views_wizard.py was querying
Location.objects.filter(is_active=True), but Location model only has
is_default field (not is_active). is_active is a property, not a DB field.

Tests ensure:
- Wizards return 200 (never 500) for valid business/membership setup
- resolve_active_location() uses correct Location fields
- Stale session location_id is handled gracefully
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import Location

User = get_user_model()


class WizardLocationResolverRegressionTests(TestCase):
    """Test that wizard location resolver doesn't crash with FieldError."""

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
        
        # Create membership (manager role)
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

    def test_clothing_wizard_returns_200_not_500(self):
        """
        CRITICAL REGRESSION TEST:
        Test that GET /inventory/wizard/clothing/ returns 200 (not 500).
        
        This test reproduces the production bug where resolve_active_location()
        was querying Location.objects.filter(is_active=True), causing FieldError
        because Location doesn't have is_active field in the database.
        """
        # Create a location
        location = Location.objects.create(
            name='Main Store',
            business=self.business,
            is_default=True
        )
        
        # Set a stale session location_id (triggers the buggy query path)
        # CRITICAL: Clear request.active_location to force fallback to session lookup
        # This triggers lines 74-77 in views_wizard.py which have the bug
        session = self.client.session
        session['active_location_id'] = location.id
        session.pop('default_location_id', None)  # Clear to force resolve_active_location
        session.save()
        
        # Hit the clothing wizard page
        url = reverse('inventory:clothing_wizard')
        response = self.client.get(url)
        
        # CRITICAL: Should return 200, not 500
        # Before fix: FieldError: Cannot resolve keyword 'is_active' into field
        self.assertEqual(
            response.status_code, 
            200, 
            f"Expected 200 but got {response.status_code}. "
            f"This indicates resolve_active_location() is still querying Location.is_active field."
        )
        
        # Verify context has location_id
        self.assertIsNotNone(response.context.get('location_id'))
        self.assertEqual(response.context['location_id'], location.id)

    def test_resolve_active_location_directly(self):
        """
        Test resolve_active_location() function directly to ensure it doesn't
        query Location.is_active field.
        """
        from inventory.views_wizard import resolve_active_location
        from django.test import RequestFactory
        
        # Create location
        location = Location.objects.create(
            name='Test Store',
            business=self.business,
            is_default=True
        )
        
        # Create mock request with session
        factory = RequestFactory()
        request = factory.get('/test/')
        
        # Add session to request
        from django.contrib.sessions.middleware import SessionMiddleware
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        
        # Set session location_id to trigger the buggy code path (line 75)
        request.session['active_location_id'] = location.id
        
        # Call resolve_active_location
        # This should NOT raise FieldError
        result = resolve_active_location(request, self.business)
        
        # Should return the location successfully
        self.assertIsNotNone(result)
        self.assertEqual(result.id, location.id)

    def test_liquor_wizard_returns_200(self):
        """Test that liquor wizard also works (uses same decorator)."""
        # Update business kind to liquor
        self.business.business_kind = 'LIQUOR'
        self.business.save()
        
        # Create location
        location = Location.objects.create(
            name='Liquor Store',
            business=self.business,
            is_default=True
        )
        
        url = reverse('inventory:liquor_wizard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)

    def test_phones_wizard_returns_200(self):
        """Test that phones wizard also works."""
        # Update business kind to phones
        self.business.business_kind = 'PHONES'
        self.business.save()
        
        # Create location
        location = Location.objects.create(
            name='Phone Store',
            business=self.business,
            is_default=True
        )
        
        url = reverse('inventory:phones_wizard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)

    def test_pharmacy_wizard_returns_200(self):
        """Test that pharmacy wizard also works."""
        # Update business kind to pharmacy
        self.business.business_kind = 'PHARMACY'
        self.business.save()
        
        # Create location
        location = Location.objects.create(
            name='Pharmacy',
            business=self.business,
            is_default=True
        )
        
        url = reverse('inventory:pharmacy_wizard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)

    def test_wizard_with_stale_session_location_id(self):
        """
        Test that stale session location_id (pointing to deleted location)
        doesn't cause 500 error.
        """
        # Create and delete a location to make session stale
        location = Location.objects.create(
            name='Temporary Store',
            business=self.business,
            is_default=False
        )
        location_id = location.id
        location.delete()
        
        # Create a valid fallback location
        valid_location = Location.objects.create(
            name='Valid Store',
            business=self.business,
            is_default=True
        )
        
        # Set session to deleted location_id
        session = self.client.session
        session['active_location_id'] = location_id
        session.save()
        
        # Hit the clothing wizard page
        url = reverse('inventory:clothing_wizard')
        response = self.client.get(url)
        
        # Should return 200 and fall back to valid location
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['location_id'], valid_location.id)

    def test_wizard_with_no_locations(self):
        """
        Test that wizard returns 200 even when business has no locations.
        Template should handle this gracefully.
        """
        # Ensure no locations exist
        Location.objects.filter(business=self.business).delete()
        
        # Hit the clothing wizard page
        url = reverse('inventory:clothing_wizard')
        response = self.client.get(url)
        
        # Should return 200 (not crash)
        self.assertEqual(response.status_code, 200)
        
        # Context should have location_id=None
        self.assertIsNone(response.context.get('location_id'))
        self.assertFalse(response.context.get('has_location'))

    def test_location_model_has_no_is_active_database_field(self):
        """
        Verify that Location model does NOT have is_active as a database field.
        
        This is the root cause: code was querying Location.objects.filter(is_active=True)
        but is_active is only a property (always returns True), not a database field.
        """
        # Create location
        location = Location.objects.create(
            name='Test Location',
            business=self.business,
            is_default=True
        )
        
        # Verify is_active is NOT a database field
        field_names = [f.name for f in Location._meta.get_fields()]
        self.assertNotIn(
            'is_active', 
            field_names,
            "Location should NOT have is_active as a database field. "
            "It should only have is_default field."
        )
        
        # Verify is_default IS a database field
        self.assertIn('is_default', field_names)
        
        # Verify is_active exists as a property (backwards compat)
        self.assertTrue(hasattr(location, 'is_active'))
        self.assertTrue(location.is_active)  # Property always returns True

    def test_cannot_query_location_by_is_active(self):
        """
        Test that querying Location.objects.filter(is_active=True) raises FieldError.
        
        This is the exact bug that caused the 500 error in production.
        """
        from django.core.exceptions import FieldError
        
        # Create location
        Location.objects.create(
            name='Test Location',
            business=self.business,
            is_default=True
        )
        
        # Attempting to query by is_active should raise FieldError
        with self.assertRaises(FieldError) as cm:
            Location.objects.filter(is_active=True).first()
        
        # Verify error message
        self.assertIn("is_active", str(cm.exception))
        self.assertIn("field", str(cm.exception).lower())

