# hq/tests/test_imei_leak_prevention.py
"""
Tests for IMEI leak prevention in sales flow.

Requirements:
1. Final amount step in phone sale wizard must NOT expose IMEI to agents
2. IMEI should not appear in HTML, hidden fields, or JS console
3. Managers can still see IMEI (for debugging/audit purposes)
4. Sale flow must still work end-to-end
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Location, Product

User = get_user_model()


class IMEILeakPreventionTestCase(TestCase):
    """Test that IMEI is not leaked to agents in sale wizard."""

    def setUp(self):
        """Set up test data."""
        # Create business
        self.business = Business.objects.create(
            name="Test Business", slug="test-business", status="ACTIVE", business_kind="phones"
        )

        # Create location
        self.location = Location.objects.create(business=self.business, name="Test Location")

        # Create product
        self.product = Product.objects.create(
            business=self.business,
            name="Test Phone",
            brand="TestBrand",
            model="TestModel",
            sale_price=Decimal("100000.00"),
        )

        # Create inventory item with IMEI
        self.test_imei = "123456789012345"
        self.stock_item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei=self.test_imei,
            status="IN_STOCK",
            current_location=self.location,
            selling_price=Decimal("100000.00"),
            is_active=True,
        )

        # Create manager user
        self.manager = User.objects.create_user(username="manager", email="manager@test.com", password="testpass123")
        Membership.objects.create(
            user=self.manager, business=self.business, role="MANAGER", status="ACTIVE", location=self.location
        )

        # Create agent user
        self.agent = User.objects.create_user(username="agent", email="agent@test.com", password="testpass123")
        Membership.objects.create(
            user=self.agent, business=self.business, role="AGENT", status="ACTIVE", location=self.location
        )

        self.client = Client()

    def _start_wizard_and_get_to_step2(self, user):
        """Helper to start wizard and navigate to step 2 (price entry)."""
        self.client.force_login(user)

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Step 1: Submit IMEI
        response = self.client.post(reverse("inventory:phone_sale_wizard_v2"), {"imei": self.test_imei})

        # Should redirect to step 2
        self.assertEqual(response.status_code, 302)

        # Get step 2 page
        response = self.client.get(reverse("inventory:phone_sale_wizard_v2") + "?step=2")
        return response

    def _get_to_step3(self, user):
        """Helper to navigate to step 3 (payment method)."""
        self._start_wizard_and_get_to_step2(user)

        # Submit price
        response = self.client.post(reverse("inventory:phone_sale_wizard_v2") + "?step=2", {"selling_price": "100000"})

        # Should redirect to step 3
        self.assertEqual(response.status_code, 302)

        # Get step 3 page
        response = self.client.get(reverse("inventory:phone_sale_wizard_v2") + "?step=3")
        return response

    def test_agent_does_not_see_imei_on_step2(self):
        """Agents should NOT see IMEI on step 2 (price entry)."""
        response = self._start_wizard_and_get_to_step2(self.agent)

        if response.status_code == 200:
            content = response.content.decode("utf-8")

            # IMEI should NOT appear in the HTML
            self.assertNotIn(self.test_imei, content, "IMEI should not be visible to agents on step 2")

            # Should still show product name and location
            self.assertIn("TestBrand", content)
            self.assertIn("Test Location", content)

    def test_manager_can_see_imei_on_step2(self):
        """Managers SHOULD see IMEI on step 2 (for audit/debugging)."""
        response = self._start_wizard_and_get_to_step2(self.manager)

        if response.status_code == 200:
            content = response.content.decode("utf-8")

            # IMEI SHOULD appear for managers
            self.assertIn(self.test_imei, content, "IMEI should be visible to managers on step 2")

    def test_agent_does_not_see_imei_on_step3(self):
        """Agents should NOT see IMEI on step 3 (payment method)."""
        response = self._get_to_step3(self.agent)

        if response.status_code == 200:
            content = response.content.decode("utf-8")

            # IMEI should NOT appear in the HTML
            self.assertNotIn(self.test_imei, content, "IMEI should not be visible to agents on step 3")

            # Should still show product name and price
            self.assertIn("TestBrand", content)
            self.assertIn("100000", content)  # Price should be visible

    def test_manager_can_see_imei_on_step3(self):
        """Managers SHOULD see IMEI on step 3 (for audit/debugging)."""
        response = self._get_to_step3(self.manager)

        if response.status_code == 200:
            content = response.content.decode("utf-8")

            # IMEI SHOULD appear for managers
            self.assertIn(self.test_imei, content, "IMEI should be visible to managers on step 3")

    def test_imei_not_in_hidden_fields_for_agents(self):
        """IMEI should not be in hidden form fields for agents."""
        response = self._get_to_step3(self.agent)

        if response.status_code == 200:
            content = response.content.decode("utf-8")

            # Check for common hidden field patterns
            self.assertNotIn(f'value="{self.test_imei}"', content)
            self.assertNotIn(f"value='{self.test_imei}'", content)
            self.assertNotIn(f'<input type="hidden" name="imei"', content.lower())

    def test_sale_flow_completes_successfully_for_agent(self):
        """Agent should be able to complete sale without seeing IMEI."""
        self.client.force_login(self.agent)

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Step 1: Submit IMEI
        response = self.client.post(reverse("inventory:phone_sale_wizard_v2"), {"imei": self.test_imei})
        self.assertEqual(response.status_code, 302)

        # Step 2: Submit price
        response = self.client.post(reverse("inventory:phone_sale_wizard_v2") + "?step=2", {"selling_price": "100000"})
        self.assertEqual(response.status_code, 302)

        # Step 3: Submit payment method
        response = self.client.post(reverse("inventory:phone_sale_wizard_v2") + "?step=3", {"payment_method": "CASH"})

        # Should redirect to success page (inventory dashboard)
        self.assertEqual(response.status_code, 302)
        self.assertIn("inventory", response.url.lower())

        # Verify stock item was sold
        self.stock_item.refresh_from_db()
        self.assertEqual(self.stock_item.status, "SOLD")

    def test_success_message_does_not_leak_imei_to_agents(self):
        """Success message after sale should not show IMEI to agents."""
        self.client.force_login(self.agent)

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Complete the sale
        self.client.post(reverse("inventory:phone_sale_wizard_v2"), {"imei": self.test_imei})
        self.client.post(reverse("inventory:phone_sale_wizard_v2") + "?step=2", {"selling_price": "100000"})
        response = self.client.post(
            reverse("inventory:phone_sale_wizard_v2") + "?step=3", {"payment_method": "CASH"}, follow=True
        )

        # Check success message
        content = response.content.decode("utf-8")

        # Should have success message (wizard uses "Sale completed successfully!")
        self.assertIn("Sale completed", content)

        # But should NOT contain IMEI
        self.assertNotIn(self.test_imei, content, "Success message should not show IMEI to agents")

    def test_success_message_shows_imei_to_managers(self):
        """Success message after sale SHOULD show IMEI to managers."""
        self.client.force_login(self.manager)

        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Complete the sale
        self.client.post(reverse("inventory:phone_sale_wizard_v2"), {"imei": self.test_imei})
        self.client.post(reverse("inventory:phone_sale_wizard_v2") + "?step=2", {"selling_price": "100000"})
        response = self.client.post(
            reverse("inventory:phone_sale_wizard_v2") + "?step=3", {"payment_method": "CASH"}, follow=True
        )

        # Check success message
        content = response.content.decode("utf-8")

        # Should have success message with IMEI for managers (wizard uses "Sale completed successfully!")
        self.assertIn("Sale completed", content)
        self.assertIn(self.test_imei, content, "Success message should show IMEI to managers")

    def test_no_imei_in_javascript_context_for_agents(self):
        """IMEI should not be embedded in JavaScript for agents."""
        response = self._get_to_step3(self.agent)

        if response.status_code == 200:
            content = response.content.decode("utf-8")

            # Check for common JS patterns
            self.assertNotIn(f'imei: "{self.test_imei}"', content)
            self.assertNotIn(f"imei: '{self.test_imei}'", content)
            self.assertNotIn(f'var imei = "{self.test_imei}"', content)
            self.assertNotIn(f"const imei = '{self.test_imei}'", content)
