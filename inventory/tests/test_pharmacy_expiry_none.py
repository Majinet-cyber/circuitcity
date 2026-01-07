"""
Test for pharmacy batches with NULL expiry_date (no crash).
"""
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from tenants.models import Business
from inventory.models import MerchProduct, Location, BusinessKind
from inventory.models_pharmacy import PharmacyBatch


class PharmacyExpiryNoneTestCase(TestCase):
    """Test that batches with NULL expiry_date don't crash"""

    def setUp(self):
        """Create test pharmacy business and product"""
        self.business = Business.objects.create(
            name="Test Pharmacy", business_kind=BusinessKind.PHARMACY, subdomain="test-pharm"
        )
        self.location = Location.objects.create(business=self.business, name="Main Store")
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Cosmetic",
            kind=BusinessKind.PHARMACY,
            selling_price=5000,
            cost_price=3000,
        )

    def test_days_to_expiry_with_null_expiry_date(self):
        """
        Test that days_to_expiry returns None (not crash) when expiry_date is NULL.
        Previously crashed with: TypeError: unsupported operand type(s) for -: 'NoneType' and 'datetime.date'
        """
        batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="TEST-001",
            quantity=100,
            cost_price=3000,
            selling_price=5000,
            expiry_date=None,  # NULL expiry (cosmetics, non-expiry items)
        )

        # Should return None (not crash)
        self.assertIsNone(batch.days_to_expiry)

    def test_is_expired_with_null_expiry_date(self):
        """Test that is_expired returns False when expiry_date is NULL"""
        batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="TEST-002",
            quantity=100,
            cost_price=3000,
            selling_price=5000,
            expiry_date=None,
        )

        # Should return False (not expired, no expiry tracking)
        self.assertFalse(batch.is_expired)

    def test_days_to_expiry_with_valid_expiry_date(self):
        """Test that days_to_expiry works normally with a valid expiry date"""
        future_date = timezone.now().date() + timedelta(days=30)

        batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="TEST-003",
            quantity=100,
            cost_price=3000,
            selling_price=5000,
            expiry_date=future_date,
        )

        # Should return positive days
        self.assertIsNotNone(batch.days_to_expiry)
        self.assertGreater(batch.days_to_expiry, 0)
        self.assertFalse(batch.is_expired)

    def test_is_expired_with_past_expiry_date(self):
        """Test that is_expired returns True for expired batches"""
        past_date = timezone.now().date() - timedelta(days=10)

        batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="TEST-004",
            quantity=100,
            cost_price=3000,
            selling_price=5000,
            expiry_date=past_date,
        )

        # Should return True (expired)
        self.assertTrue(batch.is_expired)
        self.assertLess(batch.days_to_expiry, 0)
