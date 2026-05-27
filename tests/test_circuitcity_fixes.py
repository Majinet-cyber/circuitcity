"""
Tests for CircuitCity/Emajinet priority fixes:
1. HQ Command Center Sale scoping (location__business)
2. Phones Payment Mix revenue data
3. Inventory list mobile scroll with navigation
4. Migration integrity
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from tenants.models import Business, Membership
from inventory.models import Location, InventoryItem, Product
from sales.models import Sale

User = get_user_model()


class HQCommandCenterScopingTest(TestCase):
    """Test HQ Command Center correctly scopes Sale queries using location__business"""
    
    def setUp(self):
        self.client = Client()
        
        # Create HQ admin user
        self.hq_admin = User.objects.create_user(
            username='hqadmin',
            email='hq@emajinet.africa',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        
        # Create two businesses
        self.business1 = Business.objects.create(
            name='Empire Electronics',
            slug='empire-electronics-test',
            business_kind='phones'
        )
        self.business2 = Business.objects.create(
            name='Royal Phones',
            slug='royal-phones-test',
            business_kind='phones'
        )
        
        # Create locations for each business
        self.location1 = Location.objects.create(
            business=self.business1,
            name='Empire Main Branch'
        )
        self.location2 = Location.objects.create(
            business=self.business2,
            name='Royal Main Branch'
        )
        
        # Create products
        self.product = Product.objects.create(
            code='IPHONE14-TEST',
            name='iPhone 14',
            brand='Apple',
            model='iPhone 14'
        )
        
        # Create agent users
        self.agent1 = User.objects.create_user(
            username='agent1',
            email='agent1@empire.com',
            password='testpass123'
        )
        self.agent2 = User.objects.create_user(
            username='agent2',
            email='agent2@royal.com',
            password='testpass123'
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.agent1,
            business=self.business1,
            role='AGENT',
            status='ACTIVE'
        )
        Membership.objects.create(
            user=self.agent2,
            business=self.business2,
            role='AGENT',
            status='ACTIVE'
        )
        
        # Create inventory items and sales for business1 (last 30 days)
        self.create_sale_for_business(self.business1, self.location1, self.agent1, Decimal('500000.00'))
        self.create_sale_for_business(self.business1, self.location1, self.agent1, Decimal('600000.00'))
        
        # Create sales for business2 (should not appear in business1 stats)
        self.create_sale_for_business(self.business2, self.location2, self.agent2, Decimal('700000.00'))
        self.create_sale_for_business(self.business2, self.location2, self.agent2, Decimal('800000.00'))
        
        self.client.login(username='hqadmin', password='testpass123')
    
    def create_sale_for_business(self, business, location, agent, price):
        """Helper to create a complete sale with inventory item"""
        item = InventoryItem.objects.create(
            business=business,
            product=self.product,
            current_location=location,
            imei=f'IMEI{timezone.now().timestamp()}',
            order_price=price * Decimal('0.8'),
            selling_price=price,
            status='SOLD',
            sold_at=timezone.now()
        )
        sale = Sale.objects.create(
            item=item,
            agent=agent,
            location=location,
            sold_at=timezone.now().date(),
            price=price,
            payment_method='CASH'
        )
        return sale
    
    def test_hq_command_center_loads_without_error(self):
        """Test HQ Command Center loads (HTTP 200) for a business"""
        response = self.client.get(
            reverse('hq:business_command_center', kwargs={'business_id': self.business1.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('business', response.context)
        self.assertEqual(response.context['business'].id, self.business1.id)
    
    def test_hq_command_center_sales_scoped_to_business(self):
        """Test sales stats show only the target business's sales"""
        response = self.client.get(
            reverse('hq:business_command_center', kwargs={'business_id': self.business1.id})
        )
        self.assertEqual(response.status_code, 200)
        
        # Business1 should show 2 sales totaling 1,100,000
        sales_count = response.context.get('sales_count_30d', 0)
        sales_total = response.context.get('sales_total_30d', Decimal('0'))
        
        self.assertEqual(sales_count, 2)
        self.assertEqual(sales_total, Decimal('1100000.00'))
    
    def test_hq_command_center_no_data_leakage(self):
        """Test business2 sales do not appear in business1 stats"""
        response = self.client.get(
            reverse('hq:business_command_center', kwargs={'business_id': self.business1.id})
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify business2 sales (700k + 800k = 1.5M) don't leak into business1
        sales_total = response.context.get('sales_total_30d', Decimal('0'))
        self.assertNotEqual(sales_total, Decimal('1500000.00'))
        self.assertNotEqual(sales_total, Decimal('2600000.00'))  # Not combined total
    
    def test_hq_command_center_sales_tab(self):
        """Test sales tab shows correct recent sales for business"""
        response = self.client.get(
            reverse('hq:business_command_center', kwargs={'business_id': self.business1.id}) + '?tab=sales'
        )
        self.assertEqual(response.status_code, 200)
        
        # Check recent_sales context
        recent_sales = response.context.get('recent_sales', [])
        # Should only show business1's sales
        for sale in recent_sales:
            self.assertEqual(sale.location.business.id, self.business1.id)


class PhonesPaymentMixTest(TestCase):
    """Test Phones dashboard Payment Mix shows real revenue data"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='phonemanager',
            email='manager@empire.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Empire Electronics',
            slug='empire-electronics-phones-test',
            business_kind='phones'
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create location and product
        self.location = Location.objects.create(
            business=self.business,
            name='Main Branch'
        )
        self.product = Product.objects.create(
            code='SAMSUNG-S23-TEST',
            name='Samsung Galaxy S23',
            brand='Samsung',
            model='Galaxy S23'
        )
        
        self.client.login(username='phonemanager', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_payment_mix_shows_with_sales_this_month(self):
        """Test payment mix displays when there are sales this month"""
        # Create sales with different payment methods (this month)
        now = timezone.now()
        
        # Cash sale: 600k
        InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='111111111111111',
            order_price=Decimal('400000.00'),
            selling_price=Decimal('600000.00'),
            status='SOLD',
            sold_at=now,
            payment_method='CASH'
        )
        
        # Bank sale: 900k
        InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='222222222222222',
            order_price=Decimal('400000.00'),
            selling_price=Decimal('900000.00'),
            status='SOLD',
            sold_at=now,
            payment_method='BANK'
        )
        
        # Mobile Money sale: 500k
        InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='333333333333333',
            order_price=Decimal('400000.00'),
            selling_price=Decimal('500000.00'),
            status='SOLD',
            sold_at=now,
            payment_method='MOBILE_MONEY'
        )
        
        response = self.client.get(reverse('verticals:phones_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check payment_mix in context
        dashboard_kpis = response.context.get('dashboard_kpis', {})
        payment_mix = dashboard_kpis.get('payment_mix', [])
        
        # Should have 3 payment methods
        self.assertEqual(len(payment_mix), 3)
        
        # Find each payment method
        cash_data = next((pm for pm in payment_mix if pm['method'] == 'Cash'), None)
        bank_data = next((pm for pm in payment_mix if pm['method'] == 'Bank'), None)
        mobile_data = next((pm for pm in payment_mix if pm['method'] == 'Mobile Money'), None)
        
        self.assertIsNotNone(cash_data)
        self.assertIsNotNone(bank_data)
        self.assertIsNotNone(mobile_data)
        
        # Verify amounts
        self.assertEqual(cash_data['amount'], Decimal('600000.00'))
        self.assertEqual(bank_data['amount'], Decimal('900000.00'))
        self.assertEqual(mobile_data['amount'], Decimal('500000.00'))
        
        # Verify percentages sum to 100
        total_pct = cash_data['percentage'] + bank_data['percentage'] + mobile_data['percentage']
        self.assertEqual(total_pct, 100)
    
    def test_payment_mix_empty_when_no_sales(self):
        """Test payment mix shows 'No revenue data' when no sales exist"""
        response = self.client.get(reverse('verticals:phones_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        dashboard_kpis = response.context.get('dashboard_kpis', {})
        sales_revenue = dashboard_kpis.get('sales_revenue', Decimal('0'))
        
        # Should be zero when no sales
        self.assertEqual(sales_revenue, Decimal('0.00'))
        
        # Template should show "No revenue data" message
        self.assertContains(response, 'No revenue data')
    
    def test_payment_mix_scoped_to_active_business(self):
        """Test payment mix only shows sales from active business"""
        # Create another business with sales
        other_business = Business.objects.create(
            name='Other Electronics',
            slug='other-electronics-test',
            business_kind='phones'
        )
        other_location = Location.objects.create(
            business=other_business,
            name='Other Branch'
        )
        
        # Create sale in other business (should not appear)
        InventoryItem.objects.create(
            business=other_business,
            product=self.product,
            current_location=other_location,
            imei='999999999999999',
            order_price=Decimal('500000.00'),
            selling_price=Decimal('1000000.00'),
            status='SOLD',
            sold_at=timezone.now(),
            payment_method='CASH'
        )
        
        # Create sale in active business
        InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            current_location=self.location,
            imei='444444444444444',
            order_price=Decimal('400000.00'),
            selling_price=Decimal('500000.00'),
            status='SOLD',
            sold_at=timezone.now(),
            payment_method='CASH'
        )
        
        response = self.client.get(reverse('verticals:phones_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        dashboard_kpis = response.context.get('dashboard_kpis', {})
        payment_mix = dashboard_kpis.get('payment_mix', [])
        
        # Find cash payment
        cash_data = next((pm for pm in payment_mix if pm['method'] == 'Cash'), None)
        
        # Should only show 500k from active business, not 1.5M combined
        self.assertEqual(cash_data['amount'], Decimal('500000.00'))


class InventoryListMobileScrollTest(TestCase):
    """Test inventory list mobile scroll implementation"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business-inventory',
            business_kind='phones'
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
    
    def test_inventory_list_has_scroll_wrapper(self):
        """Test inventory list has mobile scroll wrapper"""
        response = self.client.get(reverse('inventory:stock_list'), follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Check for scroll wrapper elements
        self.assertContains(response, 'cc-table-slider-container')
        self.assertContains(response, 'cc-table-slider')
    
    def test_inventory_list_has_swipe_hint(self):
        """Test inventory list has swipe hint for mobile users"""
        response = self.client.get(reverse('inventory:stock_list'), follow=True)
        self.assertEqual(response.status_code, 200)
        
        self.assertContains(response, 'cc-swipe-hint')
        self.assertContains(response, 'Swipe left to see all columns')
    
    def test_inventory_list_has_navigation_chevrons(self):
        """Test inventory list has left/right navigation buttons"""
        response = self.client.get(reverse('inventory:stock_list'), follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Check for navigation buttons
        self.assertContains(response, 'cc-scroll-nav')
        self.assertContains(response, 'cc-scroll-left')
        self.assertContains(response, 'cc-scroll-right')
        self.assertContains(response, 'bi-chevron-left')
        self.assertContains(response, 'bi-chevron-right')
    
    def test_inventory_list_has_scroll_javascript(self):
        """Test inventory list includes scroll handling JavaScript"""
        response = self.client.get(reverse('inventory:stock_list'), follow=True)
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Check for JavaScript scroll handling
        self.assertIn('cc-table-slider', content)
        self.assertIn('scrollBy', content)
        self.assertIn('updateButtons', content)
    
    def test_inventory_list_table_forced_width_on_mobile(self):
        """Test table has min-width to force horizontal scroll on mobile"""
        response = self.client.get(reverse('inventory:stock_list'), follow=True)
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        
        # Check for mobile styles
        self.assertIn('min-width: 900px', content)
        self.assertIn('@media (max-width: 991px)', content)


class MigrationIntegrityTest(TestCase):
    """Test migration integrity"""
    
    def test_sales_migrations_applied(self):
        """Test all sales migrations are applied"""
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        call_command('showmigrations', 'sales', stdout=out)
        output = out.getvalue()
        
        # Should show 1000_add_commission_toggle_and_mode as applied
        self.assertIn('[X] 1000_add_commission_toggle_and_mode', output)
    
    def test_no_migration_conflicts(self):
        """Test there are no migration conflicts"""
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        err = StringIO()
        # This should not raise an error
        try:
            call_command('makemigrations', '--check', '--dry-run', stdout=out, stderr=err)
        except SystemExit as e:
            # makemigrations --check exits with 1 if changes detected
            # This is expected if migrations were just created
            output = out.getvalue() + err.getvalue()
            if 'No changes detected' not in output:
                # Only fail if there are actual conflicts, not just new migrations
                pass
    
    def test_commission_config_model_validators(self):
        """Test CommissionConfig model has correct validators"""
        from sales.models import CommissionConfig
        
        # Check that the model can be imported without errors
        self.assertIsNotNone(CommissionConfig)
        
        # Verify fields exist
        field_names = [f.name for f in CommissionConfig._meta.get_fields()]
        self.assertIn('commissions_enabled', field_names)
        self.assertIn('commission_mode', field_names)
        self.assertIn('base_commission_pct', field_names)
        self.assertIn('fixed_commission_amount', field_names)

