# tests/test_phones_features.py
"""
Unit tests for phones-specific features:
1. Agent ranking
2. Location stock assignment
3. Warranty checking
4. Manager approval workflow
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import Location, InventoryItem, Product, PhoneStockEditRequest
from sales.models import Sale
from inventory.services.agent_ranking import compute_agent_ranking, format_rank
from inventory.services.warranty import check_carlcare_warranty, is_carlcare_brand

User = get_user_model()


@pytest.mark.django_db
class TestAgentRanking:
    """Test agent ranking by sales amount within a business."""
    
    def test_agent_ranking_by_sales_amount(self):
        """
        Create a business with 3 agents, create sales with different amounts,
        verify ranking is correct.
        """
        # Create business and location
        business = Business.objects.create(
            name="Test Shop",
            status="ACTIVE"
        )
        location = Location.objects.create(
            business=business,
            name="Main Branch"
        )
        
        # Create 3 agents
        agent1 = User.objects.create_user(username="agent1", password="pass")
        agent2 = User.objects.create_user(username="agent2", password="pass")
        agent3 = User.objects.create_user(username="agent3", password="pass")
        
        for agent in [agent1, agent2, agent3]:
            Membership.objects.create(
                user=agent,
                business=business,
                role="AGENT",
                status="ACTIVE",
                location=location
            )
        
        # Create product
        product = Product.objects.create(
            code="TEST001",
            brand="Samsung",
            model="Galaxy S21"
        )
        
        # Create inventory items and sales
        # Agent1: 3 sales totaling MK 600,000
        for i in range(3):
            item = InventoryItem.objects.create(
                business=business,
                imei=f"11111111111111{i}",
                product=product,
                current_location=location,
                order_price=Decimal("100000"),
                selling_price=Decimal("200000"),
                status="SOLD"
            )
            Sale.objects.create(
                item=item,
                agent=agent1,
                location=location,
                sold_at=date.today(),
                price=Decimal("200000")
            )
        
        # Agent2: 2 sales totaling MK 500,000
        for i in range(2):
            item = InventoryItem.objects.create(
                business=business,
                imei=f"22222222222222{i}",
                product=product,
                current_location=location,
                order_price=Decimal("120000"),
                selling_price=Decimal("250000"),
                status="SOLD"
            )
            Sale.objects.create(
                item=item,
                agent=agent2,
                location=location,
                sold_at=date.today(),
                price=Decimal("250000")
            )
        
        # Agent3: 1 sale totaling MK 150,000
        item = InventoryItem.objects.create(
            business=business,
            imei="333333333333330",
            product=product,
            current_location=location,
            order_price=Decimal("80000"),
            selling_price=Decimal("150000"),
            status="SOLD"
        )
        Sale.objects.create(
            item=item,
            agent=agent3,
            location=location,
            sold_at=date.today(),
            price=Decimal("150000")
        )
        
        # Compute ranking
        ranking = compute_agent_ranking(business, days=None, agent_user=agent2)
        
        # Verify rankings
        assert len(ranking["rankings"]) == 3
        
        # Agent1 should be rank 1 (600,000)
        assert ranking["rankings"][0]["agent_id"] == agent1.id
        assert ranking["rankings"][0]["rank"] == 1
        assert ranking["rankings"][0]["total_sales"] == Decimal("600000")
        
        # Agent2 should be rank 2 (500,000)
        assert ranking["rankings"][1]["agent_id"] == agent2.id
        assert ranking["rankings"][1]["rank"] == 2
        assert ranking["rankings"][1]["total_sales"] == Decimal("500000")
        
        # Agent3 should be rank 3 (150,000)
        assert ranking["rankings"][2]["agent_id"] == agent3.id
        assert ranking["rankings"][2]["rank"] == 3
        assert ranking["rankings"][2]["total_sales"] == Decimal("150000")
        
        # Verify agent2's position (the agent_user parameter)
        assert ranking["agent_rank"] == 2
        assert ranking["agent_total"] == Decimal("500000")
        assert ranking["agent_above"]["agent_id"] == agent1.id
        assert ranking["agent_below"]["agent_id"] == agent3.id
    
    def test_format_rank(self):
        """Test ordinal rank formatting."""
        assert format_rank(1) == "1st"
        assert format_rank(2) == "2nd"
        assert format_rank(3) == "3rd"
        assert format_rank(4) == "4th"
        assert format_rank(11) == "11th"
        assert format_rank(21) == "21st"
        assert format_rank(22) == "22nd"
        assert format_rank(23) == "23rd"


@pytest.mark.django_db
class TestLocationStockAssignment:
    """Test location and agent stock assignment."""
    
    def test_stock_assignment_filtering(self):
        """
        Create a business with 2 locations and 2 agents.
        Create stock in different combinations.
        Verify managers see all, agents see only theirs.
        """
        # Create business
        business = Business.objects.create(name="Multi-Location Shop", status="ACTIVE")
        
        # Create 2 locations
        loc_a = Location.objects.create(business=business, name="Location A")
        loc_b = Location.objects.create(business=business, name="Location B")
        
        # Create manager and 2 agents
        manager = User.objects.create_user(username="manager", password="pass")
        agent1 = User.objects.create_user(username="agent1", password="pass")
        agent2 = User.objects.create_user(username="agent2", password="pass")
        
        Membership.objects.create(user=manager, business=business, role="MANAGER", status="ACTIVE")
        Membership.objects.create(user=agent1, business=business, role="AGENT", status="ACTIVE", location=loc_a)
        Membership.objects.create(user=agent2, business=business, role="AGENT", status="ACTIVE", location=loc_b)
        
        # Create product
        product = Product.objects.create(code="LOC001", brand="Apple", model="iPhone 14")
        
        # Create stock in different combinations
        # 1. Location A only
        stock_loc_a = InventoryItem.objects.create(
            business=business,
            imei="100000000000001",
            product=product,
            current_location=loc_a,
            order_price=Decimal("500000"),
            status="IN_STOCK"
        )
        
        # 2. Location B + Agent 1
        stock_loc_b_agent1 = InventoryItem.objects.create(
            business=business,
            imei="100000000000002",
            product=product,
            current_location=loc_b,
            assigned_agent=agent1,
            order_price=Decimal("500000"),
            status="IN_STOCK"
        )
        
        # 3. No location + Agent 2
        stock_agent2 = InventoryItem.objects.create(
            business=business,
            imei="100000000000003",
            product=product,
            current_location=loc_a,  # Must have a location (model constraint)
            assigned_agent=agent2,
            order_price=Decimal("500000"),
            status="IN_STOCK"
        )
        
        # Manager sees all stock
        manager_stock = InventoryItem.objects.filter(business=business, is_active=True)
        assert manager_stock.count() == 3
        
        # Agent1 sees only stock assigned to them
        agent1_stock = InventoryItem.objects.filter(
            business=business,
            assigned_agent=agent1,
            is_active=True
        )
        assert agent1_stock.count() == 1
        assert stock_loc_b_agent1 in agent1_stock
        
        # Agent2 sees only stock assigned to them
        agent2_stock = InventoryItem.objects.filter(
            business=business,
            assigned_agent=agent2,
            is_active=True
        )
        assert agent2_stock.count() == 1
        assert stock_agent2 in agent2_stock
        
        # Location summary
        loc_a_stock = InventoryItem.objects.filter(
            business=business,
            current_location=loc_a,
            is_active=True
        )
        assert loc_a_stock.count() == 2  # stock_loc_a + stock_agent2
        
        loc_b_stock = InventoryItem.objects.filter(
            business=business,
            current_location=loc_b,
            is_active=True
        )
        assert loc_b_stock.count() == 1  # stock_loc_b_agent1


@pytest.mark.django_db
class TestPhoneStockEditRequest:
    """Test manager approval workflow for stock edits."""
    
    def test_agent_edit_request_creation(self):
        """Agent submits edit request, stock unchanged."""
        # Setup
        business = Business.objects.create(name="Approval Shop", status="ACTIVE")
        location = Location.objects.create(business=business, name="Branch")
        
        agent = User.objects.create_user(username="agent", password="pass")
        Membership.objects.create(user=agent, business=business, role="AGENT", status="ACTIVE", location=location)
        
        product = Product.objects.create(code="EDIT001", brand="Samsung", model="A54")
        stock = InventoryItem.objects.create(
            business=business,
            imei="200000000000001",
            product=product,
            current_location=location,
            order_price=Decimal("150000"),
            selling_price=Decimal("200000"),
            status="IN_STOCK"
        )
        
        # Agent creates edit request
        edit_request = PhoneStockEditRequest.objects.create(
            business=business,
            stock=stock,
            requested_by=agent,
            payload={"selling_price": "250000"},
            status="PENDING"
        )
        
        # Stock should be unchanged
        stock.refresh_from_db()
        assert stock.selling_price == Decimal("200000")
        
        # Request should exist
        assert edit_request.status == "PENDING"
        assert edit_request.requested_by == agent
    
    def test_manager_approves_edit(self):
        """Manager approves edit request, stock updated."""
        # Setup
        business = Business.objects.create(name="Approval Shop", status="ACTIVE")
        location = Location.objects.create(business=business, name="Branch")
        
        manager = User.objects.create_user(username="manager", password="pass")
        agent = User.objects.create_user(username="agent", password="pass")
        
        Membership.objects.create(user=manager, business=business, role="MANAGER", status="ACTIVE")
        Membership.objects.create(user=agent, business=business, role="AGENT", status="ACTIVE", location=location)
        
        product = Product.objects.create(code="EDIT002", brand="Samsung", model="A54")
        stock = InventoryItem.objects.create(
            business=business,
            imei="200000000000002",
            product=product,
            current_location=location,
            order_price=Decimal("150000"),
            selling_price=Decimal("200000"),
            status="IN_STOCK"
        )
        
        # Agent creates edit request
        edit_request = PhoneStockEditRequest.objects.create(
            business=business,
            stock=stock,
            requested_by=agent,
            payload={"selling_price": Decimal("250000")},
            status="PENDING"
        )
        
        # Manager approves
        edit_request.approve(manager, reason="Price updated")
        
        # Stock should be updated
        stock.refresh_from_db()
        assert stock.selling_price == Decimal("250000")
        
        # Request should be marked approved
        edit_request.refresh_from_db()
        assert edit_request.status == "APPROVED"
        assert edit_request.reviewed_by == manager
        assert edit_request.reviewed_at is not None


class TestWarrantyChecking:
    """Test warranty checking logic (mocked, no actual HTTP calls)."""
    
    def test_carlcare_brand_detection(self):
        """Test brand detection for Carlcare support."""
        assert is_carlcare_brand("Tecno")
        assert is_carlcare_brand("tecno")
        assert is_carlcare_brand("TECNO")
        assert is_carlcare_brand("Itel")
        assert is_carlcare_brand("Infinix")
        assert not is_carlcare_brand("Samsung")
        assert not is_carlcare_brand("Apple")
        assert not is_carlcare_brand("")
        assert not is_carlcare_brand(None)
    
    def test_warranty_check_invalid_imei(self):
        """Test warranty check with invalid IMEI."""
        result = check_carlcare_warranty("12345")  # Too short
        assert result["status"] == "unknown"
        assert "Invalid IMEI" in result["message"]
        
        result = check_carlcare_warranty("123456789012345678")  # Too long
        assert result["status"] == "unknown"


@pytest.mark.django_db
class TestPhoneTotals:
    """Test that phone totals (sum_sold, sold, etc.) update correctly."""
    
    def test_totals_update_on_sale(self):
        """Create stock + sale, verify totals updated."""
        # Create business and location
        business = Business.objects.create(name="Totals Shop", status="ACTIVE")
        location = Location.objects.create(business=business, name="Main")
        
        agent = User.objects.create_user(username="agent", password="pass")
        Membership.objects.create(user=agent, business=business, role="AGENT", status="ACTIVE", location=location)
        
        product = Product.objects.create(code="TOT001", brand="Nokia", model="G50")
        
        # Create stock
        stock = InventoryItem.objects.create(
            business=business,
            imei="300000000000001",
            product=product,
            current_location=location,
            order_price=Decimal("80000"),
            selling_price=Decimal("120000"),
            status="IN_STOCK"
        )
        
        # Initial counts
        in_stock_count = InventoryItem.objects.filter(business=business, status="IN_STOCK").count()
        sold_count = InventoryItem.objects.filter(business=business, status="SOLD").count()
        assert in_stock_count == 1
        assert sold_count == 0
        
        # Create sale
        stock.status = "SOLD"
        stock.sold_at = timezone.now()
        stock.save()
        
        Sale.objects.create(
            item=stock,
            agent=agent,
            location=location,
            sold_at=date.today(),
            price=Decimal("120000")
        )
        
        # Verify counts updated
        in_stock_count = InventoryItem.objects.filter(business=business, status="IN_STOCK").count()
        sold_count = InventoryItem.objects.filter(business=business, status="SOLD").count()
        assert in_stock_count == 0
        assert sold_count == 1
        
        # Verify sales aggregates
        from django.db.models import Sum
        total_sales = Sale.objects.filter(location__business=business).aggregate(total=Sum("price"))["total"]
        assert total_sales == Decimal("120000")

