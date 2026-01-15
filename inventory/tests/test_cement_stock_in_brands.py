"""
Regression tests for cement stock-in wizard (2-step flow - Jan 2026).

NEW FLOW (Simplified):
- Step 1: Select cement brand directly (from seeded DB products)
- Step 2: Enter quantity, cost price, selling price

Tests verify:
1. Step 1 shows real cement brands from DB
2. Step 2 shows selected product name
3. Stock-in updates existing product (no duplicates)
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

    def test_step1_shows_cement_brands_from_db(self):
        """
        TEST 1: Step 1 shows cement brands from DB (NEW 2-STEP FLOW).
        
        Verify that step 1 displays actual cement products (Dangote, Akshar)
        from the database, not catalog brands.
        """
        url = reverse('cement:stock_in')
        response = self.client.get(f"{url}?step=1")
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Should contain actual cement brands
        self.assertIn('Dangote', content)
        self.assertIn('Akshar', content)
        
        # Should contain product IDs (proving we're using DB products)
        self.assertIn(str(self.dangote.id), content)
        self.assertIn(str(self.akshar.id), content)

    def test_step1_to_step2_advances_flow(self):
        """
        TEST 2: Selecting brand in step 1 advances to step 2 (NEW 2-STEP FLOW).
        
        Verify that posting a product_id in step 1 redirects to step 2.
        """
        url = reverse('cement:stock_in')
        
        # POST step 1: Select Dangote
        response = self.client.post(
            f"{url}?step=1",
            {'product_id': str(self.dangote.id)}
        )
        
        # Should redirect to step 2
        self.assertEqual(response.status_code, 302)
        self.assertIn('?step=2', response.url)

    def test_step2_shows_selected_product_name(self):
        """
        TEST 3: Step 2 shows selected brand product name (NEW 2-STEP FLOW).
        
        Verify that after selecting "Dangote" in step 1, step 2 shows
        "Dangote Cement BAG (50KG)" not just generic "Cement".
        """
        url = reverse('cement:stock_in')
        
        # Step 1: Select Dangote
        self.client.post(f"{url}?step=1", {'product_id': str(self.dangote.id)})
        
        # Get step 2 (quantity & pricing)
        response = self.client.get(f"{url}?step=2")
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Should show the specific product name
        self.assertIn('Dangote', content)

    def test_step2_updates_existing_product_stock(self):
        """
        TEST 4: Submitting step 2 updates selected product stock (NEW 2-STEP FLOW).
        
        Verify that completing the flow adds stock to the selected product.
        """
        url = reverse('cement:stock_in')
        
        # Step 1: Select Dangote
        self.client.post(f"{url}?step=1", {'product_id': str(self.dangote.id)})
        
        # Check initial stock
        self.dangote.refresh_from_db()
        initial_stock = self.dangote.quantity_in_stock
        
        # Step 2: Submit quantity & pricing
        response = self.client.post(
            f"{url}?step=2",
            {
                'quantity': '20',
                'cost_price': '25000',
                'selling_price': '28000'
            }
        )
        
        # Should redirect (success)
        self.assertEqual(response.status_code, 302)
        
        # Verify stock was updated
        self.dangote.refresh_from_db()
        self.assertEqual(self.dangote.quantity_in_stock, initial_stock + 20)
        self.assertEqual(self.dangote.cost_price, 25000)
        self.assertEqual(self.dangote.selling_price, 28000)

    def test_step1_filters_only_cement_products(self):
        """
        TEST 5: Step 1 shows only cement products (NEW 2-STEP FLOW).
        
        Verify that paint/iron products don't appear in cement brand list.
        """
        # Create a paint product (should not appear in cement stock-in)
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
        
        # Get step 1
        url = reverse('cement:stock_in')
        response = self.client.get(f"{url}?step=1")
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Should show cement brands
        self.assertIn('Dangote', content)
        self.assertIn('Akshar', content)
        
        # Should NOT show paint products (paint has its own flow)
        # Note: "Rainbow" is distinctive enough to test
        self.assertNotIn('Rainbow', content)

