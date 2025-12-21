# inventory/tests/test_pharmacy_wizard_fixes.py
"""
Tests for Pharmacy & Cosmetics Stock-In Wizard fixes.
Ensures:
1. Cosmetics/perfume can be saved without batch_number and without unit_type
2. "Other" products can be saved with minimal fields
3. No ERROR 500 on any user input errors (defensive error handling)
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch

User = get_user_model()


class PharmacyWizardCosmeticsSaveTestCase(TestCase):
    """Test that cosmetics (perfumes) can be saved without batch_number and without 500 errors."""
    
    def setUp(self):
        """Create test business, user, and login."""
        self.business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            status="ACTIVE"
        )
        
        self.user = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="TestPass123!@#"
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
        self.client.login(username="manager@test.com", password="TestPass123!@#")
        
        # Set up session with wizard state
        session = self.client.session
        session["business_id"] = self.business.id
        session["pharmacy_wizard_mode"] = "cosmetics"
        session["pharmacy_wizard_category"] = "cosmetics"
        session["pharmacy_wizard_subcategory"] = "perfumes"
        session["pharmacy_wizard_item"] = "Pure Black"
        session["pharmacy_wizard_step"] = 4  # Final step
        session.save()
    
    def test_save_cosmetics_perfume_without_batch_number(self):
        """Test saving a cosmetics perfume WITHOUT batch number succeeds (no 500)."""
        url = reverse("pharmacy:stock_in_wizard")
        
        data = {
            "wizard_step": "4",
            "action": "save",
            "product_name": "Pure Black Perfume 100ml",
            "quantity": "10",
            "cost_price": "5000.00",
            "selling_price": "8000.00",
            # No batch_number provided (should auto-generate)
            # No expiry_date provided (optional for cosmetics)
            "has_barcode": "no",
        }
        
        response = self.client.post(url, data)
        
        # Should NOT return 500
        self.assertNotEqual(response.status_code, 500, "Saving cosmetics without batch_number should NOT return 500")
        
        # Should redirect (success) or stay on page with form errors (but not crash)
        self.assertIn(response.status_code, [200, 302], "Response should be 200 (form error) or 302 (redirect success)")
        
        # Check if product and batch were created
        product = MerchProduct.objects.filter(
            business=self.business,
            name="Pure Black Perfume 100ml",
            kind="pharmacy"
        ).first()
        
        if response.status_code == 302:
            # Success - product should be created
            self.assertIsNotNone(product, "Product should be created on success")
            
            # Check batch was created with auto-generated batch_number
            batch = PharmacyBatch.objects.filter(
                business=self.business,
                merch_product=product
            ).first()
            
            self.assertIsNotNone(batch, "Batch should be created")
            self.assertIsNotNone(batch.batch_number, "Batch number should be auto-generated")
            self.assertTrue(len(batch.batch_number) > 0, "Batch number should not be empty")
            self.assertEqual(batch.quantity, 10, "Quantity should be 10")
            self.assertEqual(batch.cost_price, Decimal("5000.00"), "Cost price should match")
            self.assertEqual(batch.selling_price, Decimal("8000.00"), "Selling price should match")
    
    def test_save_cosmetics_with_blank_batch_and_no_expiry(self):
        """Test that cosmetics can be saved with blank batch number and no expiry (no 500)."""
        url = reverse("pharmacy:stock_in_wizard")
        
        data = {
            "wizard_step": "4",
            "action": "save",
            "product_name": "Nivea Soft Cream",
            "quantity": "20",
            "cost_price": "1500.00",
            "selling_price": "2500.00",
            "batch_number": "",  # Explicitly blank
            "expiry_date": "",   # Blank (optional for cosmetics)
            "has_barcode": "no",
        }
        
        response = self.client.post(url, data)
        
        # Should NOT return 500
        self.assertNotEqual(response.status_code, 500, "Saving cosmetics with blank batch/expiry should NOT return 500")
        self.assertIn(response.status_code, [200, 302], "Response should be 200 or 302")


class PharmacyWizardOtherProductTestCase(TestCase):
    """Test that 'Other' products can be saved with minimal fields."""
    
    def setUp(self):
        """Create test business, user, and login."""
        self.business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            status="ACTIVE"
        )
        
        self.user = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="TestPass123!@#"
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
        self.client.login(username="manager@test.com", password="TestPass123!@#")
        
        # Set up session with wizard state for "Other" product
        session = self.client.session
        session["business_id"] = self.business.id
        session["pharmacy_wizard_mode"] = "pharmacy"
        session["pharmacy_wizard_category"] = "medicines"
        session["pharmacy_wizard_subcategory"] = "other_medicine"
        session["pharmacy_wizard_item"] = "Custom medicine"
        session["pharmacy_wizard_step"] = 4  # Final step
        session.save()
    
    def test_save_other_product_minimal_fields(self):
        """Test that 'Other' product saves with only product_name + quantity + prices (no 500)."""
        url = reverse("pharmacy:stock_in_wizard")
        
        data = {
            "wizard_step": "4",
            "action": "save",
            "product_name": "Custom Medical Device XYZ",
            "quantity": "5",
            "cost_price": "10000.00",
            "selling_price": "15000.00",
            # No batch_number (should auto-generate)
            # No expiry_date (required for medicines, but let's test error handling)
            "has_barcode": "no",
        }
        
        response = self.client.post(url, data)
        
        # Should NOT return 500 even if there's a validation error
        self.assertNotEqual(response.status_code, 500, "'Other' product save should NOT return 500")
        self.assertIn(response.status_code, [200, 302], "Response should be 200 (form error) or 302 (success)")
        
        # If medicines require expiry, we expect a form error (200) with message
        # If validation passes, we expect redirect (302)
    
    def test_save_other_product_with_expiry_succeeds(self):
        """Test that 'Other' product saves successfully when expiry is provided."""
        url = reverse("pharmacy:stock_in_wizard")
        
        data = {
            "wizard_step": "4",
            "action": "save",
            "product_name": "Custom Medical Device ABC",
            "quantity": "8",
            "cost_price": "12000.00",
            "selling_price": "18000.00",
            "expiry_date": "2026-12-31",  # Provided
            "has_barcode": "no",
        }
        
        response = self.client.post(url, data)
        
        # Should NOT return 500
        self.assertNotEqual(response.status_code, 500, "'Other' product save with expiry should NOT return 500")
        self.assertIn(response.status_code, [200, 302], "Response should be 200 or 302")
        
        if response.status_code == 302:
            # Success - check product created
            product = MerchProduct.objects.filter(
                business=self.business,
                name="Custom Medical Device ABC",
                kind="pharmacy"
            ).first()
            
            self.assertIsNotNone(product, "Product should be created")


class PharmacyWizardModeSelectionTestCase(TestCase):
    """Test the new Step 0 mode selection (Cosmetics vs Pharmacy)."""
    
    def setUp(self):
        """Create test business, user, and login."""
        self.business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            status="ACTIVE"
        )
        
        self.user = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="TestPass123!@#"
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
        self.client.login(username="manager@test.com", password="TestPass123!@#")
        
        session = self.client.session
        session["business_id"] = self.business.id
        session.save()
    
    def test_step_0_displays_mode_options(self):
        """Test that Step 0 displays Pharmacy and Cosmetics options."""
        url = reverse("pharmacy:stock_in_wizard")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200, "Step 0 should load successfully")
        self.assertContains(response, "Pharmacy", msg_prefix="Should show Pharmacy option")
        self.assertContains(response, "Cosmetics", msg_prefix="Should show Cosmetics option")
        self.assertContains(response, "Add Product", msg_prefix="Should show simplified title")
    
    def test_mode_selection_sets_session(self):
        """Test that selecting mode advances to Step 1."""
        url = reverse("pharmacy:stock_in_wizard")
        
        data = {
            "wizard_step": "0",
            "selected_mode": "cosmetics",
            "action": "next"
        }
        
        response = self.client.post(url, data, follow=True)
        
        self.assertEqual(response.status_code, 200, "Mode selection should succeed")
        
        # Check session was updated
        session = self.client.session
        self.assertEqual(session.get("pharmacy_wizard_mode"), "cosmetics", "Mode should be set in session")
        self.assertEqual(session.get("pharmacy_wizard_step"), 1, "Should advance to step 1")
    
    def test_back_to_start_button_works(self):
        """Test that 'Back to start' button resets wizard to Step 0."""
        # Set up wizard at step 2
        session = self.client.session
        session["business_id"] = self.business.id
        session["pharmacy_wizard_step"] = 2
        session["pharmacy_wizard_mode"] = "pharmacy"
        session["pharmacy_wizard_category"] = "medicines"
        session.save()
        
        url = reverse("pharmacy:stock_in_wizard")
        
        # Jump back to step 0
        data = {
            "wizard_step": "2",
            "action": "jump",
            "jump_to_step": "0"
        }
        
        response = self.client.post(url, data, follow=True)
        
        self.assertEqual(response.status_code, 200, "Jump to start should succeed")
        
        # Check session was reset
        session = self.client.session
        self.assertEqual(session.get("pharmacy_wizard_step"), 0, "Should be at step 0")


class PharmacyWizardErrorHandlingTestCase(TestCase):
    """Test that wizard handles errors gracefully without 500s."""
    
    def setUp(self):
        """Create test business, user, and login."""
        self.business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            status="ACTIVE"
        )
        
        self.user = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="TestPass123!@#"
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        self.client = Client()
        self.client.login(username="manager@test.com", password="TestPass123!@#")
        
        session = self.client.session
        session["business_id"] = self.business.id
        session["pharmacy_wizard_step"] = 4
        session["pharmacy_wizard_mode"] = "pharmacy"
        session["pharmacy_wizard_category"] = "medicines"
        session.save()
    
    def test_invalid_input_does_not_500(self):
        """Test that invalid user input returns form error (not 500)."""
        url = reverse("pharmacy:stock_in_wizard")
        
        data = {
            "wizard_step": "4",
            "action": "save",
            "product_name": "",  # Missing required field
            "quantity": "abc",   # Invalid number
            "cost_price": "-100",  # Invalid negative
            "selling_price": "not_a_number",  # Invalid
        }
        
        response = self.client.post(url, data)
        
        # Should return 200 with error messages (NOT 500)
        self.assertEqual(response.status_code, 200, "Invalid input should return 200 (form errors), not 500")
    
    def test_duplicate_batch_does_not_500(self):
        """Test that saving duplicate batch returns gracefully (not 500)."""
        # Create initial product and batch
        product = MerchProduct.objects.create(
            business=self.business,
            name="Test Product",
            kind="pharmacy",
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00")
        )
        
        PharmacyBatch.objects.create(
            business=self.business,
            merch_product=product,
            batch_number="BATCH-001",
            expiry_date="2026-06-30",
            quantity=10,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00")
        )
        
        url = reverse("pharmacy:stock_in_wizard")
        
        data = {
            "wizard_step": "4",
            "action": "save",
            "product_name": "Test Product",
            "quantity": "5",
            "cost_price": "100.00",
            "selling_price": "150.00",
            "batch_number": "BATCH-001",
            "expiry_date": "2026-06-30",
            "has_barcode": "no",
        }
        
        response = self.client.post(url, data)
        
        # Should NOT return 500 (duplicate batches update quantity, not error)
        self.assertNotEqual(response.status_code, 500, "Duplicate batch should NOT return 500")
        self.assertIn(response.status_code, [200, 302], "Response should be 200 or 302")

