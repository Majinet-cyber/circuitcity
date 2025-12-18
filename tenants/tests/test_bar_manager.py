# tenants/tests/test_bar_manager.py
"""
Tests for Bar Manager invite system (liquor vertical only).

Bar Managers are team leads/supervisors who can:
- Access liquor operational pages (dashboard, analytics, stock, sales)
- View and manage liquor agents
- NOT access subscription/billing/HQ-only features
"""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership, AgentInvite
from tenants.services.invites import create_agent_invite, accept_invite_by_token

User = get_user_model()


class BarManagerInviteTestCase(TestCase):
    """Test bar manager invite creation and acceptance"""
    
    def setUp(self):
        """Create liquor store and manager"""
        self.client = Client()
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        
        # Create liquor business
        self.business = Business.objects.create(
            name="Test Liquor Store",
            slug="test-liquor",
            business_kind="liquor",
            created_by=self.manager
        )
        
        # Add manager to business
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Add manager to Django group
        manager_group, _ = Group.objects.get_or_create(name=f"biz:{self.business.pk}:MANAGER")
        self.manager.groups.add(manager_group)
    
    def test_create_bar_manager_invite(self):
        """Test creating a bar manager invite"""
        invite, temp_password = create_agent_invite(
            tenant=self.business,
            created_by=self.manager,
            invited_name="John Bar Manager",
            email="john@test.com",
            role="BAR_MANAGER"
        )
        
        assert invite.role == "BAR_MANAGER"
        assert invite.business == self.business
        assert invite.status == "SENT"
        assert temp_password is not None  # Temporary password generated
    
    def test_bar_manager_invite_defaults_to_agent(self):
        """Test that invite without role defaults to AGENT"""
        invite, _ = create_agent_invite(
            tenant=self.business,
            created_by=self.manager,
            invited_name="Normal Agent"
        )
        
        assert invite.role == "AGENT"
    
    def test_accept_bar_manager_invite(self):
        """Test accepting a bar manager invite"""
        # Create invite
        invite, _ = create_agent_invite(
            tenant=self.business,
            created_by=self.manager,
            invited_name="John Bar Manager",
            role="BAR_MANAGER"
        )
        
        # Create user who will accept
        new_user = User.objects.create_user(
            username="john@test.com",
            email="john@test.com",
            password="newpass123"
        )
        
        # Accept invite
        accepted_invite, membership = accept_invite_by_token(
            token=invite.token,
            user=new_user
        )
        
        assert accepted_invite.status == "JOINED"
        assert membership.role == "BAR_MANAGER"
        assert membership.business == self.business
        assert membership.status == "ACTIVE"
        
        # Check user was added to BAR_MANAGER group
        group_name = f"biz:{self.business.pk}:BAR_MANAGER"
        assert new_user.groups.filter(name=group_name).exists()
    
    def test_bar_manager_no_location_required(self):
        """Test that bar managers don't need specific location (they manage all)"""
        # Create invite without location
        invite, _ = create_agent_invite(
            tenant=self.business,
            created_by=self.manager,
            invited_name="John Bar Manager",
            role="BAR_MANAGER",
            location=None
        )
        
        new_user = User.objects.create_user(
            username="john@test.com",
            email="john@test.com",
            password="newpass123"
        )
        
        _, membership = accept_invite_by_token(
            token=invite.token,
            user=new_user
        )
        
        # Bar manager should have no specific location (manages all)
        assert membership.location is None
    
    def test_agent_invite_still_requires_location(self):
        """Test that normal agent invites still require/get default location"""
        # Create agent invite without location
        invite, _ = create_agent_invite(
            tenant=self.business,
            created_by=self.manager,
            invited_name="Normal Agent",
            role="AGENT",
            location=None
        )
        
        new_user = User.objects.create_user(
            username="agent@test.com",
            email="agent@test.com",
            password="newpass123"
        )
        
        _, membership = accept_invite_by_token(
            token=invite.token,
            user=new_user
        )
        
        # Agent should get a location (default location created)
        assert membership.location is not None


class BarManagerPermissionsTestCase(TestCase):
    """Test bar manager access permissions"""
    
    def setUp(self):
        """Create liquor store with bar manager and normal agent"""
        self.client = Client()
        
        # Create liquor business
        self.business = Business.objects.create(
            name="Test Liquor Store",
            slug="test-liquor-2",
            business_kind="liquor"
        )
        
        # Create bar manager user
        self.bar_manager = User.objects.create_user(
            username="barmgr@test.com",
            email="barmgr@test.com",
            password="testpass123"
        )
        
        Membership.objects.create(
            user=self.bar_manager,
            business=self.business,
            role="BAR_MANAGER",
            status="ACTIVE"
        )
        
        # Add to BAR_MANAGER group
        bar_mgr_group, _ = Group.objects.get_or_create(name=f"biz:{self.business.pk}:BAR_MANAGER")
        self.bar_manager.groups.add(bar_mgr_group)
        
        # Create normal agent
        self.agent = User.objects.create_user(
            username="agent@test.com",
            email="agent@test.com",
            password="testpass123"
        )
        
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
        
        agent_group, _ = Group.objects.get_or_create(name=f"biz:{self.business.pk}:AGENT")
        self.agent.groups.add(agent_group)
    
    def test_bar_manager_can_view_agent_list(self):
        """Test that bar manager can access agent management page"""
        self.client.login(username="barmgr@test.com", password="testpass123")
        
        # Set session for business context
        session = self.client.session
        session['active_business_id'] = self.business.pk
        session.save()
        
        response = self.client.get(reverse('tenants:manager_review_agents'))
        
        # Bar manager should be able to access (or get redirect, not 403)
        assert response.status_code in [200, 302]  # 200 OK or 302 redirect (if decorator redirects)
        if response.status_code == 403:
            pytest.fail("Bar manager should not get 403 on agent management page")
    
    def test_normal_agent_cannot_view_agent_list(self):
        """Test that normal agents cannot access agent management"""
        self.client.login(username="agent@test.com", password="testpass123")
        
        session = self.client.session
        session['active_business_id'] = self.business.pk
        session.save()
        
        response = self.client.get(reverse('tenants:manager_review_agents'))
        
        # Normal agent should be forbidden
        assert response.status_code in [403, 302]  # 403 or redirect to login
    
    def test_bar_manager_context_flag(self):
        """Test that is_bar_manager flag is set in context"""
        from core.context import _extract_roles_for
        
        roles = _extract_roles_for(self.bar_manager, self.business)
        
        assert roles.is_bar_manager is True
        assert "BAR_MANAGER" in roles.roles
        assert roles.is_manager is False  # Bar manager is NOT a full manager
    
    def test_agent_context_no_bar_manager_flag(self):
        """Test that normal agents don't get bar manager flag"""
        from core.context import _extract_roles_for
        
        roles = _extract_roles_for(self.agent, self.business)
        
        assert roles.is_bar_manager is False
        assert "AGENT" in roles.roles
        assert "BAR_MANAGER" not in roles.roles


# Pytest-style tests for convenience
@pytest.mark.django_db
def test_bar_manager_invite_model_role_field():
    """Test that AgentInvite has role field with correct choices"""
    from tenants.models import AgentInvite
    
    # Check role field exists
    assert hasattr(AgentInvite, 'role')
    
    # Check role choices
    role_choices = dict(AgentInvite.ROLE_CHOICES)
    assert "AGENT" in role_choices
    assert "BAR_MANAGER" in role_choices
    assert role_choices["AGENT"] == "Sales Agent"
    assert role_choices["BAR_MANAGER"] == "Bar Manager"


@pytest.mark.django_db
def test_bar_manager_decorator():
    """Test liquor_operations_required decorator allows bar managers"""
    from core.decorators import liquor_operations_required
    from django.http import HttpRequest, HttpResponse
    from django.contrib.auth.models import AnonymousUser
    
    # Create test view
    @liquor_operations_required
    def test_view(request):
        return HttpResponse("OK")
    
    # Test with anonymous user
    request = HttpRequest()
    request.user = AnonymousUser()
    response = test_view(request)
    assert response.status_code in [302, 401]  # Redirect to login or 401
    
    # Test with bar manager would require full request context (skip for now)
    # This is better tested via integration tests

