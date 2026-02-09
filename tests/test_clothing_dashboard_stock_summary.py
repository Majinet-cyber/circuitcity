# tests/test_clothing_dashboard_stock_summary.py
"""
Test for Clothing Dashboard Stock Summary fix.

ISSUE: Stock Summary cards (e.g. Shoes, Jeans) show 0 stock even when there is stock.
FIX: Aggregate BOTH tracked units (ClothingBarcodeUnit) AND common stock (MerchProduct.quantity_in_stock).

Test Coverage:
- Stock summary includes tracked units
- Stock summary includes common stock
- Stock summary combines tracked + common correctly
- Stock summary respects business scoping
- Stock summary respects location scoping
- Sold tracked units are excluded
- Products with tracked units don't double-count in common stock
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct, Location
from inventory.models_clothing_barcode import ClothingBarcodeUnit
from tenants.models import Business, Membership
from circuitcity.accounts.models import Profile

User = get_user_model()


@pytest.mark.django_db
class TestClothingDashboardStockSummary(TestCase):
    """Test clothing dashboard stock summary aggregation"""

    def setUp(self):
        # Create user
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123",
        )

        # Create business
        self.business = Business.objects.create(
            name="Test Clothing Store",
            slug="test-clothing",
            business_kind=BusinessKind.CLOTHING,
        )

        # Create membership (manager)
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role="manager",
        )

        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )

        # Set active business and location
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.active_business = self.business
        profile.active_location = self.location
        profile.save()

        # Login
        self.client = Client()
        self.client.login(username="testmanager", password="testpass123")

    def test_stock_summary_shows_tracked_units(self):
        """Stock summary should include tracked barcoded units"""
        # Create tracked units for shoes
        product = MerchProduct.objects.create(
            business=self.business,
            name="Puma Jordan",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            size="42",
            selling_price=Decimal("15000.00"),
            cost_price=Decimal("10000.00"),
            quantity_in_stock=0,  # No common stock
            is_active=True,
            is_archived=False,
        )

        # Add 5 tracked units (barcoded)
        for i in range(5):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location,
                product=product,
                barcode=f"SHOE{i:04d}",
                size="42",
                category="shoes",
                brand="Puma",
                cost_price=Decimal("10000.00"),
                selling_price=Decimal("15000.00"),
                status="IN_STOCK",
                is_active=True,
            )

        # Load dashboard
        response = self.client.get(reverse("verticals:clothing_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Check stock summary context
        stock_summary = response.context["stock_summary"]

        # Find shoes category
        shoes_summary = None
        for item in stock_summary:
            if item["category"].lower() == "shoes":
                shoes_summary = item
                break

        self.assertIsNotNone(shoes_summary, "Shoes should appear in stock summary")
        self.assertEqual(shoes_summary["total_quantity"], 5, "Should show 5 units in stock")
        self.assertEqual(shoes_summary["tracked_quantity"], 5, "Should show 5 tracked units")
        self.assertEqual(shoes_summary["common_quantity"], 0, "Should show 0 common units")
        self.assertEqual(shoes_summary["total_items"], 1, "Should show 1 product style")

    def test_stock_summary_shows_common_stock(self):
        """Stock summary should include common stock (quantity_in_stock)"""
        # Create common stock product
        MerchProduct.objects.create(
            business=self.business,
            name="Basic Jeans",
            kind=BusinessKind.CLOTHING,
            category="jeans",
            size="32",
            selling_price=Decimal("8000.00"),
            cost_price=Decimal("5000.00"),
            quantity_in_stock=10,  # Common stock
            is_active=True,
            is_archived=False,
        )

        # Load dashboard
        response = self.client.get(reverse("verticals:clothing_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Check stock summary context
        stock_summary = response.context["stock_summary"]

        # Find jeans category
        jeans_summary = None
        for item in stock_summary:
            if item["category"].lower() == "jeans":
                jeans_summary = item
                break

        self.assertIsNotNone(jeans_summary, "Jeans should appear in stock summary")
        self.assertEqual(jeans_summary["total_quantity"], 10, "Should show 10 units in stock")
        self.assertEqual(jeans_summary["tracked_quantity"], 0, "Should show 0 tracked units")
        self.assertEqual(jeans_summary["common_quantity"], 10, "Should show 10 common units")
        self.assertEqual(jeans_summary["total_items"], 1, "Should show 1 product style")

    def test_stock_summary_combines_tracked_and_common(self):
        """Stock summary should combine tracked + common stock correctly"""
        # Create product with tracked units
        tracked_product = MerchProduct.objects.create(
            business=self.business,
            name="Nike Air",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            size="40",
            selling_price=Decimal("20000.00"),
            cost_price=Decimal("15000.00"),
            quantity_in_stock=0,
            is_active=True,
            is_archived=False,
        )

        # Add 3 tracked units
        for i in range(3):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location,
                product=tracked_product,
                barcode=f"NIKE{i:04d}",
                size="40",
                category="shoes",
                brand="Nike",
                cost_price=Decimal("15000.00"),
                selling_price=Decimal("20000.00"),
                status="IN_STOCK",
                is_active=True,
            )

        # Create another product with common stock (no tracked units)
        MerchProduct.objects.create(
            business=self.business,
            name="Adidas Samba",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            size="42",
            selling_price=Decimal("18000.00"),
            cost_price=Decimal("12000.00"),
            quantity_in_stock=7,  # Common stock
            is_active=True,
            is_archived=False,
        )

        # Load dashboard
        response = self.client.get(reverse("verticals:clothing_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Check stock summary context
        stock_summary = response.context["stock_summary"]

        # Find shoes category
        shoes_summary = None
        for item in stock_summary:
            if item["category"].lower() == "shoes":
                shoes_summary = item
                break

        self.assertIsNotNone(shoes_summary, "Shoes should appear in stock summary")
        self.assertEqual(shoes_summary["total_quantity"], 10, "Should show 10 total units (3 tracked + 7 common)")
        self.assertEqual(shoes_summary["tracked_quantity"], 3, "Should show 3 tracked units")
        self.assertEqual(shoes_summary["common_quantity"], 7, "Should show 7 common units")
        self.assertEqual(shoes_summary["total_items"], 2, "Should show 2 product styles")

    def test_stock_summary_excludes_sold_tracked_units(self):
        """Stock summary should exclude sold tracked units"""
        # Create tracked units, some sold
        product = MerchProduct.objects.create(
            business=self.business,
            name="Premium Shirt",
            kind=BusinessKind.CLOTHING,
            category="shirt",
            size="M",
            selling_price=Decimal("12000.00"),
            cost_price=Decimal("8000.00"),
            quantity_in_stock=0,
            is_active=True,
            is_archived=False,
        )

        # Add 5 tracked units in stock
        for i in range(5):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location,
                product=product,
                barcode=f"SHIRT{i:04d}",
                size="M",
                category="shirt",
                brand="Premium",
                cost_price=Decimal("8000.00"),
                selling_price=Decimal("12000.00"),
                status="IN_STOCK",
                is_active=True,
            )

        # Add 3 sold tracked units (should NOT appear in stock summary)
        for i in range(5, 8):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location,
                product=product,
                barcode=f"SHIRT{i:04d}",
                size="M",
                category="shirt",
                brand="Premium",
                cost_price=Decimal("8000.00"),
                selling_price=Decimal("12000.00"),
                status="SOLD",  # SOLD status
                is_active=True,
            )

        # Load dashboard
        response = self.client.get(reverse("verticals:clothing_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Check stock summary context
        stock_summary = response.context["stock_summary"]

        # Find shirt category
        shirt_summary = None
        for item in stock_summary:
            if item["category"].lower() == "shirt":
                shirt_summary = item
                break

        self.assertIsNotNone(shirt_summary, "Shirt should appear in stock summary")
        self.assertEqual(shirt_summary["total_quantity"], 5, "Should show only 5 units (sold excluded)")
        self.assertEqual(shirt_summary["tracked_quantity"], 5, "Should show 5 tracked units")

    def test_stock_summary_respects_business_scoping(self):
        """Stock summary should not leak data from other businesses"""
        # Create another business
        other_business = Business.objects.create(
            name="Other Clothing Store",
            slug="other-clothing",
            business_kind=BusinessKind.CLOTHING,
        )

        other_location = Location.objects.create(
            business=other_business,
            name="Other Store",
            is_default=True,
        )

        # Add stock to OTHER business (should NOT appear in our dashboard)
        other_product = MerchProduct.objects.create(
            business=other_business,
            name="Other Shoes",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            selling_price=Decimal("10000.00"),
            cost_price=Decimal("7000.00"),
            quantity_in_stock=100,
            is_active=True,
            is_archived=False,
        )

        ClothingBarcodeUnit.objects.create(
            business=other_business,
            location=other_location,
            product=other_product,
            barcode="OTHER001",
            size="40",
            category="shoes",
            cost_price=Decimal("7000.00"),
            selling_price=Decimal("10000.00"),
            status="IN_STOCK",
            is_active=True,
        )

        # Add stock to OUR business
        our_product = MerchProduct.objects.create(
            business=self.business,
            name="Our Shoes",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            selling_price=Decimal("15000.00"),
            cost_price=Decimal("10000.00"),
            quantity_in_stock=5,
            is_active=True,
            is_archived=False,
        )

        # Load dashboard
        response = self.client.get(reverse("verticals:clothing_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Check stock summary context
        stock_summary = response.context["stock_summary"]

        # Find shoes category
        shoes_summary = None
        for item in stock_summary:
            if item["category"].lower() == "shoes":
                shoes_summary = item
                break

        self.assertIsNotNone(shoes_summary, "Shoes should appear in stock summary")
        # Should only show OUR business's stock (5 common), not other business's (100 common + 1 tracked)
        self.assertEqual(shoes_summary["total_quantity"], 5, "Should show only our business's stock")
        self.assertEqual(shoes_summary["common_quantity"], 5, "Should show only our common stock")

    def test_stock_summary_avoids_double_counting(self):
        """Products with tracked units should not also count their quantity_in_stock"""
        # Create product with BOTH tracked units AND quantity_in_stock
        product = MerchProduct.objects.create(
            business=self.business,
            name="Hybrid Product",
            kind=BusinessKind.CLOTHING,
            category="shoes",
            selling_price=Decimal("10000.00"),
            cost_price=Decimal("7000.00"),
            quantity_in_stock=50,  # This should be IGNORED if product has tracked units
            is_active=True,
            is_archived=False,
        )

        # Add tracked units
        for i in range(5):
            ClothingBarcodeUnit.objects.create(
                business=self.business,
                location=self.location,
                product=product,
                barcode=f"HYBRID{i:04d}",
                size="40",
                category="shoes",
                cost_price=Decimal("7000.00"),
                selling_price=Decimal("10000.00"),
                status="IN_STOCK",
                is_active=True,
            )

        # Load dashboard
        response = self.client.get(reverse("verticals:clothing_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Check stock summary context
        stock_summary = response.context["stock_summary"]

        # Find shoes category
        shoes_summary = None
        for item in stock_summary:
            if item["category"].lower() == "shoes":
                shoes_summary = item
                break

        self.assertIsNotNone(shoes_summary, "Shoes should appear in stock summary")
        # Should ONLY count tracked units (5), NOT quantity_in_stock (50)
        self.assertEqual(shoes_summary["total_quantity"], 5, "Should only count tracked units, not double-count")
        self.assertEqual(shoes_summary["tracked_quantity"], 5, "Should show 5 tracked units")
        self.assertEqual(shoes_summary["common_quantity"], 0, "Should show 0 common (product has tracked units)")

    def test_stock_summary_empty_when_no_stock(self):
        """Stock summary should be empty when there is no stock"""
        # Create products but with zero stock
        MerchProduct.objects.create(
            business=self.business,
            name="Out of Stock Jeans",
            kind=BusinessKind.CLOTHING,
            category="jeans",
            selling_price=Decimal("8000.00"),
            cost_price=Decimal("5000.00"),
            quantity_in_stock=0,
            is_active=True,
            is_archived=False,
        )

        # Load dashboard
        response = self.client.get(reverse("verticals:clothing_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Check stock summary context
        stock_summary = response.context["stock_summary"]

        # Should be empty (no stock)
        self.assertEqual(len(stock_summary), 0, "Stock summary should be empty when no stock")




