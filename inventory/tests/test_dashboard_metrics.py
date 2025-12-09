"""
Tests for dashboard metrics accuracy.

Ensures that revenue, costs, profit, payment mix, and battery percentages
are calculated correctly and update after sales.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date

from tenants.models import Business, Membership
from inventory.models import Location, InventoryItem, Product
from sales.models import Sale, PaymentMethod

User = get_user_model()


class DashboardMetricsTestCase(TestCase):
    """Test dashboard metrics calculations."""
    
    def setUp(self):
        """Set up test data."""
        # Create user
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123'
        )
        
        # Create business
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business'
        )
        
        # Add user to business with manager role
        Membership.objects.create(
            business=self.business,
            user=self.user,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Get or create location (default location is auto-created for businesses)
        self.location = Location.objects.filter(business=self.business).first()
        if not self.location:
            self.location = Location.objects.create(
                business=self.business,
                name='Main Store',
                is_default=False
            )
        
        # Create product
        self.product = Product.objects.create(
            business=self.business,
            brand='TestBrand',
            model='TestModel',
            variant='128GB',
            low_stock_threshold=5
        )
        
        self.client = Client()
        self.client.login(username='testmanager', password='testpass123')
        
    def test_dashboard_metrics_zero_when_no_sales(self):
        """Test that metrics are zero when there are no sales."""
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        self.assertEqual(context['total_revenue'], 0)
        self.assertEqual(context['costs_total'], 0)
        self.assertEqual(context['profit_total'], 0)
        self.assertEqual(context['total_units'], 0)
        
    def test_dashboard_metrics_update_after_sale(self):
        """Test that metrics update correctly after a sale."""
        # Create inventory item
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei='123456789012345',
            order_price=Decimal('400000.00'),
            selling_price=Decimal('600000.00'),
            status='IN_STOCK',
            current_location=self.location
        )
        
        # Create sale
        sale = Sale.objects.create(
            item=item,
            agent=self.user,
            location=self.location,
            sold_at=date.today(),
            price=Decimal('600000.00'),
            commission_pct=Decimal('12.00'),
            payment_method=PaymentMethod.MOBILE_MONEY
        )
        
        # Update item status
        item.status = 'SOLD'
        item.sold_at = timezone.now()
        item.save()
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        
        # Check basic metrics
        self.assertEqual(float(context['total_revenue']), 600000.0)
        self.assertEqual(float(context['costs_total']), 400000.0)
        self.assertEqual(float(context['profit_total']), 200000.0)
        self.assertEqual(context['total_units'], 1)
        
        # Check profit margin (33.33%)
        self.assertAlmostEqual(context['profit_margin'], 33, delta=1)
        
    def test_payment_mix_percentages_sum_to_100(self):
        """Test that payment mix percentages sum to 100%."""
        # Create sales with different payment methods
        for i, payment_method in enumerate([
            PaymentMethod.CASH,
            PaymentMethod.BANK,
            PaymentMethod.MOBILE_MONEY
        ]):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                imei=f'12345678901234{i}',
                order_price=Decimal('100000.00'),
                selling_price=Decimal('150000.00'),
                status='SOLD',
                current_location=self.location,
                sold_at=timezone.now()
            )
            
            Sale.objects.create(
                item=item,
                agent=self.user,
                location=self.location,
                sold_at=date.today(),
                price=Decimal('150000.00'),
                payment_method=payment_method
            )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        payment_mix = context.get('payment_mix')
        
        self.assertIsNotNone(payment_mix)
        
        # Check percentages sum to 100
        total_pct = (
            payment_mix['cash']['pct'] +
            payment_mix['bank']['pct'] +
            payment_mix['mobile']['pct']
        )
        self.assertEqual(total_pct, 100)
        
        # Each should be roughly 33% (with rounding)
        self.assertAlmostEqual(payment_mix['cash']['pct'], 33, delta=2)
        self.assertAlmostEqual(payment_mix['bank']['pct'], 33, delta=2)
        self.assertAlmostEqual(payment_mix['mobile']['pct'], 33, delta=2)
        
    def test_revenue_vs_costs_battery_sums_to_100(self):
        """Test that Revenue vs Costs battery percentages sum to 100%."""
        # Create a sale
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei='111111111111111',
            order_price=Decimal('300000.00'),
            selling_price=Decimal('500000.00'),
            status='SOLD',
            current_location=self.location,
            sold_at=timezone.now()
        )
        
        Sale.objects.create(
            item=item,
            agent=self.user,
            location=self.location,
            sold_at=date.today(),
            price=Decimal('500000.00'),
            payment_method=PaymentMethod.CASH
        )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        rev_cost_mix = context.get('rev_cost_mix')
        
        self.assertIsNotNone(rev_cost_mix)
        
        # Check percentages sum to 100
        total_pct = (
            rev_cost_mix['revenue']['pct'] +
            rev_cost_mix['costs']['pct']
        )
        self.assertEqual(total_pct, 100)
        
        # Revenue should be 62.5%, costs 37.5% (500k / 800k total)
        self.assertAlmostEqual(rev_cost_mix['revenue']['pct'], 62, delta=2)
        self.assertAlmostEqual(rev_cost_mix['costs']['pct'], 38, delta=2)
        
    def test_profit_vs_costs_battery_sums_to_100(self):
        """Test that Profit vs Costs battery percentages sum to 100%."""
        # Create a sale
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei='222222222222222',
            order_price=Decimal('400000.00'),
            selling_price=Decimal('600000.00'),
            status='SOLD',
            current_location=self.location,
            sold_at=timezone.now()
        )
        
        Sale.objects.create(
            item=item,
            agent=self.user,
            location=self.location,
            sold_at=date.today(),
            price=Decimal('600000.00'),
            payment_method=PaymentMethod.BANK
        )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        profit_cost_mix = context.get('profit_cost_mix')
        
        self.assertIsNotNone(profit_cost_mix)
        
        # Check percentages sum to 100
        total_pct = (
            profit_cost_mix['profit']['pct'] +
            profit_cost_mix['costs']['pct']
        )
        self.assertEqual(total_pct, 100)
        
        # Profit is 200k, costs 400k, total 600k
        # So profit should be 33%, costs 67%
        self.assertAlmostEqual(profit_cost_mix['profit']['pct'], 33, delta=2)
        self.assertAlmostEqual(profit_cost_mix['costs']['pct'], 67, delta=2)
        
        # No low margin warning (margin is 33% > 10%)
        self.assertFalse(profit_cost_mix['low_margin_warning'])
        
    def test_low_margin_warning_triggers_when_margin_below_10_percent(self):
        """Test that low margin warning triggers when profit margin < 10%."""
        # Create a sale with low margin (cost 550k, price 600k = 8.3% margin)
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei='333333333333333',
            order_price=Decimal('550000.00'),
            selling_price=Decimal('600000.00'),
            status='SOLD',
            current_location=self.location,
            sold_at=timezone.now()
        )
        
        Sale.objects.create(
            item=item,
            agent=self.user,
            location=self.location,
            sold_at=date.today(),
            price=Decimal('600000.00'),
            payment_method=PaymentMethod.CASH
        )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        profit_cost_mix = context.get('profit_cost_mix')
        
        self.assertIsNotNone(profit_cost_mix)
        
        # Check that low margin warning is triggered
        self.assertTrue(profit_cost_mix['low_margin_warning'])
        
        # Profit margin should be around 8%
        margin = (
            float(profit_cost_mix['profit']['amount']) /
            float(context['total_revenue']) * 100
        )
        self.assertLess(margin, 10)
        
    def test_stock_alerts_update_after_sale(self):
        """Test that stock alerts update when the last item is sold."""
        # Create a single item
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei='444444444444444',
            order_price=Decimal('400000.00'),
            selling_price=Decimal('600000.00'),
            status='IN_STOCK',
            current_location=self.location
        )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Check dashboard before sale - should have 1 item in stock
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_stock_count'], 1)
        
        # Sell the item
        Sale.objects.create(
            item=item,
            agent=self.user,
            location=self.location,
            sold_at=date.today(),
            price=Decimal('600000.00'),
            payment_method=PaymentMethod.MOBILE_MONEY
        )
        
        item.status = 'SOLD'
        item.sold_at = timezone.now()
        item.save()
        
        # Check dashboard after sale - should have 0 items in stock
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_stock_count'], 0)
        
        # Should show out of stock alert
        self.assertGreater(response.context['out_of_stock_count'], 0)


class DashboardMetricsEdgeCasesTestCase(TestCase):
    """Test edge cases for dashboard metrics."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.business = Business.objects.create(
            name='Test Business 2',
            slug='test-business-2'
        )
        
        Membership.objects.create(
            business=self.business,
            user=self.user,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Get or create location (default location is auto-created for businesses)
        self.location = Location.objects.filter(business=self.business).first()
        if not self.location:
            self.location = Location.objects.create(
                business=self.business,
                name='Test Store',
                is_default=False
            )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
        
    def test_dashboard_handles_zero_revenue_gracefully(self):
        """Test that dashboard doesn't divide by zero when revenue is 0."""
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        # Should not crash and should show 0 percentages
        context = response.context
        self.assertEqual(context['payment_mix']['cash']['pct'], 0)
        self.assertEqual(context['payment_mix']['bank']['pct'], 0)
        self.assertEqual(context['payment_mix']['mobile']['pct'], 0)
        
    def test_payment_mix_handles_single_payment_method(self):
        """Test payment mix when only one payment method is used."""
        product = Product.objects.create(
            business=self.business,
            brand='SingleBrand',
            model='SingleModel'
        )
        
        # Create 3 sales all with CASH
        for i in range(3):
            item = InventoryItem.objects.create(
                business=self.business,
                product=product,
                imei=f'55555555555555{i}',
                order_price=Decimal('100000.00'),
                selling_price=Decimal('120000.00'),
                status='SOLD',
                current_location=self.location,
                sold_at=timezone.now()
            )
            
            Sale.objects.create(
                item=item,
                agent=self.user,
                location=self.location,
                sold_at=date.today(),
                price=Decimal('120000.00'),
                payment_method=PaymentMethod.CASH
            )
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        payment_mix = response.context['payment_mix']
        
        # Cash should be 100%, others 0
        self.assertEqual(payment_mix['cash']['pct'], 100)
        self.assertEqual(payment_mix['bank']['pct'], 0)
        self.assertEqual(payment_mix['mobile']['pct'], 0)
        
        # Total should still sum to 100
        total = (
            payment_mix['cash']['pct'] +
            payment_mix['bank']['pct'] +
            payment_mix['mobile']['pct']
        )
        self.assertEqual(total, 100)


class DashboardAdminCostsTestCase(TestCase):
    """Test that admin costs from wallet are included in dashboard metrics."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testadmin',
            password='testpass123',
            is_staff=True
        )
        
        # Create business with all required fields
        self.business = Business.objects.create(
            name='Test Business 3',
            slug='test-business-3'
        )
        
        # Add user to business using Membership
        Membership.objects.create(
            business=self.business,
            user=self.user,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Get the default location (auto-created) or create a non-default one
        self.location = Location.objects.filter(business=self.business).first()
        if not self.location:
            self.location = Location.objects.create(
                business=self.business,
                name='Main Location',
                is_default=False
            )
        
        # Product model might not have business field in this version
        # Use the pattern from the working test class
        try:
            self.product = Product.objects.create(
                business=self.business,
                brand='AdminTest',
                model='CostTest'
            )
        except TypeError:
            # Fallback: if Product doesn't have business field
            self.product = Product.objects.create(
                brand='AdminTest',
                model='CostTest'
            )
        
        self.client = Client()
        self.client.login(username='testadmin', password='testpass123')
        
    def test_admin_costs_included_in_dashboard_costs(self):
        """Test that admin costs from wallet are added to COGS in dashboard."""
        # Import wallet models
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        # Create a sale: Revenue 600k, COGS 400k
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei='777777777777777',
            order_price=Decimal('400000.00'),  # COGS
            selling_price=Decimal('600000.00'),
            status='SOLD',
            current_location=self.location,
            sold_at=timezone.now()
        )
        
        Sale.objects.create(
            item=item,
            agent=self.user,
            location=self.location,
            sold_at=date.today(),
            price=Decimal('600000.00'),
            payment_method=PaymentMethod.CASH
        )
        
        # Add admin cost: Rent MK 200,000 (stored as negative)
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal('-200000.00'),  # Negative = expense
            note='Rent',
            effective_date=date.today(),
            created_by=self.user
        )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        
        # Revenue should be 600k
        self.assertEqual(float(context['total_revenue']), 600000.0)
        
        # Costs should be 400k (COGS) + 200k (Admin) = 600k
        self.assertEqual(float(context['costs_total']), 600000.0)
        
        # Profit should be 600k - 600k = 0
        self.assertEqual(float(context['profit_total']), 0.0)
        
        # Check that kpis_detail includes breakdown
        kpis_detail = context.get('kpis_detail')
        if kpis_detail:
            self.assertEqual(float(kpis_detail['total_cogs']), 400000.0)
            self.assertEqual(float(kpis_detail['total_admin_costs']), 200000.0)
            self.assertEqual(float(kpis_detail['total_costs']), 600000.0)
            
    def test_recurring_admin_costs_included(self):
        """Test that recurring admin costs are included in dashboard."""
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        # Create a sale
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei='888888888888888',
            order_price=Decimal('300000.00'),
            selling_price=Decimal('500000.00'),
            status='SOLD',
            current_location=self.location,
            sold_at=timezone.now()
        )
        
        Sale.objects.create(
            item=item,
            agent=self.user,
            location=self.location,
            sold_at=date.today(),
            price=Decimal('500000.00'),
            payment_method=PaymentMethod.BANK
        )
        
        # Add recurring cost: Monthly salary MK 150,000
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal('-150000.00'),
            note='Salaries',
            effective_date=date.today(),
            effective_from=date.today(),
            is_recurring=True,
            created_by=self.user
        )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        
        # Revenue = 500k
        self.assertEqual(float(context['total_revenue']), 500000.0)
        
        # Costs = 300k (COGS) + 150k (Recurring) = 450k
        self.assertEqual(float(context['costs_total']), 450000.0)
        
        # Profit = 500k - 450k = 50k
        self.assertEqual(float(context['profit_total']), 50000.0)
        
    def test_profit_vs_costs_warning_with_admin_costs(self):
        """Test that low margin warning considers admin costs."""
        from wallet.models import WalletTransaction, Ledger, TxnType
        
        # Create a sale with decent COGS margin
        item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei='999999999999999',
            order_price=Decimal('400000.00'),  # COGS
            selling_price=Decimal('600000.00'),
            status='SOLD',
            current_location=self.location,
            sold_at=timezone.now()
        )
        
        Sale.objects.create(
            item=item,
            agent=self.user,
            location=self.location,
            sold_at=date.today(),
            price=Decimal('600000.00'),
            payment_method=PaymentMethod.CASH
        )
        
        # Add high admin costs that push total costs > 10% of revenue
        # Admin costs: 200k, Total costs: 600k, which is 100% of revenue
        WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal('-200000.00'),
            note='High overhead',
            effective_date=date.today(),
            created_by=self.user
        )
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get('/inventory/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        profit_cost_mix = context.get('profit_cost_mix')
        
        # Warning should be triggered because costs (600k) > 10% of revenue (600k)
        self.assertTrue(profit_cost_mix['low_margin_warning'])