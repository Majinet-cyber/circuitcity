"""
Regression tests for Phones Stock Page fixes (Feb 2026).

Covers:
1. Dashboard sales trend populates when sales records exist
2. Dashboard top models populates when stock records exist (fallback)
3. Transfer lists real agents (not "manager pool")
4. Transfer updates agent successfully
5. Edit IMEI duplicate shows error, not 500
6. Edit price never 500s (even with None old price)
7. Archive never 500s
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Product, Location
from inventory.business_kinds import BusinessKind

User = get_user_model()


class DashboardSalesTrendTestCase(TestCase):
    """Sales trend chart must populate when sales records exist."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="mgr_trend", email="mgr@test.com", password="testpass123",
            is_staff=True,
        )
        self.business = Business.objects.create(
            name="Trend Phone Shop", slug="trend-phone-shop",
            business_kind=BusinessKind.PHONES,
        )
        Membership.objects.create(
            business=self.business, user=self.user,
            role="MANAGER", status="ACTIVE",
        )
        self.location = Location.objects.create(
            business=self.business, name="Main", is_default=True,
        )
        self.product = Product.objects.create(
            code="TREND-001", brand="TECNO", model="Spark 20",
            variant="4+64",
        )
        self.client.login(username="mgr_trend", password="testpass123")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_sales_trend_has_30_data_points(self):
        """Sales trend always has 30 data points (even with no sales)."""
        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        trend = response.context.get("sales_trend_30d", [])
        self.assertEqual(len(trend), 30)

    def test_sales_trend_includes_today(self):
        """Sales trend's last data point is today (not yesterday)."""
        # Create a sale today
        item = InventoryItem.objects.create(
            business=self.business, product=self.product,
            imei="111222333444555", order_price=Decimal("300000"),
            selling_price=Decimal("500000"), status="SOLD",
            current_location=self.location, sold_at=timezone.now(),
            is_active=True,
        )

        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        trend = response.context.get("sales_trend_30d", [])
        self.assertEqual(len(trend), 30)

        # The last data point should be today
        today_str = timezone.now().strftime("%Y-%m-%d")
        self.assertEqual(trend[-1]["date"], today_str)

        # Today's data point should show the sale
        self.assertGreaterEqual(trend[-1]["units"], 1)

    def test_sales_trend_shows_data_when_sales_exist(self):
        """If sales exist in the last 30 days, trend must show non-zero data."""
        # Create a sale 3 days ago
        three_days_ago = timezone.now() - timedelta(days=3)
        InventoryItem.objects.create(
            business=self.business, product=self.product,
            imei="222333444555666", order_price=Decimal("300000"),
            selling_price=Decimal("500000"), status="SOLD",
            current_location=self.location, sold_at=three_days_ago,
            is_active=True,
        )

        response = self.client.get("/inventory/verticals/phones/")
        trend = response.context.get("sales_trend_30d", [])

        # At least one data point should have units > 0
        total_units = sum(d["units"] for d in trend)
        self.assertGreater(total_units, 0)


class DashboardTopModelsTestCase(TestCase):
    """Top models widget must populate when stock/sales records exist."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="mgr_models", email="mgr2@test.com", password="testpass123",
            is_staff=True,
        )
        self.business = Business.objects.create(
            name="Models Phone Shop", slug="models-phone-shop",
            business_kind=BusinessKind.PHONES,
        )
        Membership.objects.create(
            business=self.business, user=self.user,
            role="MANAGER", status="ACTIVE",
        )
        self.location = Location.objects.create(
            business=self.business, name="Main", is_default=True,
        )
        self.product1 = Product.objects.create(
            code="MOD-001", brand="Samsung", model="Galaxy A15",
            variant="4+128",
        )
        self.product2 = Product.objects.create(
            code="MOD-002", brand="TECNO", model="Pova 5",
            variant="8+256",
        )
        self.client.login(username="mgr_models", password="testpass123")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_fast_models_from_sales(self):
        """fast_models shows sold models when sales exist in period."""
        InventoryItem.objects.create(
            business=self.business, product=self.product1,
            imei="333444555666777", order_price=Decimal("200000"),
            selling_price=Decimal("350000"), status="SOLD",
            current_location=self.location, sold_at=timezone.now(),
            is_active=True,
        )

        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        fast_models = response.context.get("fast_models", [])
        self.assertGreater(len(fast_models), 0)
        self.assertEqual(response.context.get("fast_models_source"), "sales")

    def test_fast_models_fallback_to_stock(self):
        """fast_models falls back to stock data when no sales exist."""
        # Create stock items only (no sales)
        InventoryItem.objects.create(
            business=self.business, product=self.product1,
            imei="444555666777888", order_price=Decimal("200000"),
            selling_price=Decimal("350000"), status="IN_STOCK",
            current_location=self.location, is_active=True,
        )
        InventoryItem.objects.create(
            business=self.business, product=self.product2,
            imei="555666777888999", order_price=Decimal("300000"),
            selling_price=Decimal("500000"), status="IN_STOCK",
            current_location=self.location, is_active=True,
        )

        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        fast_models = response.context.get("fast_models", [])
        self.assertGreater(len(fast_models), 0, "fast_models should show stock data when no sales exist")
        self.assertEqual(response.context.get("fast_models_source"), "stock")

    def test_sales_by_model_fallback_to_stock(self):
        """sales_by_model falls back to stock data when no sales exist."""
        InventoryItem.objects.create(
            business=self.business, product=self.product1,
            imei="666777888999000", order_price=Decimal("200000"),
            selling_price=Decimal("350000"), status="IN_STOCK",
            current_location=self.location, is_active=True,
        )

        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        sales_by_model = response.context.get("sales_by_model", [])
        self.assertGreater(len(sales_by_model), 0, "sales_by_model should show stock data when no sales exist")
        self.assertEqual(response.context.get("sales_by_model_source"), "stock")

    def test_no_data_when_truly_empty(self):
        """When there's truly no data, fast_models and sales_by_model are empty."""
        response = self.client.get("/inventory/verticals/phones/")
        self.assertEqual(response.status_code, 200)

        fast_models = response.context.get("fast_models", [])
        sales_by_model = response.context.get("sales_by_model", [])
        self.assertEqual(len(fast_models), 0)
        self.assertEqual(len(sales_by_model), 0)


class TransferListsRealAgentsTestCase(TransactionTestCase):
    """Transfer modal must show real available agents, not 'manager pool'."""

    def setUp(self):
        self.business = Business.objects.create(
            name="Transfer Test Shop", business_kind="PHONES", status="ACTIVE",
        )
        self.location = Location.objects.create(
            name="Main Store", business=self.business,
        )
        self.manager = User.objects.create_user(
            username="mgr_xfer", password="test123", email="mgr@xfer.com",
        )
        self.agent1 = User.objects.create_user(
            username="agent_xfer1", password="test123", email="a1@xfer.com",
        )
        self.agent2 = User.objects.create_user(
            username="agent_xfer2", password="test123", email="a2@xfer.com",
        )
        Membership.objects.create(
            user=self.manager, business=self.business,
            role="MANAGER", status="ACTIVE",
        )
        Membership.objects.create(
            user=self.agent1, business=self.business,
            role="AGENT", status="ACTIVE", location=self.location,
        )
        Membership.objects.create(
            user=self.agent2, business=self.business,
            role="AGENT", status="ACTIVE", location=self.location,
        )
        self.product = Product.objects.create(
            code="XFER-001", name="Test Phone", model="Test",
        )
        self.item = InventoryItem.objects.create(
            business=self.business, imei="111000111000111",
            product=self.product, current_location=self.location,
            order_price=Decimal("100"), selling_price=Decimal("150"),
            status="IN_STOCK",
        )

    def _activate_business(self):
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_stock_list_has_agents_in_context(self):
        """Stock list page includes transfer_agents_by_location with real agents."""
        self.client.login(username="mgr_xfer", password="test123")
        self._activate_business()

        response = self.client.get(reverse("inventory:stock_list"))
        self.assertEqual(response.status_code, 200)

        agents_by_loc = response.context.get("transfer_agents_by_location", [])
        # Should have at least one location group
        self.assertGreater(len(agents_by_loc), 0, "transfer_agents_by_location should be populated")

        # Flatten all agent user IDs from the grouped structure
        all_user_ids = set()
        for location_name, memberships in agents_by_loc:
            for m in memberships:
                all_user_ids.add(m.user.id)

        # Must include our agents
        self.assertIn(self.agent1.id, all_user_ids)
        self.assertIn(self.agent2.id, all_user_ids)

    def test_transfer_to_agent_succeeds(self):
        """Transfer to a real agent succeeds and updates correctly."""
        self.client.login(username="mgr_xfer", password="test123")
        self._activate_business()

        response = self.client.post(
            reverse("inventory:transfer_stock", args=[self.item.id]),
            {"agent_id": self.agent1.id},
        )
        self.assertEqual(response.status_code, 302)

        self.item.refresh_from_db()
        self.assertEqual(self.item.assigned_agent, self.agent1)
        self.assertEqual(self.item.assigned_role, "AGENT")

    def test_unassign_succeeds(self):
        """Unassign (formerly 'manager pool') succeeds."""
        # First assign to agent
        self.item.assigned_agent = self.agent1
        self.item.assigned_role = "AGENT"
        self.item.save()

        self.client.login(username="mgr_xfer", password="test123")
        self._activate_business()

        response = self.client.post(
            reverse("inventory:transfer_stock", args=[self.item.id]),
            {"agent_id": "unassign"},
        )
        self.assertEqual(response.status_code, 302)

        self.item.refresh_from_db()
        self.assertIsNone(self.item.assigned_agent)
        self.assertEqual(self.item.assigned_role, "MANAGER")


class EditImeiDuplicateTestCase(TransactionTestCase):
    """Edit IMEI must show error for duplicate, never 500."""

    def setUp(self):
        self.business = Business.objects.create(
            name="IMEI Test Shop", business_kind="PHONES", status="ACTIVE",
        )
        self.location = Location.objects.create(
            name="Main", business=self.business,
        )
        self.manager = User.objects.create_user(
            username="mgr_imei", password="test123", email="mgr@imei.com",
        )
        Membership.objects.create(
            user=self.manager, business=self.business,
            role="MANAGER", status="ACTIVE",
        )
        self.product = Product.objects.create(
            code="IMEI-001", name="Test Phone", model="Test",
        )
        self.item1 = InventoryItem.objects.create(
            business=self.business, imei="100200300400500",
            product=self.product, current_location=self.location,
            order_price=Decimal("100"), status="IN_STOCK",
        )
        self.item2 = InventoryItem.objects.create(
            business=self.business, imei="500400300200100",
            product=self.product, current_location=self.location,
            order_price=Decimal("100"), status="IN_STOCK",
        )

    def _activate_business(self):
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_duplicate_imei_returns_400_not_500(self):
        """Duplicate IMEI returns 400 with error message, not 500."""
        self.client.login(username="mgr_imei", password="test123")
        self._activate_business()

        # Try to set item1's IMEI to item2's IMEI
        response = self.client.post(
            reverse("inventory:edit_imei", args=[self.item1.id]),
            {"imei": self.item2.imei},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("already exists", data["error"])

    def test_invalid_imei_returns_400_not_500(self):
        """Invalid IMEI (non-15-digit) returns 400, not 500."""
        self.client.login(username="mgr_imei", password="test123")
        self._activate_business()

        # Too short
        response = self.client.post(
            reverse("inventory:edit_imei", args=[self.item1.id]),
            {"imei": "12345"},
        )
        self.assertEqual(response.status_code, 400)

        # Contains letters
        response = self.client.post(
            reverse("inventory:edit_imei", args=[self.item1.id]),
            {"imei": "12345678901234A"},
        )
        self.assertEqual(response.status_code, 400)


class EditPriceNever500TestCase(TransactionTestCase):
    """Edit price must never throw 500, even with edge cases."""

    def setUp(self):
        self.business = Business.objects.create(
            name="Price Test Shop", business_kind="PHONES", status="ACTIVE",
        )
        self.location = Location.objects.create(
            name="Main", business=self.business,
        )
        self.manager = User.objects.create_user(
            username="mgr_price", password="test123", email="mgr@price.com",
        )
        Membership.objects.create(
            user=self.manager, business=self.business,
            role="MANAGER", status="ACTIVE",
        )
        self.product = Product.objects.create(
            code="PRICE-001", name="Test Phone", model="Test",
        )
        # Item with None order_price (edge case that previously caused 500)
        self.item_no_price = InventoryItem.objects.create(
            business=self.business, imei="900800700600500",
            product=self.product, current_location=self.location,
            order_price=None, selling_price=None,
            status="IN_STOCK",
        )
        # Normal item
        self.item_normal = InventoryItem.objects.create(
            business=self.business, imei="800700600500400",
            product=self.product, current_location=self.location,
            order_price=Decimal("100000"), selling_price=Decimal("150000"),
            status="IN_STOCK",
        )

    def _activate_business(self):
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_edit_price_with_none_old_price_does_not_500(self):
        """Edit price on item with None old price must not crash."""
        self.client.login(username="mgr_price", password="test123")
        self._activate_business()

        response = self.client.post(
            reverse("inventory:edit_price", args=[self.item_no_price.id]),
            {"price": "250000"},
        )
        # Should succeed (302 redirect) or return 400 with message, never 500
        self.assertIn(response.status_code, [200, 302])

        self.item_no_price.refresh_from_db()
        self.assertEqual(self.item_no_price.order_price, Decimal("250000"))

    def test_edit_price_with_valid_price(self):
        """Normal edit price succeeds."""
        self.client.login(username="mgr_price", password="test123")
        self._activate_business()

        response = self.client.post(
            reverse("inventory:edit_price", args=[self.item_normal.id]),
            {"price": "120000"},
        )
        self.assertEqual(response.status_code, 302)

        self.item_normal.refresh_from_db()
        self.assertEqual(self.item_normal.order_price, Decimal("120000"))

    def test_edit_price_negative_returns_400(self):
        """Negative price returns 400, not 500."""
        self.client.login(username="mgr_price", password="test123")
        self._activate_business()

        response = self.client.post(
            reverse("inventory:edit_price", args=[self.item_normal.id]),
            {"price": "-50000"},
        )
        self.assertEqual(response.status_code, 400)

    def test_edit_price_non_numeric_returns_400(self):
        """Non-numeric price returns 400, not 500."""
        self.client.login(username="mgr_price", password="test123")
        self._activate_business()

        response = self.client.post(
            reverse("inventory:edit_price", args=[self.item_normal.id]),
            {"price": "abc"},
        )
        self.assertEqual(response.status_code, 400)


class ArchiveNever500TestCase(TransactionTestCase):
    """Archive must never throw 500."""

    def setUp(self):
        self.business = Business.objects.create(
            name="Archive Test Shop", business_kind="PHONES", status="ACTIVE",
        )
        self.location = Location.objects.create(
            name="Main", business=self.business,
        )
        self.manager = User.objects.create_user(
            username="mgr_arch", password="test123", email="mgr@arch.com",
        )
        Membership.objects.create(
            user=self.manager, business=self.business,
            role="MANAGER", status="ACTIVE",
        )
        self.product = Product.objects.create(
            code="ARCH-001", name="Test Phone", model="Test",
        )
        self.item = InventoryItem.objects.create(
            business=self.business, imei="777888999000111",
            product=self.product, current_location=self.location,
            order_price=Decimal("100"), status="IN_STOCK",
        )

    def _activate_business(self):
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_archive_succeeds(self):
        """Archive a stock item successfully."""
        self.client.login(username="mgr_arch", password="test123")
        self._activate_business()

        response = self.client.post(
            reverse("inventory:archive_stock", args=[self.item.id]),
        )
        self.assertEqual(response.status_code, 302)

        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.archived_at)
        self.assertFalse(self.item.is_active)

    def test_archive_already_archived_returns_400(self):
        """Archiving an already archived item returns 400, not 500."""
        self.item.archived_at = timezone.now()
        self.item.archived_by = self.manager
        self.item.is_active = False
        self.item.save()

        self.client.login(username="mgr_arch", password="test123")
        self._activate_business()

        response = self.client.post(
            reverse("inventory:archive_stock", args=[self.item.id]),
        )
        # The item is archived + is_active=False, so InventoryItem.objects won't find it
        # get_object_or_404 should return 404
        self.assertIn(response.status_code, [400, 404])

    def test_restore_succeeds(self):
        """Restore an archived item successfully."""
        self.item.archived_at = timezone.now()
        self.item.archived_by = self.manager
        self.item.is_active = False
        self.item.save()

        self.client.login(username="mgr_arch", password="test123")
        self._activate_business()

        response = self.client.post(
            reverse("inventory:restore_stock", args=[self.item.id]),
        )
        self.assertEqual(response.status_code, 302)

        self.item.refresh_from_db()
        self.assertIsNone(self.item.archived_at)
        self.assertTrue(self.item.is_active)

    def test_agent_cannot_archive(self):
        """Agents cannot archive (403, not 500)."""
        agent = User.objects.create_user(
            username="agent_arch", password="test123", email="agent@arch.com",
        )
        Membership.objects.create(
            user=agent, business=self.business,
            role="AGENT", status="ACTIVE", location=self.location,
        )

        self.client.login(username="agent_arch", password="test123")
        self._activate_business()

        response = self.client.post(
            reverse("inventory:archive_stock", args=[self.item.id]),
        )
        self.assertEqual(response.status_code, 403)



