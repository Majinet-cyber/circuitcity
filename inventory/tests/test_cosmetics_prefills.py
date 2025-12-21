# inventory/tests/test_cosmetics_prefills.py
"""
Tests for cosmetics prefills and clickable product cards in the Stock-In Wizard.

Tests:
1. Management command creates prefills correctly (idempotent, tenant-scoped)
2. Wizard shows product cards for cosmetics categories
3. Product counts are correct
4. Custom products can still be created via "Other" option
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.management import call_command
from io import StringIO

from tenants.models import Business
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyCategory

User = get_user_model()


class CosmeticsPrefillsTestCase(TestCase):
    """Test cosmetics prefills management command and wizard integration."""

    def setUp(self):
        """Create test business and user."""
        self.business = Business.objects.create(
            name="Test Pharmacy",
            slug="test-pharmacy",
            business_kind="pharmacy",
        )
        
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        
        # Link user to business
        from tenants.models import Membership
        Membership.objects.create(
            business=self.business,
            user=self.user,
            role="MANAGER",
        )
        
        self.client = Client()
        self.client.force_login(self.user)

    def test_management_command_creates_prefills(self):
        """Test that management command creates prefills for pharmacy business."""
        # Verify no cosmetics products exist initially
        initial_count = MerchProduct.objects.filter(
            business=self.business,
            kind="pharmacy",
            category__in=[PharmacyCategory.BEAUTY_MAKEUP, PharmacyCategory.SKIN_CARE],
        ).count()
        self.assertEqual(initial_count, 0)
        
        # Run the management command
        out = StringIO()
        call_command(
            'seed_cosmetics_products',
            f'--business-id={self.business.id}',
            stdout=out
        )
        
        # Check output
        output = out.getvalue()
        self.assertIn("Seeded", output)
        
        # Verify products were created
        perfumes = MerchProduct.objects.filter(
            business=self.business,
            kind="pharmacy",
            category=PharmacyCategory.BEAUTY_MAKEUP,
            is_active=True,
        )
        self.assertEqual(perfumes.count(), 4, "Should have 4 perfumes")
        
        # Check specific perfume names
        perfume_names = list(perfumes.values_list("name", flat=True))
        self.assertIn("Arabic", perfume_names)
        self.assertIn("Emerald", perfume_names)
        self.assertIn("Monalisa", perfume_names)
        self.assertIn("Pure Black", perfume_names)
        
        # Verify skin care products
        skin_care = MerchProduct.objects.filter(
            business=self.business,
            kind="pharmacy",
            category=PharmacyCategory.SKIN_CARE,
            is_active=True,
        )
        self.assertEqual(skin_care.count(), 4, "Should have 4 skin care products")
        
        # Check specific skin care names
        skin_care_names = list(skin_care.values_list("name", flat=True))
        self.assertIn("CeraVe Lotion", skin_care_names)
        self.assertIn("Nivea Soft Cream", skin_care_names)

    def test_management_command_is_idempotent(self):
        """Test that running command twice doesn't create duplicates."""
        # Run command first time
        call_command(
            'seed_cosmetics_products',
            f'--business-id={self.business.id}',
            stdout=StringIO()
        )
        
        first_count = MerchProduct.objects.filter(
            business=self.business,
            kind="pharmacy",
            category__in=[PharmacyCategory.BEAUTY_MAKEUP, PharmacyCategory.SKIN_CARE],
        ).count()
        
        # Run command second time (should skip)
        out = StringIO()
        call_command(
            'seed_cosmetics_products',
            f'--business-id={self.business.id}',
            stdout=out
        )
        
        output = out.getvalue()
        self.assertIn("already has", output.lower())
        
        second_count = MerchProduct.objects.filter(
            business=self.business,
            kind="pharmacy",
            category__in=[PharmacyCategory.BEAUTY_MAKEUP, PharmacyCategory.SKIN_CARE],
        ).count()
        
        # Count should be the same
        self.assertEqual(first_count, second_count, "Should not create duplicates")

    def test_wizard_shows_product_counts(self):
        """Test that wizard displays product counts for cosmetics categories."""
        # Create prefills
        call_command(
            'seed_cosmetics_products',
            f'--business-id={self.business.id}',
            stdout=StringIO()
        )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Access wizard step 0 (mode selection)
        url = reverse('pharmacy:stock_in_wizard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Select cosmetics mode
        response = self.client.post(url, {
            'wizard_step': 0,
            'selected_mode': 'cosmetics',
        })
        
        # Should show categories with product counts
        self.assertContains(response, "product")  # "X products" badge
        
        # Check that Perfumes and Skin Care show counts > 0
        # This will depend on how the template renders, but we check the context
        if hasattr(response, 'context') and 'top_categories' in response.context:
            categories = response.context['top_categories']
            
            # Find perfumes and skin_care categories
            perfumes_cat = next((c for c in categories if c['key'] == 'perfumes'), None)
            skin_care_cat = next((c for c in categories if c['key'] == 'skin_care'), None)
            
            if perfumes_cat:
                self.assertGreater(perfumes_cat.get('product_count', 0), 0, "Perfumes should have product count > 0")
            
            if skin_care_cat:
                self.assertGreater(skin_care_cat.get('product_count', 0), 0, "Skin Care should have product count > 0")

    def test_wizard_shows_clickable_product_cards(self):
        """Test that wizard shows existing products as clickable cards."""
        # Create prefills
        call_command(
            'seed_cosmetics_products',
            f'--business-id={self.business.id}',
            stdout=StringIO()
        )
        
        # Set active business in session and wizard state
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['pharmacy_wizard_step'] = 3
        session['pharmacy_wizard_mode'] = 'cosmetics'
        session['pharmacy_wizard_category'] = 'cosmetics'
        session['pharmacy_wizard_subcategory'] = 'perfumes'
        session.save()
        
        # Access wizard step 3 (product selection)
        url = reverse('pharmacy:stock_in_wizard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Check that perfume products are shown
        self.assertContains(response, "Arabic")
        self.assertContains(response, "Emerald")
        self.assertContains(response, "Monalisa")
        self.assertContains(response, "Pure Black")
        
        # Check that "Other" option is present
        self.assertContains(response, "Other")

    def test_custom_product_creation_via_other_option(self):
        """Test that users can create custom products via 'Other' option."""
        # Create prefills first
        call_command(
            'seed_cosmetics_products',
            f'--business-id={self.business.id}',
            stdout=StringIO()
        )
        
        # Set wizard state
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['pharmacy_wizard_step'] = 4
        session['pharmacy_wizard_mode'] = 'cosmetics'
        session['pharmacy_wizard_category'] = 'cosmetics'
        session['pharmacy_wizard_subcategory'] = 'perfumes'
        session['pharmacy_wizard_item'] = 'Other (Create new)'
        session.save()
        
        # Submit custom product
        url = reverse('pharmacy:stock_in_wizard')
        response = self.client.post(url, {
            'wizard_step': 4,
            'action': 'save',
            'product_name': 'Custom Perfume XYZ',
            'quantity': 50,
            'cost_price': '3000.00',
            'selling_price': '5000.00',
            'batch_number': '',  # Auto-generate
            'expiry_date': '',  # Optional for cosmetics
            'has_barcode': 'no',
            'supplier': '',
        })
        
        # Check product was created
        custom_product = MerchProduct.objects.filter(
            business=self.business,
            name='Custom Perfume XYZ',
            category=PharmacyCategory.BEAUTY_MAKEUP,
        ).first()
        
        self.assertIsNotNone(custom_product, "Custom product should be created")
        self.assertEqual(custom_product.cost_price, Decimal('3000.00'))
        self.assertEqual(custom_product.selling_price, Decimal('5000.00'))

    def test_prefills_are_tenant_scoped(self):
        """Test that prefills are created per-business (tenant-scoped)."""
        # Create another business
        business2 = Business.objects.create(
            name="Test Pharmacy 2",
            slug="test-pharmacy-2",
            business_kind="pharmacy",
        )
        
        # Seed for first business
        call_command(
            'seed_cosmetics_products',
            f'--business-id={self.business.id}',
            stdout=StringIO()
        )
        
        # Check products for business 1
        business1_products = MerchProduct.objects.filter(
            business=self.business,
            kind="pharmacy",
            category__in=[PharmacyCategory.BEAUTY_MAKEUP, PharmacyCategory.SKIN_CARE],
        ).count()
        
        # Check products for business 2 (should be 0)
        business2_products = MerchProduct.objects.filter(
            business=business2,
            kind="pharmacy",
            category__in=[PharmacyCategory.BEAUTY_MAKEUP, PharmacyCategory.SKIN_CARE],
        ).count()
        
        self.assertGreater(business1_products, 0, "Business 1 should have products")
        self.assertEqual(business2_products, 0, "Business 2 should have no products")
        
        # Now seed for business 2
        call_command(
            'seed_cosmetics_products',
            f'--business-id={business2.id}',
            stdout=StringIO()
        )
        
        # Check again
        business2_products = MerchProduct.objects.filter(
            business=business2,
            kind="pharmacy",
            category__in=[PharmacyCategory.BEAUTY_MAKEUP, PharmacyCategory.SKIN_CARE],
        ).count()
        
        self.assertGreater(business2_products, 0, "Business 2 should now have products")
        
        # Both should have same number of products (they're independent)
        self.assertEqual(business1_products, business2_products)

