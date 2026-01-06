"""
Test cement costs view (/cement/costs/).

This test ensures:
1. GET /cement/costs/ loads without database errors
2. POST creates a new cost entry with created_by field
3. No regressions with created_by_id, category, or notes columns
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from inventory.models_verticals import CementCost
from tenants.models import Business, Location, Membership

User = get_user_model()


class CementCostsViewTest(TestCase):
    """Test /cement/costs/ view (GET and POST)"""

    def setUp(self):
        """Set up test user and business"""
        self.business = Business.objects.create(
            name="Test Hardware Store",
            slug="test-hardware",
            business_kind=BusinessKind.CEMENT,
            status="ACTIVE",
            currency="MWK",
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Branch",
        )
        self.user = User.objects.create_user(username="testuser", password="testpass123", is_staff=True)
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            location=None,  # Managers don't have specific locations
            role="MANAGER",
            status="ACTIVE",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_costs_page_loads_without_error(self):
        """Test that GET /cement/costs/ returns 200 OK"""
        # Create some existing costs
        cost1 = CementCost.objects.create(
            business=self.business,
            cost_type="operating",
            amount=Decimal("5000.00"),
            category="transport",
            description="Truck hire",
            notes="Delivery to site A",
            created_by=self.user,
        )
        cost2 = CementCost.objects.create(
            business=self.business,
            cost_type="operating",
            amount=Decimal("2500.00"),
            category="labor",
            description="Daily wages",
            notes="3 workers",
            created_by=self.user,
        )

        # Try to load the costs page
        response = self.client.get(reverse("verticals:cement_costs"))

        # Should return 200 OK, not crash with OperationalError
        self.assertEqual(response.status_code, 200)

        # Should contain the costs we created
        self.assertContains(response, "Truck hire")
        self.assertContains(response, "Daily wages")

        # Verify the costs are in the context (more reliable than checking HTML formatting)
        self.assertIn("costs", response.context)
        costs_list = list(response.context["costs"])
        self.assertEqual(len(costs_list), 2)
        self.assertIn(cost1, costs_list)
        self.assertIn(cost2, costs_list)

    def test_costs_page_with_no_data(self):
        """Test that GET /cement/costs/ works even with no costs"""
        response = self.client.get(reverse("verticals:cement_costs"))
        self.assertEqual(response.status_code, 200)

    def test_create_cost_via_post(self):
        """Test that POST creates a new cost entry with created_by and cost_type"""
        initial_count = CementCost.objects.count()

        # POST a new cost with explicit cost_type
        response = self.client.post(
            reverse("verticals:cement_costs"),
            {
                "cost_type": "operating",
                "amount": "3500.50",
                "category": "utilities",
                "description": "Electricity bill",
                "cost_date": "2026-01-06",
                "notes": "Monthly payment",
            },
        )

        # Should redirect after successful creation (or 200 if error)
        if response.status_code != 302:
            print(f"Response status: {response.status_code}")
            print(f"Response content: {response.content[:500]}")

        self.assertEqual(response.status_code, 302)

        # Verify cost was created
        self.assertEqual(CementCost.objects.count(), initial_count + 1)

        # Verify cost fields
        cost = CementCost.objects.latest("created_at")
        self.assertEqual(cost.cost_type, "operating")
        self.assertEqual(cost.amount, Decimal("3500.50"))
        self.assertEqual(cost.category, "utilities")
        self.assertEqual(cost.description, "Electricity bill")
        self.assertEqual(cost.notes, "Monthly payment")

        # CRITICAL: Verify created_by is set correctly
        self.assertEqual(cost.created_by, self.user)
        self.assertIsNotNone(cost.created_by_id)

    def test_create_cost_without_optional_fields(self):
        """Test that POST works with minimal fields (notes is optional)"""
        response = self.client.post(
            reverse("verticals:cement_costs"),
            {
                "cost_type": "other",
                "amount": "1500.00",
                "category": "other",
                "description": "Miscellaneous",
                "cost_date": "2026-01-06",
                "notes": "",  # Empty notes
            },
        )

        self.assertEqual(response.status_code, 302)

        # Verify cost was created with empty notes
        cost = CementCost.objects.latest("created_at")
        self.assertEqual(cost.cost_type, "other")
        self.assertEqual(cost.description, "Miscellaneous")
        self.assertEqual(cost.notes, "")
        self.assertEqual(cost.created_by, self.user)

    def test_post_cost_without_cost_type_defaults_operating(self):
        """Test that POST without cost_type defaults to 'operating'"""
        response = self.client.post(
            reverse("verticals:cement_costs"),
            {
                # No cost_type provided
                "amount": "2000.00",
                "category": "transport",
                "description": "Fuel",
                "cost_date": "2026-01-06",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        # Verify cost was created with default cost_type
        cost = CementCost.objects.latest("created_at")
        self.assertEqual(cost.cost_type, "operating")  # Should default to operating
        self.assertEqual(cost.description, "Fuel")

    def test_post_cost_with_cogs_type(self):
        """Test that POST with cost_type='cogs' is saved correctly"""
        response = self.client.post(
            reverse("verticals:cement_costs"),
            {
                "cost_type": "cogs",
                "amount": "5000.00",
                "category": "other",
                "description": "Inventory purchase",
                "cost_date": "2026-01-06",
                "notes": "Stock replenishment",
            },
        )

        self.assertEqual(response.status_code, 302)

        # Verify cost was created with cogs type
        cost = CementCost.objects.latest("created_at")
        self.assertEqual(cost.cost_type, "cogs")
        self.assertEqual(cost.description, "Inventory purchase")

    def test_costs_page_shows_category_totals(self):
        """Test that costs page calculates category totals correctly"""
        # Create costs in different categories
        CementCost.objects.create(
            business=self.business,
            cost_type="operating",
            amount=Decimal("1000.00"),
            category="transport",
            description="Trip 1",
            created_by=self.user,
        )
        CementCost.objects.create(
            business=self.business,
            cost_type="operating",
            amount=Decimal("2000.00"),
            category="transport",
            description="Trip 2",
            created_by=self.user,
        )
        CementCost.objects.create(
            business=self.business,
            cost_type="operating",
            amount=Decimal("500.00"),
            category="labor",
            description="Helper",
            created_by=self.user,
        )

        response = self.client.get(reverse("verticals:cement_costs"))

        self.assertEqual(response.status_code, 200)

        # Verify totals are calculated
        self.assertIn("category_totals", response.context)
        self.assertIn("total_costs", response.context)

        # Total should be 3500
        self.assertEqual(response.context["total_costs"], Decimal("3500.00"))

    def test_costs_list_ordered_by_date(self):
        """Test that costs are ordered by date (newest first)"""
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.now().date()
        yesterday = today - timedelta(days=1)

        # Create costs with different dates
        old_cost = CementCost.objects.create(
            business=self.business,
            cost_type="operating",
            amount=Decimal("1000.00"),
            category="transport",
            description="Old cost",
            cost_date=yesterday,
            created_by=self.user,
        )
        new_cost = CementCost.objects.create(
            business=self.business,
            cost_type="operating",
            amount=Decimal("2000.00"),
            category="transport",
            description="New cost",
            cost_date=today,
            created_by=self.user,
        )

        response = self.client.get(reverse("verticals:cement_costs"))

        # New cost should appear first
        costs = list(response.context["costs"])
        self.assertEqual(costs[0].id, new_cost.id)
        self.assertEqual(costs[1].id, old_cost.id)
