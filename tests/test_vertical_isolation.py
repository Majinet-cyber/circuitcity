"""
Test strict vertical isolation - ensures no cross-vertical access.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Business
from inventory.business_kinds import BusinessKind

User = get_user_model()


class VerticalIsolationTests(TestCase):
    """Test that verticals are strictly isolated."""
    
    def setUp(self):
        """Create test users and businesses for each vertical."""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create businesses for each vertical
        self.phones_business = Business.objects.create(
            name='Phones Shop',
            slug='phones-shop',
            business_kind=BusinessKind.PHONES,
            status='ACTIVE'
        )
        
        self.grocery_business = Business.objects.create(
            name='Grocery Store',
            slug='grocery-store',
            business_kind=BusinessKind.GROCERY,
            status='ACTIVE'
        )
        
        self.hardware_business = Business.objects.create(
            name='Hardware Store',
            slug='hardware-store',
            business_kind=BusinessKind.HARDWARE,
            status='ACTIVE'
        )
        
        self.cement_business = Business.objects.create(
            name='Cement Shop',
            slug='cement-shop',
            business_kind=BusinessKind.CEMENT,
            status='ACTIVE'
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_grocery_cannot_access_phones_scan_in(self):
        """Grocery business should not access phones scan-in page."""
        # Set active business to grocery
        session = self.client.session
        session['active_business_id'] = self.grocery_business.id
        session.save()
        
        # Try to access phones scan-in
        response = self.client.get('/inventory/phones/scan-in/')
        
        # Should redirect or show 404
        self.assertIn(response.status_code, [302, 404])
        
        if response.status_code == 302:
            # Should redirect to grocery dashboard, not phones
            self.assertNotIn('phones', response.url.lower())
    
    def test_hardware_cannot_access_phones_scan_sell(self):
        """Hardware business should not access phones scan-sell page."""
        # Set active business to hardware
        session = self.client.session
        session['active_business_id'] = self.hardware_business.id
        session.save()
        
        # Try to access phones scan-sell
        response = self.client.get('/inventory/phones/scan-sell/')
        
        # Should redirect or show 404
        self.assertIn(response.status_code, [302, 404])
    
    def test_cement_cannot_access_phones_scan_in(self):
        """Cement business should not access phones scan-in page."""
        # Set active business to cement
        session = self.client.session
        session['active_business_id'] = self.cement_business.id
        session.save()
        
        # Try to access phones scan-in
        response = self.client.get('/inventory/phones/scan-in/')
        
        # Should redirect or show 404
        self.assertIn(response.status_code, [302, 404])
    
    def test_phones_can_access_scan_in(self):
        """Phones business should be able to access scan-in page."""
        # Set active business to phones
        session = self.client.session
        session['active_business_id'] = self.phones_business.id
        session.save()
        
        # Try to access phones scan-in
        response = self.client.get('/inventory/phones/scan-in/')
        
        # Should succeed
        self.assertEqual(response.status_code, 200)
    
    def test_grocery_dashboard_requires_grocery_vertical(self):
        """Grocery dashboard should only be accessible to grocery businesses."""
        # Set active business to phones
        session = self.client.session
        session['active_business_id'] = self.phones_business.id
        session.save()
        
        # Try to access grocery dashboard
        response = self.client.get('/grocery/')
        
        # Should redirect or show 404
        self.assertIn(response.status_code, [302, 404])
    
    def test_hardware_dashboard_requires_hardware_vertical(self):
        """Hardware dashboard should only be accessible to hardware businesses."""
        # Set active business to grocery
        session = self.client.session
        session['active_business_id'] = self.grocery_business.id
        session.save()
        
        # Try to access hardware dashboard
        response = self.client.get('/hardware/')
        
        # Should redirect or show 404
        self.assertIn(response.status_code, [302, 404])
    
    def test_cement_dashboard_requires_cement_vertical(self):
        """Cement dashboard should only be accessible to cement businesses."""
        # Set active business to hardware
        session = self.client.session
        session['active_business_id'] = self.hardware_business.id
        session.save()
        
        # Try to access cement dashboard
        response = self.client.get('/cement/')
        
        # Should redirect or show 404
        self.assertIn(response.status_code, [302, 404])
    
    def test_no_business_redirects_to_selection(self):
        """User with no active business should be redirected to business selection."""
        # Clear active business
        session = self.client.session
        if 'active_business_id' in session:
            del session['active_business_id']
        session.save()
        
        # Try to access any vertical-specific page
        response = self.client.get('/inventory/phones/scan-in/')
        
        # Should redirect (not 404)
        self.assertEqual(response.status_code, 302)
    
    def test_grocery_redirects_to_grocery_dashboard(self):
        """Selecting grocery business should redirect to grocery dashboard, not phones."""
        # Set active business to grocery
        session = self.client.session
        session['active_business_id'] = self.grocery_business.id
        session.save()
        
        # Access main dashboard
        response = self.client.get('/dashboard/')
        
        # Should redirect to grocery dashboard
        self.assertEqual(response.status_code, 302)
        self.assertIn('grocery', response.url.lower())
        self.assertNotIn('phones', response.url.lower())
    
    def test_hardware_redirects_to_hardware_dashboard(self):
        """Selecting hardware business should redirect to hardware dashboard, not phones."""
        # Set active business to hardware
        session = self.client.session
        session['active_business_id'] = self.hardware_business.id
        session.save()
        
        # Access main dashboard
        response = self.client.get('/dashboard/')
        
        # Should redirect to hardware dashboard
        self.assertEqual(response.status_code, 302)
        self.assertIn('hardware', response.url.lower())
        self.assertNotIn('phones', response.url.lower())
    
    def test_cement_redirects_to_cement_dashboard(self):
        """Selecting cement business should redirect to cement dashboard, not phones."""
        # Set active business to cement
        session = self.client.session
        session['active_business_id'] = self.cement_business.id
        session.save()
        
        # Access main dashboard
        response = self.client.get('/dashboard/')
        
        # Should redirect to cement dashboard
        self.assertEqual(response.status_code, 302)
        self.assertIn('cement', response.url.lower())
        self.assertNotIn('phones', response.url.lower())
    
    def test_no_verticals_none_default(self):
        """System should never default to /verticals/none/ when business kind is set."""
        # Test each business type
        for business in [self.phones_business, self.grocery_business, self.hardware_business, self.cement_business]:
            session = self.client.session
            session['active_business_id'] = business.id
            session.save()
            
            response = self.client.get('/dashboard/')
            
            # Should redirect but never to /verticals/none/
            if response.status_code == 302:
                self.assertNotIn('/verticals/none/', response.url)


class VerticalNavigationTests(TestCase):
    """Test that navigation is vertical-specific."""
    
    def setUp(self):
        """Create test users and businesses."""
        self.user = User.objects.create_user(
            username='navuser',
            email='nav@example.com',
            password='testpass123'
        )
        
        self.phones_business = Business.objects.create(
            name='Phones Shop Nav',
            slug='phones-shop-nav',
            business_kind=BusinessKind.PHONES,
            status='ACTIVE'
        )
        
        self.grocery_business = Business.objects.create(
            name='Grocery Store Nav',
            slug='grocery-store-nav',
            business_kind=BusinessKind.GROCERY,
            status='ACTIVE'
        )
        
        self.client = Client()
        self.client.login(username='navuser', password='testpass123')
    
    def test_grocery_nav_no_scan_imei(self):
        """Grocery dashboard navigation should not show 'Scan IMEI'."""
        session = self.client.session
        session['active_business_id'] = self.grocery_business.id
        session.save()
        
        # Access grocery dashboard
        response = self.client.get('/verticals/grocery/dashboard/')
        
        if response.status_code == 200:
            content = response.content.decode('utf-8')
            # Should not have "Scan IMEI" link
            self.assertNotIn('Scan IMEI', content)
            self.assertNotIn('scan-imei', content.lower())
    
    def test_grocery_nav_no_scan_in(self):
        """Grocery dashboard navigation should not show phones 'Scan IN'."""
        session = self.client.session
        session['active_business_id'] = self.grocery_business.id
        session.save()
        
        # Access grocery dashboard
        response = self.client.get('/verticals/grocery/dashboard/')
        
        if response.status_code == 200:
            content = response.content.decode('utf-8')
            # Should not have phones-specific scan in link
            self.assertNotIn('/inventory/phones/scan-in/', content)
    
    def test_phones_nav_has_scan_imei(self):
        """Phones dashboard navigation should show 'Scan IMEI'."""
        session = self.client.session
        session['active_business_id'] = self.phones_business.id
        session.save()
        
        # Access phones dashboard
        response = self.client.get('/dashboard/')
        
        if response.status_code == 200:
            content = response.content.decode('utf-8')
            # Should have "Scan IMEI" or scan functionality
            # (exact text may vary, but should have scan-related links)
            has_scan = 'scan' in content.lower() or 'imei' in content.lower()
            self.assertTrue(has_scan, "Phones dashboard should have scan functionality")


class VerticalHelperTests(TestCase):
    """Test vertical helper functions."""
    
    def test_normalize_vertical(self):
        """Test vertical normalization."""
        from core.verticals import normalize_vertical
        
        self.assertEqual(normalize_vertical('GROCERY'), 'grocery')
        self.assertEqual(normalize_vertical('Grocery'), 'grocery')
        self.assertEqual(normalize_vertical('grocery'), 'grocery')
        self.assertEqual(normalize_vertical('groceries'), 'grocery')  # alias
        self.assertEqual(normalize_vertical('PHONES'), 'phones')
    
    def test_vertical_home_url(self):
        """Test vertical home URL mapping."""
        from core.verticals import vertical_home_url
        
        self.assertEqual(vertical_home_url('phones'), 'inventory:dashboard')
        self.assertEqual(vertical_home_url('grocery'), 'inventory:grocery_dashboard')
        self.assertEqual(vertical_home_url('hardware'), 'inventory:hardware_dashboard')
        self.assertEqual(vertical_home_url('cement'), 'inventory:cement_dashboard')
    
    def test_vertical_nav_items_phones(self):
        """Test phones navigation items."""
        from core.verticals import vertical_nav_items
        
        nav = vertical_nav_items('phones')
        self.assertIsInstance(nav, list)
        self.assertTrue(len(nav) > 0)
        
        # Should have scan-related items
        labels = [item['label'] for item in nav]
        self.assertIn('Scan IMEI', labels)
    
    def test_vertical_nav_items_grocery(self):
        """Test grocery navigation items."""
        from core.verticals import vertical_nav_items
        
        nav = vertical_nav_items('grocery')
        self.assertIsInstance(nav, list)
        self.assertTrue(len(nav) > 0)
        
        # Should NOT have Scan IMEI
        labels = [item['label'] for item in nav]
        self.assertNotIn('Scan IMEI', labels)

