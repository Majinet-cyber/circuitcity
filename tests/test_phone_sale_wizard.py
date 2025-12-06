# tests/test_phone_sale_wizard.py
"""
Tests for phone sale wizard v2.
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership, Location
from inventory.models import InventoryItem, Product
from sales.models import Sale, CommissionConfig
from wallet.models import WalletTransaction

User = get_user_model()


@pytest.mark.django_db
class TestPhoneSaleWizard(TestCase):
    """Test the 3-step phone sale wizard."""
    
    def setUp(self):
        """Create test data."""
        self.client = Client()
        
        # Create business and location
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business"
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store"
        )
        
        # Create agent
        self.agent = User.objects.create_user(
            username="agent1",
            password="testpass123"
        )
        self.agent_membership = Membership.objects.create(
            user=self.agent,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        # Create product
        self.product = Product.objects.create(
            name="iPhone 13",
            brand="Apple",
            model="13",
            business=self.business,
            sale_price=Decimal('500000')
        )
        
        # Create in-stock item assigned to agent
        self.stock = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012345",
            status="IN_STOCK",
            current_location=self.location,
            assigned_agent=self.agent,
            assigned_role="AGENT",
            order_price=Decimal('400000'),
            selling_price=Decimal('500000')
        )
        
        # Create commission config
        CommissionConfig.objects.create(
            business=self.business,
            base_commission_pct=Decimal('10.00'),
            is_active=True
        )
    
    def test_wizard_full_flow_creates_sale_and_commission(self):
        """Complete wizard flow should create sale and commission."""
        self.client.login(username='agent1', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Step 1: POST IMEI
        response = self.client.post(
            reverse('inventory:phone_sale_wizard_v2'),
            {'imei': '123456789012345'}
        )
        self.assertEqual(response.status_code, 302)  # Redirect to step 2
        
        # Step 2: POST price
        response = self.client.post(
            reverse('inventory:phone_sale_wizard_v2') + '?step=2',
            {'selling_price': '550000'}
        )
        self.assertEqual(response.status_code, 302)  # Redirect to step 3
        
        # Step 3: POST payment method
        response = self.client.post(
            reverse('inventory:phone_sale_wizard_v2') + '?step=3',
            {'payment_method': 'CASH'}
        )
        self.assertEqual(response.status_code, 302)  # Redirect after sale
        
        # Verify sale was created
        sale = Sale.objects.filter(
            item=self.stock,
            agent=self.agent
        ).first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.price, Decimal('550000'))
        self.assertEqual(sale.payment_method, 'CASH')
        
        # Verify stock is marked sold
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.status, 'SOLD')
        self.assertEqual(self.stock.selling_price, Decimal('550000'))
        
        # Verify commission transaction was created
        commission_txn = WalletTransaction.objects.filter(
            agent=self.agent,
            type='commission',
            business=self.business
        ).first()
        self.assertIsNotNone(commission_txn)
        # Commission should be 10% of 550000 = 55000
        self.assertEqual(commission_txn.amount, Decimal('55000.00'))
    
    def test_wizard_rejects_unknown_imei(self):
        """Wizard should reject IMEI not in stock."""
        self.client.login(username='agent1', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Step 1: POST unknown IMEI
        response = self.client.post(
            reverse('inventory:phone_sale_wizard_v2'),
            {'imei': '999999999999999'}
        )
        
        # Should stay on step 1 with error
        self.assertEqual(response.status_code, 200)
        # Check for error message in context or messages framework
    
    def test_agent_cannot_sell_stock_not_assigned_to_them(self):
        """Agent should not be able to sell stock not assigned to them."""
        # Create second agent
        agent2 = User.objects.create_user(
            username="agent2",
            password="testpass123"
        )
        Membership.objects.create(
            user=agent2,
            business=self.business,
            location=self.location,
            role='AGENT',
            status='ACTIVE'
        )
        
        # Create stock assigned to agent2
        stock2 = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012346",
            status="IN_STOCK",
            current_location=self.location,
            assigned_agent=agent2,
            assigned_role="AGENT"
        )
        
        # Login as agent1
        self.client.login(username='agent1', password='testpass123')
        
        # Set active business in session
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Try to sell stock2 (assigned to agent2)
        response = self.client.post(
            reverse('inventory:phone_sale_wizard_v2'),
            {'imei': '123456789012346'}
        )
        
        # Should fail - stock not found for this agent
        self.assertEqual(response.status_code, 200)
        # Should show error that stock is not available

