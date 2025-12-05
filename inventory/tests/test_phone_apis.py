# inventory/tests/test_phone_apis.py
"""
Tests for phone catalog API endpoints (Brand and Model filtering).
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.models_phone_products import PhoneProductCatalog
from inventory.business_kinds import BusinessKind

User = get_user_model()


class PhoneAPIsTestCase(TestCase):
    """Test phone brands and models API endpoints"""
    
    def setUp(self):
        """Set up test data"""
        # Create a PHONES business
        self.business = Business.objects.create(
            name="Test Phone Shop",
            kind=BusinessKind.PHONES,
            is_active=True
        )
        
        # Create a test user
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        # Create some phone products
        PhoneProductCatalog.objects.create(
            business=self.business,
            brand="TECNO",
            model_name="Spark 40",
            ram_gb=4,
            rom_gb=128,
            variant_label="4+128",
            is_active=True
        )
        
        PhoneProductCatalog.objects.create(
            business=self.business,
            brand="TECNO",
            model_name="Spark 40",
            ram_gb=8,
            rom_gb=256,
            variant_label="8+256",
            is_active=True
        )
        
        PhoneProductCatalog.objects.create(
            business=self.business,
            brand="ITEL",
            model_name="A58",
            ram_gb=3,
            rom_gb=128,
            variant_label="3+128",
            is_active=True
        )
        
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")
    
    def test_api_phone_brands_returns_brands(self):
        """Test that brands API returns list of unique brands"""
        # Attach business to session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('inventory:api_phone_brands')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('brands', data)
        self.assertIsInstance(data['brands'], list)
        self.assertIn('TECNO', data['brands'])
        self.assertIn('ITEL', data['brands'])
    
    def test_api_phone_models_filters_by_brand(self):
        """Test that models API filters correctly by brand"""
        # Attach business to session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('inventory:api_phone_models')
        response = self.client.get(url, {'brand': 'TECNO'})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('models', data)
        self.assertIsInstance(data['models'], list)
        
        # Should return 2 TECNO variants
        self.assertEqual(len(data['models']), 2)
        
        # All models should be TECNO Spark 40
        for model in data['models']:
            self.assertEqual(model['model_name'], 'Spark 40')
    
    def test_api_phone_models_requires_brand_param(self):
        """Test that models API returns error when brand is missing"""
        # Attach business to session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('inventory:api_phone_models')
        response = self.client.get(url)  # No brand parameter
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('Brand parameter required', data['error'])
    
    def test_api_phone_brands_requires_authentication(self):
        """Test that brands API requires login"""
        self.client.logout()
        url = reverse('inventory:api_phone_brands')
        response = self.client.get(url)
        
        # Should redirect to login or return 302/401
        self.assertIn(response.status_code, [302, 401, 403])
