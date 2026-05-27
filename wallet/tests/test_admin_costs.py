# wallet/tests/test_admin_costs.py
"""Tests for admin costs creation and recurring flag persistence."""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership
from wallet.models import WalletTransaction, Ledger, TxnType


User = get_user_model()


class AdminCostsTest(TestCase):
    """Test admin cost creation with recurring flag."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123'
        )
        
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            created_by=self.user,
            status='ACTIVE'
        )
        
        # Create manager membership
        self.membership = Membership.objects.create(
            user=self.user,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        self.client = Client()
        self.client.login(username='testmanager', password='testpass123')
    
    def test_create_once_off_cost(self):
        """Test creating a once-off cost."""
        url = reverse('wallet:admin_costs_create')
        
        response = self.client.post(url, {
            'name': 'Equipment Purchase',
            'amount': '50000.00',
            'is_recurring': '0',  # Once-off
        })
        
        self.assertEqual(response.status_code, 302)  # Redirect after success
        
        # Verify cost was created correctly
        cost = WalletTransaction.objects.filter(
            business=self.business,
            ledger=Ledger.COMPANY,
            note='Equipment Purchase'
        ).first()
        
        self.assertIsNotNone(cost)
        self.assertEqual(cost.amount, Decimal('-50000.00'))  # Negative for expense
        self.assertEqual(cost.type, TxnType.COST_ONCE_OFF)
        self.assertFalse(cost.is_recurring, "Once-off cost should have is_recurring=False")
    
    def test_create_recurring_cost(self):
        """Test creating a recurring cost."""
        url = reverse('wallet:admin_costs_create')
        
        response = self.client.post(url, {
            'name': 'Monthly Rent',
            'amount': '120000.00',
            'is_recurring': '1',  # Recurring
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Verify cost was created correctly
        cost = WalletTransaction.objects.filter(
            business=self.business,
            ledger=Ledger.COMPANY,
            note='Monthly Rent'
        ).first()
        
        self.assertIsNotNone(cost)
        self.assertEqual(cost.amount, Decimal('-120000.00'))
        self.assertEqual(cost.type, TxnType.COST_RECURRING)
        self.assertTrue(cost.is_recurring, "Recurring cost should have is_recurring=True")
    
    def test_update_cost_to_recurring(self):
        """Test updating a once-off cost to recurring."""
        # Create once-off cost
        cost = WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_ONCE_OFF,
            amount=Decimal('-30000.00'),
            note='Utilities',
            business=self.business,
            created_by=self.user,
            is_recurring=False
        )
        
        url = reverse('wallet:admin_costs_update', args=[cost.id])
        
        response = self.client.post(url, {
            'name': 'Utilities',
            'amount': '30000.00',
            'is_recurring': '1',  # Change to recurring
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Verify cost was updated
        cost.refresh_from_db()
        self.assertEqual(cost.type, TxnType.COST_RECURRING)
        self.assertTrue(cost.is_recurring, "Cost should now be recurring after update")
    
    def test_update_cost_to_once_off(self):
        """Test updating a recurring cost to once-off."""
        # Create recurring cost
        cost = WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal('-50000.00'),
            note='Temporary Expense',
            business=self.business,
            created_by=self.user,
            is_recurring=True
        )
        
        url = reverse('wallet:admin_costs_update', args=[cost.id])
        
        response = self.client.post(url, {
            'name': 'Temporary Expense',
            'amount': '50000.00',
            'is_recurring': '0',  # Change to once-off
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Verify cost was updated
        cost.refresh_from_db()
        self.assertEqual(cost.type, TxnType.COST_ONCE_OFF)
        self.assertFalse(cost.is_recurring, "Cost should now be once-off after update")

