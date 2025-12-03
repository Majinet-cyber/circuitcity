# tests/test_phones_products_catalog.py
"""
Tests for the PHONES products catalog functionality.
"""
import pytest
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import Location
from inventory.models_phone_products import PhoneProductCatalog
from inventory.business_kinds import BusinessKind
from inventory.phone_catalog_seed import (
    should_seed_phone_catalog,
    seed_phone_catalog,
    get_brands_for_business,
    get_models_for_brand,
)

User = get_user_model()


@pytest.mark.django_db
class TestPhoneProductCatalog(TestCase):
    """Test the phone products catalog model and seeding"""
    
    def setUp(self):
        """Set up test data"""
        self.business = Business.objects.create(
            name="Test Phones Store",
            kind=BusinessKind.PHONES,
            is_active=True
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True
        )
        
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="manager"
        )
    
    def test_should_seed_phone_catalog_for_empty_business(self):
        """Test should_seed_phone_catalog returns True for empty PHONES business"""
        result = should_seed_phone_catalog(self.business)
        self.assertTrue(result)
    
    def test_should_not_seed_phone_catalog_for_non_phones_business(self):
        """Test should_seed_phone_catalog returns False for non-PHONES business"""
        liquor_business = Business.objects.create(
            name="Liquor Store",
            kind=BusinessKind.LIQUOR,
            is_active=True
        )
        
        result = should_seed_phone_catalog(liquor_business)
        self.assertFalse(result)
    
    def test_seed_phone_catalog_creates_flagship_phones(self):
        """Test seed_phone_catalog creates all flagship phones"""
        created_count = seed_phone_catalog(self.business, created_by=self.manager)
        
        # Should create multiple products
        self.assertGreater(created_count, 0)
        
        # Check specific brands exist
        tecno_products = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand="TECNO"
        )
        self.assertGreater(tecno_products.count(), 0)
        
        itel_products = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand="ITEL"
        )
        self.assertGreater(itel_products.count(), 0)
        
        samsung_products = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand="SAMSUNG"
        )
        self.assertGreater(samsung_products.count(), 0)
    
    def test_seed_phone_catalog_creates_specific_models(self):
        """Test seed_phone_catalog creates specific expected models"""
        seed_phone_catalog(self.business, created_by=self.manager)
        
        # Check TECNO Spark 40 exists with correct variants
        spark40_4_128 = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand="TECNO",
            model_name="Spark 40",
            ram_gb=4,
            rom_gb=128
        ).first()
        self.assertIsNotNone(spark40_4_128)
        self.assertEqual(spark40_4_128.variant_label, "4+128")
        
        spark40_8_256 = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand="TECNO",
            model_name="Spark 40",
            ram_gb=8,
            rom_gb=256
        ).first()
        self.assertIsNotNone(spark40_8_256)
        self.assertEqual(spark40_8_256.variant_label, "8+256")
        
        # Check ITEL City 100
        city100 = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand="ITEL",
            model_name="City 100",
            ram_gb=4,
            rom_gb=128
        ).first()
        self.assertIsNotNone(city100)
    
    def test_get_brands_for_business(self):
        """Test get_brands_for_business returns correct brands"""
        seed_phone_catalog(self.business)
        
        brands = get_brands_for_business(self.business)
        
        # Should have TECNO, ITEL, SAMSUNG
        self.assertIn("TECNO", brands)
        self.assertIn("ITEL", brands)
        self.assertIn("SAMSUNG", brands)
    
    def test_get_models_for_brand(self):
        """Test get_models_for_brand returns correct models"""
        seed_phone_catalog(self.business)
        
        tecno_models = get_models_for_brand(self.business, "TECNO")
        
        # Should have multiple TECNO models
        self.assertGreater(len(tecno_models), 0)
        
        # Check structure
        first_model = tecno_models[0]
        self.assertIn("id", first_model)
        self.assertIn("model_name", first_model)
        self.assertIn("variant_label", first_model)
        self.assertIn("ram_gb", first_model)
        self.assertIn("rom_gb", first_model)
    
    def test_phone_product_catalog_unique_constraint(self):
        """Test PhoneProductCatalog enforces unique constraint"""
        # Create a product
        PhoneProductCatalog.objects.create(
            business=self.business,
            brand="TECNO",
            model_name="Spark 40",
            ram_gb=4,
            rom_gb=128,
            created_by=self.manager
        )
        
        # Try to create duplicate
        with self.assertRaises(Exception):  # IntegrityError
            PhoneProductCatalog.objects.create(
                business=self.business,
                brand="TECNO",
                model_name="Spark 40",
                ram_gb=4,
                rom_gb=128,
                created_by=self.manager
            )
    
    def test_phone_product_catalog_auto_variant_label(self):
        """Test PhoneProductCatalog auto-generates variant_label"""
        product = PhoneProductCatalog.objects.create(
            business=self.business,
            brand="TECNO",
            model_name="Spark 40",
            ram_gb=4,
            rom_gb=128,
            created_by=self.manager
        )
        
        # Should auto-generate variant_label
        self.assertEqual(product.variant_label, "4+128")


@pytest.mark.django_db
class TestPhoneProductsViews(TestCase):
    """Test the phone products catalog views"""
    
    def setUp(self):
        """Set up test data"""
        self.business = Business.objects.create(
            name="Test Phones Store",
            kind=BusinessKind.PHONES,
            is_active=True
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True
        )
        
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="manager"
        )
        
        self.client = Client()
    
    def test_phone_products_list_auto_seeds(self):
        """Test phone_products_list auto-seeds catalog for empty business"""
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Catalog should be empty initially
        self.assertEqual(PhoneProductCatalog.objects.filter(business=self.business).count(), 0)
        
        # Access products list
        response = self.client.get(reverse('inventory:phone_products'))
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
        
        # Catalog should now be seeded
        self.assertGreater(PhoneProductCatalog.objects.filter(business=self.business).count(), 0)
    
    def test_phone_products_list_shows_products(self):
        """Test phone_products_list shows products correctly"""
        # Seed catalog
        seed_phone_catalog(self.business, created_by=self.manager)
        
        self.client.login(username="manager@test.com", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('inventory:phone_products'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('products_by_brand', response.context)
        self.assertIn('all_brands', response.context)
        
        # Should have brands
        brands = response.context['all_brands']
        self.assertIn("TECNO", brands)
        self.assertIn("ITEL", brands)
    
    def test_phone_products_list_filters_by_brand(self):
        """Test phone_products_list filters by brand correctly"""
        seed_phone_catalog(self.business, created_by=self.manager)
        
        self.client.login(username="manager@test.com", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Filter by TECNO
        response = self.client.get(reverse('inventory:phone_products') + '?brand=TECNO')
        
        self.assertEqual(response.status_code, 200)
        
        products_by_brand = response.context['products_by_brand']
        
        # Should only have TECNO products
        self.assertIn("TECNO", products_by_brand)
        self.assertNotIn("ITEL", products_by_brand)
    
    def test_phone_product_create_success(self):
        """Test creating a new phone product"""
        self.client.login(username="manager@test.com", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create product
        response = self.client.post(reverse('inventory:phone_product_create'), {
            'brand': 'INFINIX',
            'model_name': 'Hot 40',
            'ram_gb': '8',
            'rom_gb': '256',
            'model_number': 'X6871',
            'default_cost_price': '480000.00',
            'default_selling_price': '580000.00',
        })
        
        # Should redirect to products list
        self.assertEqual(response.status_code, 302)
        
        # Product should exist
        product = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand="INFINIX",
            model_name="Hot 40",
            ram_gb=8,
            rom_gb=256
        ).first()
        
        self.assertIsNotNone(product)
        self.assertEqual(product.model_number, "X6871")
        self.assertEqual(product.default_cost_price, Decimal("480000.00"))
        self.assertEqual(product.default_selling_price, Decimal("580000.00"))
    
    def test_phone_product_edit_success(self):
        """Test editing an existing phone product"""
        # Create product
        product = PhoneProductCatalog.objects.create(
            business=self.business,
            brand="TECNO",
            model_name="Spark 40",
            ram_gb=4,
            rom_gb=128,
            created_by=self.manager
        )
        
        self.client.login(username="manager@test.com", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Edit product
        response = self.client.post(
            reverse('inventory:phone_product_edit', args=[product.id]),
            {
                'model_number': 'KJ7',
                'default_cost_price': '450000.00',
                'default_selling_price': '550000.00',
                'is_active': 'on',
            }
        )
        
        # Should redirect
        self.assertEqual(response.status_code, 302)
        
        # Product should be updated
        product.refresh_from_db()
        self.assertEqual(product.model_number, "KJ7")
        self.assertEqual(product.default_cost_price, Decimal("450000.00"))
        self.assertEqual(product.default_selling_price, Decimal("550000.00"))
        self.assertTrue(product.is_active)
    
    def test_phone_product_delete_deactivates(self):
        """Test deleting a phone product deactivates it"""
        # Create product
        product = PhoneProductCatalog.objects.create(
            business=self.business,
            brand="TECNO",
            model_name="Spark 40",
            ram_gb=4,
            rom_gb=128,
            is_active=True,
            created_by=self.manager
        )
        
        self.client.login(username="manager@test.com", password="testpass123")
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Delete product
        response = self.client.post(
            reverse('inventory:phone_product_delete', args=[product.id])
        )
        
        # Should redirect
        self.assertEqual(response.status_code, 302)
        
        # Product should be deactivated (soft delete)
        product.refresh_from_db()
        self.assertFalse(product.is_active)

