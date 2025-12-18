# inventory/tests/test_stock_overview_analytics.py
"""
Tests for cross-vertical stock overview analytics feature.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Product, Location, MerchProduct
from inventory.services.analytics_stock_overview import get_cross_vertical_stock_overview

User = get_user_model()


@pytest.mark.django_db
class TestStockOverviewAnalytics:
    """Test cross-vertical stock overview feature."""
    
    @pytest.fixture
    def business(self):
        """Create a test business."""
        return Business.objects.create(
            name="Test Multi-Vertical",
            business_kind="phones",
        )
    
    @pytest.fixture
    def manager_user(self, business):
        """Create a manager user."""
        user = User.objects.create_user(
            username="manager",
            password="testpass123",
            email="manager@test.com",
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )
        return user
    
    @pytest.fixture
    def agent_user(self, business):
        """Create an agent user."""
        user = User.objects.create_user(
            username="agent",
            password="testpass123",
            email="agent@test.com",
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="AGENT",
            status="ACTIVE",
        )
        return user
    
    @pytest.fixture
    def location(self, business):
        """Create a test location."""
        return Location.objects.create(
            business=business,
            name="Main Store",
        )
    
    @pytest.fixture
    def phone_product(self, business):
        """Create a phone product."""
        return Product.objects.create(
            business=business,
            brand="Samsung",
            model="Galaxy S21",
            category="phone",
        )
    
    def test_get_cross_vertical_stock_overview_empty(self, business):
        """Test stock overview with no stock."""
        result = get_cross_vertical_stock_overview(business)
        
        assert result['total_units'] == 0
        assert result['labels'] == []
        assert result['values'] == []
        assert result['most_stocked_vertical'] == "None"
    
    def test_get_cross_vertical_stock_overview_phones_only(self, business, location, phone_product):
        """Test stock overview with phone inventory only."""
        # Create 5 phone items
        for i in range(5):
            InventoryItem.objects.create(
                business=business,
                product=phone_product,
                current_location=location,
                status='IN_STOCK',
                is_active=True,
                order_price=Decimal('500.00'),
                selling_price=Decimal('600.00'),
            )
        
        result = get_cross_vertical_stock_overview(business)
        
        assert result['total_units'] == 5
        assert 'Phones' in result['labels']
        assert 'Phones' in result['breakdown']
        assert result['breakdown']['Phones'] == 5
        assert result['most_stocked_vertical'] == 'Phones'
    
    def test_get_cross_vertical_stock_overview_multiple_verticals(self, business, location, phone_product):
        """Test stock overview with multiple verticals having stock."""
        # Create phones
        for i in range(3):
            InventoryItem.objects.create(
                business=business,
                product=phone_product,
                current_location=location,
                status='IN_STOCK',
                is_active=True,
                order_price=Decimal('500.00'),
                selling_price=Decimal('600.00'),
            )
        
        # Create liquor products
        liquor_product = MerchProduct.objects.create(
            business=business,
            name="Carlsberg Beer",
            kind="liquor",
            quantity=50,
        )
        
        # Create clothing products
        clothing_product = MerchProduct.objects.create(
            business=business,
            name="T-Shirt",
            kind="clothing",
            quantity=20,
        )
        
        result = get_cross_vertical_stock_overview(business)
        
        assert result['total_units'] == 73  # 3 + 50 + 20
        assert 'Phones' in result['breakdown']
        assert 'Liquor' in result['breakdown']
        assert 'Clothing' in result['breakdown']
        assert result['breakdown']['Phones'] == 3
        assert result['breakdown']['Liquor'] == 50
        assert result['breakdown']['Clothing'] == 20
        assert result['most_stocked_vertical'] == 'Liquor'
    
    def test_api_stock_overview_endpoint_manager(self, business, manager_user, client: Client):
        """Test API endpoint returns stock overview for manager."""
        client.force_login(manager_user)
        
        # Set business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('inventory:analytics_stock_overview_cross_vertical')
        response = client.get(url)
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'ok' in data
        assert 'labels' in data
        assert 'values' in data
        assert 'total_units' in data
        assert 'most_stocked_vertical' in data
    
    def test_api_stock_overview_endpoint_agent(self, business, agent_user, client: Client):
        """Test API endpoint works for agent (should respect scoping if any)."""
        client.force_login(agent_user)
        
        # Set business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        url = reverse('inventory:analytics_stock_overview_cross_vertical')
        response = client.get(url)
        
        assert response.status_code == 200
        data = response.json()
        
        # Agent should still see data (global view for analytics per requirements)
        assert 'ok' in data
        assert 'labels' in data
        assert 'values' in data
    
    def test_stock_overview_ignores_sold_items(self, business, location, phone_product):
        """Test that sold items are not counted in stock overview."""
        # Create in-stock items
        for i in range(3):
            InventoryItem.objects.create(
                business=business,
                product=phone_product,
                current_location=location,
                status='IN_STOCK',
                is_active=True,
                order_price=Decimal('500.00'),
                selling_price=Decimal('600.00'),
            )
        
        # Create sold items (should not be counted)
        for i in range(2):
            InventoryItem.objects.create(
                business=business,
                product=phone_product,
                current_location=location,
                status='SOLD',
                is_active=True,
                order_price=Decimal('500.00'),
                selling_price=Decimal('600.00'),
            )
        
        result = get_cross_vertical_stock_overview(business)
        
        assert result['total_units'] == 3  # Only in-stock items
        assert result['breakdown']['Phones'] == 3
    
    def test_stock_overview_ignores_archived_items(self, business, location, phone_product):
        """Test that archived items are not counted in stock overview."""
        # Create active items
        for i in range(2):
            InventoryItem.objects.create(
                business=business,
                product=phone_product,
                current_location=location,
                status='IN_STOCK',
                is_active=True,
                order_price=Decimal('500.00'),
                selling_price=Decimal('600.00'),
            )
        
        # Create archived items (should not be counted)
        for i in range(3):
            InventoryItem.objects.create(
                business=business,
                product=phone_product,
                current_location=location,
                status='IN_STOCK',
                is_active=False,  # Archived
                order_price=Decimal('500.00'),
                selling_price=Decimal('600.00'),
            )
        
        result = get_cross_vertical_stock_overview(business)
        
        assert result['total_units'] == 2  # Only active items
        assert result['breakdown']['Phones'] == 2

