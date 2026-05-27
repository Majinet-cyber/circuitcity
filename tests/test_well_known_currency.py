"""
Tests for well-known endpoint and currency system.
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import ExchangeRate
from circuitcity.accounts.models import Profile

User = get_user_model()


class WellKnownEndpointTest(TestCase):
    """Test the Chrome DevTools well-known endpoint"""
    
    def test_chrome_devtools_endpoint(self):
        """Test that /.well-known/appspecific/com.chrome.devtools.json returns 200"""
        client = Client()
        response = client.get("/.well-known/appspecific/com.chrome.devtools.json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {})


class CurrencySystemTest(TestCase):
    """Test currency conversion and formatting"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.profile, _ = Profile.objects.get_or_create(user=self.user)
        
        # Create exchange rate: 1 USD = 1750 MWK (singleton)
        self.exchange_rate = ExchangeRate.objects.create(
            base="MWK",
            quote="USD",
            mwk_per_usd=Decimal("1750.00")
        )
    
    def test_exchange_rate_model(self):
        """Test ExchangeRate model"""
        rate = ExchangeRate.get_current_rate()
        self.assertIsNotNone(rate)
        self.assertEqual(rate.mwk_per_usd, Decimal("1750.00"))
        self.assertEqual(rate.base, "MWK")
        self.assertEqual(rate.quote, "USD")
        
        rate_value = ExchangeRate.get_rate_value()
        self.assertEqual(rate_value, Decimal("1750.00"))
    
    def test_profile_display_currency_default(self):
        """Test that profile defaults to MWK"""
        self.assertEqual(self.profile.display_currency, "MWK")
    
    def test_currency_conversion_mwk_to_usd(self):
        """Test MWK to USD conversion"""
        from core.utils.money import mwk_to_usd, get_mwk_per_usd
        
        # Test get_mwk_per_usd helper
        rate = get_mwk_per_usd()
        self.assertIsNotNone(rate)
        self.assertEqual(rate, Decimal("1750.00"))
        
        # 1750 MWK should equal 1 USD
        mwk_amount = Decimal("1750")
        usd = mwk_to_usd(mwk_amount, Decimal("1750.00"))
        self.assertIsNotNone(usd)
        self.assertEqual(usd, Decimal("1.00"))
        
        # 3500 MWK should equal 2 USD
        mwk_amount = Decimal("3500")
        usd = mwk_to_usd(mwk_amount, Decimal("1750.00"))
        self.assertEqual(usd, Decimal("2.00"))
        
        # Test with None rate
        usd = mwk_to_usd(mwk_amount, None)
        self.assertIsNone(usd)
    
    def test_format_money_mwk(self):
        """Test money formatting in MWK"""
        from core.utils.money import format_money
        
        result = format_money(Decimal("100000"), "MWK", None, False)
        self.assertEqual(result, "MWK 100,000")
        
        result = format_money(Decimal("1000000"), "MWK", None, True)
        self.assertIn("MWK", result)
        self.assertIn("M", result)
    
    def test_format_money_usd(self):
        """Test money formatting in USD"""
        from core.utils.money import format_money
        
        # 1750 MWK = 1 USD
        result = format_money(Decimal("1750"), "USD", Decimal("1750.00"), False)
        self.assertEqual(result, "USD 1.00")
        
        # 3500 MWK = 2 USD
        result = format_money(Decimal("3500"), "USD", Decimal("1750.00"), False)
        self.assertEqual(result, "USD 2.00")
        
        # Test fallback to MWK when rate is None
        result = format_money(Decimal("1000"), "USD", None, False)
        self.assertIn("MWK", result)
        self.assertNotIn("USD", result)
    
    def test_currency_switcher_view(self):
        """Test currency switcher endpoint"""
        client = Client()
        client.force_login(self.user)
        
        # Switch to USD
        response = client.post(
            reverse("accounts:settings_currency"),
            {"currency": "USD"},
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["currency"], "USD")
        
        # Verify profile was updated
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.display_currency, "USD")
        
        # Switch back to MWK
        response = client.post(
            reverse("accounts:settings_currency"),
            {"currency": "MWK"},
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.display_currency, "MWK")
    
    def test_currency_switcher_invalid(self):
        """Test currency switcher with invalid currency"""
        client = Client()
        client.force_login(self.user)
        
        response = client.post(
            reverse("accounts:settings_currency"),
            {"currency": "INVALID"},
            HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 400)
        
        # Profile should remain unchanged
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.display_currency, "MWK")

