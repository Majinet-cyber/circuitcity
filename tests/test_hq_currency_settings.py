"""
Tests for HQ currency settings functionality.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import ExchangeRate
from hq.permissions import is_hq_admin

User = get_user_model()


class HQCurrencySettingsTest(TestCase):
    """Test HQ currency settings view"""
    
    def setUp(self):
        """Set up test data"""
        # Create HQ admin user
        self.hq_admin = User.objects.create_user(
            username="hq_admin",
            email="hq@example.com",
            password="testpass123"
        )
        self.hq_admin.is_superuser = True
        self.hq_admin.is_staff = True
        self.hq_admin.save()
        
        # Create regular user (should not access)
        self.regular_user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="testpass123"
        )
    
    def test_hq_admin_can_access_currency_settings(self):
        """Test that HQ admin can access currency settings page"""
        client = Client()
        client.force_login(self.hq_admin)
        
        response = client.get(reverse("hq:currency_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Currency Settings")
        self.assertContains(response, "MWK → USD Exchange Rate")
    
    def test_regular_user_cannot_access_currency_settings(self):
        """Test that regular user cannot access currency settings"""
        client = Client()
        client.force_login(self.regular_user)
        
        response = client.get(reverse("hq:currency_settings"))
        self.assertNotEqual(response.status_code, 200)  # Should redirect or 403
    
    def test_create_exchange_rate(self):
        """Test creating a new exchange rate"""
        client = Client()
        client.force_login(self.hq_admin)
        
        # Initially no rate should exist
        self.assertIsNone(ExchangeRate.get_current_rate())
        
        # POST to create rate
        response = client.post(
            reverse("hq:currency_settings"),
            {"mwk_per_usd": "1750.00"}
        )
        self.assertEqual(response.status_code, 302)  # Redirect after success
        
        # Verify rate was created
        rate = ExchangeRate.get_current_rate()
        self.assertIsNotNone(rate)
        self.assertEqual(rate.mwk_per_usd, Decimal("1750.00"))
        self.assertEqual(rate.updated_by, self.hq_admin)
    
    def test_update_exchange_rate(self):
        """Test updating existing exchange rate"""
        client = Client()
        client.force_login(self.hq_admin)
        
        # Create initial rate
        ExchangeRate.objects.create(
            base="MWK",
            quote="USD",
            mwk_per_usd=Decimal("1700.00"),
            updated_by=self.hq_admin
        )
        
        # Update rate
        response = client.post(
            reverse("hq:currency_settings"),
            {"mwk_per_usd": "1800.00"}
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify rate was updated (singleton - should be same object)
        rate = ExchangeRate.get_current_rate()
        self.assertIsNotNone(rate)
        self.assertEqual(rate.mwk_per_usd, Decimal("1800.00"))
        self.assertEqual(rate.updated_by, self.hq_admin)
    
    def test_invalid_exchange_rate(self):
        """Test validation of exchange rate"""
        client = Client()
        client.force_login(self.hq_admin)
        
        # Test negative rate
        response = client.post(
            reverse("hq:currency_settings"),
            {"mwk_per_usd": "-100"}
        )
        self.assertEqual(response.status_code, 200)  # Form error, not redirect
        self.assertContains(response, "greater than 0")
        
        # Test zero rate
        response = client.post(
            reverse("hq:currency_settings"),
            {"mwk_per_usd": "0"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "greater than 0")
        
        # Test invalid format
        response = client.post(
            reverse("hq:currency_settings"),
            {"mwk_per_usd": "not a number"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid exchange rate")
    
    def test_exchange_rate_singleton(self):
        """Test that only one exchange rate exists (singleton pattern)"""
        # Create first rate
        rate1 = ExchangeRate.objects.create(
            base="MWK",
            quote="USD",
            mwk_per_usd=Decimal("1700.00")
        )
        
        # Try to create second rate with same base/quote (should fail due to unique_together)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ExchangeRate.objects.create(
                base="MWK",
                quote="USD",
                mwk_per_usd=Decimal("1800.00")
            )
        
        # get_current_rate should return the one that exists
        current = ExchangeRate.get_current_rate()
        self.assertEqual(current.pk, rate1.pk)

