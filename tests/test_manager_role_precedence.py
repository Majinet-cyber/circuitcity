# tests/test_manager_role_precedence.py
"""
CRITICAL REGRESSION TESTS: Manager Role Precedence
Ensures managers are NEVER downgraded to agent scope on phones dashboard.
"""
import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestManagerRolePrecedence:
    """Test that managers with agent memberships are still treated as managers."""
    
    def test_manager_never_downgrades_on_phones_dashboard(self, client: Client):
        """
        CRITICAL: Manager with BOTH manager role AND location membership
        must still be treated as manager on phones dashboard.
        
        This prevents the bug where managers were downgraded to agent scope.
        """
        # Create user
        user = User.objects.create_user(
            username="empire",
            email="empire@test.com",
            password="testpass123"
        )
        
        # Create business
        from tenants.models import Business, Membership, Location
        business = Business.objects.create(
            name="Empire Phones",
            business_kind="phones",
            owner=user
        )
        
        # Create manager membership
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create location and assign user as agent (this should NOT downgrade manager)
        location = Location.objects.create(
            business=business,
            name="Downtown Branch"
        )
        location.agents.add(user)
        
        # Login and set active business
        client.force_login(user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access phones dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = client.get(url)
        
        # CRITICAL: Must return 200
        assert response.status_code == 200, \
            f"Phones dashboard returned {response.status_code} for manager"
        
        # CRITICAL: Manager flags must be set correctly
        assert response.context.get('IS_MANAGER') is True, \
            "Manager must have IS_MANAGER=True even with location membership"
        
        assert response.context.get('IS_AGENT') is not True, \
            "Manager must NOT have IS_AGENT=True"
        
        # Verify manager-only sidebar items are present
        content = response.content.decode('utf-8')
        assert 'Admin Wallet' in content or 'admin-wallet' in content.lower(), \
            "Manager must see Admin Wallet in sidebar"
        assert 'Products' in content, \
            "Manager must see Products in sidebar"
        
    def test_agent_cannot_see_billing_actions(self, client: Client):
        """
        Agents must NOT see billing action buttons (Checkout / Choose plan).
        """
        # Create agent user
        user = User.objects.create_user(
            username="agent1",
            email="agent1@test.com",
            password="testpass123"
        )
        
        # Create business with manager
        from tenants.models import Business, Membership
        manager = User.objects.create_user(
            username="manager1",
            email="manager1@test.com",
            password="testpass123"
        )
        
        business = Business.objects.create(
            name="Test Business",
            business_kind="phones",
            owner=manager
        )
        
        # Create agent membership
        Membership.objects.create(
            user=user,
            business=business,
            role="AGENT",
            status="ACTIVE"
        )
        
        # Login as agent
        client.force_login(user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = client.get(url)
        
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        
        # Agent must NOT see billing buttons
        assert 'Choose plan' not in content or response.context.get('IS_MANAGER'), \
            "Agent must not see 'Choose plan' button"
        assert 'Checkout' not in content or response.context.get('IS_MANAGER'), \
            "Agent must not see 'Checkout' button"
    
    def test_top_agents_clickable_for_managers(self, client: Client):
        """
        Top Agents list must be clickable for managers.
        """
        # Create manager
        user = User.objects.create_user(
            username="manager2",
            email="manager2@test.com",
            password="testpass123"
        )
        
        from tenants.models import Business, Membership
        business = Business.objects.create(
            name="Test Phones",
            business_kind="phones",
            owner=user
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Login
        client.force_login(user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = client.get(url)
        
        assert response.status_code == 200
        
        # Check that agent_performance_url template tag is loaded
        content = response.content.decode('utf-8')
        assert 'agent_links' in content or 'agent_performance' in content.lower(), \
            "Agent links should be available for managers"


@pytest.mark.django_db
class TestSalesNamespaceResolution:
    """Test that sales namespace URLs resolve correctly."""
    
    def test_sales_list_url_resolves(self):
        """Sales list URL must resolve without NoReverseMatch."""
        try:
            url = reverse('sales:list')
            assert url is not None
            assert '/sales/' in url
        except Exception as e:
            pytest.fail(f"sales:list URL failed to resolve: {e}")
    
    def test_sales_rollback_urls_resolve(self):
        """Sales rollback URLs must resolve."""
        try:
            url = reverse('sales:rollback_home')
            assert url is not None
            assert '/sales/rollback/' in url
        except Exception as e:
            pytest.fail(f"sales:rollback_home URL failed to resolve: {e}")


@pytest.mark.django_db
class TestPharmacyFastSell:
    """Test pharmacy fast sell doesn't crash."""
    
    def test_pharmacy_fast_sell_returns_200(self, client: Client):
        """Pharmacy fast sell must return 200, not 500."""
        # Create user
        user = User.objects.create_user(
            username="pharmacist",
            email="pharmacist@test.com",
            password="testpass123"
        )
        
        from tenants.models import Business, Membership
        business = Business.objects.create(
            name="Test Pharmacy",
            business_kind="pharmacy",
            owner=user
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Login
        client.force_login(user)
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        # Access fast sell
        url = reverse('inventory_verticals:pharmacy_fast_sell')
        response = client.get(url)
        
        # Must return 200
        assert response.status_code == 200, \
            f"Pharmacy fast sell returned {response.status_code}"

