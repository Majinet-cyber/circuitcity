"""
Tests for Liquor Wizard V2 - Pure Link Flow (No JS Alerts)

This test suite verifies that:
1. The liquor wizard page renders without JavaScript alerts
2. Category cards are pure <a> links (no JavaScript)
3. The catalog flow works end-to-end
4. Stock-in flow saves transactions correctly
5. LIQUOR_WIZARD_V2 proof markers are present
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from inventory.models import MerchProduct, Location
from inventory.business_kinds import BusinessKind

User = get_user_model()


class LiquorWizardV2TestCase(TestCase):
    """Test the new liquor wizard flow (pure links, no JS alerts)"""

    def setUp(self):
        """Set up test fixtures"""
        self.client = Client()
        
        # Create user
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123'
        )
        
        # Create business
        self.business = Business.objects.create(
            name='Test Liquor Store',
            slug='test-liquor-store',
            kind=BusinessKind.LIQUOR
        )
        
        # Add user as manager
        Membership.objects.create(
            business=self.business,
            user=self.user,
            role='manager'
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store',
            is_active=True
        )
        
        # Login and set active business
        self.client.login(username='testmanager', password='testpass123')
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_liquor_wizard_renders_successfully(self):
        """Test that /inventory/wizard/liquor/ returns 200"""
        url = reverse('inventory:liquor_wizard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose Liquor Category')

    def test_liquor_wizard_has_proof_marker(self):
        """Test that LIQUOR_WIZARD_V2 proof marker is present"""
        url = reverse('inventory:liquor_wizard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Check for proof marker in content
        content = response.content.decode('utf-8')
        self.assertIn('LIQUOR_WIZARD_V2', content, "LIQUOR_WIZARD_V2 marker should be present in the page")

    def test_liquor_wizard_has_pure_links(self):
        """Test that category cards are pure <a> links (no JavaScript)"""
        url = reverse('inventory:liquor_wizard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check for pure <a> tags to catalog pages
        self.assertContains(response, 'href="/inventory/liquor/catalog/beer/"')
        self.assertContains(response, 'href="/inventory/liquor/catalog/cider/"')
        self.assertContains(response, 'href="/inventory/liquor/catalog/wine/"')
        self.assertContains(response, 'href="/inventory/liquor/catalog/spirits/"')
        self.assertContains(response, 'href="/inventory/liquor/catalog/whisky/"')
        
        # Verify NO wizard-engine.js
        self.assertNotContains(response, 'wizard-engine.js')
        
        # Verify NO WizardEngine class instantiation
        self.assertNotContains(response, 'new WizardEngine')

    def test_liquor_wizard_no_javascript_validation(self):
        """Test that there's no JavaScript validation code"""
        url = reverse('inventory:liquor_wizard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify NO validation code
        self.assertNotContains(response, 'required: true')
        self.assertNotContains(response, 'product_name')
        self.assertNotContains(response, 'submitMultiInput')
        self.assertNotContains(response, 'selectCard')

    def test_beer_catalog_renders(self):
        """Test that /inventory/liquor/catalog/beer/ returns 200"""
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'beer'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Beer Catalog')
        self.assertContains(response, 'data-proof="LIQUOR_WIZARD_V2"')

    def test_cider_catalog_renders(self):
        """Test that /inventory/liquor/catalog/cider/ returns 200"""
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'cider'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cider Catalog')

    def test_wine_catalog_renders(self):
        """Test that /inventory/liquor/catalog/wine/ returns 200"""
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'wine'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Wine Catalog')

    def test_spirits_catalog_renders(self):
        """Test that /inventory/liquor/catalog/spirits/ returns 200"""
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'spirits'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Spirits Catalog')

    def test_whisky_catalog_renders(self):
        """Test that /inventory/liquor/catalog/whisky/ returns 200"""
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'whisky'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Whisky Catalog')

    def test_catalog_auto_seeds_products(self):
        """Test that catalog auto-seeds products if empty"""
        # Verify no products exist initially
        count_before = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.LIQUOR,
            category='beer'
        ).count()
        self.assertEqual(count_before, 0)
        
        # Visit catalog
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'beer'})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify products were seeded
        count_after = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.LIQUOR,
            category='beer'
        ).count()
        self.assertGreater(count_after, 0, "Catalog should auto-seed products")

    def test_stock_in_page_renders(self):
        """Test that stock-in page renders for a product"""
        # Create a product
        product = MerchProduct.objects.create(
            business=self.business,
            name='Test Beer',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=1000,
            selling_price=1000,
            is_active=True
        )
        
        url = reverse('inventory:liquor_stock_in', kwargs={'product_id': product.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Stock In')
        self.assertContains(response, 'Test Beer')
        self.assertContains(response, 'data-proof="LIQUOR_WIZARD_V2"')

    def test_stock_in_submit_saves_transaction(self):
        """Test that stock-in form submission saves correctly"""
        # Create a product
        product = MerchProduct.objects.create(
            business=self.business,
            name='Test Beer',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=1000,
            selling_price=1000,
            quantity_in_stock=0,
            is_active=True
        )
        
        # Submit stock-in form
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
        data = {
            'quantity': 50,
            'cost_per_unit': 800,
            'notes': 'Test stock-in'
        }
        response = self.client.post(url, data)
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        # Verify stock was updated
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 50)
        self.assertEqual(float(product.cost_per_bottle), 800.0)

    def test_stock_in_requires_quantity(self):
        """Test that stock-in form requires quantity"""
        # Create a product
        product = MerchProduct.objects.create(
            business=self.business,
            name='Test Beer',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=1000,
            selling_price=1000,
            is_active=True
        )
        
        # Submit without quantity
        url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
        data = {
            'cost_per_unit': 800,
        }
        response = self.client.post(url, data)
        
        # Should redirect back with error
        self.assertEqual(response.status_code, 302)

    def test_invalid_category_redirects(self):
        """Test that invalid category redirects with error"""
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'invalid'})
        response = self.client.get(url)
        
        # Should redirect
        self.assertEqual(response.status_code, 302)

    def test_catalog_search_works(self):
        """Test that catalog search filters products"""
        # Create products
        MerchProduct.objects.create(
            business=self.business,
            name='Castle Lager',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=1000,
            selling_price=1000,
            is_active=True
        )
        MerchProduct.objects.create(
            business=self.business,
            name='Carlsberg',
            kind=BusinessKind.LIQUOR,
            category='beer',
            price_per_bottle=1200,
            selling_price=1200,
            is_active=True
        )
        
        # Search for "Castle"
        url = reverse('inventory:liquor_catalog', kwargs={'category': 'beer'})
        response = self.client.get(url, {'q': 'Castle'})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Castle Lager')
        self.assertNotContains(response, 'Carlsberg')

    def test_end_to_end_flow(self):
        """Test complete flow: wizard → catalog → stock-in"""
        # Step 1: Visit wizard
        wizard_url = reverse('inventory:liquor_wizard')
        response = self.client.get(wizard_url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('LIQUOR_WIZARD_V2', content, "Wizard page should have V2 marker")
        
        # Step 2: Visit catalog (should auto-seed)
        catalog_url = reverse('inventory:liquor_catalog', kwargs={'category': 'beer'})
        response = self.client.get(catalog_url)
        self.assertEqual(response.status_code, 200)
        
        # Get first product
        product = MerchProduct.objects.filter(
            business=self.business,
            kind=BusinessKind.LIQUOR,
            category='beer',
            is_active=True
        ).first()
        self.assertIsNotNone(product, "Catalog should have seeded products")
        
        # Step 3: Visit stock-in page
        stock_in_url = reverse('inventory:liquor_stock_in', kwargs={'product_id': product.id})
        response = self.client.get(stock_in_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, product.name)
        
        # Step 4: Submit stock-in
        submit_url = reverse('inventory:liquor_stock_in_submit', kwargs={'product_id': product.id})
        data = {
            'quantity': 100,
            'cost_per_unit': 900,
            'notes': 'End-to-end test'
        }
        response = self.client.post(submit_url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify stock was updated
        product.refresh_from_db()
        self.assertEqual(product.quantity_in_stock, 100)


@pytest.mark.django_db
class TestLiquorWizardV2Pytest:
    """Pytest version of liquor wizard tests"""
    
    def test_wizard_page_has_no_alerts(self, client, django_user_model):
        """Verify no JavaScript alert code in wizard page"""
        # Create user and business
        user = django_user_model.objects.create_user(
            username='testuser',
            password='testpass'
        )
        business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            kind=BusinessKind.LIQUOR
        )
        Membership.objects.create(
            business=business,
            user=user,
            role='manager'
        )
        
        # Login
        client.login(username='testuser', password='testpass')
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Get wizard page
        url = reverse('inventory:liquor_wizard')
        response = client.get(url)
        
        assert response.status_code == 200
        assert b'LIQUOR_WIZARD_V2' in response.content
        assert b'wizard-engine.js' not in response.content
        assert b'alert(' not in response.content
        assert b'Product name is required' not in response.content

