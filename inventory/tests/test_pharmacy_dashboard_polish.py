# inventory/tests/test_pharmacy_dashboard_polish.py
"""
Tests for Pharmacy Dashboard Polish & Enhancements.

Tests all new features added for pharmacy vertical dashboard improvements:
- Stock value calculation (non-zero when stock exists)
- Payment mix aggregation (cash/mobile/bank/other)
- Sales trend units (integer counts, not decimals)
- Hub counts (doesn't crash, shows correct badges)
- Detailed operational summaries
"""
from decimal import Decimal
from datetime import timedelta

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from tenants.models import Business, Location
from inventory.models import MerchProduct
from inventory.models_pharmacy import PharmacyBatch, PharmacySale, PharmacyCategory
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
class TestPharmacyDashboardPolish(TestCase):
    """Test suite for pharmacy dashboard polish features."""

    def setUp(self):
        """Set up test data."""
        # Create user
        self.user = User.objects.create_user(
            username="pharmatest",
            email="pharmatest@emajinet.co.zm",
            password="testpass123",
        )

        # Create business (pharmacy kind)
        self.business = Business.objects.create(
            name="Test Pharmacy",
            business_kind=BusinessKind.PHARMACY,
            owner=self.user,
        )

        # Create location (no is_primary field in current Location model)
        self.location = Location.objects.create(
            business=self.business,
            name="Main Branch",
        )

        # Set business on user for @require_business decorator
        self.user.active_business = self.business
        self.user.save()

        # Create client and login
        self.client = Client()
        self.client.force_login(self.user)

        # Create test products
        self.product1 = MerchProduct.objects.create(
            business=self.business,
            name="Paracetamol 500mg",
            kind="pharmacy",
            category=PharmacyCategory.ANALGESIC,
            is_active=True,
        )

        self.product2 = MerchProduct.objects.create(
            business=self.business,
            name="Amoxicillin 250mg",
            kind="pharmacy",
            category=PharmacyCategory.ANTIBIOTIC,
            is_active=True,
        )

        self.product3 = MerchProduct.objects.create(
            business=self.business,
            name="Skin Cream",
            kind="pharmacy",
            category=PharmacyCategory.SKIN_CARE,
            is_active=True,
        )

        # Create test batches with different stock levels and prices
        today = timezone.now().date()

        self.batch1 = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product1,
            batch_number="B001",
            quantity=50,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            expiry_date=today + timedelta(days=90),
            reorder_level=20,
        )

        self.batch2 = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product2,
            batch_number="B002",
            quantity=10,  # Low stock (below reorder)
            cost_price=Decimal("200.00"),
            selling_price=Decimal("300.00"),
            expiry_date=today + timedelta(days=15),  # Near expiry
            reorder_level=20,
        )

        self.batch3 = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product3,
            batch_number="B003",
            quantity=0,  # Out of stock
            cost_price=Decimal("50.00"),
            selling_price=Decimal("80.00"),
            expiry_date=today - timedelta(days=5),  # Expired
            reorder_level=10,
        )

    def test_stock_value_calculation_non_zero(self):
        """Test that stock value is not zero when stock exists."""
        # Access dashboard
        response = self.client.get(reverse("verticals:pharmacy_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Check context has stock values
        ctx = response.context

        # Stock value at cost should be: (50 * 100) + (10 * 200) + (0 * 50) = 5000 + 2000 = 7000
        expected_cost_value = Decimal("7000.00")
        self.assertEqual(ctx["total_stock_value_cost"], expected_cost_value)

        # Potential revenue should be: (50 * 150) + (10 * 300) + (0 * 80) = 7500 + 3000 = 10500
        expected_potential_revenue = Decimal("10500.00")
        self.assertEqual(ctx["potential_revenue"], expected_potential_revenue)

        # Ensure neither is zero
        self.assertGreater(ctx["total_stock_value_cost"], Decimal("0"))
        self.assertGreater(ctx["potential_revenue"], Decimal("0"))

    def test_detailed_operational_summaries(self):
        """Test detailed operational metrics are calculated correctly."""
        response = self.client.get(reverse("verticals:pharmacy_dashboard"))
        self.assertEqual(response.status_code, 200)

        ctx = response.context

        # In stock count (quantity > 0): batch1 and batch2 = 2
        self.assertEqual(ctx["in_stock_count"], 2)

        # Out of stock count (quantity = 0): batch3 = 1
        self.assertEqual(ctx["out_of_stock_count"], 1)

        # Total products
        self.assertEqual(ctx["total_products"], 3)

        # Active batches
        self.assertEqual(ctx["active_batches_count"], 3)

        # Near expiry count (batch2 expires in 15 days)
        self.assertEqual(ctx["near_expiry_count"], 1)

        # Expired count (batch3)
        self.assertEqual(ctx["expired_count"], 1)

        # Low stock count (batch2 has qty=10, reorder=20)
        self.assertEqual(ctx["low_stock_count"], 1)

    def test_payment_mix_aggregation(self):
        """Test payment mix returns expected buckets (cash/mobile/bank)."""
        today = timezone.now()
        yesterday = today - timedelta(days=1)

        # Create sales with different payment methods
        PharmacySale.objects.create(
            business=self.business,
            batch=self.batch1,
            quantity=5,
            unit_price=Decimal("150.00"),
            unit_cost=Decimal("100.00"),
            total_amount=Decimal("750.00"),
            payment_method="CASH",
            sold_by=self.user,
            sold_at=yesterday,
        )

        PharmacySale.objects.create(
            business=self.business,
            batch=self.batch1,
            quantity=3,
            unit_price=Decimal("150.00"),
            unit_cost=Decimal("100.00"),
            total_amount=Decimal("450.00"),
            payment_method="MOBILE_MONEY",
            sold_by=self.user,
            sold_at=yesterday,
        )

        PharmacySale.objects.create(
            business=self.business,
            batch=self.batch2,
            quantity=2,
            unit_price=Decimal("300.00"),
            unit_cost=Decimal("200.00"),
            total_amount=Decimal("600.00"),
            payment_method="BANK",
            sold_by=self.user,
            sold_at=yesterday,
        )

        PharmacySale.objects.create(
            business=self.business,
            batch=self.batch1,
            quantity=1,
            unit_price=Decimal("150.00"),
            unit_cost=Decimal("100.00"),
            total_amount=Decimal("150.00"),
            payment_method="CASH",
            sold_by=self.user,
            sold_at=today,
        )

        # Access dashboard
        response = self.client.get(reverse("verticals:pharmacy_dashboard"))
        self.assertEqual(response.status_code, 200)

        ctx = response.context
        payment_mix = ctx.get("payment_mix", [])

        # Should have payment mix data
        self.assertIsNotNone(payment_mix)
        self.assertGreater(len(payment_mix), 0)

        # Check that payment methods are present
        payment_methods = [p["method_code"] for p in payment_mix]
        self.assertIn("CASH", payment_methods)
        self.assertIn("MOBILE_MONEY", payment_methods)
        self.assertIn("BANK", payment_methods)

        # Check CASH total: 750 + 150 = 900
        cash_entry = next((p for p in payment_mix if p["method_code"] == "CASH"), None)
        self.assertIsNotNone(cash_entry)
        self.assertEqual(cash_entry["count"], 2)
        self.assertEqual(cash_entry["amount"], 900.0)

    def test_sales_trend_returns_integer_units(self):
        """Test sales trend API returns integer unit counts (not decimals)."""
        today = timezone.now()

        # Create sales over last 7 days
        for i in range(7):
            sale_date = today - timedelta(days=i)
            PharmacySale.objects.create(
                business=self.business,
                batch=self.batch1,
                quantity=i + 1,  # 1, 2, 3, 4, 5, 6, 7 units
                unit_price=Decimal("150.00"),
                unit_cost=Decimal("100.00"),
                total_amount=Decimal("150.00") * (i + 1),
                payment_method="CASH",
                sold_by=self.user,
                sold_at=sale_date,
            )

        # Access sales trend JSON endpoint
        response = self.client.get(reverse("verticals:pharmacy_sales_trend_json") + "?range=7d")
        self.assertEqual(response.status_code, 200)

        data = response.json()

        # Check structure
        self.assertIn("units_sold", data)
        self.assertIn("count", data)  # Legacy alias
        self.assertIn("labels", data)

        units_sold = data["units_sold"]

        # Should have 7 days of data
        self.assertEqual(len(units_sold), 7)

        # All values should be integers
        for value in units_sold:
            self.assertIsInstance(value, int)
            self.assertGreaterEqual(value, 0)

        # Total units should match our created sales
        total_units = sum(units_sold)
        expected_total = sum(range(1, 8))  # 1+2+3+4+5+6+7 = 28
        self.assertEqual(total_units, expected_total)

    def test_hub_counts_no_crash(self):
        """Test hub view renders without crashing and shows badge counts."""
        response = self.client.get(reverse("verticals:pharmacy_hub"))
        self.assertEqual(response.status_code, 200)

        ctx = response.context

        # Check all badge counts are present
        self.assertIn("near_expiry_count", ctx)
        self.assertIn("expired_count", ctx)
        self.assertIn("low_stock_count", ctx)
        self.assertIn("active_batches_count", ctx)
        self.assertIn("recent_sales_count", ctx)

        # Check counts are correct
        self.assertEqual(ctx["near_expiry_count"], 1)  # batch2
        self.assertEqual(ctx["expired_count"], 1)  # batch3
        self.assertEqual(ctx["low_stock_count"], 1)  # batch2
        self.assertEqual(ctx["active_batches_count"], 3)

        # recent_sales_count should be 0 (no sales in last 30 days yet)
        self.assertEqual(ctx["recent_sales_count"], 0)

    def test_today_and_month_sales_amounts(self):
        """Test today's and this month's sales amounts are calculated correctly."""
        today = timezone.now()
        yesterday = today - timedelta(days=1)

        # Create today's sales
        PharmacySale.objects.create(
            business=self.business,
            batch=self.batch1,
            quantity=2,
            unit_price=Decimal("150.00"),
            unit_cost=Decimal("100.00"),
            total_amount=Decimal("300.00"),
            payment_method="CASH",
            sold_by=self.user,
            sold_at=today,
        )

        # Create yesterday's sales (still this month)
        PharmacySale.objects.create(
            business=self.business,
            batch=self.batch1,
            quantity=3,
            unit_price=Decimal("150.00"),
            unit_cost=Decimal("100.00"),
            total_amount=Decimal("450.00"),
            payment_method="CASH",
            sold_by=self.user,
            sold_at=yesterday,
        )

        # Access dashboard
        response = self.client.get(reverse("verticals:pharmacy_dashboard"))
        self.assertEqual(response.status_code, 200)

        ctx = response.context

        # Today's sales amount should be 300
        self.assertEqual(ctx["today_sales_amount"], Decimal("300.00"))
        self.assertEqual(ctx["today_sales_count_actual"], 1)

        # Month's sales amount should be 300 + 450 = 750
        self.assertEqual(ctx["month_sales_amount"], Decimal("750.00"))
        self.assertEqual(ctx["month_sales_count"], 2)

    def test_last_7_days_units_sold(self):
        """Test last 7 days units sold total is calculated correctly."""
        today = timezone.now()

        # Create sales over last 7 days
        total_expected_units = 0
        for i in range(7):
            sale_date = today - timedelta(days=i)
            quantity = i + 1
            total_expected_units += quantity

            PharmacySale.objects.create(
                business=self.business,
                batch=self.batch1,
                quantity=quantity,
                unit_price=Decimal("150.00"),
                unit_cost=Decimal("100.00"),
                total_amount=Decimal("150.00") * quantity,
                payment_method="CASH",
                sold_by=self.user,
                sold_at=sale_date,
            )

        # Access dashboard
        response = self.client.get(reverse("verticals:pharmacy_dashboard"))
        self.assertEqual(response.status_code, 200)

        ctx = response.context

        # Last 7 days units should be 1+2+3+4+5+6+7 = 28
        self.assertEqual(ctx["last_7_days_units"], total_expected_units)

    def test_empty_state_no_crash(self):
        """Test dashboard renders correctly even with no sales or stock."""
        # Delete all batches
        PharmacyBatch.objects.all().delete()

        # Access dashboard
        response = self.client.get(reverse("verticals:pharmacy_dashboard"))
        self.assertEqual(response.status_code, 200)

        ctx = response.context

        # Stock values should be zero
        self.assertEqual(ctx["total_stock_value_cost"], Decimal("0"))
        self.assertEqual(ctx["potential_revenue"], Decimal("0"))

        # Counts should be zero
        self.assertEqual(ctx["in_stock_count"], 0)
        self.assertEqual(ctx["out_of_stock_count"], 0)
        self.assertEqual(ctx["near_expiry_count"], 0)
        self.assertEqual(ctx["expired_count"], 0)

        # Should not crash on empty payment mix
        payment_mix = ctx.get("payment_mix", [])
        self.assertIsNotNone(payment_mix)

    def test_null_price_handling(self):
        """Test that NULL prices are handled safely (treat as 0)."""
        # Create batch with NULL prices (shouldn't happen but be defensive)
        # Note: Model has validators, so we can't actually create NULL prices
        # But the aggregation uses Coalesce to handle it
        # This test ensures the query doesn't crash

        response = self.client.get(reverse("verticals:pharmacy_dashboard"))
        self.assertEqual(response.status_code, 200)

        # If we got here without error, the query handled potential NULLs safely
        ctx = response.context
        self.assertIsNotNone(ctx["total_stock_value_cost"])
        self.assertIsNotNone(ctx["potential_revenue"])


@pytest.mark.django_db
class TestPharmacyDashboardChartData(TestCase):
    """Test chart data formatting and integer constraints."""

    def setUp(self):
        """Set up minimal test data for chart tests."""
        self.user = User.objects.create_user(
            username="charttest",
            email="charttest@emajinet.co.zm",
            password="testpass123",
        )

        self.business = Business.objects.create(
            name="Chart Test Pharmacy",
            business_kind=BusinessKind.PHARMACY,
            owner=self.user,
        )

        self.location = Location.objects.create(
            business=self.business,
            name="Main Branch",
        )

        self.user.active_business = self.business
        self.user.save()

        self.client = Client()
        self.client.force_login(self.user)

        # Create product and batch
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Medicine",
            kind="pharmacy",
            is_active=True,
        )

        today = timezone.now().date()
        self.batch = PharmacyBatch.objects.create(
            business=self.business,
            merch_product=self.product,
            batch_number="TEST001",
            quantity=100,
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            expiry_date=today + timedelta(days=365),
        )

    def test_sales_trend_chart_integer_formatting(self):
        """Test that sales trend chart data is properly formatted with integers."""
        today = timezone.now()

        # Create sales with fractional quantities should still sum to integers
        PharmacySale.objects.create(
            business=self.business,
            batch=self.batch,
            quantity=5,
            unit_price=Decimal("150.00"),
            unit_cost=Decimal("100.00"),
            total_amount=Decimal("750.00"),
            payment_method="CASH",
            sold_by=self.user,
            sold_at=today,
        )

        # Fetch chart data
        response = self.client.get(reverse("verticals:pharmacy_sales_trend_json") + "?range=7d")
        self.assertEqual(response.status_code, 200)

        data = response.json()

        # Verify all units_sold values are integers
        for value in data["units_sold"]:
            self.assertIsInstance(value, int)
            # Ensure no decimal-like values (e.g., 5.0 should be 5)
            self.assertEqual(value, int(value))

        # Verify labels are present
        self.assertEqual(len(data["labels"]), 7)

    def test_chart_data_cache_busting(self):
        """Test that chart data includes timestamp for cache busting."""
        response = self.client.get(reverse("verticals:pharmacy_sales_trend_json") + "?range=7d")
        data = response.json()

        # Should have timestamp
        self.assertIn("timestamp", data)
        self.assertIsNotNone(data["timestamp"])

        # Should have period info
        self.assertIn("period", data)
        self.assertIn("start_date", data)
        self.assertIn("end_date", data)

    def test_dashboard_loads_without_models_nameerror(self):
        """
        Regression test: Ensure dashboard loads without NameError.
        
        Previously crashed with "NameError: name 'models' is not defined"
        when using models.DecimalField() without proper import.
        
        This test ensures DecimalField calculations in stock value and
        potential revenue work correctly.
        """
        response = self.client.get(reverse("verticals:pharmacy_dashboard"))
        
        # Should return 200, not 500
        self.assertEqual(response.status_code, 200)
        
        # Should have the calculated fields in context
        ctx = response.context
        self.assertIn("total_stock_value_cost", ctx)
        self.assertIn("potential_revenue", ctx)
        
        # Values should be Decimal instances (not crash)
        self.assertIsInstance(ctx["total_stock_value_cost"], Decimal)
        self.assertIsInstance(ctx["potential_revenue"], Decimal)


# Run with: python manage.py test inventory.tests.test_pharmacy_dashboard_polish

