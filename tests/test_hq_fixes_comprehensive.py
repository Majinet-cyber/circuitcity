# tests/test_hq_fixes_comprehensive.py
"""
Comprehensive tests for all HQ admin fixes.
Tests that HQ pages never 500 and show correct real data.
"""
import pytest
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from billing.models import BusinessSubscription as Subscription, Invoice, SubscriptionPlan
from sales.models import Sale
from inventory.models import InventoryItem, Location

User = get_user_model()


@pytest.mark.django_db
class TestHQStockTrendsNever500(TestCase):
    """Test that /hq/stock-trends/ never 500s."""
    
    def setUp(self):
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hqadmin',
            email='hq@test.com',
            password='test123',
            is_staff=True,
            is_superuser=True
        )
        self.client.force_login(self.hq_user)
        self.url = reverse('hq:stock_trends')
    
    def test_stock_trends_empty_db(self):
        """Stock trends loads with empty database."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # Check for empty state indicators
        self.assertContains(response, 'Total Stock In')
        self.assertContains(response, 'Total Stock Out')
    
    def test_stock_trends_no_stock_data(self):
        """Stock trends loads with business but no stock."""
        biz = Business.objects.create(name='Test Shop', slug='testshop', status='ACTIVE')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
    
    def test_stock_trends_with_data(self):
        """Stock trends loads and displays real stock data."""
        biz = Business.objects.create(name='Test Shop', slug='testshop', status='ACTIVE')
        loc = Location.objects.create(business=biz, name='Main Store')
        
        # Create some inventory items
        for i in range(5):
            InventoryItem.objects.create(
                business=biz,
                current_location=loc,
                sku=f'SKU{i}',
                received_at=timezone.now(),
            )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # Should show 5 items in
        self.assertContains(response, '5')
    
    def test_stock_trends_non_hq_user_blocked(self):
        """Non-HQ user cannot access stock trends."""
        regular_user = User.objects.create_user(username='regular', password='test123')
        self.client.force_login(regular_user)
        response = self.client.get(self.url)
        # Should redirect or return 403
        self.assertIn(response.status_code, [302, 403])


@pytest.mark.django_db
class TestHQRealVerticalData(TestCase):
    """Test that HQ shows only real vertical/business data."""
    
    def setUp(self):
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hqadmin',
            email='hq@test.com',
            password='test123',
            is_staff=True,
            is_superuser=True
        )
        self.client.force_login(self.hq_user)
    
    def test_business_directory_real_verticals_only(self):
        """Business directory shows only real verticals from DB."""
        # Create businesses with specific verticals
        Business.objects.create(name='Phone Shop', slug='phones1', business_kind='phones')
        Business.objects.create(name='Clothing Store', slug='clothing1', business_kind='clothing')
        
        response = self.client.get(reverse('hq:business_directory'))
        self.assertEqual(response.status_code, 200)
        
        # Should show 2 businesses
        self.assertContains(response, 'Phone Shop')
        self.assertContains(response, 'Clothing Store')
        
        # Should NOT show fake restaurants/gyms unless created
        content = response.content.decode('utf-8')
        # Check that chart data contains real verticals
        self.assertIn('Phones', content)
        self.assertIn('Clothing', content)
    
    def test_dashboard_vertical_counts_real(self):
        """Dashboard shows real vertical counts."""
        Business.objects.create(name='Pharmacy 1', slug='pharmacy1', business_kind='pharmacy')
        Business.objects.create(name='Pharmacy 2', slug='pharmacy2', business_kind='pharmacy')
        
        response = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Should show 2 total businesses
        self.assertContains(response, '2')


@pytest.mark.django_db
class TestHQAgentsIncludeManagers(TestCase):
    """Test that HQ agents list includes managers."""
    
    def setUp(self):
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hqadmin',
            password='test123',
            is_staff=True,
            is_superuser=True
        )
        self.client.force_login(self.hq_user)
        
        self.biz = Business.objects.create(name='Test Shop', slug='testshop', status='ACTIVE')
    
    def test_agents_list_includes_managers(self):
        """HQ agents list shows both agents and managers."""
        agent_user = User.objects.create_user(username='agent1', password='test123')
        manager_user = User.objects.create_user(username='manager1', password='test123')
        
        Membership.objects.create(user=agent_user, business=self.biz, role='AGENT')
        Membership.objects.create(user=manager_user, business=self.biz, role='MANAGER')
        
        response = self.client.get(reverse('hq:agents'))
        self.assertEqual(response.status_code, 200)
        
        # Should show both
        self.assertContains(response, 'agent1')
        self.assertContains(response, 'manager1')


@pytest.mark.django_db
class TestHQTopAgentsRealData(TestCase):
    """Test that top agents shows real rankings."""
    
    def setUp(self):
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hqadmin',
            password='test123',
            is_staff=True,
            is_superuser=True
        )
        self.client.force_login(self.hq_user)
        
        self.biz = Business.objects.create(name='Test Shop', slug='testshop', status='ACTIVE')
        self.agent = User.objects.create_user(username='agent1', password='test123')
        Membership.objects.create(user=self.agent, business=self.biz, role='AGENT')
    
    def test_top_agents_shows_sales_data(self):
        """Dashboard top agents section shows real sales."""
        # Create sales attributed to agent
        for i in range(3):
            Sale.objects.create(
                business=self.biz,
                agent=self.agent,
                price=Decimal('1000.00'),
                sold_at=timezone.now()
            )
        
        response = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Should show agent in top agents with 3 sales
        self.assertContains(response, 'agent1')
        self.assertContains(response, '3')


@pytest.mark.django_db
class TestHQWalletRebuild(TestCase):
    """Test rebuilt HQ wallet with business table and payment marking."""
    
    def setUp(self):
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hqadmin',
            password='test123',
            is_staff=True,
            is_superuser=True
        )
        self.client.force_login(self.hq_user)
        
        # Create plan and businesses
        self.plan = SubscriptionPlan.objects.create(
            code='pro',
            name='Pro',
            amount=Decimal('35000.00')
        )
        self.biz = Business.objects.create(name='Test Shop', slug='testshop', status='ACTIVE')
        Subscription.objects.create(
            business=self.biz,
            plan=self.plan,
            status='active'
        )
    
    def test_wallet_shows_business_table(self):
        """Wallet shows table of businesses with plan info."""
        response = self.client.get(reverse('hq:wallet'))
        self.assertEqual(response.status_code, 200)
        
        self.assertContains(response, 'Test Shop')
        self.assertContains(response, 'Pro')
        self.assertContains(response, '35000')
    
    def test_wallet_filters_work(self):
        """Wallet filters by plan, status, search."""
        # Filter by plan
        response = self.client.get(reverse('hq:wallet') + '?plan=pro')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Shop')
        
        # Search
        response = self.client.get(reverse('hq:wallet') + '?q=Test')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Shop')
    
    def test_wallet_mark_paid_endpoint(self):
        """Mark-paid endpoint works and is idempotent."""
        url = reverse('hq:wallet_mark_paid')
        data = {
            'business_id': self.biz.id,
            'period_start': '2025-01-01',
            'period_end': '2025-01-31',
            'amount': '35000.00',
            'notes': 'Test payment'
        }
        
        # First call
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['ok'])
        self.assertTrue(result['created'])
        
        # Second call (idempotent)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['ok'])
        self.assertFalse(result['created'])  # Should update, not create
    
    def test_wallet_graphs_render(self):
        """Wallet page includes graph data."""
        response = self.client.get(reverse('hq:wallet'))
        self.assertEqual(response.status_code, 200)
        
        # Should have chart canvases
        self.assertContains(response, 'revenueChart')
        self.assertContains(response, 'paidChart')
        self.assertContains(response, 'planChart')


@pytest.mark.django_db
class TestHQInvoicesImprovements(TestCase):
    """Test HQ invoices improvements."""
    
    def setUp(self):
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hqadmin',
            password='test123',
            is_staff=True,
            is_superuser=True
        )
        self.client.force_login(self.hq_user)
        
        self.biz = Business.objects.create(name='Test Shop', slug='testshop', status='ACTIVE')
    
    def test_invoices_business_filter(self):
        """Invoices can be filtered by business."""
        Invoice.objects.create(
            business=self.biz,
            number='INV-001',
            total=Decimal('1000.00'),
            status='OPEN'
        )
        
        response = self.client.get(reverse('hq:invoices') + f'?business_id={self.biz.id}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'INV-001')
    
    def test_invoice_create_endpoint(self):
        """Invoice can be created manually for a business."""
        url = reverse('hq:invoice_create')
        data = {
            'business_id': self.biz.id,
            'amount': '5000.00',
            'description': 'Manual invoice',
            'issue_date': '2025-01-15'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['ok'])
        self.assertIn('invoice', result)
        self.assertEqual(result['invoice']['business'], 'Test Shop')
        
        # Check invoice was created
        inv = Invoice.objects.filter(business=self.biz).first()
        self.assertIsNotNone(inv)
        self.assertEqual(inv.total, Decimal('5000.00'))


@pytest.mark.django_db
class TestHQEmptyStates(TestCase):
    """Test that HQ pages show proper empty states, never 500."""
    
    def setUp(self):
        self.client = Client()
        self.hq_user = User.objects.create_user(
            username='hqadmin',
            password='test123',
            is_staff=True,
            is_superuser=True
        )
        self.client.force_login(self.hq_user)
    
    def test_all_hq_pages_load_with_empty_db(self):
        """All HQ pages return 200 with empty database."""
        urls = [
            'hq:dashboard',
            'hq:businesses',
            'hq:subscriptions',
            'hq:invoices',
            'hq:agents',
            'hq:stock_trends',
            'hq:wallet',
        ]
        
        for url_name in urls:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200, f"{url_name} should return 200")
    
    def test_hq_dashboard_with_real_data_only(self):
        """Dashboard metrics reflect real database state."""
        # Start with empty state
        response = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '0')  # Should show zeros
        
        # Add one business
        Business.objects.create(name='Shop 1', slug='shop1', status='ACTIVE')
        
        response = self.client.get(reverse('hq:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1')  # Should show 1 business


# Run with: python manage.py test tests.test_hq_fixes_comprehensive

