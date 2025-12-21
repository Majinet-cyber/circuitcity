"""
Tests for Pharmacy & Cosmetics Stock-In Wizard Fixes

Tests verify that the wizard correctly handles:
1. Cosmetics categories show products even when DB is empty (using prefills)
2. Product selection advances to the save step
3. Save creates MerchProduct if it doesn't exist
4. Pharmacy requires expiry date, cosmetics makes it optional
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from datetime import date, timedelta

from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch, PharmacyCategory

User = get_user_model()


class PharmacyWizardCosmeticsFlowTest(TestCase):
    """Test the cosmetics flow in the pharmacy wizard."""
    
    def setUp(self):
        """Set up test user, business, and client."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Pharmacy',
            vertical='pharmacy',
            owner=self.user
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='manager'
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        self.wizard_url = reverse('pharmacy:stock_in_wizard')
    
    def test_cosmetics_step2_shows_prefills_when_db_empty(self):
        """
        Test that Step 2 (Select Product) shows prefill products for cosmetics
        categories even when the database has zero products.
        
        ACCEPTANCE TEST A: Step 3 must not be blank; show prefills + custom option.
        """
        # Step 0: Select cosmetics mode
        response = self.client.post(self.wizard_url, {
            'wizard_step': '0',
            'selected_mode': 'cosmetics',
            'action': 'next'
        })
        self.assertEqual(response.status_code, 302)
        
        # Step 1: Select Body Care category
        response = self.client.post(self.wizard_url, {
            'wizard_step': '1',
            'selected_mode': 'cosmetics',
            'selected_category': 'body_care',
            'action': 'next'
        })
        self.assertEqual(response.status_code, 302)
        
        # Step 2: Verify product options are shown (GET request)
        response = self.client.get(self.wizard_url)
        self.assertEqual(response.status_code, 200)
        
        # Verify we're at step 2
        self.assertEqual(response.context['step'], 2)
        self.assertEqual(response.context['wizard_mode'], 'cosmetics')
        self.assertEqual(response.context['selected_category'], 'body_care')
        
        # Verify items list is NOT empty
        items = response.context.get('items', [])
        self.assertIsNotNone(items, "Items context should exist")
        self.assertGreater(len(items), 0, "Items list should not be empty - should have prefills + custom option")
        
        # Verify prefill products are included (Body Care prefills)
        item_names = [item['name'] for item in items]
        self.assertIn('Body Spray', item_names, "Body Spray should be in prefills")
        self.assertIn('Body Wash', item_names, "Body Wash should be in prefills")
        
        # Verify custom option is always present
        self.assertIn('+ Add Custom Product', item_names, "Custom product option should always be available")
        
        # Verify template renders without errors
        self.assertContains(response, 'Select Product')
        self.assertContains(response, 'Body Care')
    
    def test_cosmetics_step2_combines_db_and_prefills(self):
        """
        Test that Step 2 combines existing DB products with prefills,
        deduplicating by name (case-insensitive).
        """
        # Create an existing product in DB
        MerchProduct.objects.create(
            name='Body Spray',  # This matches a prefill
            business=self.business,
            kind='pharmacy',
            category=PharmacyCategory.PERSONAL_CARE,
            is_active=True
        )
        MerchProduct.objects.create(
            name='Custom Body Lotion',  # This doesn't match any prefill
            business=self.business,
            kind='pharmacy',
            category=PharmacyCategory.PERSONAL_CARE,
            is_active=True
        )
        
        # Navigate to Step 2 for body_care
        self.client.post(self.wizard_url, {
            'wizard_step': '0',
            'selected_mode': 'cosmetics',
            'action': 'next'
        })
        self.client.post(self.wizard_url, {
            'wizard_step': '1',
            'selected_mode': 'cosmetics',
            'selected_category': 'body_care',
            'action': 'next'
        })
        
        response = self.client.get(self.wizard_url)
        items = response.context.get('items', [])
        item_names = [item['name'] for item in items]
        
        # Should have DB products
        self.assertIn('Custom Body Lotion', item_names)
        
        # Should have Body Spray only once (deduplicated)
        body_spray_count = sum(1 for name in item_names if name == 'Body Spray')
        self.assertEqual(body_spray_count, 1, "Body Spray should appear only once (deduplicated)")
        
        # Should still have other prefills not in DB
        self.assertIn('Body Wash', item_names)
        
        # Should have custom option
        self.assertIn('+ Add Custom Product', item_names)
    
    def test_select_product_advances_to_save_step(self):
        """
        Test that selecting a product from Step 2 advances to Step 4 (save).
        
        ACCEPTANCE TEST A: Selecting a product MUST advance to Step 4.
        """
        # Navigate to Step 2
        self.client.post(self.wizard_url, {
            'wizard_step': '0',
            'selected_mode': 'cosmetics',
            'action': 'next'
        })
        self.client.post(self.wizard_url, {
            'wizard_step': '1',
            'selected_mode': 'cosmetics',
            'selected_category': 'body_care',
            'action': 'next'
        })
        
        # Select a product
        response = self.client.post(self.wizard_url, {
            'wizard_step': '2',
            'selected_mode': 'cosmetics',
            'selected_category': 'body_care',
            'selected_item': 'Body Spray',
            'action': 'next'
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify we're now at Step 4 (save form)
        response = self.client.get(self.wizard_url)
        self.assertEqual(response.context['step'], 4)
        self.assertEqual(response.context['selected_item'], 'Body Spray')
        
        # Verify the save form is displayed
        self.assertContains(response, 'Quantity & Pricing')
        self.assertContains(response, 'Body Spray')
    
    def test_save_creates_merchproduct_if_missing(self):
        """
        Test that Step 4 save creates a MerchProduct if it doesn't exist in DB.
        
        ACCEPTANCE TEST A: Step 4 save MUST create/ensure MerchProduct exists.
        """
        # Navigate through wizard to save step
        self.client.post(self.wizard_url, {
            'wizard_step': '0',
            'selected_mode': 'cosmetics',
            'action': 'next'
        })
        self.client.post(self.wizard_url, {
            'wizard_step': '1',
            'selected_mode': 'cosmetics',
            'selected_category': 'body_care',
            'action': 'next'
        })
        self.client.post(self.wizard_url, {
            'wizard_step': '2',
            'selected_mode': 'cosmetics',
            'selected_category': 'body_care',
            'selected_item': 'Body Spray',
            'action': 'next'
        })
        
        # Verify product doesn't exist yet
        self.assertFalse(
            MerchProduct.objects.filter(
                name='Body Spray',
                business=self.business
            ).exists()
        )
        
        # Save the product with quantity and pricing
        response = self.client.post(self.wizard_url, {
            'wizard_step': '4',
            'selected_mode': 'cosmetics',
            'selected_category': 'body_care',
            'selected_item': 'Body Spray',
            'quantity': '100',
            'buying_price': '5.00',
            'selling_price': '10.00',
            'barcode': '',
            'batch_number': 'BATCH001',
            'expiry_date': '',  # Optional for cosmetics
            'action': 'save'
        })
        
        # Verify redirect after successful save
        self.assertEqual(response.status_code, 302)
        
        # Verify MerchProduct was created
        product = MerchProduct.objects.filter(
            name='Body Spray',
            business=self.business,
            kind='pharmacy',
            category=PharmacyCategory.PERSONAL_CARE
        ).first()
        self.assertIsNotNone(product, "MerchProduct should be created")
        
        # Verify PharmacyBatch was created
        batch = PharmacyBatch.objects.filter(
            merch_product=product,
            business=self.business
        ).first()
        self.assertIsNotNone(batch, "PharmacyBatch should be created")
        self.assertEqual(batch.quantity_total, 100)
        self.assertEqual(batch.buying_price, Decimal('5.00'))
        self.assertEqual(batch.selling_price, Decimal('10.00'))
    
    def test_cosmetics_expiry_date_optional(self):
        """
        Test that expiry date is optional for cosmetics products.
        
        ACCEPTANCE TEST A & B: Expiry date OPTIONAL for cosmetics.
        """
        # Navigate to save step
        self.client.post(self.wizard_url, {
            'wizard_step': '0',
            'selected_mode': 'cosmetics',
            'action': 'next'
        })
        self.client.post(self.wizard_url, {
            'wizard_step': '1',
            'selected_mode': 'cosmetics',
            'selected_category': 'makeup',
            'action': 'next'
        })
        self.client.post(self.wizard_url, {
            'wizard_step': '2',
            'selected_mode': 'cosmetics',
            'selected_category': 'makeup',
            'selected_item': 'Lipstick',
            'action': 'next'
        })
        
        # Save WITHOUT expiry date
        response = self.client.post(self.wizard_url, {
            'wizard_step': '4',
            'selected_mode': 'cosmetics',
            'selected_category': 'makeup',
            'selected_item': 'Lipstick',
            'quantity': '50',
            'buying_price': '15.00',
            'selling_price': '30.00',
            'barcode': '',
            'batch_number': 'MAKEUP001',
            'expiry_date': '',  # Empty - should be allowed
            'action': 'save'
        })
        
        # Should succeed
        self.assertEqual(response.status_code, 302)
        
        # Verify product and batch were created
        product = MerchProduct.objects.filter(name='Lipstick', business=self.business).first()
        self.assertIsNotNone(product)
        
        batch = PharmacyBatch.objects.filter(merch_product=product).first()
        self.assertIsNotNone(batch)
        self.assertIsNone(batch.expiry_date, "Expiry date should be None for cosmetics")


class PharmacyWizardMedicinesFlowTest(TestCase):
    """Test the pharmacy (medicines) flow in the wizard."""
    
    def setUp(self):
        """Set up test user, business, and client."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Pharmacy',
            vertical='pharmacy',
            owner=self.user
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='manager'
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        self.wizard_url = reverse('pharmacy:stock_in_wizard')
    
    def test_pharmacy_medicines_flow_works_end_to_end(self):
        """
        Test that pharmacy (medicines) flow works end-to-end.
        
        ACCEPTANCE TEST B: Pharmacy flow works like cosmetics.
        """
        # Step 0: Select pharmacy mode
        response = self.client.post(self.wizard_url, {
            'wizard_step': '0',
            'selected_mode': 'pharmacy',
            'action': 'next'
        })
        self.assertEqual(response.status_code, 302)
        
        # Step 1: Select a medicine category (e.g., First Aid)
        response = self.client.post(self.wizard_url, {
            'wizard_step': '1',
            'selected_mode': 'pharmacy',
            'selected_category': 'first_aid',
            'action': 'next'
        })
        self.assertEqual(response.status_code, 302)
        
        # Step 2: Verify we can see products or subcategories
        response = self.client.get(self.wizard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['step'], 2)
        
        # Should have either subcategories or items (not blank)
        has_content = (
            response.context.get('subcategories') or 
            response.context.get('items')
        )
        self.assertTrue(has_content, "Step 2 should not be blank for pharmacy mode")
    
    def test_pharmacy_requires_expiry_date(self):
        """
        Test that expiry date is REQUIRED for pharmacy (medicine) products.
        
        ACCEPTANCE TEST B: Expiry date REQUIRED for medicines.
        """
        # Navigate to save step for a medicine
        self.client.post(self.wizard_url, {
            'wizard_step': '0',
            'selected_mode': 'pharmacy',
            'action': 'next'
        })
        self.client.post(self.wizard_url, {
            'wizard_step': '1',
            'selected_mode': 'pharmacy',
            'selected_category': 'first_aid',
            'action': 'next'
        })
        
        # Try to select a product (create one if needed)
        session = self.client.session
        session['pharmacy_wizard_step'] = 4
        session['pharmacy_wizard_mode'] = 'pharmacy'
        session['pharmacy_wizard_category'] = 'first_aid'
        session['pharmacy_wizard_item'] = 'Paracetamol'
        session.save()
        
        # Try to save WITHOUT expiry date (should fail validation)
        response = self.client.post(self.wizard_url, {
            'wizard_step': '4',
            'selected_mode': 'pharmacy',
            'selected_category': 'first_aid',
            'selected_item': 'Paracetamol',
            'quantity': '100',
            'buying_price': '2.00',
            'selling_price': '5.00',
            'barcode': '',
            'batch_number': 'MED001',
            'expiry_date': '',  # Empty - should be rejected for medicines
            'action': 'save'
        })
        
        # Should either show error message or stay on same page
        # (Implementation may vary - check for error in context or messages)
        if response.status_code == 200:
            # Form validation failed, stayed on page
            self.assertContains(response, 'expiry', msg_prefix="Should show expiry date error")
        else:
            # Check for error message in redirected page
            response = self.client.get(self.wizard_url)
            messages = list(response.context.get('messages', []))
            has_error = any('expiry' in str(msg).lower() for msg in messages)
            self.assertTrue(has_error, "Should show error about missing expiry date")
    
    def test_pharmacy_saves_with_valid_expiry_date(self):
        """
        Test that pharmacy products can be saved with a valid expiry date.
        """
        # Navigate to save step
        self.client.post(self.wizard_url, {
            'wizard_step': '0',
            'selected_mode': 'pharmacy',
            'action': 'next'
        })
        self.client.post(self.wizard_url, {
            'wizard_step': '1',
            'selected_mode': 'pharmacy',
            'selected_category': 'first_aid',
            'action': 'next'
        })
        
        # Set up session for save step
        session = self.client.session
        session['pharmacy_wizard_step'] = 4
        session['pharmacy_wizard_mode'] = 'pharmacy'
        session['pharmacy_wizard_category'] = 'first_aid'
        session['pharmacy_wizard_item'] = 'Paracetamol'
        session.save()
        
        # Save WITH expiry date
        future_date = date.today() + timedelta(days=365)
        response = self.client.post(self.wizard_url, {
            'wizard_step': '4',
            'selected_mode': 'pharmacy',
            'selected_category': 'first_aid',
            'selected_item': 'Paracetamol',
            'quantity': '100',
            'buying_price': '2.00',
            'selling_price': '5.00',
            'barcode': '123456789',
            'batch_number': 'MED001',
            'expiry_date': future_date.strftime('%Y-%m-%d'),
            'action': 'save'
        })
        
        # Should succeed
        self.assertEqual(response.status_code, 302)
        
        # Verify product and batch were created with expiry
        product = MerchProduct.objects.filter(name='Paracetamol', business=self.business).first()
        self.assertIsNotNone(product)
        
        batch = PharmacyBatch.objects.filter(merch_product=product).first()
        self.assertIsNotNone(batch)
        self.assertIsNotNone(batch.expiry_date, "Expiry date should be set for medicines")
        self.assertEqual(batch.expiry_date, future_date)


class PharmacyWizardButtonFlowTest(TestCase):
    """Test that wizard navigation buttons work correctly."""
    
    def setUp(self):
        """Set up test user, business, and client."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Pharmacy',
            vertical='pharmacy',
            owner=self.user
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='manager'
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        self.wizard_url = reverse('pharmacy:stock_in_wizard')
    
    def test_back_button_returns_to_previous_step(self):
        """
        Test that "Back" button returns to the previous step without losing state.
        
        ACCEPTANCE TEST C: "Back" returns to prior step without losing state.
        """
        # Navigate to Step 2
        self.client.post(self.wizard_url, {
            'wizard_step': '0',
            'selected_mode': 'cosmetics',
            'action': 'next'
        })
        self.client.post(self.wizard_url, {
            'wizard_step': '1',
            'selected_mode': 'cosmetics',
            'selected_category': 'body_care',
            'action': 'next'
        })
        
        # Verify we're at Step 2
        response = self.client.get(self.wizard_url)
        self.assertEqual(response.context['step'], 2)
        
        # Click "Back"
        response = self.client.post(self.wizard_url, {
            'wizard_step': '2',
            'action': 'back'
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify we're back at Step 1
        response = self.client.get(self.wizard_url)
        self.assertEqual(response.context['step'], 1)
        
        # Verify mode is still set (state preserved)
        self.assertEqual(response.context['wizard_mode'], 'cosmetics')
    
    def test_next_button_enabled_when_selection_made(self):
        """
        Test that "Next" button works when a selection exists.
        
        ACCEPTANCE TEST C: "Next" must be clickable and advance when selection exists.
        """
        # Step 0: Select mode
        response = self.client.post(self.wizard_url, {
            'wizard_step': '0',
            'selected_mode': 'cosmetics',
            'action': 'next'
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify we advanced to Step 1
        response = self.client.get(self.wizard_url)
        self.assertEqual(response.context['step'], 1)
        self.assertEqual(response.context['wizard_mode'], 'cosmetics')
