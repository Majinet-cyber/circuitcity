"""
Regression tests for cement stock-in wizard (brand product selection).

Tests that cement stock-in wizard:
1. Shows only Cement in step 2 when only cement products exist
2. Shows real cement brand products from DB (not catalog) in step 3
3. Shows selected brand product name (not generic) in step 4

FIX (Jan 2026): Cement stock-in must use actual DB products, not catalog brands.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind

User = get_user_model()


class CementStockInBrandTests(TestCase):
    """Test cement stock-in wizard brand product selection."""

    def setUp(self):
        """Set up test fixtures."""
        # Create user
        self.user = User.objects.create_user(
            username='cementmanager',
            email='cement@example.com',
            password='cement123'
        )
        
        # Create cement business
        self.business = Business.objects.create(
            name='Test Cement Business',
            business_kind='CEMENT',
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
        self.client.login(username='cementmanager', password='cement123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create cement products (Dangote, Akshar)
        self.dangote = MerchProduct.objects.create(
            business=self.business,
            name='Dangote Cement BAG (50KG)',
            kind=BusinessKind.CEMENT,
            category='cement',
            spec_label='',
            cost_price=25000,
            selling_price=28000,
            quantity_in_stock=10,
            base_unit='bag',
            is_active=True,
            track_inventory=True
        )
        
        self.akshar = MerchProduct.objects.create(
            business=self.business,
            name='Akshar Cement BAG (50KG)',
            kind=BusinessKind.CEMENT,
            category='cement',
            spec_label='',
            cost_price=24000,
            selling_price=27000,
            quantity_in_stock=5,
            base_unit='bag',
            is_active=True,
            track_inventory=True
        )

    def test_step2_shows_only_cement_when_only_cement_products_exist(self):
        """
        TEST 1: Step 2 shows only Cement when only cement products exist.
        
        Verify that Paint, Iron Sheets, Angle Iron are hidden when the business
        has not stocked those products.
        """
        # Start wizard - navigate to step 2 (product type selection)
        # First select category
        url = reverse('cement:stock_in')
        response = self.client.post(
            f"{url}?step=1",
            {'category': 'construction-materials'}
        )
        self.assertEqual(response.status_code, 302)
        
        # Get step 2
        response = self.client.get(f"{url}?step=2")
        self.assertEqual(response.status_code, 200)
        
        # Should contain "Cement"
        content = response.content.decode('utf-8')
        self.assertIn('Cement', content)
        
        # Should NOT contain other product types (no paint/iron products exist)
        self.assertNotIn('Paint', content)
        self.assertNotIn('Iron Sheets', content)
        self.assertNotIn('Angle Iron', content)

    def test_step3_lists_real_cement_brand_products_from_db(self):
        """
        TEST 2: Step 3 lists real cement brand products from DB.
        
        Verify that the brand selection step shows actual products
        (Dangote, Akshar) not catalog brands.
        """
        # Navigate to step 3 for cement
        url = reverse('cement:stock_in')
        
        # Select category
        self.client.post(f"{url}?step=1", {'category': 'construction-materials'})
        
        # Select cement product
        self.client.post(f"{url}?step=2", {'product': 'cement'})
        
        # Get step 3 (brand selection)
        response = self.client.get(f"{url}?step=3")
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Should contain actual product brand names
        self.assertIn('Dangote', content)
        self.assertIn('Akshar', content)
        
        # Should contain product IDs (proving we're using DB products)
        self.assertIn(f'value="{self.dangote.id}"', content)
        self.assertIn(f'value="{self.akshar.id}"', content)

    def test_step4_shows_selected_brand_product_name(self):
        """
        TEST 3: Step 4 shows the selected brand product name (not generic).
        
        Verify that after selecting "Dangote", step 4 shows
        "Product: Dangote Cement BAG (50KG)" not just "Cement BAG (50KG)".
        """
        url = reverse('cement:stock_in')
        
        # Navigate through wizard to step 4
        # Step 1: Select category
        self.client.post(f"{url}?step=1", {'category': 'construction-materials'})
        
        # Step 2: Select cement
        self.client.post(f"{url}?step=2", {'product': 'cement'})
        
        # Step 3: Select Dangote product
        self.client.post(f"{url}?step=3", {'product_id': str(self.dangote.id)})
        
        # Get step 4 (quantity & pricing)
        response = self.client.get(f"{url}?step=4")
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Should show the specific product name (Dangote Cement BAG 50KG)
        self.assertIn('Dangote Cement BAG (50KG)', content)
        
        # Should NOT show just generic "Cement BAG (50KG)" without brand
        # (We allow it if it's part of the full name, but verify brand is there)
        self.assertIn('Dangote', content)

    def test_step4_updates_existing_cement_product_stock(self):
        """
        TEST 4: Submitting step 4 updates the selected product's stock.
        
        Verify that stocking in adds to the selected product's quantity.
        """
        url = reverse('cement:stock_in')
        
        # Navigate to step 4 with Dangote selected
        self.client.post(f"{url}?step=1", {'category': 'construction-materials'})
        self.client.post(f"{url}?step=2", {'product': 'cement'})
        self.client.post(f"{url}?step=3", {'product_id': str(self.dangote.id)})
        
        # Check initial stock
        self.dangote.refresh_from_db()
        initial_stock = self.dangote.quantity_in_stock
        
        # Submit step 4 (add 20 bags)
        response = self.client.post(
            f"{url}?step=4",
            {
                'quantity': '20',
                'cost_price': '25000',
                'selling_price': '28000'
            }
        )
        
        # Should redirect to stock-in home (success)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('cement:stock_in')))
        
        # Verify stock was updated
        self.dangote.refresh_from_db()
        self.assertEqual(self.dangote.quantity_in_stock, initial_stock + 20)
        self.assertEqual(self.dangote.cost_price, 25000)
        self.assertEqual(self.dangote.selling_price, 28000)

    def test_step2_shows_paint_when_paint_products_exist(self):
        """
        TEST 5: Step 2 shows Paint when business has paint products.
        
        Verify that non-cement product types appear once they're stocked.
        """
        # Create a paint product
        MerchProduct.objects.create(
            business=self.business,
            name='Rainbow Paint 5L Emulsion White',
            kind=BusinessKind.CEMENT,
            category='paint',
            spec_label='',
            cost_price=15000,
            selling_price=18000,
            quantity_in_stock=3,
            base_unit='tin',
            is_active=True,
            track_inventory=True
        )
        
        # Navigate to step 2
        url = reverse('cement:stock_in')
        self.client.post(f"{url}?step=1", {'category': 'construction-materials'})
        
        response = self.client.get(f"{url}?step=2")
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Should show both Cement and Paint
        self.assertIn('Cement', content)
        self.assertIn('Paint', content)
        
        # Should NOT show Iron Sheets (no iron products)
        self.assertNotIn('Iron Sheets', content)

