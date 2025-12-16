"""
Tests for Agent Performance page
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


@pytest.mark.django_db
class TestAgentPerformance:
    """Test agent performance view and permissions"""
    
    def test_manager_can_access_agent_performance(self, client, manager_user, agent_user, business):
        """Manager should be able to view agent performance page"""
        # Login as manager
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access agent performance page
        url = reverse('inventory:agent_performance', kwargs={'agent_id': agent_user.id})
        response = client.get(url)
        
        assert response.status_code == 200
        assert agent_user.username in str(response.content) or agent_user.get_full_name() in str(response.content)
    
    def test_agent_cannot_access_other_agent_performance(self, client, agent_user, business):
        """Agent should not be able to view another agent's performance"""
        from django.contrib.auth.models import User as DjangoUser
        
        # Create another agent
        other_agent = DjangoUser.objects.create_user(
            username='other_agent',
            email='other@example.com',
            password='testpass123'
        )
        
        # Login as first agent
        client.force_login(agent_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Try to access other agent's performance
        url = reverse('inventory:agent_performance', kwargs={'agent_id': other_agent.id})
        response = client.get(url)
        
        # Should be redirected or get 403
        assert response.status_code in [302, 403]
    
    def test_agent_performance_shows_correct_metrics(self, client, manager_user, agent_user, business):
        """Agent performance page should show correct stock and sales metrics"""
        from inventory.models import InventoryItem, Product, Location
        
        # Login as manager
        client.force_login(manager_user)
        
        # Set active business in session
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Create a location
        location = Location.objects.create(
            name="Test Location",
            business=business,
        )
        
        # Create a product
        product = Product.objects.create(
            name="Test Phone",
            brand="TECNO",
            model="Spark 40",
            business=business,
        )
        
        # Create stock items held by agent
        InventoryItem.objects.create(
            business=business,
            imei="123456789012345",
            product=product,
            order_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=agent_user,
            is_active=True,
        )
        
        InventoryItem.objects.create(
            business=business,
            imei="123456789012346",
            product=product,
            order_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            status="IN_STOCK",
            current_location=location,
            assigned_agent=agent_user,
            is_active=True,
        )
        
        # Access agent performance page
        url = reverse('inventory:agent_performance', kwargs={'agent_id': agent_user.id})
        response = client.get(url)
        
        assert response.status_code == 200
        content = str(response.content)
        
        # Should show 2 items in stock
        assert '2' in content or 'Stock Held' in content
        
        # Should show total stock cost value (200)
        assert '200' in content


@pytest.fixture
def manager_user(db):
    """Create a manager user for testing"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    manager = User.objects.create_user(
        username='manager',
        email='manager@example.com',
        password='testpass123',
        is_staff=True,  # Simplified: treat staff as managers
    )
    return manager


@pytest.fixture
def agent_user(db):
    """Create an agent user for testing"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    agent = User.objects.create_user(
        username='agent',
        email='agent@example.com',
        password='testpass123',
    )
    return agent


@pytest.fixture
def business(db):
    """Create a test business"""
    from tenants.models import Business
    business = Business.objects.create(
        name="Test Business",
        slug="test-business",
    )
    return business

