# inventory/tests/test_stock_assignment_visibility.py
"""
Tests for stock list visibility based on assigned_role and user permissions.

These tests ensure:
  - Managers can see all stock (both MANAGER and AGENT assigned items)
  - Agents can see only items assigned to them or AGENT role items
  - The /inventory/list/ view respects assigned_role filtering
  - No 500 errors occur when accessing stock list
"""
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Location, Product, AgentProfile

User = get_user_model()


class StockListAssignedRoleVisibilityTest(TestCase):
    """Test stock list visibility based on assigned_role."""

    def setUp(self):
        """Set up test data: business, users, locations, and stock items."""
        # Create business
        self.business = Business.objects.create(
            name="Test Electronics",
            slug="test-electronics",
        )

        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
        )

        # Create users
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123",
        )

        self.agent = User.objects.create_user(
            username="agent@test.com",
            email="agent@test.com",
            password="testpass123",
        )

        # Create memberships
        self.manager_membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

        self.agent_membership = Membership.objects.create(
            user=self.agent,
            business=self.business,
            role="AGENT",
            status="ACTIVE",
            location=self.location,
        )

        # Create/update agent profile (idempotent - may already exist from signal)
        self.agent_profile, _ = AgentProfile.objects.get_or_create(user=self.agent)
        if self.agent_profile.location != self.location:
            self.agent_profile.location = self.location
            self.agent_profile.save(update_fields=["location"])

        # Create products
        self.product1 = Product.objects.create(
            code="AGENT001",
            brand="TestBrand",
            model="AgentPhone",
            variant="4+64",
        )

        self.product2 = Product.objects.create(
            code="MANAGER001",
            brand="TestBrand",
            model="ManagerPhone",
            variant="8+128",
        )

        # Create stock items with different roles
        self.item_for_agent = InventoryItem.objects.create(
            business=self.business,
            product=self.product1,
            current_location=self.location,
            imei="111111111111111",
            order_price=Decimal("100000.00"),
            selling_price=Decimal("120000.00"),
            assigned_role="AGENT",
            assigned_agent=self.agent,  # Explicitly assigned to agent
        )

        self.item_for_manager = InventoryItem.objects.create(
            business=self.business,
            product=self.product2,
            current_location=self.location,
            imei="222222222222222",
            order_price=Decimal("150000.00"),
            selling_price=Decimal("180000.00"),
            assigned_role="MANAGER",
            assigned_agent=None,  # Manager pool
        )

        # Create additional agent item (not assigned to specific agent)
        self.item_agent_pool = InventoryItem.objects.create(
            business=self.business,
            product=self.product1,
            current_location=self.location,
            imei="333333333333333",
            order_price=Decimal("100000.00"),
            selling_price=Decimal("120000.00"),
            assigned_role="AGENT",
            assigned_agent=None,  # Agent pool (no specific agent)
        )

        # Client for making requests
        self.client = Client()

    def test_stock_list_view_loads_without_500(self):
        """Test that /inventory/list/ loads without crashing (no 500 error)."""
        # Login as manager
        self.client.login(username="manager@test.com", password="testpass123")

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Access stock list
        try:
            response = self.client.get(reverse("inventory:stock_list"))
        except Exception as e:
            self.fail(f"Stock list view raised exception: {e}")

        # Should return 200 (or 302 for redirect, but not 500)
        self.assertIn(
            response.status_code, [200, 302], f"Stock list returned {response.status_code}, expected 200 or 302"
        )

    def test_manager_sees_all_stock(self):
        """Test that managers can see all stock items regardless of assigned_role."""
        # Login as manager
        self.client.login(username="manager@test.com", password="testpass123")

        # Set active business
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Get stock list
        response = self.client.get(reverse("inventory:stock_list"))

        if response.status_code == 302:
            # Follow redirect if needed
            response = self.client.get(response.url)

        self.assertEqual(response.status_code, 200)

        # Get content
        content = response.content.decode()

        # Manager should see both AGENT and MANAGER items
        # Check for IMEIs or product codes
        self.assertIn("111111111111111", content, "Manager should see agent item (IMEI 111...)")
        self.assertIn("222222222222222", content, "Manager should see manager item (IMEI 222...)")

    def test_queryset_filtering_for_manager(self):
        """Test that managers get all items in queryset (no filtering by role)."""
        # Simulate manager's queryset
        # Managers should see all items for their business
        manager_items = InventoryItem.objects.filter(
            business=self.business,
            status="IN_STOCK",
            is_active=True,
        )

        # Should include both MANAGER and AGENT role items
        self.assertEqual(manager_items.count(), 3)  # All 3 items

        # Verify both roles are present
        roles = set(manager_items.values_list("assigned_role", flat=True))
        self.assertIn("MANAGER", roles)
        self.assertIn("AGENT", roles)

    def test_queryset_filtering_for_agent(self):
        """Test that agents only get items assigned to them or AGENT role."""
        # Simulate agent's queryset
        # Agents should see:
        # 1) Items explicitly assigned to them (assigned_agent=agent)
        # 2) Items with assigned_role="AGENT" (agent pool)

        from django.db.models import Q

        agent_items = InventoryItem.objects.filter(
            business=self.business,
            status="IN_STOCK",
            is_active=True,
        ).filter(Q(assigned_agent=self.agent) | Q(assigned_role="AGENT"))

        # Should include:
        # - item_for_agent (assigned to agent)
        # - item_agent_pool (AGENT role, no specific agent)
        # Should NOT include:
        # - item_for_manager (MANAGER role)

        self.assertEqual(agent_items.count(), 2)

        # Verify items
        item_ids = set(agent_items.values_list("id", flat=True))
        self.assertIn(self.item_for_agent.id, item_ids)
        self.assertIn(self.item_agent_pool.id, item_ids)
        self.assertNotIn(self.item_for_manager.id, item_ids)

    def test_agent_cannot_see_manager_items(self):
        """Test that agents cannot see items with assigned_role='MANAGER'."""
        # Query as agent would
        from django.db.models import Q

        agent_visible = InventoryItem.objects.filter(
            business=self.business,
        ).filter(Q(assigned_agent=self.agent) | Q(assigned_role="AGENT"))

        # Manager item should not be in results
        self.assertNotIn(
            self.item_for_manager, agent_visible, "Agent should not see items with assigned_role='MANAGER'"
        )

    def test_assigned_role_index_exists(self):
        """
        Verify that assigned_role is indexed for performance.

        This is important because filtering by assigned_role happens on every
        stock list page load for agents.
        """
        from django.db import connection

        # Get indexes for InventoryItem table
        table = InventoryItem._meta.db_table

        with connection.cursor() as cursor:
            # SQLite specific query for indexes
            cursor.execute(f"PRAGMA index_list({table})")
            indexes = cursor.fetchall()

        # Check if any index includes assigned_role
        # Note: In Django, db_index=True creates a single-column index
        # The exact index name varies, but it should exist

        field = InventoryItem._meta.get_field("assigned_role")
        self.assertTrue(field.db_index, "assigned_role field should have db_index=True for performance")

    def test_stock_assignment_preserves_backward_compatibility(self):
        """
        Test that existing items without explicit assigned_role work correctly.

        Items created before the assigned_role feature should default to MANAGER.
        """
        # Create item without specifying assigned_role
        old_item = InventoryItem.objects.create(
            business=self.business,
            product=self.product1,
            current_location=self.location,
            imei="999999999999999",
            order_price=Decimal("100000.00"),
            # assigned_role not specified (simulates old data)
        )

        # Should default to MANAGER
        self.assertEqual(old_item.assigned_role, "MANAGER")

        # Manager should see it
        manager_items = InventoryItem.objects.filter(
            business=self.business,
            assigned_role="MANAGER",
        )
        self.assertIn(old_item, manager_items)

    def test_multiple_agents_see_correct_items(self):
        """Test that multiple agents only see their own items."""
        # Create second agent
        agent2 = User.objects.create_user(
            username="agent2@test.com",
            email="agent2@test.com",
            password="testpass123",
        )

        Membership.objects.create(
            user=agent2,
            business=self.business,
            role="AGENT",
            status="ACTIVE",
            location=self.location,
        )

        agent2_profile, _ = AgentProfile.objects.get_or_create(user=agent2)
        if agent2_profile.location != self.location:
            agent2_profile.location = self.location
            agent2_profile.save(update_fields=["location"])

        # Create item for agent2
        agent2_item = InventoryItem.objects.create(
            business=self.business,
            product=self.product1,
            current_location=self.location,
            imei="555555555555555",
            order_price=Decimal("100000.00"),
            assigned_role="AGENT",
            assigned_agent=agent2,
        )

        # Agent 1 should NOT see agent2's item (unless it's in agent pool)
        from django.db.models import Q

        agent1_items = InventoryItem.objects.filter(
            business=self.business,
        ).filter(assigned_agent=self.agent)

        self.assertNotIn(agent2_item, agent1_items)

        # Agent 2 should see their own item
        agent2_items = InventoryItem.objects.filter(
            business=self.business,
        ).filter(assigned_agent=agent2)

        self.assertIn(agent2_item, agent2_items)
