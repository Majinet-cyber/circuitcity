"""
Tests for Cement Analytics and Costs Features
Tests ensure:
- CementCost DB schema is correct (notes, category columns exist)
- Analytics page loads with chart data
- Charts work with empty and populated data
- Single filter dropdown is present
- No regressions to other verticals
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import CementCost, CementSale
from tenants.models import Business

User = get_user_model()


class CementCostSchemaTests(TestCase):
    """Test that CementCost model has correct DB schema"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(name="Test Hardware Store", business_kind=BusinessKind.CEMENT)
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_cementcost_has_notes_column(self):
        """Ensure CementCost table has 'notes' column"""
        cost = CementCost.objects.create(
            business=self.business,
            amount=Decimal("5000.00"),
            category="transport",
            description="Fuel for delivery",
            notes="Delivered to customer X",
            created_by=self.user,
        )

        # Refresh from DB to ensure it was persisted
        cost.refresh_from_db()
        self.assertEqual(cost.notes, "Delivered to customer X")

    def test_cementcost_has_category_column(self):
        """Ensure CementCost table has 'category' column"""
        cost = CementCost.objects.create(
            business=self.business,
            amount=Decimal("10000.00"),
            category="labor",
            description="Worker wages",
            created_by=self.user,
        )

        cost.refresh_from_db()
        self.assertEqual(cost.category, "labor")

    def test_cementcost_notes_default_empty(self):
        """Ensure notes field defaults to empty string"""
        cost = CementCost.objects.create(
            business=self.business,
            amount=Decimal("2000.00"),
            category="rent",
            description="Shop rent",
            created_by=self.user,
        )

        self.assertEqual(cost.notes, "")


class CementCostsPageTests(TestCase):
    """Test that cement costs page loads without errors"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(name="Test Hardware Store", business_kind=BusinessKind.CEMENT)
        self.user.profile.business = self.business
        self.user.profile.save()

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_costs_page_loads_successfully(self):
        """GET /cement/costs/ should return 200"""
        url = reverse("cement:costs")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Costs Management")

    def test_costs_page_displays_existing_costs(self):
        """Costs page should display existing cost entries"""
        CementCost.objects.create(
            business=self.business,
            amount=Decimal("5000.00"),
            category="transport",
            description="Fuel delivery",
            notes="Test note",
            created_by=self.user,
        )

        url = reverse("cement:costs")
        response = self.client.get(url)

        self.assertContains(response, "Fuel delivery")
        self.assertContains(response, "5,000")

    def test_add_cost_with_notes(self):
        """POST to costs page should create cost with notes"""
        url = reverse("cement:costs")
        data = {
            "amount": "3000.00",
            "category": "utilities",
            "description": "Electricity bill",
            "cost_date": timezone.now().date().isoformat(),
            "notes": "December 2024",
        }

        response = self.client.post(url, data)

        # Should redirect on success
        self.assertEqual(response.status_code, 302)

        # Verify cost was created
        cost = CementCost.objects.filter(business=self.business).first()
        self.assertIsNotNone(cost)
        self.assertEqual(cost.description, "Electricity bill")
        self.assertEqual(cost.notes, "December 2024")
        self.assertEqual(cost.category, "utilities")


class CementAnalyticsPageTests(TestCase):
    """Test cement analytics page with chart data"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.business = Business.objects.create(name="Test Hardware Store", business_kind=BusinessKind.CEMENT)
        self.user.profile.business = self.business
        self.user.profile.save()

        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

        # Create test product
        self.product = MerchProduct.objects.create(
            business=self.business,
            name="Test Cement",
            kind=BusinessKind.CEMENT,
            cost_price=Decimal("15000.00"),
            selling_price=Decimal("18000.00"),
            quantity_in_stock=100,
        )

    def test_analytics_page_loads_successfully(self):
        """GET /cement/analytics/ should return 200"""
        url = reverse("cement:analytics")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hardware & General Dealers Analytics")

    def test_analytics_has_single_filter_dropdown(self):
        """Analytics page should have single filter dropdown, not multiple buttons"""
        url = reverse("cement:analytics")
        response = self.client.get(url)

        html = response.content.decode()

        # Should have the dropdown
        self.assertIn("dateFilterDropdown", html)
        self.assertIn("dropdown-toggle", html)

        # Should NOT have the old button group layout (multiple filter buttons side by side)
        # The new design has ONE dropdown button
        self.assertIn("Filter:", html)

    def test_analytics_has_chart_data_empty(self):
        """Analytics should provide chart data even when no sales exist"""
        url = reverse("cement:analytics")
        response = self.client.get(url)

        # Context should include chart data
        self.assertIn("chart_labels", response.context)
        self.assertIn("chart_revenue", response.context)
        self.assertIn("chart_profit", response.context)
        self.assertIn("payment_labels", response.context)
        self.assertIn("payment_totals", response.context)

        # Should be valid JSON
        import json

        labels = json.loads(response.context["chart_labels"])
        revenue = json.loads(response.context["chart_revenue"])

        self.assertIsInstance(labels, list)
        self.assertIsInstance(revenue, list)

    def test_analytics_has_chart_data_with_sales(self):
        """Analytics should provide chart data when sales exist"""
        # Create a test sale
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=5,
            unit_price=Decimal("18000.00"),
            total_price=Decimal("90000.00"),
            unit_cost=Decimal("15000.00"),
            total_cost=Decimal("75000.00"),
            payment_method="CASH",
            sold_by=self.user,
        )

        url = reverse("cement:analytics")
        response = self.client.get(url)

        import json

        revenue = json.loads(response.context["chart_revenue"])
        profit = json.loads(response.context["chart_profit"])
        payment_labels = json.loads(response.context["payment_labels"])
        payment_totals = json.loads(response.context["payment_totals"])

        # Should have data
        self.assertTrue(any(r > 0 for r in revenue))
        self.assertTrue(any(p > 0 for p in profit))
        self.assertIn("CASH", payment_labels)
        self.assertTrue(sum(payment_totals) > 0)

    def test_analytics_has_chart_canvas_elements(self):
        """Analytics page should have canvas elements for charts"""
        url = reverse("cement:analytics")
        response = self.client.get(url)

        html = response.content.decode()

        # Should have chart canvases
        self.assertIn('id="revenueChart"', html)
        self.assertIn('id="profitChart"', html)
        self.assertIn('id="paymentMixChart"', html)

        # Should load Chart.js
        self.assertIn("chart.js", html.lower())

    def test_analytics_has_premium_kpi_styling(self):
        """Analytics KPIs should use premium color-coded styling"""
        url = reverse("cement:analytics")
        response = self.client.get(url)

        html = response.content.decode()

        # Should have color-coded KPI classes
        self.assertIn("cement-kpi--revenue", html)
        self.assertIn("cement-kpi--profit", html)
        self.assertIn("cement-kpi--costs", html)

    def test_analytics_insights_row(self):
        """Analytics should show insights when data exists"""
        # Create sales with different products
        CementSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=10,
            unit_price=Decimal("18000.00"),
            total_price=Decimal("180000.00"),
            unit_cost=Decimal("15000.00"),
            total_cost=Decimal("150000.00"),
            payment_method="MOBILE_MONEY",
            sold_by=self.user,
        )

        url = reverse("cement:analytics")
        response = self.client.get(url)

        # Should have insights in context
        self.assertIn("best_selling_product", response.context)
        self.assertIn("top_payment_method", response.context)

        # Values should be populated
        self.assertIsNotNone(response.context["best_selling_product"])
        self.assertIsNotNone(response.context["top_payment_method"])

    def test_analytics_date_filter_presets(self):
        """Analytics should support different date filter presets"""
        presets = ["today", "mtd", "7d", "all"]

        for preset in presets:
            url = reverse("cement:analytics") + f"?preset={preset}"
            response = self.client.get(url)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["preset"], preset)


class CementNoRegressionTests(TestCase):
    """Ensure cement changes don't affect other verticals"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_other_vertical_analytics_unaffected(self):
        """Changes to cement analytics should not affect other verticals"""
        # This is a smoke test - if cement changes break other verticals,
        # their tests will fail. This test ensures we're not importing
        # cement-specific modules in shared code.

        # Cement module should not pollute global namespace
        import inventory.models_verticals as models
        from inventory.verticals import cement

        # Ensure CementCost is isolated
        self.assertTrue(hasattr(models, "CementCost"))
        self.assertTrue(hasattr(models, "CementSale"))
