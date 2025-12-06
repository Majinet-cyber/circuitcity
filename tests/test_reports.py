# tests/test_reports.py
"""
Django regression tests for reports functionality.

Tests:
- /reports/ loads successfully (no NoReverseMatch)
- Context contains expected metrics (report_summary, report_trend_json, payment_mix_json)
- Net profit calculation is correct
- URL name 'reports:sales' exists and doesn't break
- Monthly metrics calculations are accurate
"""

import json
from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from sales.models import Sale
from inventory.models import InventoryItem, Product
from wallet.models import WalletTransaction, TxnType, Ledger
from tenants.models import Business, Location

User = get_user_model()


class ReportsHomeTestCase(TestCase):
    """Test reports home page with monthly business overview."""

    def setUp(self):
        """Set up test data: business, products, sales, costs, commissions."""
        # Create test business
        self.business = Business.objects.create(
            name="Test Phone Shop",
            kind="phones",
            is_active=True,
        )

        # Create test location
        self.location = Location.objects.create(
            name="Main Branch",
            business=self.business,
        )

        # Create test user (manager)
        self.user = User.objects.create_user(
            username="testmanager",
            email="manager@test.com",
            password="testpass123",
            is_staff=True,
        )

        # Create test product
        self.product = Product.objects.create(
            code="TECNO-POP10-128",
            name="TECNO Pop 10",
            brand="TECNO",
            model="Pop 10",
            variant="4+128",
            cost_price=Decimal("50000.00"),
        )

        # Create inventory items
        self.item1 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012345",
            status="SOLD",
        )

        self.item2 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012346",
            status="SOLD",
        )

        # Create sales with payment methods
        today = date.today()
        self.sale1 = Sale.objects.create(
            item=self.item1,
            agent=self.user,
            location=self.location,
            sold_at=today,
            price=Decimal("75000.00"),
            commission_pct=Decimal("12.00"),
            payment_method="CASH",
        )

        self.sale2 = Sale.objects.create(
            item=self.item2,
            agent=self.user,
            location=self.location,
            sold_at=today,
            price=Decimal("80000.00"),
            commission_pct=Decimal("12.00"),
            payment_method="BANK",
        )

        # Create costs
        self.cost = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-10000.00"),  # Costs are negative
            note="Test rent",
            effective_date=today,
            created_by=self.user,
        )

        # Create commissions (these should be calculated from sales)
        self.commission1 = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.AGENT,
            agent=self.user,
            type=TxnType.COMMISSION,
            amount=Decimal("9000.00"),  # 12% of 75000
            note="Commission for sale #1",
            effective_date=today,
            created_by=self.user,
        )

        self.commission2 = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.AGENT,
            agent=self.user,
            type=TxnType.COMMISSION,
            amount=Decimal("9600.00"),  # 12% of 80000
            note="Commission for sale #2",
            effective_date=today,
            created_by=self.user,
        )

        # Set up client with session
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_reports_home_loads_successfully(self):
        """Test that /reports/ loads with HTTP 200 and no template errors."""
        response = self.client.get(reverse('reports:home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'NoReverseMatch')
        self.assertNotContains(response, '500 Internal Server Error')
        self.assertNotContains(response, 'TemplateDoesNotExist')

    def test_reports_home_context_contains_expected_metrics(self):
        """Test that reports_home context includes all required metrics."""
        response = self.client.get(reverse('reports:home'))
        
        self.assertEqual(response.status_code, 200)
        
        # Check context variables exist
        self.assertIn('report_summary', response.context)
        self.assertIn('report_trend_json', response.context)
        self.assertIn('payment_mix_json', response.context)
        
        # Verify summary structure
        summary = response.context['report_summary']
        self.assertIn('total_revenue', summary)
        self.assertIn('total_costs', summary)
        self.assertIn('total_commissions', summary)
        self.assertIn('gross_profit', summary)
        self.assertIn('net_profit', summary)

    def test_reports_metrics_calculations(self):
        """Test that revenue, costs, and profit calculations are correct."""
        response = self.client.get(reverse('reports:home'))
        summary = response.context['report_summary']
        
        # Expected values
        expected_revenue = float(Decimal("75000.00") + Decimal("80000.00"))  # 155000
        expected_cogs = float(Decimal("50000.00") + Decimal("50000.00"))     # 100000
        expected_costs = float(Decimal("10000.00"))                          # 10000
        expected_commissions = float(Decimal("9000.00") + Decimal("9600.00"))  # 18600
        expected_gross_profit = expected_revenue - expected_cogs              # 55000
        expected_net_profit = expected_gross_profit - expected_costs - expected_commissions  # 26400
        
        # Assert calculations
        self.assertEqual(summary['total_revenue'], expected_revenue)
        self.assertAlmostEqual(summary['total_costs'], expected_costs, places=2)
        self.assertAlmostEqual(summary['total_commissions'], expected_commissions, places=2)
        self.assertAlmostEqual(summary['gross_profit'], expected_gross_profit, places=2)
        self.assertAlmostEqual(summary['net_profit'], expected_net_profit, places=2)

    def test_payment_mix_json(self):
        """Test that payment mix JSON contains correct data."""
        response = self.client.get(reverse('reports:home'))
        payment_mix_str = response.context['payment_mix_json']
        payment_mix = json.loads(payment_mix_str)
        
        # Should have 2 payment methods (CASH and BANK)
        self.assertGreaterEqual(len(payment_mix), 2)
        
        # Find CASH and BANK entries
        cash_entry = next((p for p in payment_mix if p['method'] == 'CASH'), None)
        bank_entry = next((p for p in payment_mix if p['method'] == 'BANK'), None)
        
        self.assertIsNotNone(cash_entry)
        self.assertIsNotNone(bank_entry)
        
        # Verify amounts
        self.assertEqual(cash_entry['amount'], 75000.0)
        self.assertEqual(bank_entry['amount'], 80000.0)

    def test_report_trend_json(self):
        """Test that daily trend JSON is properly formatted."""
        response = self.client.get(reverse('reports:home'))
        trend_str = response.context['report_trend_json']
        trend = json.loads(trend_str)
        
        # Should have at least 1 day (today)
        self.assertGreater(len(trend), 0)
        
        # Check structure of first entry
        first_day = trend[0]
        self.assertIn('date', first_day)
        self.assertIn('revenue', first_day)
        self.assertIn('costs', first_day)
        self.assertIn('commissions', first_day)
        self.assertIn('net_profit', first_day)

    def test_top_products_and_agents(self):
        """Test that top products and agents are calculated."""
        response = self.client.get(reverse('reports:home'))
        
        self.assertIn('top_products', response.context)
        self.assertIn('top_agents', response.context)
        
        top_products = response.context['top_products']
        top_agents = response.context['top_agents']
        
        # Should have at least 1 product
        self.assertGreater(len(top_products), 0)
        
        # Should have at least 1 agent
        self.assertGreater(len(top_agents), 0)
        
        # Check agent data
        top_agent = top_agents[0]
        self.assertIn('name', top_agent)
        self.assertIn('revenue', top_agent)
        self.assertIn('count', top_agent)
        self.assertIn('commission', top_agent)


class ReportsURLTestCase(TestCase):
    """Test that reports URL patterns are correctly configured."""

    def setUp(self):
        """Create test user."""
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
            is_staff=True,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_sales_url_exists(self):
        """Test that 'reports:sales' URL name exists and doesn't throw NoReverseMatch."""
        try:
            url = reverse('reports:sales')
            self.assertIsNotNone(url)
            self.assertIn('/reports/sales/', url)
        except Exception as e:
            self.fail(f"reverse('reports:sales') raised {type(e).__name__}: {e}")

    def test_inventory_url_exists(self):
        """Test that 'reports:inventory' URL name exists."""
        try:
            url = reverse('reports:inventory')
            self.assertIsNotNone(url)
            self.assertIn('/reports/inventory/', url)
        except Exception as e:
            self.fail(f"reverse('reports:inventory') raised {type(e).__name__}: {e}")

    def test_home_url_exists(self):
        """Test that 'reports:home' URL name exists."""
        try:
            url = reverse('reports:home')
            self.assertIsNotNone(url)
            self.assertEqual(url, '/reports/')
        except Exception as e:
            self.fail(f"reverse('reports:home') raised {type(e).__name__}: {e}")

    def test_sales_page_loads(self):
        """Test that /reports/sales/ loads successfully."""
        response = self.client.get(reverse('reports:sales'))
        self.assertEqual(response.status_code, 200)

    def test_inventory_page_loads(self):
        """Test that /reports/inventory/ loads successfully."""
        response = self.client.get(reverse('reports:inventory'))
        self.assertEqual(response.status_code, 200)


class ReportsExportTestCase(TestCase):
    """Test CSV export endpoints."""

    def setUp(self):
        """Set up test data for exports."""
        # Create test business
        self.business = Business.objects.create(
            name="Export Test Shop",
            kind="phones",
            is_active=True,
        )

        # Create test user
        self.user = User.objects.create_user(
            username="exportuser",
            password="testpass123",
            is_staff=True,
        )

        # Create test location
        self.location = Location.objects.create(
            name="Test Location",
            business=self.business,
        )

        # Create product and sale
        self.product = Product.objects.create(
            code="TEST-PRODUCT",
            name="Test Product",
            brand="TEST",
            model="Model X",
            variant="1+1",
            cost_price=Decimal("1000.00"),
        )

        self.item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="999999999999999",
            status="SOLD",
        )

        today = date.today()
        self.sale = Sale.objects.create(
            item=self.item,
            agent=self.user,
            location=self.location,
            sold_at=today,
            price=Decimal("2000.00"),
            commission_pct=Decimal("10.00"),
            payment_method="CASH",
        )

        # Create cost
        self.cost = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal("-500.00"),
            note="Export test cost",
            effective_date=today,
            created_by=self.user,
        )

        # Set up client
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()

    def test_export_monthly_sales(self):
        """Test /reports/export/sales/ returns CSV."""
        response = self.client.get(reverse('reports:export_monthly_sales'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        
        # Verify CSV contains data
        content = response.content.decode('utf-8')
        self.assertIn('date', content.lower())
        self.assertIn('product', content.lower())
        self.assertIn('payment_method', content.lower())

    def test_export_monthly_costs(self):
        """Test /reports/export/costs/ returns CSV."""
        response = self.client.get(reverse('reports:export_monthly_costs'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        
        # Verify CSV contains cost data
        content = response.content.decode('utf-8')
        self.assertIn('Export test cost', content)

    def test_export_monthly_summary(self):
        """Test /reports/export/summary/ returns CSV."""
        response = self.client.get(reverse('reports:export_monthly_summary'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        
        # Verify CSV structure
        content = response.content.decode('utf-8')
        self.assertIn('date', content.lower())
        self.assertIn('total_revenue', content.lower())
        self.assertIn('net_profit', content.lower())

    def test_export_with_custom_date_range(self):
        """Test exports with custom date range query params."""
        today = date.today()
        start = today - timedelta(days=7)
        end = today
        
        url = f"{reverse('reports:export_monthly_sales')}?start={start}&end={end}"
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')


class ReportsRegressionTestCase(TestCase):
    """Regression tests to prevent past bugs from reoccurring."""

    def setUp(self):
        """Set up minimal test data."""
        self.user = User.objects.create_user(
            username="regressionuser",
            password="testpass123",
            is_staff=True,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_no_reverse_match_for_sales(self):
        """
        Regression test: Ensure 'reports:sales' URL never throws NoReverseMatch.
        
        This was the original bug that broke /reports/ page.
        """
        try:
            url = reverse('reports:sales')
            response = self.client.get(url)
            self.assertNotEqual(response.status_code, 500)
            self.assertNotContains(response, 'NoReverseMatch', status_code=200)
        except Exception as e:
            self.fail(f"Regression detected: reverse('reports:sales') failed with {e}")

    def test_reports_home_template_renders(self):
        """Regression test: Ensure reports home template renders without errors."""
        response = self.client.get(reverse('reports:home'))
        
        # Should render successfully
        self.assertEqual(response.status_code, 200)
        
        # Should not have template errors
        self.assertNotContains(response, 'TemplateDoesNotExist')
        self.assertNotContains(response, 'NoReverseMatch')
        self.assertNotContains(response, 'KeyError')

    def test_empty_metrics_dont_crash(self):
        """Regression test: Empty metrics (no sales/costs) should not crash."""
        # No sales or costs created - metrics should default to zero
        response = self.client.get(reverse('reports:home'))
        
        self.assertEqual(response.status_code, 200)
        summary = response.context.get('report_summary', {})
        
        # Should have zero values, not crash
        self.assertEqual(summary.get('total_revenue', -1), 0.0)
        self.assertEqual(summary.get('net_profit', -1), 0.0)

