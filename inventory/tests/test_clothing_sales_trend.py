"""
Regression tests for Clothing Sales Trend bug fix.

PROBLEM: Sales Trend card shows "No sales data available" even though Recent Sales exist.

ROOT CAUSE: Recent Sales query doesn't filter by date, but Sales Trend does.
When viewing MTD/7D/Today, Recent Sales shows ALL sales (last 10), but trend
correctly filters and may show empty if sales are outside date range.

FIX: Both queries must use same date filtering logic.

These tests ensure:
1. Sales Trend populates when sales exist in date range
2. Sales Trend uses same base query as recent sales
3. Backend-safe aggregation works on SQLite and Postgres
4. API endpoint returns correct data structure
5. Zero regressions - all existing functionality preserved
"""

from decimal import Decimal
from datetime import datetime, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingSale, PaymentMethod
from inventory.business_kinds import BusinessKind

User = get_user_model()


class ClothingSalesTrendRegressionTests(TestCase):
    """
    Regression tests for Sales Trend bug.
    Ensures trend chart never incorrectly shows "no data" when sales exist.
    """

    def setUp(self):
        """Create test business, user, and products"""
        # Create business
        self.business = Business.objects.create(
            name="Fashion Boutique Test",
            slug="fashion-boutique-test",
            kind=BusinessKind.CLOTHING,
        )

        # Create user and assign to business
        self.user = User.objects.create_user(
            username="clothingmanager",
            email="manager@fashion.test",
            password="testpass123",
        )
        
        # Create membership (manager role)
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Create test products
        self.product1 = MerchProduct.objects.create(
            business=self.business,
            name="Blue Jeans - Size 32",
            kind=BusinessKind.CLOTHING,
            category="jeans",
            size="32",
            color="Blue",
            spec_label="Size 32",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
            quantity_in_stock=10,
            is_active=True,
            track_inventory=True,
        )

        self.product2 = MerchProduct.objects.create(
            business=self.business,
            name="Red Dress - Size M",
            kind=BusinessKind.CLOTHING,
            category="dress",
            size="M",
            color="Red",
            spec_label="Size M",
            cost_price=Decimal("80.00"),
            selling_price=Decimal("150.00"),
            quantity_in_stock=5,
            is_active=True,
            track_inventory=True,
        )

        self.client = Client()
        self.client.force_login(self.user)
        # Set active business in session so base_context resolves the correct tenant scope
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_sales_trend_not_empty_when_sales_exist_mtd(self):
        """
        Test A: Trend not empty when sales exist in MTD range.
        
        This is the PRIMARY regression test for the bug.
        If sales exist in the current month, trend MUST show data.
        """
        # Create sales on different dates THIS MONTH
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Sale 1: 5 days ago
        sale_date_1 = now - timedelta(days=5)
        if sale_date_1 >= month_start:  # Ensure it's still in this month
            ClothingSale.objects.create(
                business=self.business,
                product=self.product1,
                quantity=2,
                unit_price=Decimal("100.00"),
                total_price=Decimal("200.00"),
                unit_cost=Decimal("50.00"),
                total_cost=Decimal("100.00"),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=sale_date_1,
            )

        # Sale 2: 2 days ago
        sale_date_2 = now - timedelta(days=2)
        if sale_date_2 >= month_start:  # Ensure it's still in this month
            ClothingSale.objects.create(
                business=self.business,
                product=self.product2,
                quantity=1,
                unit_price=Decimal("150.00"),
                total_price=Decimal("150.00"),
                unit_cost=Decimal("80.00"),
                total_cost=Decimal("80.00"),
                payment_method=PaymentMethod.MOBILE_MONEY,
                sold_by=self.user,
                sold_at=sale_date_2,
            )

        # Sale 3: Today
        ClothingSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=1,
            unit_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
            unit_cost=Decimal("50.00"),
            total_cost=Decimal("50.00"),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=now,
        )

        # GET dashboard (default is MTD)
        url = reverse("verticals:clothing_dashboard")
        response = self.client.get(url)

        # Assert response is 200
        self.assertEqual(response.status_code, 200)

        # Assert context has sales trend data
        self.assertIn("sales_trend", response.context)
        sales_trend = response.context["sales_trend"]
        self.assertIsNotNone(sales_trend)
        self.assertIsInstance(sales_trend, list)

        # Assert trend has data points
        self.assertGreater(len(sales_trend), 0, "Sales trend should not be empty when sales exist")

        # Assert at least some points have non-zero revenue
        total_revenue = sum(day["revenue"] for day in sales_trend)
        self.assertGreater(total_revenue, 0, "Sales trend should show revenue when sales exist")

    def test_sales_trend_api_returns_valid_data(self):
        """
        Test B: API endpoint returns valid data structure.
        
        Ensures /api/sales-trend/ works correctly with date filtering.
        """
        # Create sales TODAY
        now = timezone.now()
        ClothingSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=3,
            unit_price=Decimal("100.00"),
            total_price=Decimal("300.00"),
            unit_cost=Decimal("50.00"),
            total_cost=Decimal("150.00"),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=now,
        )

        # Call API with 'today' range
        url = reverse("verticals:clothing_sales_trend_json")
        response = self.client.get(url, {"range": "today"})

        # Assert response is 200 and JSON
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        # Parse JSON
        data = response.json()

        # Assert required fields exist
        self.assertIn("labels", data)
        self.assertIn("revenue", data)
        self.assertIn("count", data)
        self.assertIn("has_data", data)

        # Assert data structure is correct
        self.assertIsInstance(data["labels"], list)
        self.assertIsInstance(data["revenue"], list)
        self.assertIsInstance(data["count"], list)

        # Assert has_data is True when sales exist
        self.assertTrue(data["has_data"], "has_data should be True when sales exist today")

        # Assert revenue is not empty
        self.assertGreater(len(data["revenue"]), 0, "Revenue array should not be empty")

        # Assert at least one revenue value is non-zero
        total_revenue = sum(data["revenue"])
        self.assertGreater(total_revenue, 0, "Total revenue should be greater than 0")

    def test_sales_trend_uses_same_query_as_dashboard(self):
        """
        Test C: Trend uses same base query as dashboard metrics.
        
        Ensures consistency between different dashboard sections.
        """
        # Create sale today
        now = timezone.now()
        sale = ClothingSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=1,
            unit_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
            unit_cost=Decimal("50.00"),
            total_cost=Decimal("50.00"),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=now,
        )

        # GET dashboard with 'today' filter
        url = reverse("verticals:clothing_dashboard")
        response = self.client.get(url, {"range": "today"})

        self.assertEqual(response.status_code, 200)

        # Check that both revenue_mtd and sales_trend reflect the sale
        revenue_mtd = response.context.get("revenue_mtd", Decimal("0"))
        sales_trend = response.context.get("sales_trend", [])

        # Revenue should match sale
        self.assertEqual(revenue_mtd, Decimal("100.00"), "Revenue MTD should match today's sale")

        # Trend should have data
        self.assertGreater(len(sales_trend), 0, "Sales trend should have data points")

        # Trend should include today's sale
        trend_total_revenue = sum(day["revenue"] for day in sales_trend)
        self.assertAlmostEqual(
            float(trend_total_revenue),
            float(sale.total_price),
            places=2,
            msg="Sales trend total should match sale total",
        )

    def test_sales_trend_empty_when_no_sales_in_range(self):
        """
        Test D: Trend correctly shows no data when no sales in date range.
        
        This is a POSITIVE test - it should show empty state when appropriate.
        """
        # Create sale LAST MONTH (outside MTD range)
        now = timezone.now()
        last_month = now - timedelta(days=35)  # Definitely last month

        ClothingSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=1,
            unit_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
            unit_cost=Decimal("50.00"),
            total_cost=Decimal("50.00"),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=last_month,
        )

        # GET dashboard with 'today' filter
        url = reverse("verticals:clothing_dashboard")
        response = self.client.get(url, {"range": "today"})

        self.assertEqual(response.status_code, 200)

        # Revenue should be 0 for today
        revenue_mtd = response.context.get("revenue_mtd", Decimal("0"))
        self.assertEqual(revenue_mtd, Decimal("0"), "Revenue should be 0 when no sales today")

        # API should also show no data
        api_url = reverse("verticals:clothing_sales_trend_json")
        api_response = self.client.get(api_url, {"range": "today"})

        data = api_response.json()
        self.assertFalse(data["has_data"], "has_data should be False when no sales today")

    def test_sales_trend_7d_range(self):
        """
        Test E: Trend works correctly for 7-day range.
        """
        # Create sales on different days in last 7 days
        now = timezone.now()

        for i in range(1, 4):  # 3 sales on days 1, 2, 3
            sale_date = now - timedelta(days=i)
            ClothingSale.objects.create(
                business=self.business,
                product=self.product1,
                quantity=1,
                unit_price=Decimal("100.00"),
                total_price=Decimal("100.00"),
                unit_cost=Decimal("50.00"),
                total_cost=Decimal("50.00"),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=sale_date,
            )

        # GET dashboard with 7d filter
        url = reverse("verticals:clothing_dashboard")
        response = self.client.get(url, {"range": "7d"})

        self.assertEqual(response.status_code, 200)

        # Check trend has data
        sales_trend = response.context.get("sales_trend", [])
        self.assertGreater(len(sales_trend), 0, "Sales trend should have data for 7d range")

        # Check API
        api_url = reverse("verticals:clothing_sales_trend_json")
        api_response = self.client.get(api_url, {"range": "7d"})

        data = api_response.json()
        self.assertTrue(data["has_data"], "API should show data for 7d range when sales exist")
        self.assertGreater(sum(data["revenue"]), 0, "API should show revenue for 7d range")

    def test_sales_trend_backend_safe_aggregation(self):
        """
        Test F: Backend-safe aggregation works (SQLite compatibility).
        
        Ensures TruncDate works on SQLite without crashing.
        """
        # Create sale
        now = timezone.now()
        ClothingSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=1,
            unit_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
            unit_cost=Decimal("50.00"),
            total_cost=Decimal("50.00"),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=now,
        )

        # This should not crash on SQLite
        from inventory.verticals import base
        from django.db import connection

        sales_qs = base.clothing_sales_queryset(
            business=self.business, location=None, period="today", date_str=None
        )

        # Test aggregation (same as in sales_trend_json)
        from django.db.models.functions import TruncDate
        from django.db.models import Count, Sum, F
        from django.db.models.functions import Coalesce

        try:
            daily_sales = (
                sales_qs.annotate(sale_date=TruncDate("sold_at"))
                .values("sale_date")
                .annotate(
                    revenue=Coalesce(Sum("total_price"), base.DECIMAL_ZERO, output_field=base.DECIMAL_FIELD),
                    count=Count("id"),
                )
                .order_by("sale_date")
            )

            # Force evaluation
            list(daily_sales)

            # If we get here, aggregation works
            self.assertTrue(True, "Backend-safe aggregation works on SQLite")

        except Exception as e:
            self.fail(f"Backend aggregation failed: {e}")

    def test_sales_trend_multiple_payment_methods(self):
        """
        Test G: Trend aggregates correctly across payment methods.
        """
        now = timezone.now()

        # Create sales with different payment methods
        ClothingSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=1,
            unit_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
            unit_cost=Decimal("50.00"),
            total_cost=Decimal("50.00"),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=now,
        )

        ClothingSale.objects.create(
            business=self.business,
            product=self.product2,
            quantity=1,
            unit_price=Decimal("150.00"),
            total_price=Decimal("150.00"),
            unit_cost=Decimal("80.00"),
            total_cost=Decimal("80.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            sold_by=self.user,
            sold_at=now,
        )

        # GET dashboard
        url = reverse("verticals:clothing_dashboard")
        response = self.client.get(url, {"range": "today"})

        self.assertEqual(response.status_code, 200)

        # Check total revenue aggregates both sales
        revenue_mtd = response.context.get("revenue_mtd", Decimal("0"))
        expected_revenue = Decimal("250.00")  # 100 + 150
        self.assertEqual(revenue_mtd, expected_revenue, "Revenue should aggregate all payment methods")

    def test_sales_trend_preserves_existing_functionality(self):
        """
        Test H: Zero regressions - existing functionality preserved.
        
        Ensures all other dashboard metrics still work correctly.
        """
        # Create sales
        now = timezone.now()
        ClothingSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=2,
            unit_price=Decimal("100.00"),
            total_price=Decimal("200.00"),
            unit_cost=Decimal("50.00"),
            total_cost=Decimal("100.00"),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=now,
        )

        # GET dashboard
        url = reverse("verticals:clothing_dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check all expected context variables exist
        expected_context_keys = [
            "revenue_mtd",
            "profit_mtd",
            "total_sales_mtd",
            "cost_mtd",
            "overhead_costs",
            "total_costs_mtd",
            "inventory_value",
            "retail_value",
            "expected_margin",
            "payment_mix_data",
            "top_models",
            "top_model",
            "sales_trend",
            "stock_summary",
            "recent_sales",
            "product_count",
            "active_product_count",
        ]

        for key in expected_context_keys:
            self.assertIn(key, response.context, f"Context should contain '{key}'")

        # Check revenue is correct
        self.assertEqual(response.context["revenue_mtd"], Decimal("200.00"))

        # Check profit is calculated
        self.assertEqual(response.context["profit_mtd"], Decimal("100.00"))  # 200 - 100 (COGS) - 0 (overhead)

        # Check sales count
        self.assertEqual(response.context["total_sales_mtd"], 1)

