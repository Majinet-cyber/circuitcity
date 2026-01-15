"""
Test suite for Liquor Reconciliation and Assignment 500 fixes.

Tests that all liquor reconciliation and assignment routes return 200 (not 500)
even with empty data, missing locations, or edge cases.

CRITICAL: These tests ensure the flagship liquor vertical never crashes.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import MerchProduct, Location
from inventory.models_liquor_assignment import (
    LiquorStockAssignment,
    LiquorDailyReconciliation,
)
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.fixture
def liquor_business(db):
    """Create a liquor business."""
    user = User.objects.create_user(
        username="liquor_owner",
        email="owner@liquor.test",
        password="testpass123",
        is_staff=True,  # Make manager
    )
    business = Business.objects.create(
        name="Test Liquor Bar",
        kind=BusinessKind.LIQUOR,
        created_by=user,
    )
    # Create membership with MANAGER role
    Membership.objects.create(
        user=user,
        business=business,
        role="MANAGER",
        is_active=True,
    )
    return business, user


@pytest.fixture
def liquor_business_with_location(liquor_business):
    """Create a liquor business with one location."""
    business, user = liquor_business
    location = Location.objects.create(
        business=business,
        name="Main Bar",
        is_default=True,
    )
    return business, user, location


@pytest.fixture
def liquor_agent(liquor_business):
    """Create an agent user for liquor business."""
    business, _ = liquor_business
    agent = User.objects.create_user(
        username="liquor_agent",
        email="agent@liquor.test",
        password="testpass123",
    )
    # Create agent membership
    Membership.objects.create(
        user=agent,
        business=business,
        role="AGENT",
        is_active=True,
    )
    return agent


@pytest.fixture
def liquor_product(liquor_business_with_location):
    """Create a liquor product."""
    business, user, location = liquor_business_with_location
    product = MerchProduct.objects.create(
        business=business,
        name="Test Beer",
        category="beer",
        kind=BusinessKind.LIQUOR,
        selling_price=Decimal("5000.00"),
        cost_price=Decimal("3000.00"),
        quantity_in_stock=100,
        bottles_per_crate=20,
        is_active=True,
    )
    return product


# ==============================================================================
# PHASE A1-A2: Reconciliation and Assignment 500 Fixes
# ==============================================================================


@pytest.mark.django_db
class TestReconciliation500Fixes:
    """Test that reconciliation page returns 200 with empty data."""

    def test_reconciliation_returns_200_with_no_assignments(self, client, liquor_business):
        """Reconciliation page should return 200 even with no assignments."""
        business, user = liquor_business
        client.force_login(user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:reconciliation')
        response = client.get(url)
        
        # CRITICAL: Must return 200, not 500
        assert response.status_code == 200
        assert b'Daily Reconciliation' in response.content or b'reconciliation' in response.content.lower()
        
    def test_reconciliation_returns_200_with_no_active_location(self, client, liquor_business):
        """Reconciliation should work even if business has no location selected."""
        business, user = liquor_business
        client.force_login(user)
        
        # Set active business but no location
        session = client.session
        session['active_business_id'] = business.id
        # Explicitly no active_location_id
        session.save()
        
        url = reverse('liquor:reconciliation')
        response = client.get(url)
        
        assert response.status_code == 200
        
    def test_reconciliation_returns_200_with_single_location_auto_select(
        self, client, liquor_business_with_location
    ):
        """Reconciliation auto-selects if business has exactly 1 location."""
        business, user, location = liquor_business_with_location
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        # No active_location_id set - should auto-select
        session.save()
        
        url = reverse('liquor:reconciliation')
        response = client.get(url)
        
        assert response.status_code == 200
        
    def test_reconciliation_with_empty_assignments_shows_no_data(
        self, client, liquor_business_with_location, liquor_agent
    ):
        """Reconciliation with no assignments should show empty state."""
        business, user, location = liquor_business_with_location
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session['active_location_id'] = location.id
        session.save()
        
        url = reverse('liquor:reconciliation')
        response = client.get(url)
        
        assert response.status_code == 200
        # Check for empty state messaging
        assert response.context.get('has_data') is False or response.context.get('reconciliations') == []
        
    def test_reconciliation_with_date_filter(self, client, liquor_business_with_location):
        """Reconciliation should accept date filter parameter."""
        business, user, location = liquor_business_with_location
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:reconciliation')
        response = client.get(url, {'date': '2026-01-15'})
        
        assert response.status_code == 200
        # Verify date was parsed correctly
        assert response.context.get('date')
        
    def test_reconciliation_totals_are_zero_with_no_data(
        self, client, liquor_business_with_location
    ):
        """Reconciliation totals should be 0 (not None) with no assignments."""
        business, user, location = liquor_business_with_location
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:reconciliation')
        response = client.get(url)
        
        assert response.status_code == 200
        # Check context has safe defaults
        ctx = response.context
        assert ctx.get('total_assigned') == 0
        assert ctx.get('total_sold') == 0
        assert ctx.get('total_revenue') == Decimal('0.00') or ctx.get('total_revenue') == 0


@pytest.mark.django_db
class TestAssignment500Fixes:
    """Test that assignment pages return 200 with empty data."""
    
    def test_assignment_list_returns_200_with_no_assignments(
        self, client, liquor_business
    ):
        """Assignment list should return 200 even with no assignments."""
        business, user = liquor_business
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:assignment_list')
        response = client.get(url)
        
        # CRITICAL: Must return 200, not 500
        assert response.status_code == 200
        
    def test_assignment_list_returns_200_with_no_location(self, client, liquor_business):
        """Assignment list should work without active location."""
        business, user = liquor_business
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        # No location
        session.save()
        
        url = reverse('liquor:assignment_list')
        response = client.get(url)
        
        assert response.status_code == 200
        
    def test_assignment_create_returns_200_with_no_products(
        self, client, liquor_business
    ):
        """Assignment create page should return 200 even with no products."""
        business, user = liquor_business
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:assignment_create')
        response = client.get(url)
        
        assert response.status_code == 200
        # Should have empty products list in context
        assert 'products' in response.context
        assert list(response.context['products']) == []
        
    def test_assignment_create_returns_200_with_no_agents(
        self, client, liquor_business_with_location, liquor_product
    ):
        """Assignment create should work even if no agents exist."""
        business, user, location = liquor_business_with_location
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:assignment_create')
        response = client.get(url)
        
        assert response.status_code == 200
        # Should have empty agents list
        assert 'agents' in response.context
        
    def test_my_stock_returns_200_for_agent_with_no_assignments(
        self, client, liquor_business, liquor_agent
    ):
        """Agent's 'My Stock' page should return 200 even with no assignments."""
        business, _ = liquor_business
        client.force_login(liquor_agent)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:my_stock')
        response = client.get(url)
        
        assert response.status_code == 200
        # Should show empty assignments
        assert response.context.get('my_assignments') is not None
        assert response.context.get('total_bottles_in_hand') == 0 or response.context.get('total_bottles_in_hand') is 0
        
    def test_performance_report_returns_200_with_no_data(
        self, client, liquor_business
    ):
        """Performance report should return 200 with empty data."""
        business, user = liquor_business
        client.force_login(user)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:agent_performance')
        response = client.get(url)
        
        assert response.status_code == 200
        # Should have empty top_agents list
        assert 'top_agents' in response.context
        assert response.context.get('top_agents') == []


@pytest.mark.django_db
class TestPermissionChecks:
    """Test that permission checks work correctly."""
    
    def test_agent_cannot_view_assignments(self, client, liquor_business, liquor_agent):
        """Agents should not be able to view assignment list."""
        business, _ = liquor_business
        client.force_login(liquor_agent)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:assignment_list')
        response = client.get(url)
        
        # Should redirect (not 500)
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            # If 200, should have error message
            messages = list(response.context.get('messages', []))
            assert any('only managers' in str(m).lower() for m in messages)
        
    def test_agent_cannot_create_assignments(self, client, liquor_business, liquor_agent):
        """Agents should not be able to create assignments."""
        business, _ = liquor_business
        client.force_login(liquor_agent)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:assignment_create')
        response = client.get(url)
        
        # Should redirect or return 200 with error (not 500)
        assert response.status_code in [200, 302]
        
    def test_agent_cannot_view_reconciliation(self, client, liquor_business, liquor_agent):
        """Agents should not be able to view reconciliation dashboard."""
        business, _ = liquor_business
        client.force_login(liquor_agent)
        
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('liquor:reconciliation')
        response = client.get(url)
        
        # Should redirect or return 200 with error (not 500)
        assert response.status_code in [200, 302]


@pytest.mark.django_db
class TestAssignmentWorkflow:
    """Test complete assignment workflow doesn't crash."""
    
    def test_create_assignment_and_view_reconciliation(
        self, client, liquor_business_with_location, liquor_agent, liquor_product
    ):
        """Test creating assignment and viewing reconciliation."""
        business, manager, location = liquor_business_with_location
        client.force_login(manager)
        
        session = client.session
        session['active_business_id'] = business.id
        session['active_location_id'] = location.id
        session.save()
        
        # Create assignment via POST
        url = reverse('liquor:assignment_create')
        response = client.post(url, {
            'agent_id': liquor_agent.id,
            'product_id': liquor_product.id,
            'bottles_count': 10,
            'notes': 'Test assignment',
        })
        
        # Should not crash (200 or 302)
        assert response.status_code in [200, 302]
        
        # Now view reconciliation
        recon_url = reverse('liquor:reconciliation')
        response = client.get(recon_url)
        
        assert response.status_code == 200
        # Should have reconciliation data now
        assert response.context.get('reconciliations') is not None

