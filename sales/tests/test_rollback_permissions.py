# sales/tests/test_rollback_permissions.py
"""
Regression tests for rollback permissions.

Tests ensure:
- ✅ Manager can rollback sale created by agent
- ❌ Agent cannot rollback (even if they created the sale)
- ❌ Manager from a different business cannot rollback
- ✅ Superuser/HQ can rollback
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Product, Location
from sales.models import Sale
from sales.services.rollback import RollbackService, RollbackError
from sales.permissions import can_rollback_sale

User = get_user_model()


class RollbackPermissionsTestCase(TestCase):
    """Test rollback permissions for managers vs agents."""

    def setUp(self):
        """Create test data."""
        # Create two businesses
        self.business1 = Business.objects.create(
            name="Business 1", slug="business-1", business_kind="PHONES", status="ACTIVE"
        )
        self.business2 = Business.objects.create(
            name="Business 2", slug="business-2", business_kind="PHONES", status="ACTIVE"
        )

        # Create users
        self.manager1 = User.objects.create_user(username="manager1", password="testpass123", email="manager1@test.com")
        self.manager2 = User.objects.create_user(username="manager2", password="testpass123", email="manager2@test.com")
        self.agent1 = User.objects.create_user(username="agent1", password="testpass123", email="agent1@test.com")
        self.superuser = User.objects.create_user(
            username="superuser", password="testpass123", email="superuser@test.com", is_superuser=True, is_staff=True
        )

        # Create location (needed before agent membership)
        self.location = Location.objects.create(business=self.business1, name="Main Store")

        # Create memberships
        Membership.objects.create(user=self.manager1, business=self.business1, role="MANAGER", status="ACTIVE")
        Membership.objects.create(user=self.manager2, business=self.business2, role="MANAGER", status="ACTIVE")
        Membership.objects.create(
            user=self.agent1, business=self.business1, role="AGENT", status="ACTIVE", location=self.location
        )

        # Create product
        self.product = Product.objects.create(
            code="TEST-PHONE-001",
            name="Test Phone",
            brand="Test",
            model="Model 1",
            variant="128GB",
            cost_price=Decimal("400000.00"),
            sale_price=Decimal("500000.00"),
        )

        # Create inventory item
        self.item = InventoryItem.objects.create(
            business=self.business1,
            product=self.product,
            imei="123456789012345",
            status="SOLD",
            current_location=self.location,
            order_price=Decimal("400000.00"),
            selling_price=Decimal("500000.00"),
            sold_at=timezone.now(),
            sold_by=self.agent1,
        )

        # Create sale (created by agent)
        self.sale = Sale.objects.create(
            item=self.item,
            agent=self.agent1,
            location=self.location,
            price=Decimal("500000.00"),
            sold_at=timezone.now().date(),
            payment_method="CASH",
        )

        self.client = Client()

    def test_manager_can_rollback_sale_created_by_agent(self):
        """✅ Manager can rollback sale created by agent."""
        can_rollback, error_msg = RollbackService.can_rollback(self.sale, self.manager1, self.business1)
        self.assertTrue(can_rollback, f"Manager should be able to rollback, but got: {error_msg}")
        self.assertEqual(error_msg, "")

    def test_agent_cannot_rollback_own_sale(self):
        """❌ Agent cannot rollback even their own sale."""
        can_rollback, error_msg = RollbackService.can_rollback(self.sale, self.agent1, self.business1)
        self.assertFalse(can_rollback, "Agent should NOT be able to rollback")
        self.assertIn("Only managers can roll back", error_msg)
        self.assertNotIn("agent responsible", error_msg.lower())

    def test_manager_from_different_business_cannot_rollback(self):
        """❌ Manager from different business cannot rollback."""
        can_rollback, error_msg = RollbackService.can_rollback(self.sale, self.manager2, self.business1)
        # Manager2 is not a member of business1, so should fail
        self.assertFalse(can_rollback, "Manager from different business should NOT be able to rollback")

    def test_superuser_can_rollback(self):
        """✅ Superuser can rollback any sale."""
        can_rollback, error_msg = RollbackService.can_rollback(self.sale, self.superuser, self.business1)
        self.assertTrue(can_rollback, f"Superuser should be able to rollback, but got: {error_msg}")

    def test_manager_can_rollback_via_permissions_helper(self):
        """✅ Manager can rollback via permissions helper function."""
        result = can_rollback_sale(self.manager1, self.sale)
        self.assertTrue(result, "Manager should be able to rollback via helper")

    def test_agent_cannot_rollback_via_permissions_helper(self):
        """❌ Agent cannot rollback via permissions helper function."""
        result = can_rollback_sale(self.agent1, self.sale)
        self.assertFalse(result, "Agent should NOT be able to rollback via helper")

    def test_manager_can_execute_rollback(self):
        """✅ Manager can actually execute rollback (not just permission check)."""
        self.client.force_login(self.manager1)

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business1.id
        session.save()

        # Execute rollback
        rollback = RollbackService.rollback_sale(
            sale=self.sale,
            user=self.manager1,
            business=self.business1,
            reason="RETURNED",
            refunded=False,
            return_to_stock=True,
            notes="Test rollback",
        )

        # Verify rollback was created
        self.assertIsNotNone(rollback)
        self.assertEqual(rollback.sale, self.sale)
        self.assertEqual(rollback.reason, "RETURNED")

        # Verify sale is marked as rolled back
        self.sale.refresh_from_db()
        self.assertTrue(self.sale.is_rolled_back)

        # Verify inventory was restored
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "IN_STOCK")
        self.assertIsNone(self.item.sold_at)
        self.assertIsNone(self.item.sold_by)

    def test_agent_cannot_execute_rollback(self):
        """❌ Agent cannot execute rollback (should raise RollbackError)."""
        with self.assertRaises(RollbackError) as cm:
            RollbackService.rollback_sale(
                sale=self.sale,
                user=self.agent1,
                business=self.business1,
                reason="RETURNED",
                refunded=False,
                return_to_stock=True,
                notes="Test rollback",
            )

        error_msg = str(cm.exception)
        self.assertIn("Only managers can roll back", error_msg)
        self.assertNotIn("agent responsible", error_msg.lower())

    def test_rollback_endpoint_manager_success(self):
        """✅ Manager can access rollback endpoint successfully."""
        self.client.force_login(self.manager1)

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business1.id
        session.save()

        # Get rollback confirm page
        url = reverse("sales:rollback_confirm", args=[self.sale.pk])
        response = self.client.get(url)

        # Should return 200 (not 403)
        self.assertEqual(
            response.status_code, 200, f"Expected 200, got {response.status_code}. Response: {response.content[:500]}"
        )

        # Should show rollback form
        self.assertIn(b"rollback", response.content.lower())

    def test_rollback_endpoint_agent_forbidden(self):
        """❌ Agent gets 403 or error message when trying to rollback."""
        self.client.force_login(self.agent1)

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business1.id
        session.save()

        # Try to access rollback confirm page
        url = reverse("sales:rollback_confirm", args=[self.sale.pk])
        response = self.client.get(url)

        # Should either redirect with error or show error message
        # The view checks permissions and shows error message
        if response.status_code == 200:
            # If page loads, it should show error message
            content = response.content.decode("utf-8").lower()
            self.assertTrue(
                "only managers" in content or "cannot rollback" in content or "permission" in content,
                f"Page should show permission error. Content: {content[:500]}",
            )

    def test_rollback_post_manager_success(self):
        """✅ Manager can POST rollback successfully."""
        # Capture initial state
        initial_item_status = self.item.status

        self.client.force_login(self.manager1)

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business1.id
        session.save()

        # POST rollback (action must be in query param, not POST data)
        url = reverse("sales:rollback_confirm", args=[self.sale.pk]) + "?action=rollback"
        response = self.client.post(
            url,
            {"reason": "RETURNED", "refunded": "no", "return_to_stock": "yes", "notes": "Test rollback"},
            follow=True,
        )

        # Should redirect to rollback home (success)
        self.assertIn(response.status_code, [200, 302])

        # Verify sale was rolled back
        self.sale.refresh_from_db()
        self.assertTrue(self.sale.is_rolled_back)
        self.assertIsNotNone(self.sale.rolled_back_at)

        # Verify inventory was restored
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "IN_STOCK")

        # Try second rollback - should return 409 or show error message
        url2 = reverse("sales:rollback_confirm", args=[self.sale.pk]) + "?action=rollback"
        response2 = self.client.post(
            url2,
            {"reason": "RETURNED", "refunded": "no", "return_to_stock": "yes", "notes": "Second rollback attempt"},
            follow=True,
        )

        # Should show error message about already rolled back
        messages = list(response2.context.get("messages", [])) if hasattr(response2, "context") else []
        if messages:
            error_found = any("already rolled back" in str(m).lower() for m in messages)
            self.assertTrue(
                error_found, f"Should show 'already rolled back' error. Messages: {[str(m) for m in messages]}"
            )

        # Verify no double-reversal: item status should still be IN_STOCK
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "IN_STOCK")

    def test_rollback_post_agent_forbidden(self):
        """❌ Agent cannot POST rollback."""
        self.client.force_login(self.agent1)

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business1.id
        session.save()

        # Try to POST rollback
        url = reverse("sales:rollback_confirm", args=[self.sale.pk])
        response = self.client.post(
            url,
            {
                "action": "rollback",
                "reason": "RETURNED",
                "refunded": "no",
                "return_to_stock": "yes",
                "notes": "Test rollback",
            },
            follow=True,
        )

        # Should not succeed - sale should not be rolled back
        self.sale.refresh_from_db()
        self.assertFalse(self.sale.is_rolled_back)

        # Should show error message
        messages = list(response.context.get("messages", [])) if hasattr(response, "context") else []
        if messages:
            error_found = any(
                "only managers" in str(m).lower() or "cannot rollback" in str(m).lower() for m in messages
            )
            self.assertTrue(error_found, f"Should show permission error. Messages: {[str(m) for m in messages]}")

    def test_already_rolled_back_sale_cannot_be_rolled_back_again(self):
        """Test that already rolled back sale cannot be rolled back again."""
        # First rollback by manager
        rollback1 = RollbackService.rollback_sale(
            sale=self.sale,
            user=self.manager1,
            business=self.business1,
            reason="RETURNED",
            refunded=False,
            return_to_stock=True,
            notes="First rollback",
        )

        # Verify first rollback succeeded
        self.assertIsNotNone(rollback1)
        self.sale.refresh_from_db()
        self.assertTrue(self.sale.is_rolled_back)
        self.assertIsNotNone(self.sale.rolled_back_at)

        # Verify inventory was restored
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "IN_STOCK")
        self.assertIsNone(self.item.sold_at)
        self.assertIsNone(self.item.sold_by)

        # Capture state after first rollback (this is what we want to preserve)
        after_first_rollback_item_status = self.item.status
        after_first_rollback_item_sold_at = self.item.sold_at
        after_first_rollback_item_sold_by = self.item.sold_by

        # Try to rollback again - should raise ValidationError
        with self.assertRaises(ValidationError) as cm:
            RollbackService.rollback_sale(
                sale=self.sale,
                user=self.manager1,
                business=self.business1,
                reason="RETURNED",
                refunded=False,
                return_to_stock=True,
                notes="Second rollback attempt",
            )

        error_message = str(cm.exception)
        self.assertIn("already rolled back", error_message.lower())

        # Verify no double-reversal: state should be unchanged after second attempt
        self.item.refresh_from_db()
        self.assertEqual(
            self.item.status,
            after_first_rollback_item_status,
            "Item status should not change on second rollback attempt",
        )
        self.assertEqual(
            self.item.sold_at,
            after_first_rollback_item_sold_at,
            "Item sold_at should not change on second rollback attempt",
        )
        self.assertEqual(
            self.item.sold_by,
            after_first_rollback_item_sold_by,
            "Item sold_by should not change on second rollback attempt",
        )

        # Verify permission check also returns False
        can_rollback, error_msg = RollbackService.can_rollback(self.sale, self.manager1, self.business1)
        self.assertFalse(can_rollback)
        self.assertIn("already been rolled back", error_msg.lower())

    def test_error_message_does_not_mention_agent_responsible(self):
        """Test that error messages don't mention 'agent responsible'."""
        can_rollback, error_msg = RollbackService.can_rollback(self.sale, self.agent1, self.business1)

        self.assertFalse(can_rollback)
        # Error message should NOT contain "agent responsible" or similar
        error_lower = error_msg.lower()
        self.assertNotIn("agent responsible", error_lower)
        self.assertNotIn("only agent", error_lower)
        # Should say "Only managers can roll back"
        self.assertIn("only managers", error_lower)
