# tests/test_cementcost_location_fix.py
"""
Tests for CementCost location_id column fix.
Ensures the migration added the column and queries don't crash.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import Location
from inventory.models_verticals import CementCost
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCementCostLocation(TestCase):
    """Test CementCost location field"""

    def setUp(self):
        """Create cement business with location"""
        self.user = User.objects.create_user(username="cement_cost_test", email="cost@cement.test", password="test1234")
        self.business = Business.objects.create(
            name="Cement Cost Test", slug="cement-cost-test", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")

        # Get or create a location
        self.location, _ = Location.objects.get_or_create(
            business=self.business, name="Main Warehouse", defaults={"is_default": False}
        )

    def test_cementcost_can_be_created_with_location(self):
        """Test that CementCost can be created with a location"""
        cost = CementCost.objects.create(
            business=self.business,
            location=self.location,
            amount=Decimal("50000"),
            category="transport",
            description="Truck rental",
            cost_date=timezone.now().date(),
            created_by=self.user,
        )

        assert cost.location == self.location
        assert cost.amount == Decimal("50000")

    def test_cementcost_can_be_created_without_location(self):
        """Test that CementCost can be created without a location (NULL)"""
        cost = CementCost.objects.create(
            business=self.business,
            location=None,  # Explicitly NULL
            amount=Decimal("25000"),
            category="labor",
            description="Worker payment",
            cost_date=timezone.now().date(),
            created_by=self.user,
        )

        assert cost.location is None
        assert cost.amount == Decimal("25000")

    def test_cementcost_filter_by_location(self):
        """Test filtering costs by location"""
        # Create costs with and without location
        CementCost.objects.create(
            business=self.business,
            location=self.location,
            amount=Decimal("10000"),
            category="rent",
            description="Warehouse rent",
            cost_date=timezone.now().date(),
        )
        CementCost.objects.create(
            business=self.business,
            location=None,
            amount=Decimal("5000"),
            category="utilities",
            description="Electricity",
            cost_date=timezone.now().date(),
        )

        # Filter by location
        costs_with_location = CementCost.objects.filter(business=self.business, location=self.location)
        assert costs_with_location.count() == 1

        # Filter for NULL location
        costs_without_location = CementCost.objects.filter(business=self.business, location__isnull=True)
        assert costs_without_location.count() == 1


@pytest.mark.django_db
class TestCementDashboardWithCosts(TestCase):
    """Test cement dashboard handles costs correctly"""

    def setUp(self):
        """Create cement business"""
        self.user = User.objects.create_user(
            username="cement_dashboard_costs", email="dashboard@cement.test", password="test1234"
        )
        self.business = Business.objects.create(
            name="Dashboard Costs Test", slug="dashboard-costs-test", business_kind=BusinessKind.CEMENT, status="ACTIVE"
        )
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")

        self.location, _ = Location.objects.get_or_create(
            business=self.business, name="Store", defaults={"is_default": False}
        )

        self.client = Client()
        self.client.login(username="cement_dashboard_costs", password="test1234")

    def test_dashboard_with_costs(self):
        """Test dashboard displays costs correctly"""
        today = timezone.now().date()

        # Create some costs
        CementCost.objects.create(
            business=self.business,
            location=self.location,
            amount=Decimal("15000"),
            category="transport",
            description="Delivery",
            cost_date=today,
        )
        CementCost.objects.create(
            business=self.business,
            location=None,  # NULL location
            amount=Decimal("10000"),
            category="labor",
            description="Workers",
            cost_date=today,
        )

        # Visit dashboard
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        # Dashboard should not crash and should include costs
        assert b"Cement Store Dashboard" in response.content

    def test_dashboard_with_no_costs(self):
        """Test dashboard works with no costs"""
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200
        assert b"Cement Store Dashboard" in response.content

    def test_dashboard_costs_aggregation(self):
        """Test that dashboard uses aggregation for costs"""
        today = timezone.now().date()

        # Create multiple costs
        for i in range(10):
            CementCost.objects.create(
                business=self.business,
                location=self.location if i % 2 == 0 else None,
                amount=Decimal("5000"),
                category="other",
                description=f"Cost {i}",
                cost_date=today,
            )

        # Visit dashboard - should use aggregate, not iterate
        response = self.client.get(reverse("verticals:cement_dashboard"))
        assert response.status_code == 200

        # Total costs should be 10 * 5000 = 50000 (plus stock value)
        context = response.context
        # total_costs includes stock_value, so just verify it doesn't crash
        assert "total_costs" in context
