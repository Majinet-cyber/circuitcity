# tests/test_wallet_adjustment.py
"""
Tests for agent wallet manual adjustments by admins/managers.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import Location
from wallet.agent_models import (
    AgentWallet,
    AgentWalletTransaction,
    AgentWalletTransactionType,
    add_commission,
    get_or_create_agent_wallet,
)

User = get_user_model()


@pytest.mark.django_db
class TestAgentWalletAdjustment(TestCase):
    """Test manual wallet adjustments by admins."""

    def setUp(self):
        """Set up test fixtures."""
        # Create business
        self.business = Business.objects.create(
            name="Test Shop",
            business_kind="PHONES",
            slug="test-adjustment-shop",
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
        )
        
        # Create admin/manager user
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123",
            is_staff=True,
        )
        
        # Create manager membership
        self.manager_membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
        
        # Create agent user
        self.agent = User.objects.create_user(
            username="agent@test.com",
            email="agent@test.com",
            password="testpass123",
        )
        
        # Create agent membership
        self.agent_membership = Membership.objects.create(
            user=self.agent,
            business=self.business,
            location=self.location,
            role="AGENT",
            status="ACTIVE",
        )
        
        # Give agent some starting balance
        add_commission(self.agent_membership, Decimal("1000.00"), "Starting balance")
        
        self.client = Client()
        
    def test_admin_can_access_adjustment_form(self):
        """Test that admin/manager can access the adjustment form."""
        self.client.login(username="manager@test.com", password="testpass123")
        
        # Set active business
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('wallet:wallet_adjust_agent', args=[self.agent_membership.id])
        response = self.client.get(url)
        
        # Should return 200
        self.assertEqual(response.status_code, 200)
        
        # Check context has correct data
        self.assertEqual(response.context['membership'], self.agent_membership)
        self.assertIsNotNone(response.context['wallet'])
        self.assertIn('form', response.context)
        
    def test_agent_cannot_access_adjustment_form(self):
        """Test that regular agents cannot access adjustment form."""
        self.client.login(username="agent@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('wallet:wallet_adjust_agent', args=[self.agent_membership.id])
        response = self.client.get(url)
        
        # Should redirect (access denied)
        self.assertEqual(response.status_code, 302)
        
    def test_admin_can_add_credit(self):
        """Test admin can add money to agent wallet."""
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Get starting balance
        wallet = get_or_create_agent_wallet(self.agent_membership)
        starting_balance = wallet.balance
        
        url = reverse('wallet:wallet_adjust_agent', args=[self.agent_membership.id])
        response = self.client.post(url, {
            'membership': self.agent_membership.id,
            'amount': '500.00',
            'is_deduction': False,  # Credit
            'reason': 'Performance bonus for exceeding target',
        })
        
        # Should redirect (success)
        self.assertEqual(response.status_code, 302)
        
        # Check wallet balance updated
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, starting_balance + Decimal("500.00"))
        
        # Check transaction created
        txn = AgentWalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type=AgentWalletTransactionType.ADJUSTMENT_MANUAL,
            is_debit=False,
            amount=Decimal("500.00"),
        ).first()
        
        self.assertIsNotNone(txn)
        self.assertEqual(txn.reason, 'Performance bonus for exceeding target')
        self.assertEqual(txn.created_by, self.manager)
        
    def test_admin_can_deduct(self):
        """Test admin can deduct money from agent wallet."""
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        wallet = get_or_create_agent_wallet(self.agent_membership)
        starting_balance = wallet.balance
        
        url = reverse('wallet:wallet_adjust_agent', args=[self.agent_membership.id])
        response = self.client.post(url, {
            'membership': self.agent_membership.id,
            'amount': '200.00',
            'is_deduction': True,  # Debit
            'reason': 'Deduction for lost inventory item',
        })
        
        # Should redirect (success)
        self.assertEqual(response.status_code, 302)
        
        # Check wallet balance updated
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, starting_balance - Decimal("200.00"))
        
        # Check transaction created
        txn = AgentWalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type=AgentWalletTransactionType.ADJUSTMENT_MANUAL,
            is_debit=True,
            amount=Decimal("200.00"),
        ).first()
        
        self.assertIsNotNone(txn)
        self.assertEqual(txn.reason, 'Deduction for lost inventory item')
        
    def test_cannot_deduct_more_than_balance(self):
        """Test that deduction fails if amount exceeds balance."""
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        wallet = get_or_create_agent_wallet(self.agent_membership)
        
        url = reverse('wallet:wallet_adjust_agent', args=[self.agent_membership.id])
        response = self.client.post(url, {
            'membership': self.agent_membership.id,
            'amount': str(wallet.balance + Decimal("100.00")),  # More than balance
            'is_deduction': True,
            'reason': 'Attempting to overdraw',
        })
        
        # Should show form with errors (200 status)
        self.assertEqual(response.status_code, 200)
        
        # Form should have validation error
        self.assertIn('form', response.context)
        self.assertTrue(response.context['form'].errors)
        
    def test_reason_is_required(self):
        """Test that reason field is required."""
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('wallet:wallet_adjust_agent', args=[self.agent_membership.id])
        response = self.client.post(url, {
            'membership': self.agent_membership.id,
            'amount': '100.00',
            'is_deduction': False,
            'reason': '',  # Empty reason
        })
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertIn('reason', response.context['form'].errors)
        
    def test_reason_must_be_meaningful(self):
        """Test that reason must be at least 10 characters."""
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('wallet:wallet_adjust_agent', args=[self.agent_membership.id])
        response = self.client.post(url, {
            'membership': self.agent_membership.id,
            'amount': '100.00',
            'is_deduction': False,
            'reason': 'short',  # Too short
        })
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        
    def test_amount_must_be_positive(self):
        """Test that amount must be greater than zero."""
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('wallet:wallet_adjust_agent', args=[self.agent_membership.id])
        
        # Try zero amount
        response = self.client.post(url, {
            'membership': self.agent_membership.id,
            'amount': '0.00',
            'is_deduction': False,
            'reason': 'Testing zero amount validation',
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        
        # Try negative amount
        response = self.client.post(url, {
            'membership': self.agent_membership.id,
            'amount': '-50.00',
            'is_deduction': False,
            'reason': 'Testing negative amount validation',
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        
    def test_adjustment_creates_audit_trail(self):
        """Test that adjustments create proper audit trail."""
        self.client.login(username="manager@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        url = reverse('wallet:wallet_adjust_agent', args=[self.agent_membership.id])
        
        # Make adjustment
        response = self.client.post(url, {
            'membership': self.agent_membership.id,
            'amount': '300.00',
            'is_deduction': False,
            'reason': 'Quarterly performance bonus',
        })
        
        # Get transaction
        wallet = get_or_create_agent_wallet(self.agent_membership)
        txn = AgentWalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type=AgentWalletTransactionType.ADJUSTMENT_MANUAL,
        ).first()
        
        # Verify audit trail fields
        self.assertIsNotNone(txn.created_by)
        self.assertEqual(txn.created_by, self.manager)
        self.assertIsNotNone(txn.reason)
        self.assertIsNotNone(txn.created_at)
        self.assertIsNotNone(txn.effective_date)

