# inventory/tests/test_inventory_assigned_role_migration.py
"""
Schema and migration tests for assigned_role field on InventoryItem.

These tests ensure the database schema is correct and migrations have been applied.
They will FAIL if:
  - Migration 0042 is missing or not applied
  - The assigned_role column doesn't exist in the database
  - The field cannot store the expected values
"""
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from tenants.models import Business
from inventory.models import InventoryItem, Location, Product


class InventoryItemAssignedRoleMigrationTest(TestCase):
    """Test that assigned_role column exists and works correctly."""

    def test_assigned_role_column_exists_in_db(self):
        """
        Verify the assigned_role column exists in the database schema.

        This test introspects the actual database table to ensure the migration
        was applied correctly. If this fails, run: python manage.py migrate inventory
        """
        table = InventoryItem._meta.db_table

        with connection.cursor() as cursor:
            # Get all columns from the table
            columns = {col.name for col in connection.introspection.get_table_description(cursor, table)}

        self.assertIn(
            "assigned_role",
            columns,
            "Column 'assigned_role' not found in inventory_inventoryitem table. "
            "Run: python manage.py migrate inventory",
        )

    def test_assigned_role_field_on_model(self):
        """Verify the assigned_role field is defined on the InventoryItem model."""
        # Check field exists on model
        self.assertTrue(
            hasattr(InventoryItem, "assigned_role"), "InventoryItem model does not have 'assigned_role' attribute"
        )

        # Get field from model
        field = InventoryItem._meta.get_field("assigned_role")

        # Verify field properties
        self.assertEqual(field.max_length, 20)
        self.assertTrue(field.db_index, "assigned_role should be indexed for performance")
        self.assertEqual(field.default, "MANAGER")

        # Verify choices
        choices_values = [choice[0] for choice in field.choices]
        self.assertIn("MANAGER", choices_values)
        self.assertIn("AGENT", choices_values)

    def test_can_create_item_with_assigned_role_manager(self):
        """Test creating an InventoryItem with assigned_role='MANAGER'."""
        # Setup required relations
        business = Business.objects.create(name="Test Business", slug="test-biz")
        location = Location.objects.create(business=business, name="Main Store")
        product = Product.objects.create(code="TEST001", brand="TestBrand", model="TestModel", variant="4+64")

        # Create item with MANAGER role
        item = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            imei="123456789012345",
            order_price=100000,
            selling_price=120000,
            assigned_role="MANAGER",
        )

        # Refresh from database
        item.refresh_from_db()

        # Verify it was saved correctly
        self.assertEqual(item.assigned_role, "MANAGER")

    def test_can_create_item_with_assigned_role_agent(self):
        """Test creating an InventoryItem with assigned_role='AGENT'."""
        business = Business.objects.create(name="Test Business", slug="test-biz")
        location = Location.objects.create(business=business, name="Main Store")
        product = Product.objects.create(code="TEST002", brand="TestBrand", model="TestModel", variant="8+128")

        item = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            imei="987654321098765",
            order_price=150000,
            selling_price=180000,
            assigned_role="AGENT",
        )

        item.refresh_from_db()
        self.assertEqual(item.assigned_role, "AGENT")

    def test_default_assigned_role_is_manager(self):
        """Test that new items default to MANAGER role if not specified."""
        business = Business.objects.create(name="Test Business", slug="test-biz")
        location = Location.objects.create(business=business, name="Main Store")
        product = Product.objects.create(code="TEST003", brand="TestBrand", model="TestModel", variant="6+128")

        # Create item WITHOUT specifying assigned_role
        item = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            imei="111111111111111",
            order_price=120000,
            selling_price=140000,
            # Note: assigned_role not specified
        )

        item.refresh_from_db()

        # Should default to MANAGER
        self.assertEqual(item.assigned_role, "MANAGER")

    def test_can_query_by_assigned_role(self):
        """Test that we can filter InventoryItems by assigned_role."""
        business = Business.objects.create(name="Test Business", slug="test-biz")
        location = Location.objects.create(business=business, name="Main Store")
        product = Product.objects.create(code="TEST004", brand="TestBrand", model="TestModel", variant="12+256")

        # Create items with different roles
        manager_item = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            imei="222222222222222",
            order_price=100000,
            assigned_role="MANAGER",
        )

        agent_item = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            imei="333333333333333",
            order_price=100000,
            assigned_role="AGENT",
        )

        # Query for MANAGER items
        manager_items = InventoryItem.objects.filter(assigned_role="MANAGER")
        self.assertIn(manager_item, manager_items)
        self.assertNotIn(agent_item, manager_items)

        # Query for AGENT items
        agent_items = InventoryItem.objects.filter(assigned_role="AGENT")
        self.assertIn(agent_item, agent_items)
        self.assertNotIn(manager_item, agent_items)

    def test_can_update_assigned_role(self):
        """Test that we can change an item's assigned_role."""
        business = Business.objects.create(name="Test Business", slug="test-biz")
        location = Location.objects.create(business=business, name="Main Store")
        product = Product.objects.create(
            code="TEST005",
            brand="TestBrand",
            model="TestModel",
        )

        # Create as MANAGER
        item = InventoryItem.objects.create(
            business=business,
            product=product,
            current_location=location,
            imei="444444444444444",
            order_price=100000,
            assigned_role="MANAGER",
        )

        self.assertEqual(item.assigned_role, "MANAGER")

        # Change to AGENT
        item.assigned_role = "AGENT"
        item.save()

        # Verify change persisted
        item.refresh_from_db()
        self.assertEqual(item.assigned_role, "AGENT")
