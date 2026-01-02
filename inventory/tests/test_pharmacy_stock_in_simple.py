"""
Test for pharmacy stock-in simple page (no annotate FieldError).
"""
from django.test import TestCase, Client
from django.urls import reverse
from tenants.models import Business, Membership
from inventory.models import Location, BusinessKind
from django.contrib.auth import get_user_model

User = get_user_model()


class PharmacyStockInSimpleTestCase(TestCase):
    """Test pharmacy stock-in simple page loads without errors"""

    def setUp(self):
        """Create test pharmacy business and user"""
        self.business = Business.objects.create(
            name="Test Pharmacy", business_kind=BusinessKind.PHARMACY, subdomain="test-pharm"
        )
        self.location = Location.objects.create(business=self.business, name="Main Store")
        self.user = User.objects.create_user(username="pharmacist", email="pharmacist@test.com", password="testpass123")
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.client = Client()

    def test_stock_in_simple_loads_without_field_error(self):
        """
        Test that /pharmacy/stock-in/simple/ returns 200 (not FieldError).

        Previously crashed with: FieldError: Cannot resolve keyword 'pharmacybatch'
        This test ensures the correct relation name 'pharmacy_batches' is used.
        """
        self.client.force_login(self.user)

        url = reverse("pharmacy:stock_in_simple")
        response = self.client.get(url)

        # Should return 200 (no FieldError crash)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Stock In", response.content)
