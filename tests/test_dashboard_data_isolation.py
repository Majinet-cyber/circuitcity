# tests/test_dashboard_data_isolation.py
"""
Data isolation tests for dashboard metrics and vertical dashboards.

These tests verify that dashboard KPIs, payment mix, and yesterday summaries
are correctly scoped to the active business and don't leak data from other businesses.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.utils import timezone

from tenants.models import Business
from inventory.models_verticals import ClothingSale, LiquorSale, PaymentMethod
from inventory.models import MerchProduct, Location
from inventory.business_kinds import BusinessKind

from dashboard.helpers_yesterday import get_yesterday_summary
from dashboard.helpers_payments import get_payment_mix


User = get_user_model()


@pytest.mark.django_db
class TestDashboardDataIsolation(TestCase):
    """
    Test that dashboard metrics are correctly scoped to business and don't leak data.
    
    This is the critical bug fix: a newly created store must show 0 sales/revenue
    unless that store has recorded sales.
    """
    
    def setUp(self):
        """Create two businesses and test data for isolation testing."""
        # Create test user
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        # Business A - Has sales
        self.business_a = Business.objects.create(
            name="Business A - Clothing Store",
            slug="business-a-clothing-store",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE"
        )
        self.location_a = Location.objects.create(
            name="Location A",
            business=self.business_a
        )
        
        # Business B - Brand new, no sales (this is the bug scenario)
        self.business_b = Business.objects.create(
            name="Business B - LA CASSA",
            slug="business-b-la-cassa",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE"
        )
        self.location_b = Location.objects.create(
            name="Location B",
            business=self.business_b
        )
        
        # Create products for Business A
        self.product_a = MerchProduct.objects.create(
            business=self.business_a,
            name="T-Shirt - M - Black",
            kind=BusinessKind.CLOTHING,
            cost_price=Decimal("5000.00"),
            selling_price=Decimal("10000.00"),
            quantity_in_stock=10
        )
        
        # Create sales for Business A ONLY
        from datetime import time
        yesterday = timezone.localdate() - timedelta(days=1)
        today = timezone.localdate()
        
        # Use midday (12:00) timestamps to avoid boundary issues across timezones
        yesterday_midday = timezone.make_aware(
            timezone.datetime.combine(yesterday, time(12, 0))
        )
        today_midday = timezone.make_aware(
            timezone.datetime.combine(today, time(12, 0))
        )
        
        # Yesterday sales for Business A
        ClothingSale.objects.create(
            business=self.business_a,
            product=self.product_a,
            quantity=2,
            unit_price=Decimal("10000.00"),
            total_price=Decimal("20000.00"),
            unit_cost=Decimal("5000.00"),
            total_cost=Decimal("10000.00"),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=yesterday_midday
        )
        
        # Today sales for Business A
        ClothingSale.objects.create(
            business=self.business_a,
            product=self.product_a,
            quantity=1,
            unit_price=Decimal("10000.00"),
            total_price=Decimal("10000.00"),
            unit_cost=Decimal("5000.00"),
            total_cost=Decimal("5000.00"),
            payment_method=PaymentMethod.BANK,
            sold_by=self.user,
            sold_at=today_midday
        )
        
        # Business B has NO sales (this is the test scenario)
        # A brand new store should show 0 sales, 0 revenue
    
    def test_yesterday_summary_isolated_to_business(self):
        """
        Test that yesterday summary only shows data for the active business.
        
        Bug scenario: Business B (brand new store) was showing sales from Business A.
        Fix: get_yesterday_summary must filter by business explicitly.
        """
        # Get yesterday summary for Business A (has sales)
        summary_a = get_yesterday_summary(self.user, self.business_a)
        
        # Business A should show yesterday's sales
        self.assertIsNotNone(summary_a)
        self.assertEqual(summary_a["sales_count"], 1)
        self.assertEqual(Decimal(str(summary_a["total_revenue"])), Decimal("20000.00"))
        self.assertEqual(len(summary_a["payment_mix"]), 1)  # Cash only
        
        # Get yesterday summary for Business B (new store, no sales)
        summary_b = get_yesterday_summary(self.user, self.business_b)
        
        # ✅ CRITICAL: Business B must show 0 sales, not Business A's data
        self.assertIsNotNone(summary_b)
        self.assertEqual(summary_b["sales_count"], 0)
        self.assertEqual(summary_b["total_revenue"], 0)
        self.assertEqual(len(summary_b["payment_mix"]), 0)
    
    def test_payment_mix_isolated_to_business(self):
        """
        Test that payment mix only shows data for the active business.
        
        Bug scenario: Business B was showing payment breakdown from Business A.
        Fix: get_payment_mix must filter by business explicitly.
        """
        yesterday = timezone.localdate() - timedelta(days=1)
        today = timezone.localdate()
        
        # Get payment mix for Business A (has sales from yesterday and today)
        # The helper will convert dates to datetime ranges (start of day to end of day)
        mix_a = get_payment_mix(
            business=self.business_a,
            start_date=yesterday,
            end_date=today,  # Inclusive (helper adds 1 day internally)
            user=None,
            vertical=BusinessKind.CLOTHING
        )
        
        # Business A should show payment mix (Cash from yesterday + Bank from today)
        self.assertEqual(len(mix_a), 2)  # Cash + Bank
        
        # Find cash payment
        cash_payment = next((p for p in mix_a if p["method_code"] == PaymentMethod.CASH), None)
        self.assertIsNotNone(cash_payment)
        self.assertEqual(Decimal(str(cash_payment["amount"])), Decimal("20000.00"))
        
        # Get payment mix for Business B (new store, no sales)
        mix_b = get_payment_mix(
            business=self.business_b,
            start_date=yesterday,
            end_date=today,
            user=None,
            vertical=BusinessKind.CLOTHING
        )
        
        # ✅ CRITICAL: Business B must show empty payment mix, not Business A's data
        self.assertEqual(len(mix_b), 0)
    
    def test_clothing_dashboard_metrics_isolated(self):
        """
        Test that clothing dashboard metrics are scoped to business.
        
        This tests the actual dashboard view context data.
        """
        from inventory.verticals.base import clothing_sales_metrics
        
        yesterday = timezone.localdate() - timedelta(days=1)
        today = timezone.localdate()
        
        # Get metrics for Business A (has sales)
        metrics_a = clothing_sales_metrics(
            business=self.business_a,
            location=None,
            start_date=yesterday,
            end_date=today + timedelta(days=1),
            period="mtd"
        )
        
        # Business A should show sales
        self.assertEqual(metrics_a["total_sales"], 2)  # Yesterday + today
        self.assertGreater(metrics_a["revenue"], 0)
        
        # Get metrics for Business B (new store, no sales)
        metrics_b = clothing_sales_metrics(
            business=self.business_b,
            location=None,
            start_date=yesterday,
            end_date=today + timedelta(days=1),
            period="mtd"
        )
        
        # ✅ CRITICAL: Business B must show 0 sales
        self.assertEqual(metrics_b["total_sales"], 0)
        self.assertEqual(metrics_b["revenue"], Decimal("0.00"))
        self.assertEqual(metrics_b["cost_of_goods"], Decimal("0.00"))
        self.assertEqual(len(metrics_b["payment_mix_data"]), 0)
    
    def test_liquor_vertical_data_isolation(self):
        """
        Test that liquor vertical metrics are properly isolated.
        """
        # Create liquor businesses
        liquor_a = Business.objects.create(
            name="Liquor Store A",
            slug="liquor-store-a",
            business_kind=BusinessKind.LIQUOR,
            created_by=self.user,
            status="ACTIVE"
        )
        
        liquor_b = Business.objects.create(
            name="Liquor Store B - New",
            slug="liquor-store-b-new",
            business_kind=BusinessKind.LIQUOR,
            created_by=self.user,
            status="ACTIVE"
        )
        
        # Create product for Liquor A
        product_a = MerchProduct.objects.create(
            business=liquor_a,
            name="Beer - Castle Lite",
            kind=BusinessKind.LIQUOR,
            cost_price=Decimal("500.00"),
            selling_price=Decimal("1000.00")
        )
        
        from datetime import time
        yesterday = timezone.localdate() - timedelta(days=1)
        yesterday_midday = timezone.make_aware(
            timezone.datetime.combine(yesterday, time(12, 0))
        )
        
        # Create sales for Liquor A only
        LiquorSale.objects.create(
            business=liquor_a,
            product=product_a,
            quantity=10,
            unit_price=Decimal("1000.00"),
            total_price=Decimal("10000.00"),
            unit_cost=Decimal("500.00"),
            total_cost=Decimal("5000.00"),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=yesterday_midday
        )
        
        # Test yesterday summary
        summary_a = get_yesterday_summary(self.user, liquor_a)
        summary_b = get_yesterday_summary(self.user, liquor_b)
        
        # Liquor A should have sales
        self.assertIsNotNone(summary_a)
        self.assertEqual(summary_a["sales_count"], 1)
        
        # ✅ Liquor B (new store) must show 0
        self.assertIsNotNone(summary_b)
        self.assertEqual(summary_b["sales_count"], 0)
        self.assertEqual(summary_b["total_revenue"], 0)
    
    def test_payment_mix_with_agent_scope(self):
        """
        Test that payment mix correctly filters by agent when provided.
        """
        # Create another user/agent
        agent2 = User.objects.create_user(
            username="agent2",
            email="agent2@example.com",
            password="testpass123"
        )
        
        from datetime import time
        today = timezone.localdate()
        today_midday = timezone.make_aware(
            timezone.datetime.combine(today, time(12, 0))
        )
        
        # Create sale by agent2 for Business A
        ClothingSale.objects.create(
            business=self.business_a,
            product=self.product_a,
            quantity=1,
            unit_price=Decimal("10000.00"),
            total_price=Decimal("10000.00"),
            unit_cost=Decimal("5000.00"),
            total_cost=Decimal("5000.00"),
            payment_method=PaymentMethod.MOBILE_MONEY,
            sold_by=agent2,
            sold_at=today_midday
        )
        
        # Get payment mix for Business A, scoped to self.user
        mix_user = get_payment_mix(
            business=self.business_a,
            start_date=today,
            end_date=today,  # Inclusive (helper handles range)
            user=self.user,  # Filter by agent
            vertical=BusinessKind.CLOTHING
        )
        
        # Should only show self.user's sale (Bank)
        self.assertEqual(len(mix_user), 1)
        self.assertEqual(mix_user[0]["method_code"], PaymentMethod.BANK)
        
        # Get payment mix for Business A, scoped to agent2
        mix_agent2 = get_payment_mix(
            business=self.business_a,
            start_date=today,
            end_date=today,  # Inclusive (helper handles range)
            user=agent2,  # Filter by agent
            vertical=BusinessKind.CLOTHING
        )
        
        # Should only show agent2's sale (Mobile Money)
        self.assertEqual(len(mix_agent2), 1)
        self.assertEqual(mix_agent2[0]["method_code"], PaymentMethod.MOBILE_MONEY)


@pytest.mark.django_db
class TestDashboardViewIsolation(TestCase):
    """
    Integration tests for dashboard views to ensure proper business scoping.
    """
    
    def setUp(self):
        """Setup test data."""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        self.business_a = Business.objects.create(
            name="Business A",
            slug="business-a-test",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE"
        )
        
        self.business_b = Business.objects.create(
            name="Business B",
            slug="business-b-test",
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status="ACTIVE"
        )
    
    def test_dashboard_view_requires_active_business(self):
        """
        Test that dashboard views properly use the active business from request.
        
        This ensures the @require_business decorator works correctly.
        """
        from inventory.verticals.clothing import dashboard
        
        # Create mock request with business_a
        request_a = self.factory.get('/verticals/clothing/dashboard/')
        request_a.user = self.user
        request_a.business = self.business_a
        
        # Dashboard should not crash and should use business_a
        response = dashboard(request_a)
        self.assertEqual(response.status_code, 200)
        
        # Create mock request with business_b
        request_b = self.factory.get('/verticals/clothing/dashboard/')
        request_b.user = self.user
        request_b.business = self.business_b
        
        # Dashboard should use business_b (different from business_a)
        response = dashboard(request_b)
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

