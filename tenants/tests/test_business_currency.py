"""
Smoke test to verify Business model currency field works correctly.
Regression test for: django.db.utils.OperationalError: no such column: tenants_business.currency
"""

from django.test import TestCase
from tenants.models import Business


class BusinessCurrencyTest(TestCase):
    """Test that Business objects can be created and loaded with currency field"""

    def test_business_creation_with_default_currency(self):
        """Business should be created with default currency MWK"""
        business = Business.objects.create(
            name="Test Business",
            slug="test-business",
            status="ACTIVE"
        )
        
        self.assertEqual(business.currency, "MWK")
        
        # Verify we can reload it from DB without OperationalError
        reloaded = Business.objects.get(pk=business.pk)
        self.assertEqual(reloaded.currency, "MWK")

    def test_business_creation_with_custom_currency(self):
        """Business should support custom currency codes"""
        business = Business.objects.create(
            name="USD Business",
            slug="usd-business",
            status="ACTIVE",
            currency="USD"
        )
        
        self.assertEqual(business.currency, "USD")
        
        # Verify we can reload it from DB
        reloaded = Business.objects.get(pk=business.pk)
        self.assertEqual(reloaded.currency, "USD")

    def test_existing_business_has_currency_field(self):
        """Existing Business rows should have currency field accessible"""
        # Create a business
        Business.objects.create(
            name="Existing Business",
            slug="existing-business",
            status="ACTIVE"
        )
        
        # Query all businesses - should not raise OperationalError
        businesses = list(Business.objects.all())
        self.assertGreater(len(businesses), 0)
        
        # All should have currency field
        for biz in businesses:
            self.assertIsNotNone(biz.currency)
            self.assertIsInstance(biz.currency, str)

