"""
Tests for Phones Agent Selling Feature

Requirements:
- Agents can sell phones assigned to them (existing behavior)
- Agents can sell unassigned/manager-held phones (new)
- Agents cannot sell already-sold phones
- Sale attributed to selling agent (sold_by field)
- No cross-agent leakage in UI
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from inventory.models import InventoryItem, Product, Location
from tenants.models import Business, Membership

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def business(db):
    """Create a test business"""
    return Business.objects.create(
        name="Test Phones Business",
        business_kind="phones",
        owner_email="owner@test.com"
    )


@pytest.fixture
def location(business):
    """Create a test location"""
    return Location.objects.create(
        business=business,
        name="Main Store",
        city="Lilongwe",
        is_default=True
    )


@pytest.fixture
def product(db):
    """Create a test product"""
    return Product.objects.create(
        brand="ITEL",
        model="A90",
        variant="3+128",
        name="ITEL A90 3+128",
        cost_price=Decimal("50000.00"),
        sale_price=Decimal("75000.00")
    )


@pytest.fixture
def agent1(business):
    """Create first agent"""
    user = User.objects.create_user(
        username="agent1",
        email="agent1@test.com",
        password="testpass123"
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="agent",
        status="ACTIVE"
    )
    return user


@pytest.fixture
def agent2(business):
    """Create second agent"""
    user = User.objects.create_user(
        username="agent2",
        email="agent2@test.com",
        password="testpass123"
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="agent",
        status="ACTIVE"
    )
    return user


@pytest.fixture
def manager_user(business):
    """Create manager user"""
    user = User.objects.create_user(
        username="manager",
        email="manager@test.com",
        password="testpass123",
        is_staff=True
    )
    Membership.objects.create(
        user=user,
        business=business,
        role="manager",
        status="ACTIVE"
    )
    return user


class TestAgentCanSellAssignedPhone:
    """Test that agents can sell phones assigned to them (existing behavior)"""
    
    def test_agent_sells_own_phone(self, client, agent1, business, location, product):
        """Agent can sell phone assigned to them"""
        # Create phone assigned to agent1
        phone = InventoryItem.objects.create(
            business=business,
            product=product,
            imei="123456789012345",
            order_price=Decimal("50000.00"),
            selling_price=Decimal("75000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=agent1,
            assigned_role="AGENT"
        )
        
        # Login as agent1
        client.login(username="agent1", password="testpass123")
        
        # Complete sale
        response = client.post(
            reverse("inventory:phone_scan_sell"),
            {
                "brand": "ITEL",
                "imei": "123456789012345",
                "selling_price": "75000.00",
                "payment_method": "CASH"
            }
        )
        
        # Verify sale completed
        phone.refresh_from_db()
        assert phone.status == "SOLD"
        assert phone.sold_by == agent1
        assert phone.selling_price == Decimal("75000.00")
        assert phone.sold_at is not None


class TestAgentCanSellUnassignedPhone:
    """Test that agents can sell unassigned/manager-held phones (new feature)"""
    
    def test_agent_sells_unassigned_phone(self, client, agent1, business, location, product):
        """Agent can sell phone not assigned to anyone"""
        # Create unassigned phone
        phone = InventoryItem.objects.create(
            business=business,
            product=product,
            imei="999888777666555",
            order_price=Decimal("50000.00"),
            selling_price=Decimal("75000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=None,
            assigned_role="MANAGER"
        )
        
        # Login as agent1
        client.login(username="agent1", password="testpass123")
        
        # Complete sale
        response = client.post(
            reverse("inventory:phone_scan_sell"),
            {
                "brand": "ITEL",
                "imei": "999888777666555",
                "selling_price": "75000.00",
                "payment_method": "CASH"
            }
        )
        
        # Verify sale completed and attributed to agent1
        phone.refresh_from_db()
        assert phone.status == "SOLD"
        assert phone.sold_by == agent1  # Selling agent gets credit
        assert phone.selling_price == Decimal("75000.00")
    
    def test_agent_sells_manager_held_phone(self, client, agent1, manager_user, business, location, product):
        """Agent can sell phone held by manager"""
        # Create phone assigned to manager
        phone = InventoryItem.objects.create(
            business=business,
            product=product,
            imei="111222333444555",
            order_price=Decimal("50000.00"),
            selling_price=Decimal("75000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=manager_user,
            assigned_role="MANAGER"
        )
        
        # Login as agent1
        client.login(username="agent1", password="testpass123")
        
        # Complete sale
        response = client.post(
            reverse("inventory:phone_scan_sell"),
            {
                "brand": "ITEL",
                "imei": "111222333444555",
                "selling_price": "75000.00",
                "payment_method": "BANK"
            }
        )
        
        # Verify sale completed and attributed to agent1
        phone.refresh_from_db()
        assert phone.status == "SOLD"
        assert phone.sold_by == agent1
        assert phone.payment_method == "BANK"


class TestAgentCannotSellAlreadySoldPhone:
    """Test that agents cannot sell already-sold phones"""
    
    def test_agent_cannot_sell_sold_phone(self, client, agent1, agent2, business, location, product):
        """Agent cannot sell phone that's already sold"""
        # Create phone already sold by agent2
        phone = InventoryItem.objects.create(
            business=business,
            product=product,
            imei="555666777888999",
            order_price=Decimal("50000.00"),
            selling_price=Decimal("75000.00"),
            status="SOLD",
            current_location=location,
            assigned_agent=agent2,
            assigned_role="AGENT",
            sold_at=timezone.now(),
            sold_by=agent2
        )
        
        # Login as agent1
        client.login(username="agent1", password="testpass123")
        
        # Try to sell already-sold phone
        response = client.post(
            reverse("inventory:phone_scan_sell"),
            {
                "brand": "ITEL",
                "imei": "555666777888999",
                "selling_price": "75000.00",
                "payment_method": "CASH"
            }
        )
        
        # Verify sale was rejected
        phone.refresh_from_db()
        assert phone.status == "SOLD"
        assert phone.sold_by == agent2  # Original seller unchanged


class TestSaleAttributedToSellingAgent:
    """Test that commission/sale attribution is recorded correctly"""
    
    def test_sale_attributed_to_selling_agent(self, client, agent1, agent2, business, location, product):
        """Sale attributed to agent who sold it, not who it was assigned to"""
        # Create phone assigned to agent2
        phone = InventoryItem.objects.create(
            business=business,
            product=product,
            imei="777888999000111",
            order_price=Decimal("50000.00"),
            selling_price=Decimal("75000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=agent2,  # Assigned to agent2
            assigned_role="AGENT"
        )
        
        # Login as agent1 and sell it
        client.login(username="agent1", password="testpass123")
        
        response = client.post(
            reverse("inventory:phone_scan_sell"),
            {
                "brand": "ITEL",
                "imei": "777888999000111",
                "selling_price": "75000.00",
                "payment_method": "MOBILE_MONEY"
            }
        )
        
        # Verify sale attributed to agent1 (who sold it)
        phone.refresh_from_db()
        assert phone.status == "SOLD"
        assert phone.sold_by == agent1  # Agent1 gets commission
        assert phone.assigned_agent == agent2  # Original assignment unchanged
    
    def test_wizard_sale_attributed_correctly(self, client, agent1, business, location, product):
        """Test sale through wizard also tracks sold_by"""
        # Create unassigned phone
        phone = InventoryItem.objects.create(
            business=business,
            product=product,
            imei="222333444555666",
            order_price=Decimal("50000.00"),
            selling_price=Decimal("75000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=None
        )
        
        # Login as agent1
        client.login(username="agent1", password="testpass123")
        
        # Step 1: IMEI
        response = client.post(
            reverse("inventory:phone_sale_wizard_v2"),
            {"imei": "222333444555666"}
        )
        
        # Step 2: Price
        response = client.post(
            f"{reverse('inventory:phone_sale_wizard_v2')}?step=2",
            {"selling_price": "75000.00"}
        )
        
        # Step 3: Payment
        response = client.post(
            f"{reverse('inventory:phone_sale_wizard_v2')}?step=3",
            {"payment_method": "CASH"}
        )
        
        # Verify sold_by tracked
        phone.refresh_from_db()
        assert phone.status == "SOLD"
        assert phone.sold_by == agent1


class TestNoCrossAgentLeakage:
    """Test that agent UI doesn't leak other agents' information"""
    
    def test_agent_ui_no_other_agent_names(self, client, agent1, agent2, business, location, product):
        """Agent UI should not display other agents' names"""
        # Create phones for different agents
        phone1 = InventoryItem.objects.create(
            business=business,
            product=product,
            imei="100200300400500",
            order_price=Decimal("50000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=agent1
        )
        
        phone2 = InventoryItem.objects.create(
            business=business,
            product=product,
            imei="600700800900111",
            order_price=Decimal("50000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=agent2
        )
        
        # Login as agent1
        client.login(username="agent1", password="testpass123")
        
        # Get dashboard/stock list
        response = client.get(reverse("inventory:inventory_dashboard"))
        content = response.content.decode('utf-8')
        
        # Verify agent2's name not leaked
        assert "agent2" not in content.lower()
        assert agent2.username not in content
        
    def test_manager_sees_all_agents(self, client, manager_user, agent1, agent2, business, location, product):
        """Managers can see all agents (no restriction)"""
        # Create phones for different agents
        phone1 = InventoryItem.objects.create(
            business=business,
            product=product,
            imei="300400500600700",
            order_price=Decimal("50000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=agent1
        )
        
        phone2 = InventoryItem.objects.create(
            business=business,
            product=product,
            imei="800900111222333",
            order_price=Decimal("50000.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=agent2
        )
        
        # Login as manager
        client.login(username="manager", password="testpass123")
        
        # Get dashboard/stock list
        response = client.get(reverse("inventory:inventory_dashboard"))
        
        # Manager can see global stats (no specific test for agent names here)
        assert response.status_code == 200


class TestPaymentMethods:
    """Test that different payment methods work correctly"""
    
    @pytest.mark.parametrize("payment_method", ["CASH", "BANK", "MOBILE_MONEY"])
    def test_different_payment_methods(self, client, agent1, business, location, product, payment_method):
        """Test sales with different payment methods"""
        phone = InventoryItem.objects.create(
            business=business,
            product=product,
            imei=f"111222333444{payment_method[:3]}",
            order_price=Decimal("50000.00"),
            selling_price=Decimal("75000.00"),
            status="IN_STOCK",
            current_location=location
        )
        
        client.login(username="agent1", password="testpass123")
        
        response = client.post(
            reverse("inventory:phone_scan_sell"),
            {
                "brand": "ITEL",
                "imei": phone.imei,
                "selling_price": "75000.00",
                "payment_method": payment_method
            }
        )
        
        phone.refresh_from_db()
        assert phone.status == "SOLD"
        assert phone.payment_method == payment_method
        assert phone.sold_by == agent1

