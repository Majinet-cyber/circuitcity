"""
PHASE 4: Comprehensive tests for price correction functionality
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Product, Location
from sales.models import Sale
from audit.models_price_audit import PriceAdjustment, UnsoldPriceEdit
from audit.services_price_corrections import edit_unsold_item_prices, adjust_sold_item_price, get_effective_sale_price
from wallet.models import WalletTransaction, TxnType

User = get_user_model()


@pytest.mark.django_db
class TestUnsoldPriceEdit(TestCase):
    """Tests for editing prices on unsold inventory items"""

    def setUp(self):
        # Create business
        self.business = Business.objects.create(name="Test Business", business_kind="PHONES")

        # Create users
        self.manager = User.objects.create_user(username="manager", password="testpass123")
        self.agent = User.objects.create_user(username="agent", password="testpass123")

        # Create profiles
        from circuitcity.accounts.models import Profile

        self.manager_profile = Profile.objects.create(user=self.manager, is_manager=True)
        self.agent_profile = Profile.objects.create(user=self.agent, is_manager=False)

        # Create memberships
        Membership.objects.create(user=self.manager, business=self.business, role="MANAGER", status="ACTIVE")
        Membership.objects.create(user=self.agent, business=self.business, role="AGENT", status="ACTIVE")

        # Create product and location
        self.product = Product.objects.create(
            code="TEST001", model="Test Phone", cost_price=Decimal("5000.00"), sale_price=Decimal("7000.00")
        )
        self.location = Location.objects.create(name="Main Store", business=self.business)

        # Create unsold item
        self.item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012345",
            order_price=Decimal("5000.00"),
            selling_price=Decimal("7000.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        self.client = Client()

    def test_manager_can_edit_unsold_item_prices(self):
        """Manager can successfully edit prices on unsold item"""
        result = edit_unsold_item_prices(
            item=self.item,
            new_order_price=Decimal("5200.00"),
            new_selling_price=Decimal("7200.00"),
            reason="Price increase from supplier",
            edited_by=self.manager,
            business=self.business,
        )

        assert result["success"] is True
        assert result["new_order_price"] == Decimal("5200.00")
        assert result["new_selling_price"] == Decimal("7200.00")

        # Verify item updated
        self.item.refresh_from_db()
        assert self.item.order_price == Decimal("5200.00")
        assert self.item.selling_price == Decimal("7200.00")

        # Verify audit record created
        audit = UnsoldPriceEdit.objects.get(id=result["audit_id"])
        assert audit.item == self.item
        assert audit.edited_by == self.manager
        assert audit.reason == "Price increase from supplier"

    def test_agent_cannot_edit_prices(self):
        """Agent without manager permission cannot edit prices"""
        with pytest.raises(PermissionError, match="Only managers can edit prices"):
            edit_unsold_item_prices(
                item=self.item,
                new_order_price=Decimal("5200.00"),
                reason="Trying to edit",
                edited_by=self.agent,
                business=self.business,
            )

    def test_cannot_edit_sold_item(self):
        """Cannot edit prices on sold items using unsold endpoint"""
        self.item.status = "SOLD"
        self.item.save()

        with pytest.raises(ValueError, match="Cannot edit prices on sold items"):
            edit_unsold_item_prices(
                item=self.item,
                new_order_price=Decimal("5200.00"),
                reason="Trying to edit sold item",
                edited_by=self.manager,
                business=self.business,
            )

    def test_negative_prices_rejected(self):
        """Negative prices are rejected"""
        with pytest.raises(ValueError, match="cannot be negative"):
            edit_unsold_item_prices(
                item=self.item,
                new_order_price=Decimal("-100.00"),
                reason="Testing negative price",
                edited_by=self.manager,
                business=self.business,
            )

    def test_reason_too_short_rejected(self):
        """Reason must be at least 5 characters"""
        with pytest.raises(ValueError, match="at least 5 characters"):
            edit_unsold_item_prices(
                item=self.item,
                new_order_price=Decimal("5200.00"),
                reason="Bad",
                edited_by=self.manager,
                business=self.business,
            )

    def test_must_change_at_least_one_price(self):
        """Must specify at least one price to change"""
        with pytest.raises(ValueError, match="at least one price"):
            edit_unsold_item_prices(
                item=self.item,
                new_order_price=None,
                new_selling_price=None,
                reason="No changes",
                edited_by=self.manager,
                business=self.business,
            )


@pytest.mark.django_db
class TestSoldPriceAdjustment(TestCase):
    """Tests for adjusting prices on sold items"""

    def setUp(self):
        # Create business
        self.business = Business.objects.create(name="Test Business", business_kind="PHONES")

        # Create users
        self.manager = User.objects.create_user(username="manager", password="testpass123")
        self.agent = User.objects.create_user(username="agent", password="testpass123")

        # Create profiles
        from circuitcity.accounts.models import Profile

        self.manager_profile = Profile.objects.create(user=self.manager, is_manager=True)
        self.agent_profile = Profile.objects.create(user=self.agent, is_manager=False)

        # Create product, location, item
        self.product = Product.objects.create(
            code="TEST001", model="Test Phone", cost_price=Decimal("5000.00"), sale_price=Decimal("7000.00")
        )
        self.location = Location.objects.create(name="Main Store", business=self.business)
        self.item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012345",
            order_price=Decimal("5000.00"),
            selling_price=Decimal("7000.00"),
            status="SOLD",
            current_location=self.location,
        )

        # Create sale
        self.sale = Sale.objects.create(
            item=self.item,
            agent=self.agent,
            location=self.location,
            sold_at="2026-01-01",
            price=Decimal("7000.00"),
            commission_pct=Decimal("3.00"),
        )

        self.client = Client()

    def test_manager_can_adjust_sold_item_price(self):
        """Manager can successfully adjust price on sold item"""
        result = adjust_sold_item_price(
            sale=self.sale,
            new_selling_price=Decimal("7200.00"),
            reason="Customer negotiated higher price after sale",
            adjusted_by=self.manager,
            business=self.business,
        )

        assert result["success"] is True
        assert result["new_selling_price"] == Decimal("7200.00")

        # Verify original sale NOT modified
        self.sale.refresh_from_db()
        assert self.sale.price == Decimal("7000.00")  # Original unchanged

        # Verify adjustment record created
        adjustment = PriceAdjustment.objects.get(id=result["adjustment_id"])
        assert adjustment.sale == self.sale
        assert adjustment.new_selling_price == Decimal("7200.00")
        assert adjustment.adjusted_by == self.manager

    def test_commission_recalculation(self):
        """Commission is recalculated when selling price changes"""
        result = adjust_sold_item_price(
            sale=self.sale,
            new_selling_price=Decimal("7200.00"),
            reason="Price adjustment with commission impact",
            adjusted_by=self.manager,
            business=self.business,
        )

        # Original commission: 7000 * 3% = 210
        # New commission: 7200 * 3% = 216
        # Delta: +6
        assert result["commission_delta"] == Decimal("6.00")

        # Verify wallet transaction created
        assert result["commission_txn_id"] is not None
        txn = WalletTransaction.objects.get(id=result["commission_txn_id"])
        assert txn.agent == self.agent
        assert txn.type == TxnType.ADJUSTMENT
        assert txn.amount == Decimal("6.00")

    def test_get_effective_sale_price_with_adjustment(self):
        """get_effective_sale_price returns adjusted values"""
        # Create adjustment
        adjust_sold_item_price(
            sale=self.sale,
            new_selling_price=Decimal("7200.00"),
            new_cost_price=Decimal("5100.00"),
            reason="Full price adjustment",
            adjusted_by=self.manager,
            business=self.business,
        )

        # Get effective prices
        effective = get_effective_sale_price(self.sale)
        assert effective["effective_selling_price"] == Decimal("7200.00")
        assert effective["effective_cost_price"] == Decimal("5100.00")
        assert effective["effective_profit"] == Decimal("2100.00")

    def test_get_effective_sale_price_no_adjustment(self):
        """get_effective_sale_price returns original values when no adjustment"""
        effective = get_effective_sale_price(self.sale)
        assert effective["effective_selling_price"] == Decimal("7000.00")
        assert effective["effective_cost_price"] == Decimal("5000.00")
        assert effective["effective_profit"] == Decimal("2000.00")

    def test_agent_cannot_adjust_prices(self):
        """Agent without manager permission cannot adjust prices"""
        with pytest.raises(PermissionError, match="Only managers can adjust"):
            adjust_sold_item_price(
                sale=self.sale,
                new_selling_price=Decimal("7200.00"),
                reason="Trying to adjust",
                adjusted_by=self.agent,
                business=self.business,
            )

    def test_reason_too_short_for_sold_item(self):
        """Reason for sold item adjustment must be at least 10 characters"""
        with pytest.raises(ValueError, match="at least 10 characters"):
            adjust_sold_item_price(
                sale=self.sale,
                new_selling_price=Decimal("7200.00"),
                reason="Too short",
                adjusted_by=self.manager,
                business=self.business,
            )


@pytest.mark.django_db
class TestPriceEditAPI(TestCase):
    """Tests for price edit API endpoints"""

    def setUp(self):
        # Setup similar to above
        self.business = Business.objects.create(name="Test Business", business_kind="PHONES")
        self.manager = User.objects.create_user(username="manager", password="testpass123")
        from circuitcity.accounts.models import Profile

        profile = Profile.objects.get(user=self.manager)
        profile.is_manager = True
        profile.save()

        self.product = Product.objects.create(code="TEST001", model="Test Phone")
        self.location = Location.objects.create(name="Main Store", business=self.business)
        self.item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            imei="123456789012345",
            order_price=Decimal("5000.00"),
            selling_price=Decimal("7000.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

        self.client = Client()
        self.client.login(username="manager", password="testpass123")

    def test_edit_stock_prices_api_success(self):
        """API endpoint returns success for valid request"""
        response = self.client.post(
            reverse("inventory:api_edit_stock_prices", args=[self.item.id]),
            data={"order_price": "5200.00", "selling_price": "7200.00", "reason": "Testing API endpoint"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "audit_id" in data

    def test_edit_stock_prices_api_permission_denied(self):
        """API endpoint returns 403 for non-manager"""
        agent = User.objects.create_user(username="agent", password="testpass123")
        from circuitcity.accounts.models import Profile

        profile = Profile.objects.get(user=agent)
        profile.is_manager = False
        profile.save()

        self.client.logout()
        self.client.login(username="agent", password="testpass123")

        response = self.client.post(
            reverse("inventory:api_edit_stock_prices", args=[self.item.id]),
            data={"order_price": "5200.00", "reason": "Trying as agent"},
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestAuditTrail(TestCase):
    """Tests for audit trail persistence"""

    def setUp(self):
        self.business = Business.objects.create(name="Test Business")
        self.manager = User.objects.create_user(username="manager", password="testpass123")
        from circuitcity.accounts.models import Profile

        profile = Profile.objects.get(user=self.manager)
        profile.is_manager = True
        profile.save()

        self.product = Product.objects.create(code="TEST001", model="Test Phone")
        self.location = Location.objects.create(name="Main Store", business=self.business)
        self.item = InventoryItem.objects.create(
            business=self.business,
            product=self.product,
            order_price=Decimal("5000.00"),
            status="IN_STOCK",
            current_location=self.location,
        )

    def test_audit_record_persists(self):
        """Audit records are created and persist"""
        result = edit_unsold_item_prices(
            item=self.item,
            new_order_price=Decimal("5200.00"),
            reason="Testing audit persistence",
            edited_by=self.manager,
            business=self.business,
        )

        # Verify audit record exists
        audit = UnsoldPriceEdit.objects.get(id=result["audit_id"])
        assert audit.item == self.item
        assert audit.edited_by == self.manager
        assert audit.old_order_price == Decimal("5000.00")
        assert audit.new_order_price == Decimal("5200.00")
        assert audit.reason == "Testing audit persistence"
        assert audit.business == self.business

    def test_multiple_adjustments_tracked(self):
        """Multiple adjustments on same sale are all tracked"""
        self.item.status = "SOLD"
        self.item.save()

        sale = Sale.objects.create(
            item=self.item, location=self.location, sold_at="2026-01-01", price=Decimal("7000.00")
        )

        # First adjustment
        adjust_sold_item_price(
            sale=sale,
            new_selling_price=Decimal("7200.00"),
            reason="First adjustment for testing",
            adjusted_by=self.manager,
            business=self.business,
        )

        # Second adjustment
        adjust_sold_item_price(
            sale=sale,
            new_selling_price=Decimal("7400.00"),
            reason="Second adjustment for testing",
            adjusted_by=self.manager,
            business=self.business,
        )

        # Both adjustments should exist
        adjustments = PriceAdjustment.objects.filter(sale=sale).order_by("adjusted_at")
        assert adjustments.count() == 2
        assert adjustments[0].new_selling_price == Decimal("7200.00")
        assert adjustments[1].new_selling_price == Decimal("7400.00")

        # Latest adjustment is used
        effective = get_effective_sale_price(sale)
        assert effective["effective_selling_price"] == Decimal("7400.00")
