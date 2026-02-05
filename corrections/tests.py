"""
Data Corrections Integration Tests (Feb 2026)
==============================================

Test suite for the corrections framework:
- URL routing and reverse() resolution
- Registry adapters load correctly
- Vertical-aware correction views work
- Permissions (manager-only)
- Sidebar link generation
- Apply/rollback functionality
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from corrections.registry import registry
from corrections.models import CorrectionBatch, CorrectionItem, CorrectionStatus
from corrections.service import CorrectionService

# Import models from each vertical
from inventory.models_verticals import GymMember, GymPayment
from inventory.models import InventoryItem
from tenants.models import Business, Location, Membership

User = get_user_model()


class TestCorrectionsURLRouting(TestCase):
    """Test that corrections URLs resolve correctly for all verticals."""
    
    def setUp(self):
        """Create test user and business."""
        self.user = User.objects.create_user(
            username='manager@test.com',
            email='manager@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Business',
            business_kind='gym',
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Location',
        )
        # Create manager membership
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            is_active=True,
        )
        self.client = Client()
        self.client.login(username='manager@test.com', password='testpass123')
    
    def test_corrections_urls_included_in_main_urlconf(self):
        """Test that corrections.urls is included in cc/urls.py."""
        # Try to resolve corrections dashboard for gym
        url = reverse('corrections:dashboard', kwargs={'vertical': 'gym'})
        self.assertEqual(url, '/corrections/gym/')
    
    def test_corrections_dashboard_resolves_for_all_verticals(self):
        """Test URL resolution for gym, phones, clothing."""
        verticals = ['gym', 'phones', 'clothing']
        for vertical in verticals:
            with self.subTest(vertical=vertical):
                url = reverse('corrections:dashboard', kwargs={'vertical': vertical})
                self.assertTrue(url.startswith('/corrections/'))
                self.assertIn(vertical, url)
    
    def test_browse_entity_url_resolves(self):
        """Test entity browser URL resolution."""
        url = reverse('corrections:browse_entity', kwargs={
            'vertical': 'gym',
            'entity_label': 'gym_member'
        })
        self.assertEqual(url, '/corrections/gym/entity/gym_member/')
    
    def test_edit_record_url_resolves(self):
        """Test single record edit URL resolution."""
        url = reverse('corrections:edit_record', kwargs={
            'vertical': 'gym',
            'entity_label': 'gym_member',
            'object_id': 1
        })
        self.assertEqual(url, '/corrections/gym/entity/gym_member/1/edit/')
    
    def test_batch_detail_url_resolves(self):
        """Test batch detail URL resolution."""
        url = reverse('corrections:batch_detail', kwargs={
            'vertical': 'gym',
            'batch_id': 1
        })
        self.assertEqual(url, '/corrections/gym/batch/1/')
    
    def test_audit_trail_url_resolves(self):
        """Test audit trail URL resolution."""
        url = reverse('corrections:audit_trail', kwargs={'vertical': 'gym'})
        self.assertEqual(url, '/corrections/gym/audit/')


class TestCorrectionsRegistry(TestCase):
    """Test that vertical adapters are registered correctly."""
    
    def test_registry_has_adapters_for_all_verticals(self):
        """Test that gym, phones, clothing adapters are registered."""
        expected_verticals = ['gym', 'phones', 'clothing']
        for vertical in expected_verticals:
            with self.subTest(vertical=vertical):
                adapter = registry.get_adapter(vertical)
                self.assertIsNotNone(
                    adapter,
                    f"Adapter for {vertical} should be registered"
                )
                self.assertEqual(adapter.vertical_key, vertical)
    
    def test_gym_adapter_has_entities(self):
        """Test that gym adapter exposes correctable entities."""
        adapter = registry.get_adapter('gym')
        entities = adapter.get_entities()
        
        # Should have at least gym_member entity
        self.assertIn('gym_member', entities)
        
        # Check entity config structure
        gym_member = entities['gym_member']
        self.assertEqual(gym_member.model, GymMember)
        self.assertIn('name', gym_member.fields)
        self.assertIn('phone', gym_member.fields)
    
    def test_phones_adapter_has_entities(self):
        """Test that phones adapter exposes correctable entities."""
        adapter = registry.get_adapter('phones')
        entities = adapter.get_entities()
        
        # Should have at least phone_sale entity
        self.assertIn('phone_sale', entities)
        
        # Check entity config structure
        phone_sale = entities['phone_sale']
        self.assertEqual(phone_sale.model, InventoryItem)
    
    def test_clothing_adapter_has_entities(self):
        """Test that clothing adapter exposes correctable entities."""
        adapter = registry.get_adapter('clothing')
        entities = adapter.get_entities()
        
        # Should have at least clothing_sale entity
        self.assertIn('clothing_sale', entities)


class TestCorrectionsViewsVerticalAware(TestCase):
    """Test that correction views work for all registered verticals."""
    
    def setUp(self):
        """Create test user, business, and sample data."""
        self.user = User.objects.create_user(
            username='manager@test.com',
            email='manager@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Business',
            business_kind='gym',
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Location',
        )
        # Create manager membership
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            is_active=True,
        )
        self.client = Client()
        self.client.login(username='manager@test.com', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['biz_id'] = self.business.id
        session.save()
    
    def test_corrections_dashboard_returns_200_for_gym(self):
        """Test that /corrections/gym/ returns 200 (not 404)."""
        url = reverse('corrections:dashboard', kwargs={'vertical': 'gym'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Data Corrections')
    
    def test_corrections_dashboard_shows_gym_entities(self):
        """Test that gym corrections dashboard shows gym-specific entities."""
        url = reverse('corrections:dashboard', kwargs={'vertical': 'gym'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Should show gym entities
        self.assertContains(response, 'Gym Member')
    
    def test_corrections_dashboard_does_not_show_wrong_vertical_entities(self):
        """Test that gym dashboard doesn't show phones/clothing entities."""
        url = reverse('corrections:dashboard', kwargs={'vertical': 'gym'})
        response = self.client.get(url)
        
        # Should NOT show phone-specific entities
        # (This assumes phones have different entities than gym)
        # If there's overlap, adjust this test
        self.assertNotContains(response, 'Phone IMEI')
    
    def test_unregistered_vertical_returns_error(self):
        """Test that accessing corrections for unregistered vertical shows error."""
        # 'liquor' is not registered in adapters yet
        url = reverse('corrections:dashboard', kwargs={'vertical': 'liquor'})
        response = self.client.get(url)
        
        # Should redirect or show error message
        # (Based on views.py line 67-68, it redirects with error message)
        self.assertEqual(response.status_code, 302)


class TestCorrectionsPermissions(TestCase):
    """Test that corrections are manager-only."""
    
    def setUp(self):
        """Create test users and business."""
        self.manager = User.objects.create_user(
            username='manager@test.com',
            email='manager@test.com',
            password='testpass123'
        )
        self.staff = User.objects.create_user(
            username='staff@test.com',
            email='staff@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Business',
            business_kind='gym',
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Location',
        )
        # Create manager membership
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER',
            is_active=True,
        )
        # Create staff membership (non-manager)
        Membership.objects.create(
            user=self.staff,
            business=self.business,
            role='AGENT',
            is_active=True,
        )
    
    def test_manager_can_access_corrections(self):
        """Test that manager can access corrections dashboard."""
        client = Client()
        client.login(username='manager@test.com', password='testpass123')
        
        # Set active business
        session = client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('corrections:dashboard', kwargs={'vertical': 'gym'})
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
    
    def test_staff_cannot_access_corrections(self):
        """Test that non-manager staff cannot access corrections."""
        client = Client()
        client.login(username='staff@test.com', password='testpass123')
        
        # Set active business
        session = client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('corrections:dashboard', kwargs={'vertical': 'gym'})
        response = client.get(url)
        
        # Should be redirected or get 403
        self.assertIn(response.status_code, [302, 403])


class TestCorrectionsSmokeTest(TestCase):
    """Smoke test: Apply a correction and verify it works end-to-end."""
    
    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username='manager@test.com',
            email='manager@test.com',
            password='testpass123',
            is_staff=True  # Make user a staff member for manager permissions
        )
        self.business = Business.objects.create(
            name='Test Gym',
            business_kind='gym',
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Location',
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            is_active=True,
        )
        
        # Create a gym member with an error (wrong phone number)
        self.member = GymMember.objects.create(
            business=self.business,
            name='John Doe',
            phone='0123456789',  # Wrong phone
            membership_fee=Decimal('50.00'),
        )
    
    def test_create_and_apply_correction(self):
        """Test creating and applying a correction for gym member phone."""
        # Create a mock request with the user and business context
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        request.business = self.business
        
        service = CorrectionService(
            business=self.business,
            user=self.user,
            request=request,
        )
        
        # Step 1: Create batch
        batch_result = service.create_batch(
            vertical='gym',
            reason='Fix incorrect phone number',
            notes='Member reported wrong number in system',
        )
        self.assertTrue(batch_result.success)
        batch = batch_result.batch
        
        # Step 2: Add correction item
        items = [
            {
                'entity_label': 'gym_member',
                'object_id': self.member.id,
                'field_name': 'phone',
                'new_value': '0987654321',  # Correct phone
            }
        ]
        add_result = service.add_items(batch=batch, items=items)
        self.assertTrue(add_result.success)
        
        # Step 3: Apply batch
        apply_result = service.apply_batch(batch)
        self.assertTrue(apply_result.success, f"Apply failed: {apply_result.message}")
        
        # Step 4: Verify member phone was updated
        self.member.refresh_from_db()
        self.assertEqual(self.member.phone, '0987654321')
        
        # Step 5: Verify batch status
        batch.refresh_from_db()
        self.assertEqual(batch.status, CorrectionStatus.APPLIED)
        
        # Step 6: Verify audit log was created
        self.assertEqual(batch.audit_logs.count(), 1)


class TestCorrectionsTemplateFilter(TestCase):
    """Test that the lookup template filter works correctly."""
    
    def test_lookup_filter_with_valid_attribute(self):
        """Test lookup filter returns attribute value."""
        from corrections.templatetags.corrections_tags import lookup
        
        # Create a simple object with attributes
        class TestObj:
            name = "John Doe"
            phone = "0123456789"
        
        obj = TestObj()
        
        # Test lookup
        self.assertEqual(lookup(obj, 'name'), 'John Doe')
        self.assertEqual(lookup(obj, 'phone'), '0123456789')
    
    def test_lookup_filter_with_missing_attribute(self):
        """Test lookup filter returns None for missing attribute."""
        from corrections.templatetags.corrections_tags import lookup
        
        class TestObj:
            name = "John Doe"
        
        obj = TestObj()
        
        # Test lookup for non-existent attribute
        self.assertIsNone(lookup(obj, 'missing_field'))
    
    def test_lookup_filter_with_none_object(self):
        """Test lookup filter handles None gracefully."""
        from corrections.templatetags.corrections_tags import lookup
        
        result = lookup(None, 'any_field')
        self.assertIsNone(result)


class TestCorrectionsViewRendering(TestCase):
    """Test that corrections views render without template errors."""
    
    def setUp(self):
        """Create test user, business, and sample data."""
        self.user = User.objects.create_user(
            username='manager@test.com',
            email='manager@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Gym',
            business_kind='gym',
        )
        self.location = Location.objects.create(
            business=self.business,
            name='Main Location',
        )
        # Create manager membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            is_active=True,
        )
        self.client = Client()
        self.client.login(username='manager@test.com', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['biz_id'] = self.business.id
        session.save()
        
        # Create a gym member for testing
        self.member = GymMember.objects.create(
            business=self.business,
            name='John Doe',
            phone='0123456789',
            membership_fee=Decimal('50.00'),
        )
    
    def test_browse_entity_renders_without_template_error(self):
        """Test that browse_entity view renders successfully (no TemplateSyntaxError)."""
        url = reverse('corrections:browse_entity', kwargs={
            'vertical': 'gym',
            'entity_label': 'gym_member'
        })
        response = self.client.get(url)
        
        # Should return 200, not 500
        self.assertEqual(response.status_code, 200)
        
        # Should contain expected content
        self.assertContains(response, 'Gym Member')
        self.assertContains(response, 'John Doe')
    
    def test_edit_record_renders_without_template_error(self):
        """Test that edit_record view renders successfully."""
        url = reverse('corrections:edit_record', kwargs={
            'vertical': 'gym',
            'entity_label': 'gym_member',
            'object_id': self.member.id
        })
        response = self.client.get(url)
        
        # Should return 200, not 500
        self.assertEqual(response.status_code, 200)
        
        # Should contain expected content
        self.assertContains(response, 'John Doe')
        self.assertContains(response, 'Reason for Correction')
    
    def test_dashboard_renders_without_error(self):
        """Test that corrections dashboard renders successfully."""
        url = reverse('corrections:dashboard', kwargs={'vertical': 'gym'})
        response = self.client.get(url)
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
        
        # Should contain expected content
        self.assertContains(response, 'Data Corrections')
        self.assertContains(response, 'Gym Member')


class TestCorrectionsSidebarGeneration(TestCase):
    """Test that sidebar link for Data Correction is generated correctly."""
    
    def test_get_data_correction_menu_item_for_registered_vertical(self):
        """Test _get_data_correction_menu_item() returns correct URL."""
        from inventory.utils_verticals import _get_data_correction_menu_item
        
        item = _get_data_correction_menu_item('gym')
        
        self.assertIsNotNone(item)
        self.assertEqual(item['key'], 'data_correction')
        self.assertEqual(item['label'], 'Data Correction')
        self.assertEqual(item['url'], '/corrections/gym/')
        self.assertTrue(item['require_manager'])
    
    def test_get_data_correction_menu_item_for_unregistered_vertical(self):
        """Test that unregistered vertical returns None (no menu item)."""
        from inventory.utils_verticals import _get_data_correction_menu_item
        
        # 'liquor' is not registered yet
        item = _get_data_correction_menu_item('liquor')
        
        # Should return None (no menu item shown)
        self.assertIsNone(item)
    
    def test_inject_data_correction_into_sidebar(self):
        """Test that _inject_data_correction_into_sidebar adds item."""
        from inventory.utils_verticals import _inject_data_correction_into_sidebar
        
        # Simulate a sidebar items list
        items = [
            {'section': 'MAIN', 'key': 'dashboard', 'label': 'Dashboard'},
            {'section': 'MAIN', 'key': 'members', 'label': 'Members'},
            {'section': 'MORE', 'key': 'settings', 'label': 'Settings'},
        ]
        
        result = _inject_data_correction_into_sidebar(items, 'gym')
        
        # Should have added Data Correction
        dc_items = [i for i in result if i.get('key') == 'data_correction']
        self.assertEqual(len(dc_items), 1)
        
        # Should be in MAIN section
        dc_item = dc_items[0]
        self.assertEqual(dc_item['section'], 'MAIN')
        self.assertEqual(dc_item['url'], '/corrections/gym/')


# Run tests
if __name__ == '__main__':
    import unittest
    unittest.main()
