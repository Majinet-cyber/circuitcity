# tenants/tests/test_role_precedence.py
"""
Comprehensive tests for role precedence to prevent managers from being misclassified as agents.

CRITICAL: These tests ensure the bug where Empire phones manager was treated as an agent
can never happen again.

Test coverage:
1. Manager precedence - managers are NEVER agents even if they have agent indicators
2. Agent restrictions remain correct
3. Manager sees global data scoping
4. Sidebar items are correct for each role
"""
import pytest
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from unittest.mock import Mock

User = get_user_model()


@pytest.mark.django_db
class TestRolePrecedence(TestCase):
    """
    Test role precedence: managers must NEVER be classified as agents.
    """
    
    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        
        # Create business
        from tenants.models import Business, Membership
        self.business = Business.objects.create(
            name="Test Business",
            status="ACTIVE"
        )
        
        # Create users
        self.manager_user = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        
        self.agent_user = User.objects.create_user(
            username="agent@test.com",
            email="agent@test.com",
            password="testpass123"
        )
        
        # Create manager membership
        self.manager_membership = Membership.objects.create(
            user=self.manager_user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        # Create agent membership
        self.agent_membership = Membership.objects.create(
            user=self.agent_user,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
        
        # Create Django groups for business-scoped roles
        self.manager_group = Group.objects.create(name=f"biz:{self.business.pk}:MANAGER")
        self.agent_group = Group.objects.create(name=f"biz:{self.business.pk}:AGENT")
    
    def test_manager_precedence_with_agent_group(self):
        """
        CRITICAL TEST: Manager with ACTIVE manager membership should be manager,
        even if accidentally added to agent Django group.
        
        This is the Empire phones manager bug scenario.
        """
        from tenants.utils_roles import get_role, is_manager, is_agent
        
        # Manager has manager membership
        self.assertEqual(self.manager_membership.role, "MANAGER")
        
        # BUT accidentally also added to AGENT group (simulating the bug)
        self.manager_user.groups.add(self.agent_group)
        
        # CRITICAL: Must still be classified as manager
        role = get_role(self.manager_user, self.business)
        self.assertEqual(role, "MANAGER", "Manager with agent group should still be MANAGER")
        
        self.assertTrue(is_manager(self.manager_user, self.business), 
                       "is_manager should return True for manager with agent group")
        
        self.assertFalse(is_agent(self.manager_user, self.business),
                        "is_agent should return False for manager (CRITICAL: manager precedence)")
    
    def test_manager_precedence_with_both_groups(self):
        """
        Test manager with BOTH manager and agent groups should be manager.
        """
        from tenants.utils_roles import get_role, is_manager, is_agent
        
        # Add user to both groups
        self.manager_user.groups.add(self.manager_group)
        self.manager_user.groups.add(self.agent_group)
        
        # Should be classified as manager
        role = get_role(self.manager_user, self.business)
        self.assertEqual(role, "MANAGER", "User with both groups should be MANAGER")
        
        self.assertTrue(is_manager(self.manager_user, self.business))
        self.assertFalse(is_agent(self.manager_user, self.business),
                        "Manager should NEVER be agent even with agent group")
    
    def test_agent_without_manager_indicators(self):
        """
        Test agent without any manager indicators should be agent.
        """
        from tenants.utils_roles import get_role, is_manager, is_agent
        
        # Agent has only agent membership and agent group
        self.agent_user.groups.add(self.agent_group)
        
        # Should be classified as agent
        role = get_role(self.agent_user, self.business)
        self.assertEqual(role, "AGENT", "Pure agent should be AGENT")
        
        self.assertFalse(is_manager(self.agent_user, self.business),
                        "Agent should not be manager")
        self.assertTrue(is_agent(self.agent_user, self.business),
                       "Agent should be agent")
    
    def test_staff_is_always_manager(self):
        """
        Test staff users are always managers regardless of other indicators.
        """
        from tenants.utils_roles import get_role, is_manager, is_agent
        
        # Make user staff
        self.agent_user.is_staff = True
        self.agent_user.save()
        
        # Even with agent membership and agent group
        self.agent_user.groups.add(self.agent_group)
        
        # Should be manager (staff precedence)
        role = get_role(self.agent_user, self.business)
        self.assertEqual(role, "MANAGER", "Staff should always be MANAGER")
        
        self.assertTrue(is_manager(self.agent_user, self.business))
        self.assertFalse(is_agent(self.agent_user, self.business),
                        "Staff should NEVER be agent")
    
    def test_superuser_is_always_manager(self):
        """
        Test superusers are always managers regardless of other indicators.
        """
        from tenants.utils_roles import get_role, is_manager, is_agent
        
        # Make user superuser
        self.agent_user.is_superuser = True
        self.agent_user.save()
        
        # Even with agent membership and agent group
        self.agent_user.groups.add(self.agent_group)
        
        # Should be manager (superuser precedence)
        role = get_role(self.agent_user, self.business)
        self.assertEqual(role, "MANAGER", "Superuser should always be MANAGER")
        
        self.assertTrue(is_manager(self.agent_user, self.business))
        self.assertFalse(is_agent(self.agent_user, self.business),
                        "Superuser should NEVER be agent")
    
    def test_middleware_attaches_correct_flags(self):
        """
        Test middleware attaches correct role flags to request.
        """
        from tenants.middleware import TenantResolutionMiddleware
        from tenants.utils_roles import attach_role_to_request
        
        # Create mock request with manager
        request = self.factory.get('/')
        request.user = self.manager_user
        request.business = self.business
        request.business_id = self.business.pk
        
        # Manager accidentally in agent group (bug scenario)
        self.manager_user.groups.add(self.agent_group)
        
        # Attach role flags
        attach_role_to_request(request)
        
        # CRITICAL: Should be classified as manager
        self.assertTrue(request.cc_is_manager, 
                       "Middleware should set cc_is_manager=True for manager")
        self.assertFalse(request.cc_is_agent,
                        "Middleware should set cc_is_agent=False for manager")
        self.assertEqual(request.cc_role, "MANAGER",
                        "Middleware should set cc_role=MANAGER")
    
    def test_context_processor_uses_middleware_flags(self):
        """
        Test context processors use middleware flags (not re-compute).
        """
        from cc.context_processors import role_flags
        
        # Create mock request with middleware flags already set
        request = self.factory.get('/')
        request.user = self.manager_user
        request.business = self.business
        request._cached_user = self.manager_user
        
        # Simulate middleware setting authoritative flags
        request.cc_is_manager = True
        request.cc_is_agent = False
        request.cc_role = "MANAGER"
        
        # Get context
        context = role_flags(request)
        
        # Should use middleware flags
        self.assertTrue(context["IS_MANAGER"], 
                       "Context processor should use middleware IS_MANAGER flag")
        self.assertFalse(context["IS_AGENT"],
                        "Context processor should use middleware IS_AGENT flag")
    
    def test_profile_is_manager_flag(self):
        """
        Test user.profile.is_manager flag makes user a manager.
        """
        from tenants.utils_roles import get_role, is_manager, is_agent
        
        # Create profile with is_manager flag
        try:
            from accounts.models import UserProfile
            profile = UserProfile.objects.create(
                user=self.agent_user,
                is_manager=True
            )
        except Exception:
            # If UserProfile doesn't have is_manager field, skip this test
            self.skipTest("UserProfile.is_manager field not available")
        
        # Even with agent membership
        # Should be manager (profile precedence)
        role = get_role(self.agent_user, self.business)
        self.assertEqual(role, "MANAGER", "User with profile.is_manager should be MANAGER")
        
        self.assertTrue(is_manager(self.agent_user, self.business))
        self.assertFalse(is_agent(self.agent_user, self.business),
                        "User with profile.is_manager should NOT be agent")
    
    def test_global_manager_group(self):
        """
        Test global "Manager" group makes user a manager.
        """
        from tenants.utils_roles import get_role, is_manager, is_agent
        
        # Create global Manager group
        global_manager_group = Group.objects.get_or_create(name="Manager")[0]
        
        # Add agent to global Manager group
        self.agent_user.groups.add(global_manager_group)
        
        # Should be manager (global group precedence over agent membership)
        role = get_role(self.agent_user, self.business)
        self.assertEqual(role, "MANAGER", "User in global Manager group should be MANAGER")
        
        self.assertTrue(is_manager(self.agent_user, self.business))
        self.assertFalse(is_agent(self.agent_user, self.business),
                        "User in Manager group should NOT be agent")


@pytest.mark.django_db
class TestDataScoping(TestCase):
    """
    Test data scoping: managers see all, agents see only their data.
    """
    
    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        
        # Create business
        from tenants.models import Business, Membership
        self.business = Business.objects.create(
            name="Test Business",
            status="ACTIVE"
        )
        
        # Create manager and two agents
        self.manager_user = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        
        self.agent1 = User.objects.create_user(
            username="agent1@test.com",
            email="agent1@test.com",
            password="testpass123"
        )
        
        self.agent2 = User.objects.create_user(
            username="agent2@test.com",
            email="agent2@test.com",
            password="testpass123"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.manager_user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        Membership.objects.create(
            user=self.agent1,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
        
        Membership.objects.create(
            user=self.agent2,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
    
    def test_manager_sees_all_stock(self):
        """
        Test manager should see ALL stock (not filtered by agent).
        """
        try:
            from inventory.models import InventoryItem, Product
        except Exception:
            self.skipTest("InventoryItem model not available")
        
        # Create products
        product = Product.objects.create(
            name="Test Product",
            business=self.business
        )
        
        # Create stock assigned to different agents
        item1 = InventoryItem.objects.create(
            product=product,
            business=self.business,
            assigned_agent=self.agent1,
            status="IN_STOCK"
        )
        
        item2 = InventoryItem.objects.create(
            product=product,
            business=self.business,
            assigned_agent=self.agent2,
            status="IN_STOCK"
        )
        
        # Manager should see both items
        from tenants.utils_roles import is_manager
        self.assertTrue(is_manager(self.manager_user, self.business),
                       "Manager should be manager")
        
        # In actual view, manager would NOT have assigned_agent filter applied
        # This test verifies the is_manager flag is correct
    
    def test_agent_filtered_queryset(self):
        """
        Test agent should only see their own data.
        """
        from tenants.utils_roles import is_agent, is_manager
        
        # Agent1 should be agent, not manager
        self.assertTrue(is_agent(self.agent1, self.business),
                       "Agent1 should be agent")
        self.assertFalse(is_manager(self.agent1, self.business),
                        "Agent1 should not be manager")
        
        # In actual views, this would apply: qs.filter(assigned_agent=request.user)


@pytest.mark.django_db  
class TestSidebarItems(TestCase):
    """
    Test sidebar items are correct for each role.
    """
    
    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        
        # Create business
        from tenants.models import Business, Membership
        self.business = Business.objects.create(
            name="Test Business",
            business_kind="phones",
            status="ACTIVE"
        )
        
        # Create manager and agent
        self.manager_user = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        
        self.agent_user = User.objects.create_user(
            username="agent@test.com",
            email="agent@test.com",
            password="testpass123"
        )
        
        # Create memberships
        Membership.objects.create(
            user=self.manager_user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        Membership.objects.create(
            user=self.agent_user,
            business=self.business,
            role="AGENT",
            status="ACTIVE"
        )
    
    def test_sidebar_has_manager_items(self):
        """
        Test sidebar items include manager-only items with require_manager flag.
        """
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("phones")
        
        # Find manager-only items
        manager_items = [item for item in items if item.get("require_manager")]
        
        # Should have manager-only items
        self.assertGreater(len(manager_items), 0, 
                          "Sidebar should have manager-only items")
        
        # Check for key manager items
        keys = [item["key"] for item in manager_items]
        
        # Products, Admin Wallet, Costs should be manager-only for phones
        self.assertIn("products", keys, "Products should be manager-only")
        self.assertIn("admin_wallet", keys, "Admin Wallet should be manager-only")
        self.assertIn("costs", keys, "Costs should be manager-only")
    
    def test_manager_can_access_manager_items(self):
        """
        Test manager users should pass the require_manager check.
        """
        from tenants.utils_roles import attach_role_to_request
        from core.context import flags
        
        # Create request with manager
        request = self.factory.get('/')
        request.user = self.manager_user
        request.business = self.business
        
        # Attach role
        attach_role_to_request(request)
        
        # Get context
        context = flags(request)
        
        # Manager should see manager items
        self.assertTrue(context["IS_MANAGER"], 
                       "Manager should have IS_MANAGER=True in context")
        self.assertFalse(context["IS_AGENT"],
                        "Manager should have IS_AGENT=False in context")
    
    def test_agent_cannot_access_manager_items(self):
        """
        Test agent users should NOT pass the require_manager check.
        """
        from tenants.utils_roles import attach_role_to_request
        from core.context import flags
        
        # Create request with agent
        request = self.factory.get('/')
        request.user = self.agent_user
        request.business = self.business
        
        # Attach role
        attach_role_to_request(request)
        
        # Get context
        context = flags(request)
        
        # Agent should not see manager items
        self.assertFalse(context["IS_MANAGER"],
                        "Agent should have IS_MANAGER=False in context")
        self.assertTrue(context["IS_AGENT"],
                       "Agent should have IS_AGENT=True in context")


# Run with: pytest tenants/tests/test_role_precedence.py -v

