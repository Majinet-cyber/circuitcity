# tests/test_liquor_cogs_inventory_purchases.py
"""
Tests for Liquor COGS calculation based on inventory purchases.
Ensures COGS card shows inventory purchases cost when sales COGS is unavailable.
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from inventory.models import MerchProduct
from inventory.models_verticals import LiquorStockInTransaction
from inventory.business_kinds import BusinessKind
from tenants.models import Business, Membership


@pytest.mark.django_db
class TestLiquorCOGSInventoryPurchases:
    """Test suite for Liquor COGS calculation using inventory purchases."""

    @pytest.fixture
    def business(self):
        """Create a liquor business."""
        return Business.objects.create(
            name="Test Liquor Store",
            business_kind=BusinessKind.LIQUOR,
            is_active=True
        )

    @pytest.fixture
    def manager(self, django_user_model):
        """Create a manager user."""
        return django_user_model.objects.create_user(
            username="manager",
            password="testpass123",
            email="manager@test.com"
        )

    @pytest.fixture
    def product(self, business):
        """Create a liquor product."""
        return MerchProduct.objects.create(
            business=business,
            name="Test Beer",
            kind=BusinessKind.LIQUOR,
            category="beer",
            quantity_in_stock=0,
            cost_per_bottle=Decimal("2000.00"),
            price_per_bottle=Decimal("3000.00"),
            is_active=True
        )

    def test_cogs_shows_inventory_purchases_when_no_sales(self, client, business, manager, product):
        """
        Test that COGS card shows inventory purchases cost when there are no sales.
        This is the primary fix: Liquor COGS card is inventory purchases cost when sales COGS is unavailable.
        """
        # Create membership
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=None
        )

        # Create stock-in transactions (last 30 days)
        today = timezone.localdate()
        
        # Transaction 1: 20 bottles @ MK 2000 each = MK 40,000
        LiquorStockInTransaction.objects.create(
            business=business,
            product=product,
            quantity_added=20,
            unit_cost=Decimal("2000.00"),
            total_cost=Decimal("40000.00"),
            created_by=manager,
            date_received=today - timedelta(days=5)
        )
        
        # Transaction 2: 30 bottles @ MK 2500 each = MK 75,000
        LiquorStockInTransaction.objects.create(
            business=business,
            product=product,
            quantity_added=30,
            unit_cost=Decimal("2500.00"),
            total_cost=Decimal("75000.00"),
            created_by=manager,
            date_received=today - timedelta(days=10)
        )
        
        # Expected inventory purchases cost = 40,000 + 75,000 = 115,000
        expected_inventory_purchases = Decimal("115000.00")
        
        # Access dashboard
        client.force_login(manager)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        response = client.get('/verticals/liquor/dashboard/')
        
        assert response.status_code == 200
        
        # COGS should show inventory purchases cost (not zero)
        assert response.context['inventory_costs'] == expected_inventory_purchases
        assert response.context['inventory_purchases_30d_mwk'] == expected_inventory_purchases
        
        # Verify COGS is NOT zero
        assert response.context['inventory_costs'] > Decimal("0.00")
        
        # Verify content shows COGS card
        content = response.content.decode('utf-8')
        assert 'COGS' in content
        assert 'MK 115,000.00' in content or 'MK 115000.00' in content

    def test_cogs_excludes_old_inventory_purchases(self, client, business, manager, product):
        """Test that COGS only includes inventory purchases from last 30 days."""
        # Create membership
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=None
        )

        today = timezone.localdate()
        
        # Recent transaction (within 30 days)
        LiquorStockInTransaction.objects.create(
            business=business,
            product=product,
            quantity_added=10,
            unit_cost=Decimal("2000.00"),
            total_cost=Decimal("20000.00"),
            created_by=manager,
            date_received=today - timedelta(days=15)
        )
        
        # Old transaction (outside 30 days) - should NOT be included
        LiquorStockInTransaction.objects.create(
            business=business,
            product=product,
            quantity_added=50,
            unit_cost=Decimal("2000.00"),
            total_cost=Decimal("100000.00"),
            created_by=manager,
            date_received=today - timedelta(days=35)
        )
        
        # Expected: only recent transaction
        expected_inventory_purchases = Decimal("20000.00")
        
        # Access dashboard
        client.force_login(manager)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        response = client.get('/verticals/liquor/dashboard/')
        
        assert response.status_code == 200
        assert response.context['inventory_purchases_30d_mwk'] == expected_inventory_purchases
        assert response.context['inventory_costs'] == expected_inventory_purchases

    def test_stock_value_remains_unchanged(self, client, business, manager, product):
        """Test that Stock Value calculation is NOT affected by COGS fix."""
        # Create membership
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=None
        )

        # Update product stock
        product.quantity_in_stock = 100
        product.cost_per_bottle = Decimal("2500.00")
        product.save()
        
        # Create stock-in transaction
        LiquorStockInTransaction.objects.create(
            business=business,
            product=product,
            quantity_added=100,
            unit_cost=Decimal("2500.00"),
            total_cost=Decimal("250000.00"),
            created_by=manager,
            date_received=timezone.localdate()
        )
        
        # Expected stock value = 100 × 2500 = 250,000
        expected_stock_value = Decimal("250000.00")
        
        # Access dashboard
        client.force_login(manager)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        response = client.get('/verticals/liquor/dashboard/')
        
        assert response.status_code == 200
        
        # Stock Value should remain correct
        assert response.context['total_stock_value'] == expected_stock_value
        
        # COGS should show inventory purchases
        assert response.context['inventory_costs'] == expected_stock_value
        
        # In this case, they match because we just stocked in
        assert response.context['total_stock_value'] == response.context['inventory_costs']

    def test_cogs_card_label_updated(self, client, business, manager, product):
        """Test that COGS card subtitle reflects inventory purchases."""
        # Create membership
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=None
        )

        # Create stock-in transaction
        LiquorStockInTransaction.objects.create(
            business=business,
            product=product,
            quantity_added=10,
            unit_cost=Decimal("2000.00"),
            total_cost=Decimal("20000.00"),
            created_by=manager,
            date_received=timezone.localdate()
        )
        
        # Access dashboard
        client.force_login(manager)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        response = client.get('/verticals/liquor/dashboard/')
        
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        
        # Verify COGS card has updated subtitle
        assert 'Inventory purchases' in content
        assert 'LIQUOR_DASH_COGS_V3' in content  # Proof marker

    def test_multiple_products_inventory_purchases(self, client, business, manager):
        """Test COGS calculation with multiple products."""
        # Create membership
        Membership.objects.create(
            user=manager,
            business=business,
            role="MANAGER",
            status="ACTIVE",
            location=None
        )

        # Create multiple products
        product1 = MerchProduct.objects.create(
            business=business,
            name="Beer",
            kind=BusinessKind.LIQUOR,
            category="beer",
            quantity_in_stock=0,
            cost_per_bottle=Decimal("2000.00"),
            is_active=True
        )
        
        product2 = MerchProduct.objects.create(
            business=business,
            name="Wine",
            kind=BusinessKind.LIQUOR,
            category="wine",
            quantity_in_stock=0,
            cost_per_bottle=Decimal("5000.00"),
            is_active=True
        )
        
        # Create stock-in transactions for both products
        LiquorStockInTransaction.objects.create(
            business=business,
            product=product1,
            quantity_added=20,
            unit_cost=Decimal("2000.00"),
            total_cost=Decimal("40000.00"),
            created_by=manager,
            date_received=timezone.localdate()
        )
        
        LiquorStockInTransaction.objects.create(
            business=business,
            product=product2,
            quantity_added=10,
            unit_cost=Decimal("5000.00"),
            total_cost=Decimal("50000.00"),
            created_by=manager,
            date_received=timezone.localdate()
        )
        
        # Expected total = 40,000 + 50,000 = 90,000
        expected_total = Decimal("90000.00")
        
        # Access dashboard
        client.force_login(manager)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        response = client.get('/verticals/liquor/dashboard/')
        
        assert response.status_code == 200
        assert response.context['inventory_purchases_30d_mwk'] == expected_total
        assert response.context['inventory_costs'] == expected_total

