"""
Comprehensive tests for Phones Dashboard KPIs.

This test suite ensures:
1. Revenue KPI matches Payment Mix totals
2. Costs card breakdown (COGS + Business Costs) matches total
3. Profit = Revenue - Total Costs (always consistent)
4. Margin = (Profit / Revenue) * 100 (guards division by zero)
5. No regressions, page always returns 200
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business
from inventory.models import InventoryItem, Product, Location
from inventory.business_kinds import BusinessKind
from wallet.models import WalletTransaction, Ledger, TxnType

User = get_user_model()


class PhonesDashboardKPIsTestCase(TestCase):
    """Test suite for Phones Dashboard KPI computation and consistency."""
    
    def setUp(self):
        """Create test business, location, and user."""
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123',
            is_staff=True,
        )
        
        self.business = Business.objects.create(
            name='Test Phone Store',
            kind=BusinessKind.PHONES,
            is_active=True,
        )
        
        self.location = Location.objects.create(
            business=self.business,
            name='Main Branch',
            is_active=True,
        )
        
        # Assign user to business and location
        self.user.business = self.business
        self.user.location = self.location
        self.user.save()
        
        # Create test product
        self.product = Product.objects.create(
            business=self.business,
            brand='TestBrand',
            model='X100',
            variant='128GB',
            category='phones',
        )
        
        self.client = Client()
        self.client.login(username='testmanager', password='testpass123')
    
    def test_dashboard_loads_with_empty_data(self):
        """Dashboard should load successfully with no sales and show zeros."""
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check context has the expected keys
        self.assertIn('dashboard_kpis', response.context)
        kpis = response.context['dashboard_kpis']
        
        # All KPIs should be zero
        self.assertEqual(kpis['units_sold'], 0)
        self.assertEqual(kpis['revenue'], Decimal('0.00'))
        self.assertEqual(kpis['cost_of_goods'], Decimal('0.00'))
        self.assertEqual(kpis['business_costs'], Decimal('0.00'))
        self.assertEqual(kpis['total_costs'], Decimal('0.00'))
        self.assertEqual(kpis['profit'], Decimal('0.00'))
        self.assertEqual(kpis['profit_margin'], Decimal('0.00'))
    
    def test_revenue_matches_payment_mix_totals(self):
        """
        Revenue KPI must equal the sum of Payment Mix amounts.
        This ensures they're computed from the same queryset.
        """
        now = timezone.now()
        
        # Create 3 sold phones with different payment methods
        phone1 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='111111111111111',
            status='SOLD',
            order_price=Decimal('500000.00'),
            selling_price=Decimal('700000.00'),
            payment_method='CASH',
            sold_at=now,
        )
        
        phone2 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='222222222222222',
            status='SOLD',
            order_price=Decimal('600000.00'),
            selling_price=Decimal('800000.00'),
            payment_method='BANK',
            sold_at=now,
        )
        
        phone3 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='333333333333333',
            status='SOLD',
            order_price=Decimal('450000.00'),
            selling_price=Decimal('650000.00'),
            payment_method='MOBILE_MONEY',
            sold_at=now,
        )
        
        # Get dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        kpis = response.context['dashboard_kpis']
        
        # Revenue should be sum of selling prices
        expected_revenue = Decimal('2150000.00')  # 700k + 800k + 650k
        self.assertEqual(kpis['revenue'], expected_revenue)
        
        # Payment Mix should sum to Revenue
        payment_mix = kpis['payment_mix']
        payment_mix_total = sum(pm['amount'] for pm in payment_mix)
        self.assertEqual(payment_mix_total, expected_revenue)
        
        # Individual payment methods
        cash_amount = next(pm['amount'] for pm in payment_mix if pm['method'] == 'Cash')
        bank_amount = next(pm['amount'] for pm in payment_mix if pm['method'] == 'Bank')
        mobile_amount = next(pm['amount'] for pm in payment_mix if pm['method'] == 'Mobile Money')
        
        self.assertEqual(cash_amount, Decimal('700000.00'))
        self.assertEqual(bank_amount, Decimal('800000.00'))
        self.assertEqual(mobile_amount, Decimal('650000.00'))
    
    def test_costs_breakdown_matches_total(self):
        """
        Total Costs MUST equal COGS + Business Costs.
        The breakdown shown must sum to the big number.
        """
        now = timezone.now()
        
        # Create sold phone
        phone = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='444444444444444',
            status='SOLD',
            order_price=Decimal('500000.00'),  # COGS
            selling_price=Decimal('700000.00'),
            payment_method='CASH',
            sold_at=now,
        )
        
        # Create business cost
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal('-100000.00'),  # Costs stored as negative
            note='Rent',
            effective_date=now.date(),
        )
        
        # Get dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        kpis = response.context['dashboard_kpis']
        
        # Check components
        cogs = kpis['cost_of_goods']
        business_costs = kpis['business_costs']
        total_costs = kpis['total_costs']
        
        # COGS should be order_price of sold phone
        self.assertEqual(cogs, Decimal('500000.00'))
        
        # Business costs should be absolute value of cost transaction
        self.assertEqual(business_costs, Decimal('100000.00'))
        
        # Total MUST equal COGS + Business Costs
        self.assertEqual(total_costs, cogs + business_costs)
        self.assertEqual(total_costs, Decimal('600000.00'))
    
    def test_profit_and_margin_consistency(self):
        """
        Profit = Revenue - Total Costs (always)
        Margin = (Profit / Revenue) * 100 (guards division by zero)
        """
        now = timezone.now()
        
        # Create sold phone
        phone = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='555555555555555',
            status='SOLD',
            order_price=Decimal('500000.00'),
            selling_price=Decimal('700000.00'),
            payment_method='CASH',
            sold_at=now,
        )
        
        # Create business cost
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal('-50000.00'),
            note='Marketing',
            effective_date=now.date(),
        )
        
        # Get dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        kpis = response.context['dashboard_kpis']
        
        revenue = kpis['revenue']  # 700,000
        total_costs = kpis['total_costs']  # 500,000 + 50,000 = 550,000
        profit = kpis['profit']
        margin = kpis['profit_margin']
        
        # Profit = Revenue - Total Costs
        expected_profit = revenue - total_costs
        self.assertEqual(profit, expected_profit)
        self.assertEqual(profit, Decimal('150000.00'))
        
        # Margin = (Profit / Revenue) * 100
        expected_margin = (expected_profit / revenue * 100).quantize(Decimal('0.01'))
        self.assertAlmostEqual(float(margin), float(expected_margin), places=1)
        
        # Margin should be ~21.43% (150k / 700k * 100)
        self.assertGreater(margin, Decimal('21.0'))
        self.assertLess(margin, Decimal('22.0'))
    
    def test_margin_guards_division_by_zero(self):
        """When revenue is zero, margin should be zero (not error)."""
        # Dashboard with no sales
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        kpis = response.context['dashboard_kpis']
        
        # With zero revenue, margin should be zero (not error)
        self.assertEqual(kpis['revenue'], Decimal('0.00'))
        self.assertEqual(kpis['profit_margin'], Decimal('0.00'))
    
    def test_negative_profit_scenario(self):
        """Test that negative profit (loss) is handled correctly."""
        now = timezone.now()
        
        # Create sold phone with HIGH costs
        phone = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='666666666666666',
            status='SOLD',
            order_price=Decimal('600000.00'),
            selling_price=Decimal('500000.00'),  # Sold at a LOSS
            payment_method='CASH',
            sold_at=now,
        )
        
        # Add business cost
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal('-100000.00'),
            note='High overhead',
            effective_date=now.date(),
        )
        
        # Get dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        kpis = response.context['dashboard_kpis']
        
        revenue = kpis['revenue']  # 500,000
        total_costs = kpis['total_costs']  # 600,000 + 100,000 = 700,000
        profit = kpis['profit']
        margin = kpis['profit_margin']
        
        # Profit should be negative (loss)
        self.assertEqual(profit, revenue - total_costs)
        self.assertEqual(profit, Decimal('-200000.00'))
        
        # Margin should be negative
        expected_margin = (profit / revenue * 100)
        self.assertAlmostEqual(float(margin), float(expected_margin), places=1)
        self.assertLess(margin, Decimal('0.00'))
        
        # Check absolute values are provided for template
        self.assertEqual(kpis['profit_abs'], Decimal('200000.00'))
        self.assertGreater(kpis['profit_margin_abs'], Decimal('39.0'))
    
    def test_date_range_filtering_mtd(self):
        """Test that MTD (month-to-date) filtering works correctly."""
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Create phone sold THIS MONTH
        phone_this_month = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='777777777777777',
            status='SOLD',
            order_price=Decimal('500000.00'),
            selling_price=Decimal('700000.00'),
            payment_method='CASH',
            sold_at=month_start + timedelta(days=5),
        )
        
        # Create phone sold LAST MONTH (should be excluded)
        phone_last_month = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='888888888888888',
            status='SOLD',
            order_price=Decimal('500000.00'),
            selling_price=Decimal('700000.00'),
            payment_method='CASH',
            sold_at=month_start - timedelta(days=5),
        )
        
        # Get dashboard with MTD filter (default)
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url, {'range': 'mtd'})
        
        self.assertEqual(response.status_code, 200)
        kpis = response.context['dashboard_kpis']
        
        # Should only count this month's sale
        self.assertEqual(kpis['units_sold'], 1)
        self.assertEqual(kpis['revenue'], Decimal('700000.00'))
    
    def test_date_range_filtering_custom(self):
        """Test custom date range filtering."""
        now = timezone.now()
        
        # Create sales on different dates
        phone1 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='999999999999991',
            status='SOLD',
            order_price=Decimal('500000.00'),
            selling_price=Decimal('700000.00'),
            payment_method='CASH',
            sold_at=now - timedelta(days=5),  # 5 days ago
        )
        
        phone2 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='999999999999992',
            status='SOLD',
            order_price=Decimal('500000.00'),
            selling_price=Decimal('700000.00'),
            payment_method='CASH',
            sold_at=now - timedelta(days=15),  # 15 days ago (outside range)
        )
        
        # Filter: last 7 days
        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url, {
            'range': 'custom',
            'start': start_date,
            'end': end_date,
        })
        
        self.assertEqual(response.status_code, 200)
        kpis = response.context['dashboard_kpis']
        
        # Should only count phone1 (5 days ago, within 7-day window)
        self.assertEqual(kpis['units_sold'], 1)
        self.assertEqual(kpis['revenue'], Decimal('700000.00'))
    
    def test_multiple_sales_with_costs_full_scenario(self):
        """
        Full acceptance test with multiple sales and costs.
        Ensures all KPIs are consistent and correctly computed.
        """
        now = timezone.now()
        
        # Create 3 sales
        sales_data = [
            ('111', Decimal('500000'), Decimal('700000'), 'CASH'),
            ('222', Decimal('600000'), Decimal('850000'), 'BANK'),
            ('333', Decimal('450000'), Decimal('650000'), 'MOBILE_MONEY'),
        ]
        
        for imei, cost, price, payment in sales_data:
            InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                current_location=self.location,
                imei=imei,
                status='SOLD',
                order_price=cost,
                selling_price=price,
                payment_method=payment,
                sold_at=now,
            )
        
        # Create 2 business costs
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal('-100000.00'),
            note='Rent',
            effective_date=now.date(),
        )
        
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal('-50000.00'),
            note='Utilities',
            effective_date=now.date(),
            is_recurring=True,
            effective_from=now.date(),
        )
        
        # Get dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        kpis = response.context['dashboard_kpis']
        
        # Expected values
        expected_revenue = Decimal('2200000.00')  # 700k + 850k + 650k
        expected_cogs = Decimal('1550000.00')  # 500k + 600k + 450k
        expected_business_costs = Decimal('150000.00')  # 100k + 50k
        expected_total_costs = Decimal('1700000.00')  # COGS + Business Costs
        expected_profit = Decimal('500000.00')  # Revenue - Total Costs
        expected_margin = Decimal('22.73')  # (500k / 2200k) * 100 ≈ 22.73%
        
        # Assertions
        self.assertEqual(kpis['units_sold'], 3)
        self.assertEqual(kpis['revenue'], expected_revenue)
        self.assertEqual(kpis['cost_of_goods'], expected_cogs)
        self.assertEqual(kpis['business_costs'], expected_business_costs)
        self.assertEqual(kpis['total_costs'], expected_total_costs)
        self.assertEqual(kpis['profit'], expected_profit)
        
        # Margin (allow small floating point difference)
        self.assertAlmostEqual(float(kpis['profit_margin']), float(expected_margin), places=1)
        
        # Payment Mix consistency
        payment_mix = kpis['payment_mix']
        payment_mix_total = sum(pm['amount'] for pm in payment_mix)
        self.assertEqual(payment_mix_total, expected_revenue)
        
        # Breakdown consistency
        self.assertEqual(kpis['total_costs'], kpis['cost_of_goods'] + kpis['business_costs'])
        self.assertEqual(kpis['profit'], kpis['revenue'] - kpis['total_costs'])


class PhonesDashboardRegressionTests(TestCase):
    """Regression tests to ensure no other dashboards are broken."""
    
    def setUp(self):
        """Create test user and businesses for other verticals."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123',
            is_staff=True,
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_phones_dashboard_requires_phones_business(self):
        """Phones dashboard should only be accessible to phones businesses."""
        # Create a GYM business (not phones)
        gym_business = Business.objects.create(
            name='Test Gym',
            kind=BusinessKind.GYM,
            is_active=True,
        )
        
        self.user.business = gym_business
        self.user.save()
        
        # Try to access phones dashboard - should fail/redirect
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        # Should not be 200 (either 403 or redirect)
        self.assertNotEqual(response.status_code, 200)

