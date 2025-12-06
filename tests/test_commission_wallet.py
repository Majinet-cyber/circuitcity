# tests/test_commission_wallet.py
"""
Tests for 12% commission on agent sales.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from sales.models import Sale, CommissionConfig
from wallet.models import WalletTransaction, TxnType, Ledger
from wallet.services_commission import record_sale_commission_to_wallet, get_agent_commission_summary
from tenants.models import Business, Membership
from inventory.models import InventoryItem, Location

User = get_user_model()


@pytest.mark.django_db
class TestAgentCommission:
    """Test that agent sales get 12% commission automatically."""
    
    @pytest.fixture
    def setup_business(self):
        """Create business, location, and agents for testing."""
        # Create business
        business = Business.objects.create(
            name="Test Electronics",
            slug="test-electronics",
            status="ACTIVE",
            business_kind="phones"
        )
        
        # Create location with GPS coordinates
        location = Location.objects.create(
            business=business,
            name="Main Store",
            latitude=Decimal("-15.7861"),
            longitude=Decimal("35.0058"),
            geofence_radius_m=150
        )
        
        # Create manager
        manager = User.objects.create_user(
            username="manager1",
            email="manager@test.com",
            password="testpass123"
        )
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create agent
        agent = User.objects.create_user(
            username="agent1",
            email="agent@test.com",
            password="testpass123"
        )
        Membership.objects.create(
            user=agent,
            business=business,
            location=location,
            role="AGENT",
            status="ACTIVE"
        )
        
        return {
            "business": business,
            "location": location,
            "manager": manager,
            "agent": agent
        }
    
    def test_agent_sale_gets_12_percent_commission(self, setup_business):
        """Test that agent sale creates 12% commission automatically."""
        business = setup_business["business"]
        location = setup_business["location"]
        agent = setup_business["agent"]
        
        # Create inventory item
        item = InventoryItem.objects.create(
            business=business,
            imei="123456789012345",
            product_name="iPhone 13",
            order_price=Decimal("500000.00"),
            selling_price=Decimal("600000.00"),
            status="IN_STOCK",
            current_location=location
        )
        
        # Create sale
        sale = Sale.objects.create(
            item=item,
            agent=agent,
            location=location,
            sold_at=timezone.localdate(),
            price=Decimal("600000.00"),
            payment_method="CASH"
        )
        
        # Signal should have created commission transaction
        txn = WalletTransaction.objects.filter(
            agent=agent,
            type=TxnType.COMMISSION,
            reference=f"SALE-{sale.id}"
        ).first()
        
        assert txn is not None, "Commission transaction should be created"
        
        # Check commission amount (12% of 600,000 = 72,000)
        expected_commission = Decimal("72000.00")
        assert txn.amount == expected_commission, f"Expected {expected_commission}, got {txn.amount}"
        
        # Check metadata
        assert txn.meta.get("sale_id") == sale.id
        assert txn.meta.get("commission_pct") == "12.0"
    
    def test_commission_config_default_is_12_percent(self, setup_business):
        """Test that new CommissionConfig defaults to 12%."""
        business = setup_business["business"]
        
        # Get or create config
        config = CommissionConfig.ensure_config(business)
        
        assert config.base_commission_pct == Decimal("12.00")
    
    def test_manager_sale_respects_config(self, setup_business):
        """Test that manager sales use the configured rate (not necessarily 12%)."""
        business = setup_business["business"]
        location = setup_business["location"]
        manager = setup_business["manager"]
        
        # Set custom commission rate for testing
        config = CommissionConfig.ensure_config(business)
        config.base_commission_pct = Decimal("10.00")
        config.save()
        
        # Create inventory item
        item = InventoryItem.objects.create(
            business=business,
            imei="123456789012346",
            product_name="Samsung S21",
            order_price=Decimal("400000.00"),
            selling_price=Decimal("500000.00"),
            status="IN_STOCK",
            current_location=location
        )
        
        # Create sale by manager
        sale = Sale.objects.create(
            item=item,
            agent=manager,  # Manager can also make sales
            location=location,
            sold_at=timezone.localdate(),
            price=Decimal("500000.00"),
            payment_method="CASH"
        )
        
        # Commission should use configured 10%
        txn = WalletTransaction.objects.filter(
            agent=manager,
            type=TxnType.COMMISSION,
            reference=f"SALE-{sale.id}"
        ).first()
        
        # 10% of 500,000 = 50,000
        assert txn is not None
        assert txn.amount == Decimal("50000.00")
    
    def test_historical_sales_unchanged(self, setup_business):
        """Test that changing commission config doesn't affect existing sales."""
        business = setup_business["business"]
        location = setup_business["location"]
        agent = setup_business["agent"]
        
        # Create item and sale with initial config
        item = InventoryItem.objects.create(
            business=business,
            imei="123456789012347",
            product_name="Xiaomi Note 10",
            order_price=Decimal("200000.00"),
            selling_price=Decimal("250000.00"),
            status="IN_STOCK",
            current_location=location
        )
        
        sale = Sale.objects.create(
            item=item,
            agent=agent,
            location=location,
            sold_at=timezone.localdate(),
            price=Decimal("250000.00"),
            payment_method="CASH"
        )
        
        # Get commission amount
        original_txn = WalletTransaction.objects.filter(
            agent=agent,
            type=TxnType.COMMISSION,
            reference=f"SALE-{sale.id}"
        ).first()
        
        original_amount = original_txn.amount
        
        # Change commission config
        config = CommissionConfig.ensure_config(business)
        config.base_commission_pct = Decimal("15.00")
        config.save()
        
        # Commission should not change for existing sale
        txn_after_change = WalletTransaction.objects.filter(
            agent=agent,
            type=TxnType.COMMISSION,
            reference=f"SALE-{sale.id}"
        ).first()
        
        assert txn_after_change.amount == original_amount
    
    def test_commission_summary(self, setup_business):
        """Test get_agent_commission_summary helper."""
        business = setup_business["business"]
        location = setup_business["location"]
        agent = setup_business["agent"]
        
        # Create multiple sales
        for i in range(3):
            item = InventoryItem.objects.create(
                business=business,
                imei=f"12345678901234{i}",
                product_name=f"Phone {i}",
                order_price=Decimal("100000.00"),
                selling_price=Decimal("150000.00"),
                status="IN_STOCK",
                current_location=location
            )
            
            Sale.objects.create(
                item=item,
                agent=agent,
                location=location,
                sold_at=timezone.localdate(),
                price=Decimal("150000.00"),
                payment_method="CASH"
            )
        
        # Get summary
        summary = get_agent_commission_summary(agent, business)
        
        # Each sale: 12% of 150,000 = 18,000
        # 3 sales = 54,000
        assert summary["all_time_total"] == Decimal("54000.00")
        assert summary["all_time_count"] == 3
        assert summary["mtd_total"] == Decimal("54000.00")  # All created today
        assert summary["mtd_count"] == 3
