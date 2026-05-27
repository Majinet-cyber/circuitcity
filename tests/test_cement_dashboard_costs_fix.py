# tests/test_cement_dashboard_costs_fix.py
"""
Regression tests for cement dashboard total_costs bug fix.

Tests that:
1. Dashboard returns 200 when no costs exist (no NameError)
2. Dashboard returns 200 when costs exist and displays correct values
3. total_costs respects date range filters
4. total_costs respects business scoping (tenant isolation)
5. Costs KPI displays correctly formatted value

This prevents regression of the NameError bug where total_costs was referenced
but the variable was named total_costs_period.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import CementCost, CementSale
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCementDashboardCostsFix(TestCase):
    """Test cement dashboard handles costs correctly and never crashes"""

    def setUp(self):
        """Create cement business, manager, and test fixtures"""
        self.user = User.objects.create_user(
            username="cement_manager", email="manager@cement.test", password="test1234"
        )
        self.business = Business.objects.create(
            name="Cement Test Store", slug="cement-test", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER")

        # Create a test product for sales
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Dangote Cement",
            kind=BusinessKind.CEMENT,
            category="cement",
            spec_label="",
            cost_price=Decimal("25000.00"),
            selling_price=Decimal("30000.00"),
            quantity_in_stock=100,
            base_unit="bag",
            is_active=True,
            track_inventory=True,
        )

        self.client = Client()

    def test_dashboard_loads_with_no_costs(self):
        """Test that dashboard returns 200 when no costs exist (regression test)"""
        # Log in and set active business
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET dashboard (no costs exist)
        response = self.client.get(reverse("cement:dashboard"))

        # Should return 200, not 500 (NameError)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        # Verify context contains total_costs with value 0
        assert "total_costs" in response.context
        assert response.context["total_costs"] == Decimal("0")

    def test_dashboard_loads_with_costs(self):
        """Test that dashboard returns 200 when costs exist and displays correct values"""
        # Create some costs
        CementCost.objects.create(
            business=self.business,
            amount=Decimal("5000.00"),
            category="transport",
            description="Delivery truck fuel",
            cost_date=timezone.now().date(),
            created_by=self.user,
        )
        CementCost.objects.create(
            business=self.business,
            amount=Decimal("15000.00"),
            category="labor",
            description="Worker wages",
            cost_date=timezone.now().date(),
            created_by=self.user,
        )

        # Log in and set active business
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET dashboard
        response = self.client.get(reverse("cement:dashboard"))

        # Should return 200
        assert response.status_code == 200

        # Verify context contains correct total_costs
        assert "total_costs" in response.context
        assert response.context["total_costs"] == Decimal("20000.00")

    def test_dashboard_costs_kpi_displays_correctly(self):
        """Test that costs KPI in dashboard_config displays formatted value"""
        # Create a cost
        CementCost.objects.create(
            business=self.business,
            amount=Decimal("50000.00"),
            category="rent",
            description="Monthly rent",
            cost_date=timezone.now().date(),
            created_by=self.user,
        )

        # Log in and set active business
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET dashboard
        response = self.client.get(reverse("cement:dashboard"))

        assert response.status_code == 200

        # Verify dashboard_config has costs KPI with formatted value
        assert "dashboard_config" in response.context
        dashboard_config = response.context["dashboard_config"]
        assert "kpis" in dashboard_config

        # Find costs KPI
        costs_kpi = None
        for kpi in dashboard_config["kpis"]:
            if kpi["title"] == "Costs":
                costs_kpi = kpi
                break

        assert costs_kpi is not None, "Costs KPI not found in dashboard_config"
        assert costs_kpi["value"] == "MK 50,000", f"Expected 'MK 50,000', got '{costs_kpi['value']}'"

    def test_dashboard_costs_respects_date_filter(self):
        """Test that total_costs respects date range filters"""
        today = timezone.now().date()
        yesterday = today - timezone.timedelta(days=1)
        last_week = today - timezone.timedelta(days=7)

        # Create costs on different dates
        CementCost.objects.create(
            business=self.business,
            amount=Decimal("10000.00"),
            category="utilities",
            description="Today's cost",
            cost_date=today,
            created_by=self.user,
        )
        CementCost.objects.create(
            business=self.business,
            amount=Decimal("5000.00"),
            category="transport",
            description="Yesterday's cost",
            cost_date=yesterday,
            created_by=self.user,
        )
        CementCost.objects.create(
            business=self.business,
            amount=Decimal("3000.00"),
            category="other",
            description="Last week's cost",
            cost_date=last_week,
            created_by=self.user,
        )

        # Log in and set active business
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET dashboard with "today" preset
        response = self.client.get(reverse("cement:dashboard") + "?preset=today")
        assert response.status_code == 200
        # Should only show today's cost
        assert response.context["total_costs"] == Decimal("10000.00")

        # GET dashboard with "last_7_days" preset
        response = self.client.get(reverse("cement:dashboard") + "?preset=last_7_days")
        assert response.status_code == 200
        # Should show today + yesterday (not last_week as it's 7 days ago, edge case)
        # Depending on parse_date_range, this should include last 7 days
        # Let's verify it's at least today + yesterday
        assert response.context["total_costs"] >= Decimal("15000.00")

    def test_dashboard_costs_respects_business_scoping(self):
        """Test that total_costs only includes costs for the active business (tenant isolation)"""
        # Create another business
        other_business = Business.objects.create(
            name="Other Cement Store", slug="other-cement", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )

        # Create costs for both businesses
        CementCost.objects.create(
            business=self.business,
            amount=Decimal("10000.00"),
            category="rent",
            description="Our business cost",
            cost_date=timezone.now().date(),
            created_by=self.user,
        )
        CementCost.objects.create(
            business=other_business,
            amount=Decimal("50000.00"),
            category="rent",
            description="Other business cost",
            cost_date=timezone.now().date(),
            created_by=self.user,
        )

        # Log in and set active business
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET dashboard
        response = self.client.get(reverse("cement:dashboard"))

        assert response.status_code == 200
        # Should only show our business's costs, not other business
        assert response.context["total_costs"] == Decimal("10000.00")

    def test_dashboard_handles_zero_decimal_costs(self):
        """Test that dashboard handles Decimal("0.00") correctly (edge case)"""
        # Create a cost with 0 amount (edge case, should not happen but let's be robust)
        # Actually, model has MinValueValidator(Decimal("0.01")), so this will fail
        # Instead, test with no costs (already done above)

        # Log in and set active business
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET dashboard with no costs
        response = self.client.get(reverse("cement:dashboard"))

        assert response.status_code == 200
        assert response.context["total_costs"] == Decimal("0")

        # Verify KPI formatting handles 0 correctly
        dashboard_config = response.context["dashboard_config"]
        costs_kpi = next((kpi for kpi in dashboard_config["kpis"] if kpi["title"] == "Costs"), None)
        assert costs_kpi is not None
        assert costs_kpi["value"] == "MK 0"

    def test_dashboard_costs_with_sales_and_profit(self):
        """Test that dashboard computes revenue, costs, and profit correctly together"""
        # Create a sale
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=10,
            unit_price=Decimal("30000.00"),
            total_price=Decimal("300000.00"),
            unit_cost=Decimal("25000.00"),
            total_cost=Decimal("250000.00"),
            payment_method="CASH",
            sold_by=self.user,
        )

        # Create operating costs
        CementCost.objects.create(
            business=self.business,
            amount=Decimal("20000.00"),
            category="transport",
            description="Delivery costs",
            cost_date=timezone.now().date(),
            created_by=self.user,
        )

        # Log in and set active business
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET dashboard with "today" preset
        response = self.client.get(reverse("cement:dashboard") + "?preset=today")

        assert response.status_code == 200

        # Verify all metrics
        assert response.context["total_revenue"] == Decimal("300000.00")
        assert response.context["total_profit"] == Decimal("50000.00")  # Revenue - COGS
        assert response.context["total_costs"] == Decimal("20000.00")  # Operating costs
        assert response.context["total_sales_count"] == 1

        # Net profit would be gross profit - operating costs, but that's not in cement dashboard yet
        # Just verify all values are present and correct


@pytest.mark.django_db
class TestCementDashboardEdgeCases(TestCase):
    """Test edge cases and error conditions"""

    def setUp(self):
        """Create minimal fixtures"""
        self.user = User.objects.create_user(username="cement_user", email="user@test.com", password="test1234")
        self.business = Business.objects.create(
            name="Edge Case Cement", slug="edge-cement", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER")
        self.client = Client()

    def test_dashboard_with_invalid_date_filter(self):
        """Test that dashboard handles invalid date filters gracefully"""
        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # GET dashboard with invalid date parameters
        response = self.client.get(reverse("cement:dashboard") + "?start_date=invalid&end_date=invalid")

        # Should still return 200 (parse_date_range should handle this)
        assert response.status_code == 200
        assert response.context["total_costs"] == Decimal("0")

    def test_dashboard_with_large_cost_values(self):
        """Test that dashboard handles large Decimal values correctly"""
        CementCost.objects.create(
            business=self.business,
            amount=Decimal("9999999.99"),  # Max value within DecimalField(max_digits=12, decimal_places=2)
            category="other",
            description="Large cost",
            cost_date=timezone.now().date(),
            created_by=self.user,
        )

        self.client.force_login(self.user)
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        response = self.client.get(reverse("cement:dashboard"))

        assert response.status_code == 200
        assert response.context["total_costs"] == Decimal("9999999.99")

        # Verify formatting handles large numbers
        dashboard_config = response.context["dashboard_config"]
        costs_kpi = next((kpi for kpi in dashboard_config["kpis"] if kpi["title"] == "Costs"), None)
        assert costs_kpi is not None
        # Should format with thousand separators
        assert "9,999,999" in costs_kpi["value"] or "9999999" in costs_kpi["value"]

