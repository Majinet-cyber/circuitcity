"""
Tests for vertical sales history features (phones, liquor, pharmacy).
Ensures sales history, CSV export, and trend JSON endpoints work correctly for all verticals.
"""
from decimal import Decimal
from datetime import datetime, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import Location, InventoryItem, Product, MerchProduct
from inventory.models_verticals import LiquorSale, PaymentMethod
from inventory.models_pharmacy import PharmacyBatch, PharmacySale
from inventory.business_kinds import BusinessKind
from sales.models import Sale


class PhonesVerticalSalesHistoryTests(TestCase):
    """Tests for phones vertical sales history"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.business = Business.objects.create(
            name='Test Phone Store',
            kind=BusinessKind.PHONES
        )
        Membership.objects.create(user=self.user, business=self.business, role='manager')
        
        self.location = Location.objects.create(
            business=self.business,
            name='Main Store'
        )
        
        # Create a phone product
        self.product = Product.objects.create(
            brand='Samsung',
            model='Galaxy S21',
            variant='256GB'
        )
        
        # Create inventory items and sales
        for i in range(5):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.product,
                imei=f'12345678901234{i}',
                order_price=Decimal('2000.00'),
                selling_price=Decimal('2500.00'),
                status='SOLD',
                sold_at=timezone.now() - timedelta(days=i),
                current_location=self.location
            )
            
            Sale.objects.create(
                item=item,
                agent=self.user,
                location=self.location,
                sold_at=timezone.now().date() - timedelta(days=i),
                price=Decimal('2500.00'),
                payment_method='CASH'
            )
    
    def test_sales_history_page_loads(self):
        """Test that phones sales history page loads correctly"""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('verticals:phones_sales_history')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sales History')
        self.assertContains(response, 'Samsung')
    
    def test_sales_history_date_filter(self):
        """Test that date filtering works"""
        self.client.login(username='testuser', password='testpass123')
        
        today = timezone.now().date()
        url = reverse('verticals:phones_sales_history')
        response = self.client.get(url, {'start': today.isoformat(), 'end': today.isoformat()})
        
        self.assertEqual(response.status_code, 200)
        # Should only show today's sale
        self.assertContains(response, 'Sales History')
    
    def test_sales_history_search(self):
        """Test that search works"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('verticals:phones_sales_history')
        response = self.client.get(url, {'q': 'Samsung'})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Samsung')
    
    def test_sales_export_csv(self):
        """Test that CSV export works"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('verticals:phones_sales_export_csv')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertContains(response, 'IMEI')
        self.assertContains(response, 'Samsung')
    
    def test_sales_trend_json(self):
        """Test that trend JSON endpoint works"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('verticals:phones_sales_trend_json')
        response = self.client.get(url, {'range': '7d'})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertIn('labels', data)
        self.assertIn('revenue', data)
        self.assertIn('count', data)
    
    def test_sales_history_requires_correct_business_kind(self):
        """Test that phones sales history rejects wrong business kind"""
        # Change business kind to clothing
        self.business.kind = BusinessKind.CLOTHING
        self.business.save()
        
        self.client.login(username='testuser', password='testpass123')
        url = reverse('verticals:phones_sales_history')
        response = self.client.get(url)
        
        # Should redirect or return error (not 200)
        self.assertNotEqual(response.status_code, 200)


class LiquorVerticalSalesHistoryTests(TestCase):
    """Tests for liquor vertical sales history"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='barman', password='testpass123')
        self.business = Business.objects.create(
            name='Test Bar',
            kind=BusinessKind.LIQUOR
        )
        Membership.objects.create(user=self.user, business=self.business, role='manager')
        
        # Create a liquor product
        self.product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.LIQUOR,
            name='Mosi Lager',
            category='beer',
            is_active=True
        )
        
        # Create sales
        for i in range(5):
            LiquorSale.objects.create(
                business=self.business,
                product=self.product,
                unit='bottle',
                quantity=i + 1,
                unit_price=Decimal('25.00'),
                total_price=Decimal('25.00') * (i + 1),
                unit_cost=Decimal('15.00'),
                total_cost=Decimal('15.00') * (i + 1),
                payment_method=PaymentMethod.CASH,
                sold_by=self.user,
                sold_at=timezone.now() - timedelta(days=i)
            )
    
    def test_sales_history_page_loads(self):
        """Test that liquor sales history page loads correctly"""
        self.client.login(username='barman', password='testpass123')
        url = reverse('verticals:liquor_sales_history')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sales History')
        self.assertContains(response, 'Mosi Lager')
    
    def test_sales_history_date_filter(self):
        """Test that date filtering works"""
        self.client.login(username='barman', password='testpass123')
        
        today = timezone.now().date()
        url = reverse('verticals:liquor_sales_history')
        response = self.client.get(url, {'start': today.isoformat(), 'end': today.isoformat()})
        
        self.assertEqual(response.status_code, 200)
    
    def test_sales_history_search(self):
        """Test that search works"""
        self.client.login(username='barman', password='testpass123')
        
        url = reverse('verticals:liquor_sales_history')
        response = self.client.get(url, {'q': 'Mosi'})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mosi Lager')
    
    def test_sales_export_csv(self):
        """Test that CSV export works"""
        self.client.login(username='barman', password='testpass123')
        
        url = reverse('verticals:liquor_sales_export_csv')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertContains(response, 'Mosi Lager')
    
    def test_sales_trend_json(self):
        """Test that trend JSON endpoint works"""
        self.client.login(username='barman', password='testpass123')
        
        url = reverse('verticals:liquor_sales_trend_json')
        response = self.client.get(url, {'range': '7d'})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertIn('labels', data)
        self.assertIn('revenue', data)
        self.assertIn('count', data)


class PharmacyVerticalSalesHistoryTests(TestCase):
    """Tests for pharmacy vertical sales history"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='pharmacist', password='testpass123')
        self.business = Business.objects.create(
            name='Test Pharmacy',
            kind=BusinessKind.PHARMACY
        )
        Membership.objects.create(user=self.user, business=self.business, role='manager')
        
        # Create a pharmacy product
        self.product = MerchProduct.objects.create(
            business=self.business,
            kind=BusinessKind.PHARMACY,
            name='Paracetamol 500mg',
            is_active=True
        )
        
        # Create a batch
        self.batch = PharmacyBatch.objects.create(
            merch_product=self.product,
            business=self.business,
            batch_number='BATCH001',
            quantity=100,
            unit_cost_price=Decimal('2.00'),
            unit_selling_price=Decimal('5.00'),
            expiry_date=timezone.now().date() + timedelta(days=365)
        )
        
        # Create sales
        for i in range(5):
            PharmacySale.objects.create(
                business=self.business,
                batch=self.batch,
                quantity=i + 1,
                unit_price=Decimal('5.00'),
                unit_cost=Decimal('2.00'),
                total_amount=Decimal('5.00') * (i + 1),
                payment_method='CASH',
                sold_by=self.user,
                sold_at=timezone.now() - timedelta(days=i)
            )
    
    def test_sales_history_page_loads(self):
        """Test that pharmacy sales history page loads correctly"""
        self.client.login(username='pharmacist', password='testpass123')
        url = reverse('verticals:pharmacy_sales_history')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sales History')
        self.assertContains(response, 'Paracetamol')
    
    def test_sales_history_date_filter(self):
        """Test that date filtering works"""
        self.client.login(username='pharmacist', password='testpass123')
        
        today = timezone.now().date()
        url = reverse('verticals:pharmacy_sales_history')
        response = self.client.get(url, {'start': today.isoformat(), 'end': today.isoformat()})
        
        self.assertEqual(response.status_code, 200)
    
    def test_sales_history_search(self):
        """Test that search works"""
        self.client.login(username='pharmacist', password='testpass123')
        
        url = reverse('verticals:pharmacy_sales_history')
        response = self.client.get(url, {'q': 'Paracetamol'})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paracetamol')
    
    def test_sales_export_csv(self):
        """Test that CSV export works"""
        self.client.login(username='pharmacist', password='testpass123')
        
        url = reverse('verticals:pharmacy_sales_export_csv')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertContains(response, 'Paracetamol')
    
    def test_sales_trend_json(self):
        """Test that trend JSON endpoint works"""
        self.client.login(username='pharmacist', password='testpass123')
        
        url = reverse('verticals:pharmacy_sales_trend_json')
        response = self.client.get(url, {'range': '7d'})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertIn('labels', data)
        self.assertIn('revenue', data)
        self.assertIn('count', data)

