"""
Tests for agent scoping in Phones vertical.

Ensures that:
1. Managers see global numbers (all stock, all sales)
2. Agents see only their own numbers (their stock, their sales)
3. Custom date filter works correctly
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from inventory.models import InventoryItem, Product, Location
from inventory.utils_scope import get_visible_actor, scope_sales_qs, scope_stock_qs
from tenants.models import Business, BusinessKind, Membership

User = get_user_model()


@pytest.fixture
def business():
    """Create a test business for Phones vertical."""
    return Business.objects.create(
        name="Test Phones Store",
        slug="test-phones-store",
        business_kind=BusinessKind.PHONES,
        status="ACTIVE",
    )


@pytest.fixture
def location(business):
    """Create a test location."""
    return Location.objects.create(
        name="Main Store",
        business=business,
    )


@pytest.fixture
def product(business):
    """Create a test phone product."""
    return Product.objects.create(
        brand="Tecno",
        model="Pova 5",
        variant="8GB/128GB",
        business=business,
    )


@pytest.fixture
def manager_user(business):
    """Create a manager user (can see all data)."""
    user = User.objects.create_user(
        username="manager1",
        password="test123",
        is_staff=True,  # Managers are staff
    )
    # Create membership for manager
    Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")
    return user


@pytest.fixture
def agent_user1(business):
    """Create agent user 1."""
    user = User.objects.create_user(
        username="agent1",
        password="test123",
        is_staff=False,  # Agents are not staff
    )
    # Create membership for agent
    Membership.objects.create(user=user, business=business, role="AGENT", status="ACTIVE")
    return user


@pytest.fixture
def agent_user2(business):
    """Create agent user 2."""
    user = User.objects.create_user(
        username="agent2",
        password="test123",
        is_staff=False,
    )
    # Create membership for agent
    Membership.objects.create(user=user, business=business, role="AGENT", status="ACTIVE")
    return user


@pytest.fixture
def factory():
    """Request factory for creating test requests."""
    return RequestFactory()


@pytest.mark.django_db
class TestVisibilityScoping:
    """Test get_visible_actor function."""

    def test_manager_visibility(self, factory, manager_user):
        """Managers should be identified correctly."""
        request = factory.get("/")
        request.user = manager_user

        is_manager, is_agent, actor = get_visible_actor(request)

        assert is_manager is True
        assert is_agent is False
        assert actor == manager_user

    def test_agent_visibility(self, factory, agent_user1):
        """Agents should be identified correctly."""
        request = factory.get("/")
        request.user = agent_user1

        is_manager, is_agent, actor = get_visible_actor(request)

        assert is_manager is False
        assert is_agent is True
        assert actor == agent_user1

    def test_unauthenticated_visibility(self, factory):
        """Unauthenticated users should have no visibility."""
        from django.contrib.auth.models import AnonymousUser

        request = factory.get("/")
        request.user = AnonymousUser()

        is_manager, is_agent, actor = get_visible_actor(request)

        assert is_manager is False
        assert is_agent is False
        assert actor is None


@pytest.mark.django_db
class TestStockScoping:
    """Test stock queryset scoping by role."""

    def test_manager_sees_all_stock(self, factory, manager_user, agent_user1, agent_user2, business, location, product):
        """Managers should see stock from all agents."""
        # Create stock for agent1
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=agent_user1,
            status="IN_STOCK",
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
        )

        # Create stock for agent2
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=agent_user2,
            status="IN_STOCK",
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
        )

        # Create unassigned stock
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=None,
            status="IN_STOCK",
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
        )

        # Manager request
        request = factory.get("/")
        request.user = manager_user

        base_qs = InventoryItem.objects.filter(business=business, status="IN_STOCK")
        scoped_qs = scope_stock_qs(base_qs, request)

        # Manager should see all 3 items
        assert scoped_qs.count() == 3

    def test_agent_sees_only_own_stock(self, factory, agent_user1, agent_user2, business, location, product):
        """Agents should see only their assigned stock."""
        # Create stock for agent1
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=agent_user1,
            status="IN_STOCK",
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
        )

        # Create stock for agent2
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=agent_user2,
            status="IN_STOCK",
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
        )

        # Agent1 request
        request = factory.get("/")
        request.user = agent_user1

        base_qs = InventoryItem.objects.filter(business=business, status="IN_STOCK")
        scoped_qs = scope_stock_qs(base_qs, request)

        # Agent1 should see only their 1 item
        assert scoped_qs.count() == 1
        assert scoped_qs.first().assigned_agent == agent_user1


@pytest.mark.django_db
class TestSalesScoping:
    """Test sales queryset scoping by role."""

    def test_manager_sees_all_sales(self, factory, manager_user, agent_user1, agent_user2, business, location, product):
        """Managers should see sales from all agents."""
        # Create sales for agent1
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=agent_user1,
            status="SOLD",
            sold_at=timezone.now(),
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
        )

        # Create sales for agent2
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=agent_user2,
            status="SOLD",
            sold_at=timezone.now(),
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
        )

        # Manager request
        request = factory.get("/")
        request.user = manager_user

        base_qs = InventoryItem.objects.filter(business=business, status="SOLD")
        scoped_qs = scope_sales_qs(base_qs, request)

        # Manager should see all 2 sales
        assert scoped_qs.count() == 2

    def test_agent_sees_only_own_sales(self, factory, agent_user1, agent_user2, business, location, product):
        """Agents should see only their own sales."""
        # Create sales for agent1
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=agent_user1,
            status="SOLD",
            sold_at=timezone.now(),
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
        )

        # Create sales for agent2
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=agent_user2,
            status="SOLD",
            sold_at=timezone.now(),
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
        )

        # Agent1 request
        request = factory.get("/")
        request.user = agent_user1

        base_qs = InventoryItem.objects.filter(business=business, status="SOLD")
        scoped_qs = scope_sales_qs(base_qs, request)

        # Agent1 should see only their 1 sale
        assert scoped_qs.count() == 1
        assert scoped_qs.first().assigned_agent == agent_user1


@pytest.mark.django_db
class TestPhonesDashboardIntegration:
    """Integration tests for Phones dashboard with agent scoping."""

    def test_dashboard_loads_for_manager(self, client, manager_user, business, location):
        """Dashboard should load successfully for managers."""
        client.force_login(manager_user)

        # Set business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()

        response = client.get("/inventory/verticals/phones/")

        assert response.status_code == 200
        assert "dashboard_kpis" in response.context

    def test_dashboard_loads_for_agent(self, client, agent_user1, business, location):
        """Dashboard should load successfully for agents."""
        client.force_login(agent_user1)

        # Set business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()

        response = client.get("/inventory/verticals/phones/")

        assert response.status_code == 200
        assert "dashboard_kpis" in response.context

    def test_custom_date_filter_with_valid_dates(self, client, manager_user, business, location):
        """Custom date filter should work with valid dates."""
        client.force_login(manager_user)

        # Set business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()

        start = (date.today() - timedelta(days=7)).isoformat()
        end = date.today().isoformat()

        response = client.get(f"/inventory/verticals/phones/?range=custom&start={start}&end={end}")

        assert response.status_code == 200
        assert "dashboard_kpis" in response.context
        assert response.context["dashboard_kpis"]["range_key"] == "custom"

    def test_custom_date_filter_with_invalid_dates(self, client, manager_user, business, location):
        """Custom date filter should fall back to MTD with invalid dates."""
        client.force_login(manager_user)

        # Set business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()

        response = client.get("/inventory/verticals/phones/?range=custom&start=invalid&end=invalid")

        # Should not crash, should fall back to MTD
        assert response.status_code == 200
        assert "dashboard_kpis" in response.context
        # Falls back to MTD when custom dates are invalid
        assert response.context["dashboard_kpis"]["range_key"] == "mtd"

    def test_agent_kpis_show_only_own_data(self, client, agent_user1, agent_user2, business, location, product):
        """Agent dashboard should show only their own data."""
        # Create sales for agent1 (with all required fields for dashboard filtering)
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=agent_user1,
            status="SOLD",
            sold_at=timezone.now(),
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
            is_active=True,  # Explicitly set for clarity
            imei="111111111111111",  # Add IMEI for phone items
        )

        # Create sales for agent2 (should NOT be visible to agent1)
        InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            assigned_agent=agent_user2,
            status="SOLD",
            sold_at=timezone.now(),
            order_price=Decimal("50000"),
            selling_price=Decimal("60000"),
            is_active=True,
            imei="222222222222222",
        )

        # Agent1 logs in
        client.force_login(agent_user1)

        # Set business in session
        session = client.session
        session["active_business_id"] = business.id
        session.save()

        response = client.get("/inventory/verticals/phones/")

        assert response.status_code == 200
        kpis = response.context["dashboard_kpis"]

        # Agent1 should see only their 1 sale
        assert kpis["units_sold"] == 1
        assert kpis["revenue"] == Decimal("60000")
