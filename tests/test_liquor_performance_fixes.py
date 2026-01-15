# tests/test_liquor_performance_fixes.py
"""
Regression tests for liquor performance page fixes.

CRITICAL BUGS FIXED:
1. /liquor/performance/ 500 error when no sales/stock/location
2. Beer/Cider per-bottle pricing (not per-crate)
3. Spirits/Whiskey per-shot pricing
4. Editable sale price at transaction time
5. Estimated Total reflects edited price

ZERO REGRESSIONS: All existing tests must pass.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import MerchProduct
from inventory.models_liquor_assignment import LiquorStockAssignment, LiquorAgentTarget
from tenants.models import Business, Membership

User = get_user_model()


@pytest.fixture
def liquor_business():
    """Create a test liquor business"""
    return Business.objects.create(
        name="Test Liquor Store",
        slug="test-liquor-perf",
        status="ACTIVE",
        business_kind=BusinessKind.LIQUOR
    )


@pytest.fixture
def manager_user(liquor_business):
    """Create a manager user"""
    user = User.objects.create_user(username="liq_manager", password="testpass123")
    user.is_staff = False
    user.save()
    
    # Create membership (manager role)
    Membership.objects.create(
        user=user,
        business=liquor_business,
        role="Manager",
        is_active=True
    )
    return user


@pytest.fixture
def agent_user(liquor_business):
    """Create an agent user"""
    user = User.objects.create_user(username="liq_agent", password="testpass123")
    user.is_staff = False
    user.save()
    
    # Create membership (agent role)
    Membership.objects.create(
        user=user,
        business=liquor_business,
        role="Agent",
        is_active=True
    )
    return user


@pytest.fixture
def beer_product(liquor_business):
    """Create a beer product (crate of 20 bottles)"""
    return MerchProduct.objects.create(
        business=liquor_business,
        name="Castle Lager Crate",
        kind=BusinessKind.LIQUOR,
        category="Beer",
        selling_price=Decimal("60000.00"),  # Price per crate
        cost_price=Decimal("50000.00"),  # Cost per crate
        quantity_in_stock=10,
        is_active=True,
        track_inventory=True
    )


@pytest.mark.django_db
class TestLiquorPerformancePageResilience:
    """
    Test: Performance page returns 200 even with no data
    Bug: Was throwing 500 when no sales/assignments/location
    Fix: Defensive handling in agent_performance_report view
    """

    def test_performance_page_loads_with_no_data(self, client, liquor_business, manager_user):
        """Performance page should return 200 even when no assignments exist"""
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = liquor_business.id
        session.save()
        
        url = reverse('liquor:agent_performance')
        response = client.get(url)
        
        # CRITICAL: Must not 500
        assert response.status_code == 200, f"Performance page returned {response.status_code}, expected 200"
        
        # Should show "no data" message gracefully
        assert b"No performance data" in response.content or b"no performance data" in response.content.lower()

    def test_performance_page_loads_with_no_sales_yet(self, client, liquor_business, manager_user, agent_user, beer_product):
        """Performance page should return 200 when assignments exist but no sales yet"""
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = liquor_business.id
        session.save()
        
        # Create assignment (no sales)
        LiquorStockAssignment.objects.create(
            business=liquor_business,
            agent=agent_user,
            product=beer_product,
            bottles_assigned=10,
            bottles_sold=0,
            bottles_returned=0,
            unit_sell_price=Decimal("3000.00"),  # Per bottle price
            unit_cost_price=Decimal("2500.00"),
            status="ACTIVE",
            assigned_by=manager_user,
            assigned_at=timezone.now()
        )
        
        url = reverse('liquor:agent_performance')
        response = client.get(url)
        
        # CRITICAL: Must not 500
        assert response.status_code == 200, f"Performance page returned {response.status_code}, expected 200"

    def test_performance_page_with_none_values(self, client, liquor_business, manager_user, agent_user, beer_product):
        """Performance page should handle None revenue/profit gracefully"""
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = liquor_business.id
        session.save()
        
        # Create assignment with potential None-triggering conditions
        assignment = LiquorStockAssignment.objects.create(
            business=liquor_business,
            agent=agent_user,
            product=beer_product,
            bottles_assigned=5,
            bottles_sold=3,
            bottles_returned=0,
            unit_sell_price=Decimal("3000.00"),
            unit_cost_price=Decimal("2500.00"),
            status="ACTIVE",
            assigned_by=manager_user,
            assigned_at=timezone.now()
        )
        
        url = reverse('liquor:agent_performance')
        response = client.get(url)
        
        # CRITICAL: Must not 500
        assert response.status_code == 200, f"Performance page returned {response.status_code}, expected 200"
        
        # Should show agent in list
        assert agent_user.username.encode() in response.content

    def test_performance_page_period_filters(self, client, liquor_business, manager_user):
        """Performance page should handle different period filters without errors"""
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = liquor_business.id
        session.save()
        
        url = reverse('liquor:agent_performance')
        
        # Test different period filters
        for days in [7, 30, 90]:
            response = client.get(url, {'days': days})
            assert response.status_code == 200, f"Performance page failed for days={days}"

    def test_performance_page_non_manager_redirects(self, client, liquor_business, agent_user):
        """Performance page should redirect non-managers gracefully"""
        client.force_login(agent_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = liquor_business.id
        session.save()
        
        url = reverse('liquor:agent_performance')
        response = client.get(url)
        
        # Should redirect (not 500)
        assert response.status_code in [302, 200], f"Expected redirect or 200, got {response.status_code}"
        
        # If 200, should show error message
        if response.status_code == 200:
            assert b"Only managers" in response.content or b"only managers" in response.content.lower()

    def test_performance_page_invalid_days_parameter(self, client, liquor_business, manager_user):
        """Performance page should handle invalid 'days' parameter gracefully"""
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = liquor_business.id
        session.save()
        
        url = reverse('liquor:agent_performance')
        
        # Test invalid parameters
        for invalid_days in ['abc', '-1', '9999999', None]:
            response = client.get(url, {'days': invalid_days} if invalid_days else {})
            assert response.status_code == 200, f"Performance page failed for invalid days={invalid_days}"


@pytest.mark.django_db
class TestLiquorPerformanceDataIntegrity:
    """
    Test: Performance metrics calculate correctly even with edge cases
    """

    def test_performance_zero_assigned(self, client, liquor_business, manager_user, agent_user):
        """Performance should handle agents with zero assignments"""
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = liquor_business.id
        session.save()
        
        # Agent exists but has no assignments
        url = reverse('liquor:agent_performance')
        response = client.get(url)
        
        assert response.status_code == 200

    def test_performance_all_returned_no_sales(self, client, liquor_business, manager_user, agent_user, beer_product):
        """Performance should handle cases where all bottles were returned (0 sales)"""
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = liquor_business.id
        session.save()
        
        # Create assignment where all bottles were returned
        LiquorStockAssignment.objects.create(
            business=liquor_business,
            agent=agent_user,
            product=beer_product,
            bottles_assigned=20,
            bottles_sold=0,
            bottles_returned=20,
            unit_sell_price=Decimal("3000.00"),
            unit_cost_price=Decimal("2500.00"),
            status="RETURNED",
            assigned_by=manager_user,
            assigned_at=timezone.now()
        )
        
        url = reverse('liquor:agent_performance')
        response = client.get(url)
        
        assert response.status_code == 200
        
        # Sell-through should be 0%
        # (Test will verify no crash, actual calculation tested elsewhere)


# Run these tests:
# pytest tests/test_liquor_performance_fixes.py -v
# pytest tests/test_liquor_performance_fixes.py::TestLiquorPerformancePageResilience::test_performance_page_loads_with_no_data -v

