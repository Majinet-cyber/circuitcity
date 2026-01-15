"""
Critical Tests: Phone Stock Edit Price Feature

Tests the "Edit price" action on phones stock list:
- If item is SOLD: allow editing the SELLING PRICE (update sale + item)
- If item is NOT sold: allow editing the ORDER PRICE (cost)
- Must be tenant-safe (no IDOR)
- Must not affect other verticals

All tests must pass for phones vertical to be production-ready.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Product, Location
from sales.models import Sale

User = get_user_model()


@pytest.mark.critical
@pytest.mark.django_db
class TestPhoneStockEditPrice:
    """Tests for edit price feature on phone stock items."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data for each test."""
        # Create business
        self.business = Business.objects.create(
            name="Test Phones Business",
            business_kind="phones",
            is_active=True,
        )

        # Create another business for IDOR testing
        self.other_business = Business.objects.create(
            name="Other Business",
            business_kind="phones",
            is_active=True,
        )

        # Create manager user
        self.manager = User.objects.create_user(
            username="manager",
            email="manager@test.com",
            password="testpass123",
        )
        self.manager.profile.is_manager = True
        self.manager.profile.save()

        # Create manager membership
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Create regular agent user
        self.agent = User.objects.create_user(
            username="agent",
            email="agent@test.com",
            password="testpass123",
        )
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            role="AGENT",
            status="ACTIVE",
        )

        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_active=True,
        )

        # Create product
        self.product = Product.objects.create(
            code="TEST001",
            brand="TestBrand",
            model="TestModel",
            variant="4+128",
            cost_price=Decimal("1000.00"),
            sale_price=Decimal("1500.00"),
        )

    def test_edit_order_price_unsold_updates_stock_cost_only(self, client):
        """
        Test: Editing price on unsold item updates order_price (cost) only.
        """
        # Create unsold stock item
        item = InventoryItem.objects.create(
            business=self.business,
            imei="123456789012345",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        # Login as manager
        client.force_login(self.manager)

        # POST new order price
        url = reverse("inventory:edit_price", kwargs={"pk": item.pk})
        response = client.post(url, {"price": "1200.00"})

        # Should redirect (success)
        assert response.status_code == 302

        # Refresh item from DB
        item.refresh_from_db()

        # Assert order_price updated
        assert item.order_price == Decimal("1200.00")

        # Assert selling_price unchanged
        assert item.selling_price == Decimal("1500.00")

        # Assert status unchanged
        assert item.status == "IN_STOCK"

        # Assert no Sale record exists
        assert not hasattr(item, "sale") or not Sale.objects.filter(item=item).exists()

    def test_edit_selling_price_sold_updates_sale_and_totals(self, client):
        """
        Test: Editing price on sold item updates both item.selling_price and Sale.price.
        """
        # Create sold stock item
        item = InventoryItem.objects.create(
            business=self.business,
            imei="999888777666555",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="SOLD",
            sold_at=timezone.now(),
            current_location=self.location,
        )

        # Create sale record
        sale = Sale.objects.create(
            item=item,
            agent=self.manager,
            location=self.location,
            sold_at=timezone.now().date(),
            price=Decimal("1500.00"),
            commission_pct=Decimal("10.00"),
            payment_method="CASH",
        )

        original_sale_price = sale.price

        # Login as manager
        client.force_login(self.manager)

        # POST new selling price
        url = reverse("inventory:edit_price", kwargs={"pk": item.pk})
        response = client.post(url, {"price": "1800.00"})

        # Should redirect (success)
        assert response.status_code == 302

        # Refresh from DB
        item.refresh_from_db()
        sale.refresh_from_db()

        # Assert item.selling_price updated
        assert item.selling_price == Decimal("1800.00")

        # Assert Sale.price updated
        assert sale.price == Decimal("1800.00")

        # Assert sale price changed
        assert sale.price != original_sale_price

        # Assert order_price (cost) unchanged
        assert item.order_price == Decimal("1000.00")

        # Assert status still SOLD
        assert item.status == "SOLD"

    def test_edit_price_sold_item_no_sale_record_edge_case(self, client):
        """
        Test: Editing price on item marked SOLD but with no Sale record.
        Should still update item.selling_price and not crash.
        """
        # Create item marked as SOLD but no Sale record (edge case)
        item = InventoryItem.objects.create(
            business=self.business,
            imei="111222333444555",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="SOLD",
            sold_at=timezone.now(),
            current_location=self.location,
        )

        # Confirm no sale record
        assert not Sale.objects.filter(item=item).exists()

        # Login as manager
        client.force_login(self.manager)

        # POST new selling price
        url = reverse("inventory:edit_price", kwargs={"pk": item.pk})
        response = client.post(url, {"price": "1700.00"})

        # Should redirect (success, with warning message)
        assert response.status_code == 302

        # Refresh item from DB
        item.refresh_from_db()

        # Assert item.selling_price updated
        assert item.selling_price == Decimal("1700.00")

        # Assert order_price unchanged
        assert item.order_price == Decimal("1000.00")

    def test_edit_price_is_tenant_safe_idor_guard(self, client):
        """
        Test: User cannot edit price for stock item from another business (IDOR protection).
        """
        # Create item in OTHER business
        other_location = Location.objects.create(
            business=self.other_business,
            name="Other Store",
            is_active=True,
        )
        other_item = InventoryItem.objects.create(
            business=self.other_business,
            imei="999999999999999",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="IN_STOCK",
            current_location=other_location,
        )

        # Login as manager of FIRST business
        client.force_login(self.manager)

        # Attempt to edit item from OTHER business
        url = reverse("inventory:edit_price", kwargs={"pk": other_item.pk})
        response = client.post(url, {"price": "2000.00"})

        # Should return 404 (not found) or 403 (forbidden)
        assert response.status_code in [403, 404]

        # Assert item price unchanged
        other_item.refresh_from_db()
        assert other_item.order_price == Decimal("1000.00")

    def test_edit_price_requires_manager_permission(self, client):
        """
        Test: Regular agent cannot edit price (manager-only feature).
        """
        # Create unsold stock item
        item = InventoryItem.objects.create(
            business=self.business,
            imei="777666555444333",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        # Login as regular agent (not manager)
        client.force_login(self.agent)

        # Attempt to edit price
        url = reverse("inventory:edit_price", kwargs={"pk": item.pk})
        response = client.post(url, {"price": "1200.00"})

        # Should return 403 (permission denied)
        assert response.status_code == 403

        # Assert item price unchanged
        item.refresh_from_db()
        assert item.order_price == Decimal("1000.00")

    def test_edit_price_validates_positive_price(self, client):
        """
        Test: Price must be >= 0.
        """
        # Create unsold stock item
        item = InventoryItem.objects.create(
            business=self.business,
            imei="555444333222111",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        # Login as manager
        client.force_login(self.manager)

        # Attempt to set negative price
        url = reverse("inventory:edit_price", kwargs={"pk": item.pk})
        response = client.post(url, {"price": "-100.00"})

        # Should return error (400)
        assert response.status_code == 400

        # Assert item price unchanged
        item.refresh_from_db()
        assert item.order_price == Decimal("1000.00")

    def test_edit_price_validates_decimal_format(self, client):
        """
        Test: Price must be a valid decimal.
        """
        # Create unsold stock item
        item = InventoryItem.objects.create(
            business=self.business,
            imei="444333222111000",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        # Login as manager
        client.force_login(self.manager)

        # Attempt to set invalid price
        url = reverse("inventory:edit_price", kwargs={"pk": item.pk})
        response = client.post(url, {"price": "not-a-number"})

        # Should return error (400)
        assert response.status_code == 400

        # Assert item price unchanged
        item.refresh_from_db()
        assert item.order_price == Decimal("1000.00")

    def test_edit_price_requires_price_parameter(self, client):
        """
        Test: Price parameter is required.
        """
        # Create unsold stock item
        item = InventoryItem.objects.create(
            business=self.business,
            imei="333222111000999",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        # Login as manager
        client.force_login(self.manager)

        # Attempt to edit without price parameter
        url = reverse("inventory:edit_price", kwargs={"pk": item.pk})
        response = client.post(url, {})

        # Should return error (400)
        assert response.status_code == 400

        # Assert item price unchanged
        item.refresh_from_db()
        assert item.order_price == Decimal("1000.00")

    def test_edit_price_accepts_zero_price(self, client):
        """
        Test: Price can be set to 0 (edge case for promos/write-offs).
        """
        # Create unsold stock item
        item = InventoryItem.objects.create(
            business=self.business,
            imei="222111000999888",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        # Login as manager
        client.force_login(self.manager)

        # Set price to 0
        url = reverse("inventory:edit_price", kwargs={"pk": item.pk})
        response = client.post(url, {"price": "0.00"})

        # Should succeed
        assert response.status_code == 302

        # Assert item price updated to 0
        item.refresh_from_db()
        assert item.order_price == Decimal("0.00")

    def test_edit_price_preserves_other_item_fields(self, client):
        """
        Test: Editing price does not modify other item fields (IMEI, product, etc.).
        """
        # Create unsold stock item
        item = InventoryItem.objects.create(
            business=self.business,
            imei="111000999888777",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="IN_STOCK",
            current_location=self.location,
            assigned_agent=self.agent,
            assigned_role="AGENT",
        )

        original_imei = item.imei
        original_product_id = item.product_id
        original_location_id = item.current_location_id
        original_agent_id = item.assigned_agent_id
        original_role = item.assigned_role

        # Login as manager
        client.force_login(self.manager)

        # Edit price
        url = reverse("inventory:edit_price", kwargs={"pk": item.pk})
        response = client.post(url, {"price": "1100.00"})

        # Should succeed
        assert response.status_code == 302

        # Refresh item
        item.refresh_from_db()

        # Assert price updated
        assert item.order_price == Decimal("1100.00")

        # Assert other fields unchanged
        assert item.imei == original_imei
        assert item.product_id == original_product_id
        assert item.current_location_id == original_location_id
        assert item.assigned_agent_id == original_agent_id
        assert item.assigned_role == original_role
        assert item.selling_price == Decimal("1500.00")  # selling price unchanged

    def test_edit_price_redirect_with_next_parameter(self, client):
        """
        Test: Redirect to 'next' URL if provided (preserves filter state).
        """
        # Create unsold stock item
        item = InventoryItem.objects.create(
            business=self.business,
            imei="000999888777666",
            product=self.product,
            order_price=Decimal("1000.00"),
            selling_price=Decimal("1500.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        # Login as manager
        client.force_login(self.manager)

        # Edit price with 'next' parameter
        url = reverse("inventory:edit_price", kwargs={"pk": item.pk})
        next_url = "/inventory/list/?status=in_stock&page=2"
        response = client.post(url, {"price": "1100.00", "next": next_url})

        # Should redirect to next URL
        assert response.status_code == 302
        assert response.url == next_url

