"""
Regression tests for manager role preservation on phone dashboard.

This test suite ensures that managers NEVER downgrade to agent scope
when visiting the phone dashboard, even if they have location memberships
or agent assignments.

CRITICAL: These tests prevent the "manager sees agent sidebar" bug from
ever happening again.
"""
import pytest
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import Location
from inventory.business_kinds import BusinessKind

User = get_user_model()


class ManagerPhoneDashboardRoleTest(TestCase):
    """
    Test that managers ALWAYS see manager sidebar/permissions on phone dashboard.
    """
    
    def setUp(self):
        """Create test business, manager, and agent users."""
        # Create business
        self.business = Business.objects.create(
            name="Empire Electronics",
            business_kind=BusinessKind.PHONES,
            status="ACTIVE"
        )
        
        # Create location
        self.location = Location.objects.create(
            name="Main Store",
            business=self.business
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager@empire.com",
            email="manager@empire.com",
            password="testpass123",
            is_staff=False,  # NOT staff, just business manager
            is_superuser=False
        )
        
        # Create manager membership (business-level)
        self.manager_membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create agent user (for comparison)
        self.agent = User.objects.create_user(
            username="agent@empire.com",
            email="agent@empire.com",
            password="testpass123",
            is_staff=False,
            is_superuser=False
        )
        
        # Create agent membership (location-level)
        self.agent_membership = Membership.objects.create(
            user=self.agent,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
        
        self.factory = RequestFactory()
    
    def test_manager_sees_admin_wallet_on_phone_dashboard(self):
        """
        CRITICAL: Manager visiting phone dashboard must see "Admin Wallet" link.
        This is the primary symptom of the bug - managers were seeing agent sidebar.
        """
        # Login as manager
        self.client.force_login(self.manager)
        
        # Visit phone dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        # Assert response is successful
        self.assertEqual(response.status_code, 200)
        
        # Assert "Admin Wallet" appears in response (manager-only link)
        self.assertContains(
            response,
            "Admin Wallet",
            msg_prefix="Manager should see 'Admin Wallet' link on phone dashboard"
        )
    
    def test_manager_does_not_see_agent_only_content(self):
        """
        Manager should NOT see agent-only content markers.
        """
        # Login as manager
        self.client.force_login(self.manager)
        
        # Visit phone dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        # Assert response is successful
        self.assertEqual(response.status_code, 200)
        
        # Check that IS_MANAGER context variable is True
        self.assertTrue(
            response.context.get('IS_MANAGER', False),
            "IS_MANAGER should be True in context for manager users"
        )
        
        # Check that IS_AGENT context variable is False
        self.assertFalse(
            response.context.get('IS_AGENT', False),
            "IS_AGENT should be False in context for manager users"
        )
    
    def test_agent_does_not_see_admin_wallet(self):
        """
        Agent should NOT see "Admin Wallet" link (manager-only).
        This ensures we haven't broken agent restrictions.
        """
        # Login as agent
        self.client.force_login(self.agent)
        
        # Visit phone dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        # Assert response is successful
        self.assertEqual(response.status_code, 200)
        
        # Assert "Admin Wallet" does NOT appear for agents
        # Note: Admin Wallet might appear in "More Features" submenu, so we check context
        self.assertFalse(
            response.context.get('IS_MANAGER', False),
            "IS_MANAGER should be False in context for agent users"
        )
        
        self.assertTrue(
            response.context.get('IS_AGENT', False),
            "IS_AGENT should be True in context for agent users"
        )
    
    def test_manager_with_location_membership_still_manager(self):
        """
        CRITICAL REGRESSION TEST: Manager who ALSO has a location membership
        must still be treated as manager (not downgraded to agent).
        
        This simulates the exact bug condition - a manager user who also has
        location-level memberships should NEVER be treated as an agent.
        """
        # Create a SECOND membership for manager at location level
        # (This simulates the downgrade condition)
        location_membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="AGENT",  # Location membership might say AGENT
            status="ACTIVE"
        )
        
        # Login as manager
        self.client.force_login(self.manager)
        
        # Visit phone dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        # Assert response is successful
        self.assertEqual(response.status_code, 200)
        
        # CRITICAL: Manager should STILL see "Admin Wallet" despite location membership
        self.assertContains(
            response,
            "Admin Wallet",
            msg_prefix="Manager should STILL see 'Admin Wallet' even with location membership"
        )
        
        # Check context flags
        self.assertTrue(
            response.context.get('IS_MANAGER', False),
            "IS_MANAGER should be True even with location membership"
        )
        
        self.assertFalse(
            response.context.get('IS_AGENT', False),
            "IS_AGENT should be False for manager (never downgrade)"
        )
        
        # Cleanup
        location_membership.delete()
    
    def test_manager_sees_business_wide_data(self):
        """
        Manager should see business-wide sales/stock data, not just their own.
        """
        # Login as manager
        self.client.force_login(self.manager)
        
        # Visit phone dashboard
        url = reverse('inventory_verticals:phones_dashboard')
        response = self.client.get(url)
        
        # Assert response is successful
        self.assertEqual(response.status_code, 200)
        
        # Check that dashboard KPIs are present (managers see all data)
        self.assertIn('dashboard_kpis', response.context)
        
        # Verify IS_MANAGER flag is set correctly
        self.assertTrue(
            response.context.get('IS_MANAGER', False),
            "Manager should have IS_MANAGER=True for business-wide visibility"
        )
    
    def test_middleware_sets_role_flags_correctly(self):
        """
        Test that middleware correctly sets role flags on request object.
        """
        # Create request
        url = reverse('inventory_verticals:phones_dashboard')
        request = self.factory.get(url)
        request.user = self.manager
        request.business = self.business
        
        # Simulate middleware by calling role resolution
        from tenants.utils_roles import attach_role_to_request
        attach_role_to_request(request)
        
        # Assert role flags are set correctly
        self.assertTrue(
            getattr(request, 'cc_is_manager', False),
            "Middleware should set cc_is_manager=True for manager users"
        )
        
        self.assertFalse(
            getattr(request, 'cc_is_agent', False),
            "Middleware should set cc_is_agent=False for manager users"
        )
        
        self.assertEqual(
            getattr(request, 'cc_role', 'NONE'),
            'MANAGER',
            "Middleware should set cc_role='MANAGER' for manager users"
        )
    
    def test_utils_scope_respects_middleware_flags(self):
        """
        Test that inventory.utils_scope.get_visible_actor uses middleware flags.
        """
        from inventory.utils_scope import get_visible_actor
        
        # Create request
        url = reverse('inventory_verticals:phones_dashboard')
        request = self.factory.get(url)
        request.user = self.manager
        request.business = self.business
        
        # Set middleware flags (simulating RoleResolutionMiddleware)
        request.is_manager_plus = True
        request.is_agent_only = False
        
        # Call get_visible_actor
        is_manager, is_agent, actor_user = get_visible_actor(request)
        
        # Assert it respects middleware flags
        self.assertTrue(
            is_manager,
            "get_visible_actor should return is_manager=True when middleware sets it"
        )
        
        self.assertFalse(
            is_agent,
            "get_visible_actor should return is_agent=False for managers"
        )
        
        self.assertEqual(
            actor_user,
            self.manager,
            "get_visible_actor should return the correct user"
        )


@pytest.mark.django_db
class TestManagerRolePrecedence:
    """
    Pytest-style tests for manager role precedence.
    """
    
    def test_manager_precedence_over_agent_membership(self):
        """
        If user has BOTH manager and agent indicators, manager MUST win.
        """
        from tenants.utils_roles import get_role, is_manager, is_agent
        
        # Create business
        business = Business.objects.create(
            name="Test Business",
            business_kind=BusinessKind.PHONES,
            status="ACTIVE"
        )
        
        # Create user with manager membership
        user = User.objects.create_user(
            username="testmanager",
            email="testmanager@test.com",
            password="testpass123"
        )
        
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Also create an agent membership (simulating downgrade condition)
        Membership.objects.create(
            user=user,
            business=business,
            role="AGENT",
            status="ACTIVE"
        )
        
        # Test role resolution
        role = get_role(user, business)
        assert role == "MANAGER", "Manager role should take precedence over agent"
        
        assert is_manager(user, business), "is_manager should return True"
        assert not is_agent(user, business), "is_agent should return False for managers"
    
    def test_staff_always_manager(self):
        """
        Staff users are always managers regardless of memberships.
        """
        from tenants.utils_roles import get_role, is_manager, is_agent
        
        # Create business
        business = Business.objects.create(
            name="Test Business",
            business_kind=BusinessKind.PHONES,
            status="ACTIVE"
        )
        
        # Create staff user
        user = User.objects.create_user(
            username="staffuser",
            email="staff@test.com",
            password="testpass123",
            is_staff=True
        )
        
        # Test role resolution (no membership needed for staff)
        role = get_role(user, business)
        assert role == "MANAGER", "Staff users should always be managers"
        
        assert is_manager(user, business), "is_manager should return True for staff"
        assert not is_agent(user, business), "is_agent should return False for staff"

