# wallet/tests/test_cost_management.py
"""
Tests for admin wallet cost management.
Ensures managers can create, view, edit, and delete business costs.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from wallet.models import WalletTransaction, TxnType, Ledger
from wallet.services_costs import (
    get_business_costs_for_period,
    add_business_cost,
    get_recurring_costs_for_month,
    get_cost_breakdown_by_category
)
from tenants.models import Business, Membership

User = get_user_model()


@pytest.mark.django_db
class TestCostServices(TestCase):
    """Test cost calculation services."""

    def setUp(self):
        """Set up test fixtures."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business"
        )
        
        self.today = timezone.localdate()
        
    def test_add_business_cost(self):
        """Test adding a business cost."""
        cost = add_business_cost(
            business=self.business,
            name="Office Rent",
            amount=Decimal("50000.00"),
            cost_category='fixed',
            is_recurring=True,
            effective_date=self.today
        )
        
        self.assertIsNotNone(cost)
        self.assertEqual(cost.business, self.business)
        self.assertEqual(cost.ledger, Ledger.COMPANY)
        self.assertEqual(cost.type, TxnType.COST_RECURRING)
        self.assertTrue(cost.is_recurring)
        # Costs are stored as negative
        self.assertEqual(cost.amount, Decimal("-50000.00"))
        self.assertIn("Office Rent", cost.note)
        self.assertEqual(cost.meta.get('cost_category'), 'fixed')
        self.assertEqual(cost.meta.get('cost_name'), 'Office Rent')

    def test_get_business_costs_for_month(self):
        """Test retrieving costs for current month."""
        # Add some costs
        add_business_cost(
            business=self.business,
            name="Fixed Cost 1",
            amount=Decimal("10000.00"),
            cost_category='fixed',
            is_recurring=False,
            effective_date=self.today
        )
        
        add_business_cost(
            business=self.business,
            name="Variable Cost 1",
            amount=Decimal("5000.00"),
            cost_category='variable',
            is_recurring=False,
            effective_date=self.today
        )
        
        # Get costs for current month
        costs = get_business_costs_for_period(self.business, period='month')
        
        self.assertGreater(costs['overall_costs_total'], 0)
        self.assertEqual(costs['period_start'].month, self.today.month)
        self.assertEqual(costs['period_start'].year, self.today.year)

    def test_get_cost_breakdown_by_category(self):
        """Test cost breakdown by fixed vs variable."""
        month_start = self.today.replace(day=1)
        if self.today.month == 12:
            month_end = self.today.replace(month=12, day=31)
        else:
            month_end = (self.today.replace(month=self.today.month + 1, day=1) - timedelta(days=1))
        
        # Add fixed cost
        add_business_cost(
            business=self.business,
            name="Rent",
            amount=Decimal("50000.00"),
            cost_category='fixed',
            is_recurring=True,
            effective_date=self.today
        )
        
        # Add variable cost
        add_business_cost(
            business=self.business,
            name="Utilities",
            amount=Decimal("15000.00"),
            cost_category='variable',
            is_recurring=False,
            effective_date=self.today
        )
        
        # Get breakdown
        breakdown = get_cost_breakdown_by_category(self.business, month_start, month_end)
        
        self.assertEqual(len(breakdown['fixed']), 1)
        self.assertEqual(len(breakdown['variable']), 1)
        self.assertEqual(breakdown['fixed_total'], Decimal("50000.00"))
        self.assertEqual(breakdown['variable_total'], Decimal("15000.00"))

    def test_recurring_costs_for_month(self):
        """Test retrieving recurring costs for a specific month."""
        # Add recurring cost
        add_business_cost(
            business=self.business,
            name="Monthly Subscription",
            amount=Decimal("5000.00"),
            cost_category='fixed',
            is_recurring=True,
            effective_date=self.today.replace(day=1)
        )
        
        # Get recurring costs for this month
        total = get_recurring_costs_for_month(
            self.business,
            self.today.year,
            self.today.month
        )
        
        self.assertEqual(total, Decimal("5000.00"))


@pytest.mark.django_db
class TestCostViews(TestCase):
    """Test cost management views."""

    def setUp(self):
        """Set up test fixtures."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business"
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager1",
            email="manager@test.com",
            password="password123"
        )
        self.manager.is_staff = True
        self.manager.save()
        
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role='MANAGER',
            status='ACTIVE'
        )
        
        # Create agent user
        self.agent = User.objects.create_user(
            username="agent1",
            email="agent@test.com",
            password="password123"
        )
        
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            role='AGENT',
            status='ACTIVE'
        )
        
        self.client = Client()
        self.today = timezone.localdate()

    def test_admin_cost_list_view(self):
        """Test cost list view for managers."""
        self.client.login(username="manager1", password="password123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Add a cost first
        add_business_cost(
            business=self.business,
            name="Test Cost",
            amount=Decimal("10000.00"),
            cost_category='fixed',
            is_recurring=False,
            effective_date=self.today
        )
        
        response = self.client.get(reverse('wallet:admin_cost_list'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('cost_summary', response.context)
        self.assertIn('fixed_costs', response.context)

    def test_agent_cannot_access_cost_views(self):
        """Test that agents cannot access cost management views."""
        self.client.login(username="agent1", password="password123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.get(reverse('wallet:admin_cost_list'))
        
        # Should redirect with error
        self.assertEqual(response.status_code, 302)

    def test_manager_can_create_cost(self):
        """Test manager creating a new cost."""
        self.client.login(username="manager1", password="password123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.post(
            reverse('wallet:admin_cost_create'),
            {
                'name': 'Office Supplies',
                'amount': '15000.00',
                'cost_category': 'variable',
                'is_recurring': '',  # Not recurring
                'effective_date': self.today.isoformat(),
                'note': 'Monthly office supplies purchase'
            }
        )
        
        # Should redirect to cost list after successful creation
        self.assertEqual(response.status_code, 302)
        
        # Verify cost was created
        cost = WalletTransaction.objects.filter(
            business=self.business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        ).first()
        
        self.assertIsNotNone(cost)
        self.assertEqual(abs(cost.amount), Decimal("15000.00"))

    def test_manager_can_edit_cost(self):
        """Test manager editing an existing cost."""
        self.client.login(username="manager1", password="password123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create a cost first
        cost = add_business_cost(
            business=self.business,
            name="Original Name",
            amount=Decimal("10000.00"),
            cost_category='fixed',
            is_recurring=False,
            effective_date=self.today
        )
        
        # Edit the cost
        response = self.client.post(
            reverse('wallet:admin_cost_edit', kwargs={'cost_id': cost.id}),
            {
                'name': 'Updated Name',
                'amount': '12000.00',
                'cost_category': 'variable',
                'is_recurring': 'on',  # Now recurring
                'effective_date': self.today.isoformat(),
                'note': 'Updated note'
            }
        )
        
        self.assertEqual(response.status_code, 302)
        
        # Verify cost was updated
        cost.refresh_from_db()
        self.assertEqual(abs(cost.amount), Decimal("12000.00"))
        self.assertTrue(cost.is_recurring)
        self.assertEqual(cost.type, TxnType.COST_RECURRING)

    def test_manager_can_delete_cost(self):
        """Test manager deleting a cost."""
        self.client.login(username="manager1", password="password123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Create a cost
        cost = add_business_cost(
            business=self.business,
            name="Deletable Cost",
            amount=Decimal("5000.00"),
            cost_category='variable',
            is_recurring=False,
            effective_date=self.today
        )
        
        cost_id = cost.id
        
        # Delete the cost
        response = self.client.post(
            reverse('wallet:admin_cost_delete', kwargs={'cost_id': cost.id})
        )
        
        self.assertEqual(response.status_code, 302)
        
        # Verify cost was deleted
        self.assertFalse(
            WalletTransaction.objects.filter(pk=cost_id).exists()
        )

    def test_cost_validation_positive_amount(self):
        """Test that cost amount must be positive."""
        self.client.login(username="manager1", password="password123")
        
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        response = self.client.post(
            reverse('wallet:admin_cost_create'),
            {
                'name': 'Invalid Cost',
                'amount': '-1000.00',  # Negative amount
                'cost_category': 'fixed',
                'is_recurring': '',
                'effective_date': self.today.isoformat(),
                'note': ''
            }
        )
        
        # Should not redirect (form should have errors)
        self.assertEqual(response.status_code, 200)
        
        # No cost should be created
        count = WalletTransaction.objects.filter(
            business=self.business,
            ledger=Ledger.COMPANY
        ).count()
        
        self.assertEqual(count, 0)


@pytest.mark.django_db
class TestCostCalculations(TestCase):
    """Test cost calculation edge cases."""

    def setUp(self):
        """Set up test fixtures."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-business"
        )
        self.today = timezone.localdate()

    def test_multiple_recurring_costs(self):
        """Test handling multiple recurring costs."""
        # Add multiple recurring costs
        for i in range(3):
            add_business_cost(
                business=self.business,
                name=f"Recurring Cost {i+1}",
                amount=Decimal("5000.00"),
                cost_category='fixed',
                is_recurring=True,
                effective_date=self.today.replace(day=1)
            )
        
        # Get total recurring costs
        total = get_recurring_costs_for_month(
            self.business,
            self.today.year,
            self.today.month
        )
        
        self.assertEqual(total, Decimal("15000.00"))

    def test_mixed_cost_categories(self):
        """Test handling mix of fixed and variable costs."""
        month_start = self.today.replace(day=1)
        if self.today.month == 12:
            month_end = self.today.replace(month=12, day=31)
        else:
            month_end = (self.today.replace(month=self.today.month + 1, day=1) - timedelta(days=1))
        
        # Add various costs
        add_business_cost(
            business=self.business,
            name="Fixed 1",
            amount=Decimal("10000.00"),
            cost_category='fixed',
            is_recurring=True,
            effective_date=self.today
        )
        
        add_business_cost(
            business=self.business,
            name="Fixed 2",
            amount=Decimal("8000.00"),
            cost_category='fixed',
            is_recurring=False,
            effective_date=self.today
        )
        
        add_business_cost(
            business=self.business,
            name="Variable 1",
            amount=Decimal("3000.00"),
            cost_category='variable',
            is_recurring=False,
            effective_date=self.today
        )
        
        breakdown = get_cost_breakdown_by_category(self.business, month_start, month_end)
        
        self.assertEqual(breakdown['fixed_total'], Decimal("18000.00"))
        self.assertEqual(breakdown['variable_total'], Decimal("3000.00"))

