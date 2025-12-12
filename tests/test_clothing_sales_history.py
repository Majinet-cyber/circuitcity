"""
Tests for Clothing Sales History feature.
Covers sales history page, CSV export, and JSON trend endpoint.
"""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingSale, PaymentMethod
from tenants.models import Business, Membership

User = get_user_model()


class ClothingSalesHistoryTestCase(TestCase):
    """Test clothing sales history page, export, and API endpoints."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create test user
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123'
        )
        
        # Create test business (clothing)
        self.business = Business.objects.create(
            name='Test Clothing Store',
            slug='test-clothing-store',
            business_kind=BusinessKind.CLOTHING,
            created_by=self.user,
            status='ACTIVE'
        )
        
        # Create membership
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create test products
        self.product1 = MerchProduct.objects.create(
            business=self.business,
            name='Suit - L - Black',
            kind=BusinessKind.CLOTHING,
            category='suit',
            size='L',
            color='Black',
            cost_price=Decimal('200.00'),
            selling_price=Decimal('350.00'),
            quantity_in_stock=10,
            is_active=True
        )
        
        self.product2 = MerchProduct.objects.create(
            business=self.business,
            name='Dress - M - Red',
            kind=BusinessKind.CLOTHING,
            category='dress',
            size='M',
            color='Red',
            cost_price=Decimal('150.00'),
            selling_price=Decimal('250.00'),
            quantity_in_stock=15,
            is_active=True
        )
        
        # Create test sales
        today = timezone.now()
        self.sale1 = ClothingSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=2,
            unit_price=Decimal('350.00'),
            total_price=Decimal('700.00'),
            unit_cost=Decimal('200.00'),
            total_cost=Decimal('400.00'),
            payment_method=PaymentMethod.CASH,
            sold_by=self.user,
            sold_at=today,
            notes='Test sale 1'
        )
        
        self.sale2 = ClothingSale.objects.create(
            business=self.business,
            product=self.product2,
            quantity=1,
            unit_price=Decimal('250.00'),
            total_price=Decimal('250.00'),
            unit_cost=Decimal('150.00'),
            total_cost=Decimal('150.00'),
            payment_method=PaymentMethod.BANK,
            sold_by=self.user,
            sold_at=today - timedelta(days=1),
            notes='Test sale 2'
        )
        
        self.sale3 = ClothingSale.objects.create(
            business=self.business,
            product=self.product1,
            quantity=1,
            unit_price=Decimal('350.00'),
            total_price=Decimal('350.00'),
            unit_cost=Decimal('200.00'),
            total_cost=Decimal('200.00'),
            payment_method=PaymentMethod.MOBILE_MONEY,
            sold_by=self.user,
            sold_at=today - timedelta(days=5)
        )
        
        # Set up client
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_sales_history_page_loads(self):
        """Test that sales history page loads successfully."""
        url = reverse('verticals:clothing_sales_history')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'verticals/clothing/sales_history.html')
        self.assertIn('sales', response.context)
        self.assertIn('summary', response.context)
    
    def test_sales_history_shows_all_sales(self):
        """Test that sales history displays all sales."""
        url = reverse('verticals:clothing_sales_history')
        response = self.client.get(url)
        
        # Check that all 3 sales are present
        sales = list(response.context['sales'])
        self.assertEqual(len(sales), 3)
        
        # Check summary stats
        summary = response.context['summary']
        self.assertEqual(summary['total_sales'], 3)
        self.assertEqual(summary['total_revenue'], Decimal('1300.00'))
        self.assertEqual(summary['total_cost'], Decimal('750.00'))
    
    def test_sales_history_date_filter(self):
        """Test sales history with date range filter."""
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        
        url = reverse('verticals:clothing_sales_history')
        response = self.client.get(url, {
            'start': yesterday.isoformat(),
            'end': today.isoformat()
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Should show 2 sales (today and yesterday)
        sales = list(response.context['sales'])
        self.assertEqual(len(sales), 2)
    
    def test_sales_history_search_filter(self):
        """Test sales history search functionality."""
        url = reverse('verticals:clothing_sales_history')
        
        # Search by product name
        response = self.client.get(url, {'q': 'Suit'})
        self.assertEqual(response.status_code, 200)
        sales = list(response.context['sales'])
        self.assertEqual(len(sales), 2)  # Two suit sales
        
        # Search by category
        response = self.client.get(url, {'q': 'dress'})
        self.assertEqual(response.status_code, 200)
        sales = list(response.context['sales'])
        self.assertEqual(len(sales), 1)  # One dress sale
    
    def test_sales_history_pagination(self):
        """Test sales history pagination."""
        # Create many sales to test pagination
        for i in range(55):
            ClothingSale.objects.create(
                business=self.business,
                product=self.product1,
                quantity=1,
                unit_price=Decimal('100.00'),
                total_price=Decimal('100.00'),
                unit_cost=Decimal('50.00'),
                total_cost=Decimal('50.00'),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user
            )
        
        url = reverse('verticals:clothing_sales_history')
        
        # Page 1 should have 50 items
        response = self.client.get(url, {'page': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(list(response.context['sales'])), 50)
        
        # Page 2 should have remaining items
        response = self.client.get(url, {'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(list(response.context['sales'])), 0)
    
    def test_sales_history_highlights_specific_sale(self):
        """Test that specific sale is highlighted when sale_id is provided."""
        url = reverse('verticals:clothing_sales_history')
        response = self.client.get(url, {'sale_id': self.sale1.id})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['highlighted_sale_id'], self.sale1.id)
    
    def test_csv_export_returns_csv(self):
        """Test that CSV export returns correct content type."""
        url = reverse('verticals:clothing_sales_export_csv')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('clothing_sales_', response['Content-Disposition'])
    
    def test_csv_export_includes_timestamp_column(self):
        """Test that CSV export includes Timestamp column."""
        url = reverse('verticals:clothing_sales_export_csv')
        response = self.client.get(url)
        
        content = response.content.decode('utf-8')
        lines = content.split('\r\n')
        
        # Check header row
        header = lines[0]
        self.assertIn('Timestamp', header)
        self.assertIn('Date', header)
        self.assertIn('Time', header)
        self.assertIn('Item', header)
        self.assertIn('Payment Method', header)
        self.assertIn('Cashier', header)
    
    def test_csv_export_respects_filters(self):
        """Test that CSV export respects date and search filters."""
        today = timezone.now().date()
        
        url = reverse('verticals:clothing_sales_export_csv')
        response = self.client.get(url, {
            'start': today.isoformat(),
            'end': today.isoformat()
        })
        
        content = response.content.decode('utf-8')
        lines = [line for line in content.split('\r\n') if line.strip()]
        
        # Header + 1 sale (only today's sale)
        self.assertEqual(len(lines), 2)
    
    def test_sales_trend_json_returns_json(self):
        """Test that sales trend API returns valid JSON."""
        url = reverse('verticals:clothing_sales_trend_json')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        data = json.loads(response.content)
        self.assertIn('labels', data)
        self.assertIn('revenue', data)
        self.assertIn('count', data)
        self.assertIn('timestamp', data)
    
    def test_sales_trend_json_has_matching_arrays(self):
        """Test that sales trend JSON has arrays of same length."""
        url = reverse('verticals:clothing_sales_trend_json')
        response = self.client.get(url)
        
        data = json.loads(response.content)
        
        # All arrays should have same length
        labels_len = len(data['labels'])
        self.assertEqual(len(data['revenue']), labels_len)
        self.assertEqual(len(data['count']), labels_len)
    
    def test_sales_trend_json_respects_range_param(self):
        """Test that sales trend respects range parameter."""
        url = reverse('verticals:clothing_sales_trend_json')
        
        # Test with '7d' range
        response = self.client.get(url, {'range': '7d'})
        data = json.loads(response.content)
        self.assertEqual(data['period'], '7d')
        self.assertEqual(len(data['labels']), 7)
        
        # Test with 'today' range
        response = self.client.get(url, {'range': 'today'})
        data = json.loads(response.content)
        self.assertEqual(data['period'], 'today')
        self.assertEqual(len(data['labels']), 1)
    
    def test_sales_trend_includes_cache_busting(self):
        """Test that sales trend includes timestamp for cache busting."""
        url = reverse('verticals:clothing_sales_trend_json')
        response = self.client.get(url)
        
        data = json.loads(response.content)
        self.assertIn('timestamp', data)
        # Timestamp should be a valid ISO format string
        self.assertIsNotNone(data['timestamp'])
    
    def test_requires_authentication(self):
        """Test that endpoints require authentication."""
        self.client.logout()
        
        # Sales history
        url = reverse('verticals:clothing_sales_history')
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)
        
        # CSV export
        url = reverse('verticals:clothing_sales_export_csv')
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)
        
        # JSON trend
        url = reverse('verticals:clothing_sales_trend_json')
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)
    
    def test_requires_clothing_business(self):
        """Test that endpoints require business kind to be CLOTHING."""
        # Change business kind to something else
        self.business.business_kind = BusinessKind.PHONES
        self.business.save()
        
        # Sales history should not be accessible
        url = reverse('verticals:clothing_sales_history')
        response = self.client.get(url)
        # Should redirect or show 403/404
        self.assertNotEqual(response.status_code, 200)
    
    def test_dashboard_sales_card_link(self):
        """Test that dashboard has clickable sales card."""
        url = reverse('verticals:clothing_dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Check that sales history link exists
        sales_history_url = reverse('verticals:clothing_sales_history')
        self.assertIn(sales_history_url, content)

