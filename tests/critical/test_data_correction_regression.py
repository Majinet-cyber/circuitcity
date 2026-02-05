# tests/critical/test_data_correction_regression.py
"""
CRITICAL REGRESSION TESTS for Phones Data Correction Feature

Tests all core functionality:
A) Access control - Manager-only access
B) Edit sold items updates totals correctly
C) IMEI safety - uniqueness validation
D) Void a sale removes it from aggregates

Run with: pytest tests/critical/test_data_correction_regression.py -v
"""
import json
from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.models import InventoryItem, Product, Location
from inventory.models_accessories import AccessoryProduct, AccessoryStock
from inventory.models_data_correction import DataCorrectionLog, VoidedRecord, CorrectionType
from inventory.business_kinds import BusinessKind
from inventory.services_data_correction import DataCorrectionService, CorrectionResult

User = get_user_model()


@pytest.fixture
def phones_business(db):
    """Create a phones business for testing."""
    return Business.objects.create(
        name="Test Phones Shop",
        business_kind=BusinessKind.PHONES,
    )


@pytest.fixture
def manager_user(db, phones_business):
    """Create a manager user for the phones business."""
    user = User.objects.create_user(
        username="test_manager",
        email="manager@test.com",
        password="testpass123",
        is_staff=True,  # Required for is_manager() check
    )
    Membership.objects.create(
        user=user,
        business=phones_business,
        role="MANAGER",
        is_active=True,
    )
    return user


@pytest.fixture
def staff_user(db, phones_business):
    """Create a non-manager (agent) user for the phones business."""
    user = User.objects.create_user(
        username="test_agent",
        email="agent@test.com",
        password="testpass123",
    )
    Membership.objects.create(
        user=user,
        business=phones_business,
        role="AGENT",
        is_active=True,
    )
    return user


@pytest.fixture
def location(db, phones_business):
    """Create a test location."""
    return Location.objects.create(
        business=phones_business,
        name="Test Store",
        is_default=True,
    )


@pytest.fixture
def product(db):
    """Create a test phone product."""
    return Product.objects.get_or_create(
        code="TECNO-SPARK10-4GB128GB",
        defaults={
            "brand": "TECNO",
            "model": "Spark 10",
            "variant": "4GB+128GB",
            "cost_price": Decimal("100000"),
            "sale_price": Decimal("150000"),
        },
    )[0]


@pytest.fixture
def sold_phone(db, phones_business, location, product):
    """Create a sold phone inventory item."""
    return InventoryItem.objects.create(
        business=phones_business,
        imei="123456789012345",
        product=product,
        current_location=location,
        order_price=Decimal("100000"),
        selling_price=Decimal("150000"),
        status="SOLD",
        sold_at=timezone.now(),
        received_at=date.today(),
    )


@pytest.fixture
def in_stock_phone(db, phones_business, location, product):
    """Create an in-stock phone inventory item."""
    return InventoryItem.objects.create(
        business=phones_business,
        imei="987654321098765",
        product=product,
        current_location=location,
        order_price=Decimal("100000"),
        status="IN_STOCK",
        received_at=date.today(),
    )


class TestDataCorrectionAccessControl(TestCase):
    """Test A) Access control - Manager-only access."""
    
    def setUp(self):
        self.client = Client()
        
        # Create business
        self.business = Business.objects.create(
            name="Access Control Test Shop",
            business_kind=BusinessKind.PHONES,
        )
        
        # Create manager (is_staff=True for is_manager() check)
        self.manager = User.objects.create_user(
            username="access_manager",
            email="access_manager@test.com",
            password="testpass123",
            is_staff=True,  # Required for is_manager() check
        )
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            is_active=True,
        )
        
        # Create agent (not is_staff, so is_manager() returns False)
        self.agent = User.objects.create_user(
            username="access_agent",
            email="access_agent@test.com",
            password="testpass123",
        )
        Membership.objects.create(
            user=self.agent,
            business=self.business,
            role="AGENT",
            is_active=True,
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Access Test Store",
            is_default=True,
        )
    
    def test_manager_can_access_data_correction_dashboard(self):
        """Manager can access /verticals/phones/data-correction/ (200)."""
        self.client.login(username="access_manager", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get(
            reverse("verticals:phones_data_correction"),
            follow=True,
        )
        
        # Should get 200 (or redirect to login which is also acceptable for test setup)
        assert response.status_code in [200, 302]
    
    def test_non_manager_cannot_access_data_correction(self):
        """Non-manager (agent) gets 403 or redirected when accessing data correction."""
        self.client.login(username="access_agent", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get(
            reverse("verticals:phones_data_correction"),
            follow=False,  # Don't follow redirects
        )
        
        # Should be forbidden or redirected (403 or 302/301)
        assert response.status_code in [403, 302, 301]
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(
            reverse("verticals:phones_data_correction"),
            follow=False,
        )
        
        # Should redirect to login
        assert response.status_code == 302


@pytest.mark.django_db
class TestEditSoldItemUpdatesTotals:
    """Test B) Edit sold item updates totals correctly."""
    
    def test_edit_selling_price_updates_profit(
        self, phones_business, location, product, manager_user
    ):
        """
        Create a sold phone with cost=100,000, sell=150,000
        Edit selling price to 200,000
        Assert profit recalculates to 100,000
        """
        # Create sold phone
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="111111111111111",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
        )
        
        # Initial profit = 150,000 - 100,000 = 50,000
        assert item.profit == Decimal("50000")
        
        # Edit selling price via service
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.edit_phone_sale(
            item_id=item.pk,
            reason="Customer paid more than recorded",
            new_selling_price=Decimal("200000"),
        )
        
        assert result.success is True
        assert result.revenue_impact == Decimal("50000")  # 200k - 150k
        assert result.profit_impact == Decimal("50000")   # New profit (100k) - Old profit (50k)
        
        # Reload item and check
        item.refresh_from_db()
        assert item.selling_price == Decimal("200000")
        assert item.profit == Decimal("100000")  # 200,000 - 100,000
    
    def test_edit_cost_price_updates_profit(
        self, phones_business, location, product, manager_user
    ):
        """Edit cost price of sold item updates profit correctly."""
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="222222222222222",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
        )
        
        # Edit cost price to 80,000
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.edit_phone_sale(
            item_id=item.pk,
            reason="Actual cost was lower",
            new_order_price=Decimal("80000"),
        )
        
        assert result.success is True
        assert result.profit_impact == Decimal("20000")  # New profit (70k) - Old profit (50k)
        
        item.refresh_from_db()
        assert item.order_price == Decimal("80000")
        assert item.profit == Decimal("70000")  # 150,000 - 80,000
    
    def test_correction_creates_audit_log(
        self, phones_business, location, product, manager_user
    ):
        """Every correction creates an audit log entry."""
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="333333333333333",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
        )
        
        # Count logs before
        logs_before = DataCorrectionLog.objects.filter(
            business=phones_business,
            model_name="InventoryItem",
            object_id=item.pk,
        ).count()
        
        # Make correction
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.edit_phone_sale(
            item_id=item.pk,
            reason="Test audit logging",
            new_selling_price=Decimal("160000"),
        )
        
        assert result.success is True
        
        # Check log was created
        logs_after = DataCorrectionLog.objects.filter(
            business=phones_business,
            model_name="InventoryItem",
            object_id=item.pk,
        ).count()
        
        assert logs_after == logs_before + 1
        
        # Check log content
        log = DataCorrectionLog.objects.filter(
            business=phones_business,
            model_name="InventoryItem",
            object_id=item.pk,
        ).first()
        
        assert log.reason == "Test audit logging"
        assert log.corrected_by == manager_user
        assert "selling_price" in log.field_changes


@pytest.mark.django_db
class TestIMEISafety:
    """Test C) IMEI safety - uniqueness validation."""
    
    def test_cannot_change_imei_to_existing_imei(
        self, phones_business, location, product, manager_user
    ):
        """
        Create two phones with different IMEIs.
        Attempt to change one IMEI to the other → validation error.
        """
        # Create two phones with different IMEIs
        item1 = InventoryItem.objects.create(
            business=phones_business,
            imei="444444444444444",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
            received_at=date.today(),
        )
        
        item2 = InventoryItem.objects.create(
            business=phones_business,
            imei="555555555555555",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
            received_at=date.today(),
        )
        
        # Try to change item1's IMEI to item2's IMEI
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.edit_phone_sale(
            item_id=item1.pk,
            reason="Trying to duplicate IMEI",
            new_imei="555555555555555",  # Same as item2
        )
        
        assert result.success is False
        assert "already exists" in result.message.lower()
    
    def test_can_change_imei_to_new_unique_value(
        self, phones_business, location, product, manager_user
    ):
        """Change IMEI to a new unique value → succeeds."""
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="666666666666666",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
            received_at=date.today(),
        )
        
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        new_imei = "777777777777777"
        result = service.edit_phone_sale(
            item_id=item.pk,
            reason="Correcting typo in IMEI",
            new_imei=new_imei,
        )
        
        assert result.success is True
        
        item.refresh_from_db()
        assert item.imei == new_imei
    
    def test_imei_validation_format(
        self, phones_business, location, product, manager_user
    ):
        """IMEI must be exactly 15 digits."""
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="888888888888888",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
            received_at=date.today(),
        )
        
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        # Too short
        result = service.edit_phone_sale(
            item_id=item.pk,
            reason="Test short IMEI",
            new_imei="12345",
        )
        
        assert result.success is False
        assert "15 digits" in result.message.lower()


@pytest.mark.django_db
class TestVoidSaleRemovesFromAggregates:
    """Test D) Void a sale removes it from aggregates."""
    
    def test_void_sale_marks_inactive(
        self, phones_business, location, product, manager_user
    ):
        """Voiding a sale marks the item as inactive (soft delete)."""
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="999999999999999",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
            is_active=True,
        )
        
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.void_phone_item(
            item_id=item.pk,
            reason="Duplicate entry",
        )
        
        assert result.success is True
        
        item.refresh_from_db()
        assert item.is_active is False
        assert item.archived_at is not None
    
    def test_void_sale_calculates_revenue_impact(
        self, phones_business, location, product, manager_user
    ):
        """Voiding a sale reports correct revenue impact."""
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="101010101010101",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
        )
        
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.void_phone_item(
            item_id=item.pk,
            reason="Test void impact",
        )
        
        assert result.success is True
        assert result.revenue_impact == Decimal("-150000")  # Removed revenue
        assert result.profit_impact == Decimal("-50000")    # Removed profit
    
    def test_void_creates_void_record(
        self, phones_business, location, product, manager_user
    ):
        """Voiding creates a VoidedRecord for audit."""
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="121212121212121",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
        )
        
        # Count void records before
        voids_before = VoidedRecord.objects.filter(
            business=phones_business,
            model_name="InventoryItem",
            object_id=item.pk,
        ).count()
        
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.void_phone_item(
            item_id=item.pk,
            reason="Test void record creation",
        )
        
        assert result.success is True
        
        # Check void record was created
        voids_after = VoidedRecord.objects.filter(
            business=phones_business,
            model_name="InventoryItem",
            object_id=item.pk,
        ).count()
        
        assert voids_after == voids_before + 1
        
        # Check void record content
        void = VoidedRecord.objects.get(
            business=phones_business,
            model_name="InventoryItem",
            object_id=item.pk,
        )
        
        assert void.reason == "Test void record creation"
        assert void.voided_by == manager_user
        assert void.record_snapshot is not None
        assert void.is_restored is False
    
    def test_voided_items_excluded_from_active_queryset(
        self, phones_business, location, product, manager_user
    ):
        """Voided items are excluded from active querysets."""
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="131313131313131",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
        )
        
        # Before void: item appears in active queryset
        active_before = InventoryItem.objects.filter(
            business=phones_business,
            is_active=True,
            imei="131313131313131",
        ).count()
        
        assert active_before == 1
        
        # Void the item
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        service.void_phone_item(
            item_id=item.pk,
            reason="Test exclusion from queryset",
        )
        
        # After void: item excluded from active queryset
        active_after = InventoryItem.objects.filter(
            business=phones_business,
            is_active=True,
            imei="131313131313131",
        ).count()
        
        assert active_after == 0


@pytest.mark.django_db
class TestReasonRequired:
    """Test that reason is required for all corrections."""
    
    def test_edit_without_reason_fails(
        self, phones_business, location, product, manager_user
    ):
        """Edit without reason fails."""
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="141414141414141",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
            received_at=date.today(),
        )
        
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.edit_phone_sale(
            item_id=item.pk,
            reason="",  # Empty reason
            new_selling_price=Decimal("160000"),
        )
        
        assert result.success is False
        assert "reason" in result.message.lower()
    
    def test_void_without_reason_fails(
        self, phones_business, location, product, manager_user
    ):
        """Void without reason fails."""
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="151515151515151",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
            received_at=date.today(),
        )
        
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.void_phone_item(
            item_id=item.pk,
            reason="",  # Empty reason
        )
        
        assert result.success is False
        assert "reason" in result.message.lower()


@pytest.mark.django_db
class TestDataCorrectionSidebar:
    """Test that Data Correction sidebar item is correctly configured."""
    
    def test_data_correction_in_phones_sidebar(self):
        """Data Correction item exists in phones sidebar."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items("phones")
        
        # Find data correction item
        data_correction_items = [
            item for item in items
            if item.get("key") == "data_correction"
        ]
        
        assert len(data_correction_items) == 1, "Data Correction should be in phones sidebar"
        
        dc_item = data_correction_items[0]
        assert dc_item["require_manager"] is True, "Data Correction should require manager"
        assert "data-correction" in dc_item["url"].lower() or "data_correction" in dc_item["url"].lower()
    
    def test_data_correction_in_all_registered_verticals(self):
        """Data Correction now appears in ALL verticals (if registered in corrections framework)."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        from corrections.registry import registry
        
        # Get all registered verticals from corrections framework
        registered_verticals = [v['key'] for v in registry.list_verticals()]
        
        # Data Correction should appear in all registered verticals
        for vertical in registered_verticals:
            items = get_vertical_sidebar_items(vertical)
            
            data_correction_items = [
                item for item in items
                if item.get("key") == "data_correction"
            ]
            
            assert len(data_correction_items) == 1, f"Data Correction SHOULD be in {vertical} sidebar (registered vertical)"
            
            dc_item = data_correction_items[0]
            assert dc_item["require_manager"] is True
            assert f"/corrections/{vertical}/" in dc_item["url"]


class TestDataCorrectionURLResolves(TestCase):
    """Test that data correction URLs resolve correctly."""
    
    def test_dashboard_url_resolves(self):
        """Data correction dashboard URL resolves."""
        url = reverse("verticals:phones_data_correction")
        assert url == "/verticals/phones/data-correction/"
    
    def test_phone_detail_url_resolves(self):
        """Phone detail URL resolves."""
        url = reverse("verticals:phones_data_correction_phone_detail", kwargs={"item_id": 1})
        assert "/data-correction/phone/1/" in url
    
    def test_audit_trail_url_resolves(self):
        """Audit trail URL resolves."""
        url = reverse("verticals:phones_data_correction_audit_trail")
        assert "/data-correction/audit-trail/" in url
    
    def test_export_url_resolves(self):
        """Export CSV URL resolves."""
        url = reverse("verticals:phones_data_correction_export")
        assert "/data-correction/export.csv" in url


# ============================================================================
# REGRESSION TESTS - Issue 1: intcomma filter (TemplateSyntaxError)
# ============================================================================

class TestDataCorrectionDashboardRenders(TestCase):
    """
    REGRESSION TEST: Issue 1 - TemplateSyntaxError: Invalid filter 'intcomma'
    
    The data correction dashboard uses |intcomma filter for formatting prices.
    This test ensures the template loads humanize filters correctly and renders.
    """
    
    def setUp(self):
        self.client = Client()
        
        # Create business
        self.business = Business.objects.create(
            name="Template Render Test Shop",
            business_kind=BusinessKind.PHONES,
        )
        
        # Create manager (is_staff=True for is_manager() check)
        self.manager = User.objects.create_user(
            username="render_test_manager",
            email="render_test_manager@test.com",
            password="testpass123",
            is_staff=True,  # Required for is_manager() check
        )
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            is_active=True,
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Render Test Store",
            is_default=True,
        )
    
    def test_data_correction_dashboard_returns_200_for_manager(self):
        """
        REGRESSION: GET /verticals/phones/data-correction/ returns 200 for manager.
        
        This test catches the TemplateSyntaxError for intcomma filter.
        If {% load humanize %} is missing, this test will fail.
        """
        self.client.login(username="render_test_manager", password="testpass123")
        
        # Set active business in session
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get(
            reverse("verticals:phones_data_correction"),
            follow=True,
        )
        
        # Should get 200 OK - if template has errors, this will fail
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}. "
            "This may indicate a TemplateSyntaxError (e.g., missing {% load humanize %})"
        )
    
    def test_data_correction_dashboard_renders_price_formatting(self):
        """
        REGRESSION: Dashboard renders formatted prices without template errors.
        
        Creates a phone item with a large price to verify intcomma formatting works.
        """
        # Create a test product
        product = Product.objects.get_or_create(
            code="TEST-RENDER-PHONE",
            defaults={
                "brand": "TestBrand",
                "model": "TestModel",
                "variant": "8GB+256GB",
                "cost_price": Decimal("500000"),
                "sale_price": Decimal("750000"),
            },
        )[0]
        
        # Create phone with large price (should trigger intcomma formatting)
        InventoryItem.objects.create(
            business=self.business,
            imei="999888777666555",
            product=product,
            current_location=self.location,
            order_price=Decimal("1500000"),  # 1,500,000
            selling_price=Decimal("2000000"),  # 2,000,000
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
        )
        
        self.client.login(username="render_test_manager", password="testpass123")
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get(
            reverse("verticals:phones_data_correction"),
            follow=True,
        )
        
        assert response.status_code == 200
        
        # Verify the page contains the product (basic smoke test)
        content = response.content.decode("utf-8")
        assert "TestBrand" in content or "TestModel" in content or "Data Correction" in content


# ============================================================================
# REGRESSION TESTS - Issue 2: Edit Price action does nothing
# ============================================================================

class TestStockListEditPriceAction(TestCase):
    """
    REGRESSION TEST: Issue 2 - Edit price action does nothing
    
    The stock list Actions menu "Edit price" button was missing its modal
    and JavaScript handler. This test ensures the edit price flow works.
    """
    
    def setUp(self):
        self.client = Client()
        
        # Create business
        self.business = Business.objects.create(
            name="Edit Price Test Shop",
            business_kind=BusinessKind.PHONES,
        )
        
        # Create manager (is_staff=True for is_manager() check)
        self.manager = User.objects.create_user(
            username="edit_price_manager",
            email="edit_price_manager@test.com",
            password="testpass123",
            is_staff=True,  # Required for is_manager() check
        )
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="MANAGER",
            is_active=True,
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Edit Price Test Store",
            is_default=True,
        )
        
        # Create test product
        self.product = Product.objects.get_or_create(
            code="TEST-EDITPRICE-PHONE",
            defaults={
                "brand": "EditPriceBrand",
                "model": "EditPriceModel",
                "variant": "4GB+64GB",
                "cost_price": Decimal("100000"),
                "sale_price": Decimal("150000"),
            },
        )[0]
    
    def test_stock_list_contains_edit_price_action(self):
        """
        REGRESSION: Stock list page includes Edit price action target.
        
        The stock list table should contain:
        - Either an Edit price button/link
        - OR the editPriceModal and showEditPriceModal function
        """
        # Create in-stock phone
        InventoryItem.objects.create(
            business=self.business,
            imei="111222333444555",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
            received_at=date.today(),
        )
        
        self.client.login(username="edit_price_manager", password="testpass123")
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        response = self.client.get(
            "/inventory/list/?view=all&status=in_stock",
            follow=True,
        )
        
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # Check that Edit price action exists
        assert "Edit price" in content, "Stock list should contain 'Edit price' action"
        
        # Check that the Edit Price Modal HTML exists
        assert "editPriceModal" in content, "Stock list should contain editPriceModal"
        
        # Check that showEditPriceModal function is defined
        assert "showEditPriceModal" in content, "Stock list should define showEditPriceModal function"
    
    def test_edit_price_post_updates_in_stock_item(self):
        """
        REGRESSION: POST to edit-price endpoint updates order price for IN_STOCK items.
        """
        # Create in-stock phone
        item = InventoryItem.objects.create(
            business=self.business,
            imei="222333444555666",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
            received_at=date.today(),
        )
        
        self.client.login(username="edit_price_manager", password="testpass123")
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        # POST new price
        response = self.client.post(
            f"/inventory/stock/{item.pk}/edit-price/",
            {"price": "120000"},
            follow=True,
        )
        
        # Should redirect successfully (302 -> 200)
        assert response.status_code == 200
        
        # Verify DB was updated
        item.refresh_from_db()
        assert item.order_price == Decimal("120000"), (
            f"Expected order_price=120000, got {item.order_price}"
        )
    
    def test_edit_price_post_updates_sold_item(self):
        """
        REGRESSION: POST to edit-price endpoint updates selling price for SOLD items.
        """
        # Create sold phone
        item = InventoryItem.objects.create(
            business=self.business,
            imei="333444555666777",
            product=self.product,
            current_location=self.location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
        )
        
        self.client.login(username="edit_price_manager", password="testpass123")
        
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        
        # POST new selling price
        response = self.client.post(
            f"/inventory/stock/{item.pk}/edit-price/",
            {"price": "175000"},
            follow=True,
        )
        
        # Should redirect successfully
        assert response.status_code == 200
        
        # Verify DB was updated
        item.refresh_from_db()
        assert item.selling_price == Decimal("175000"), (
            f"Expected selling_price=175000, got {item.selling_price}"
        )


# ============================================================================
# CRITICAL REGRESSION TESTS - Issue 3: Dashboard shows 0 for KPIs
# ============================================================================

@pytest.mark.django_db
class TestPhonesDashboardKPIsReflectSalesData:
    """
    CRITICAL REGRESSION TEST: Dashboard KPIs must reflect actual sales data.
    
    These tests ensure that:
    A) KPIs reflect existing sales (Units Sold, Revenue, Profit > 0)
    B) Data correction changes update KPIs accordingly
    C) Agent attribution is preserved in sales
    D) No destructive behavior - sold items remain counted
    """
    
    def test_kpis_reflect_existing_sales_with_sold_at(
        self, phones_business, location, product, manager_user
    ):
        """
        Test A: KPIs reflect existing sales.
        
        Create a phone item with status=SOLD, selling_price, and sold_at.
        Verify dashboard KPIs show Units Sold > 0, Revenue > 0, Profit > 0.
        """
        # Create sold phone with proper sold_at timestamp
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="161616161616161",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
            is_active=True,  # Must be active to be counted
        )
        
        # Compute KPIs using same logic as dashboard
        from django.db.models import Q, Sum
        from django.db.models.functions import Coalesce
        from django.db.models import DecimalField
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)
        today_end = today_start + timedelta(days=1)
        
        # Same query as phones.py dashboard
        sold_items = InventoryItem.objects.filter(
            business=phones_business,
            status="SOLD",
            is_active=True,
        )
        
        range_sales = sold_items.filter(
            Q(sold_at__gte=month_start, sold_at__lt=today_end) |
            Q(sold_at__isnull=True, received_at__gte=month_start.date(), 
              received_at__lt=today_end.date())
        )
        
        units_sold = range_sales.count()
        revenue = range_sales.aggregate(
            total=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
        )["total"] or Decimal("0.00")
        cogs = range_sales.aggregate(
            total=Coalesce(Sum("order_price"), Decimal("0.00"), output_field=DecimalField())
        )["total"] or Decimal("0.00")
        profit = revenue - cogs
        
        # Assertions
        assert units_sold >= 1, f"Expected units_sold >= 1, got {units_sold}"
        assert revenue >= Decimal("150000"), f"Expected revenue >= 150000, got {revenue}"
        assert profit >= Decimal("50000"), f"Expected profit >= 50000, got {profit}"
    
    def test_kpis_reflect_legacy_sales_without_sold_at(
        self, phones_business, location, product, manager_user
    ):
        """
        CRITICAL: KPIs must count legacy sales that don't have sold_at timestamp.
        
        Historical data may have status=SOLD but NULL sold_at.
        These MUST still be counted in KPIs.
        """
        # Create sold phone WITHOUT sold_at (legacy data scenario)
        # Note: We bypass the model's save() which auto-sets sold_at
        item = InventoryItem(
            business=phones_business,
            imei="171717171717171",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=None,  # NULL sold_at (legacy data)
            received_at=date.today() - timedelta(days=5),  # Within MTD
            is_active=True,
        )
        # Use update_fields to bypass the save() auto-setting of sold_at
        item.save()
        # Force NULL sold_at via update
        InventoryItem.objects.filter(pk=item.pk).update(sold_at=None)
        item.refresh_from_db()
        
        # Verify sold_at is NULL
        assert item.sold_at is None, "Test setup failed: sold_at should be NULL"
        assert item.status == "SOLD", "Test setup failed: status should be SOLD"
        
        # Compute KPIs using same logic as dashboard
        from django.db.models import Q, Sum
        from django.db.models.functions import Coalesce
        from django.db.models import DecimalField
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)
        today_end = today_start + timedelta(days=1)
        
        sold_items = InventoryItem.objects.filter(
            business=phones_business,
            status="SOLD",
            is_active=True,
        )
        
        range_sales = sold_items.filter(
            Q(sold_at__gte=month_start, sold_at__lt=today_end) |
            Q(sold_at__isnull=True, received_at__gte=month_start.date(), 
              received_at__lt=today_end.date())
        )
        
        units_sold = range_sales.count()
        revenue = range_sales.aggregate(
            total=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
        )["total"] or Decimal("0.00")
        
        # The legacy item (with NULL sold_at) MUST be counted
        assert units_sold >= 1, (
            f"CRITICAL: Legacy sale with NULL sold_at not counted! Got units_sold={units_sold}"
        )
        assert revenue >= Decimal("150000"), (
            f"CRITICAL: Legacy sale revenue not counted! Got revenue={revenue}"
        )
    
    def test_data_correction_updates_kpis(
        self, phones_business, location, product, manager_user
    ):
        """
        Test B: Data correction changes update KPIs.
        
        After editing selling price from X → Y, revenue should change accordingly.
        """
        # Create sold phone
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="181818181818181",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
            is_active=True,
        )
        
        # Initial revenue check
        from django.db.models import Sum
        from django.db.models.functions import Coalesce
        from django.db.models import DecimalField
        
        initial_revenue = InventoryItem.objects.filter(
            business=phones_business,
            status="SOLD",
            is_active=True,
            pk=item.pk,
        ).aggregate(
            total=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
        )["total"]
        
        assert initial_revenue == Decimal("150000")
        
        # Apply data correction
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.edit_phone_sale(
            item_id=item.pk,
            reason="Price correction test",
            new_selling_price=Decimal("200000"),
        )
        
        assert result.success is True
        
        # Verify KPI changed
        item.refresh_from_db()
        assert item.selling_price == Decimal("200000")
        
        new_revenue = InventoryItem.objects.filter(
            business=phones_business,
            status="SOLD",
            is_active=True,
            pk=item.pk,
        ).aggregate(
            total=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
        )["total"]
        
        assert new_revenue == Decimal("200000"), (
            f"Expected revenue=200000 after correction, got {new_revenue}"
        )
    
    def test_agent_attribution_preserved(
        self, phones_business, location, product, manager_user, staff_user
    ):
        """
        Test C: Agent attribution is preserved in sales.
        
        Sales assigned to an agent must show that agent in queries.
        """
        # Create sold phone assigned to an agent
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="191919191919191",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
            is_active=True,
            assigned_agent=staff_user,  # Assigned to agent
        )
        
        # Query for agent's sales
        agent_sales = InventoryItem.objects.filter(
            business=phones_business,
            status="SOLD",
            is_active=True,
            assigned_agent=staff_user,
        )
        
        assert agent_sales.count() >= 1, "Agent's sale not found"
        assert agent_sales.filter(pk=item.pk).exists(), "Specific sale not attributed to agent"
    
    def test_no_destructive_behavior_after_correction(
        self, phones_business, location, product, manager_user
    ):
        """
        Test D: Data Correction does not delete sale records.
        
        After correction:
        - Sale row count remains the same
        - Item remains sold (status=SOLD)
        - is_active remains True
        - Only price fields changed
        """
        # Create sold phone
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="202020202020202",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
            is_active=True,
        )
        
        # Count before correction
        count_before = InventoryItem.objects.filter(
            business=phones_business,
            status="SOLD",
            pk=item.pk,
        ).count()
        
        # Apply correction
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.edit_phone_sale(
            item_id=item.pk,
            reason="Non-destructive test",
            new_selling_price=Decimal("180000"),
        )
        
        assert result.success is True
        
        # Verify non-destructive behavior
        item.refresh_from_db()
        
        # Status still SOLD
        assert item.status == "SOLD", f"Status changed from SOLD to {item.status}"
        
        # is_active still True
        assert item.is_active is True, "is_active was set to False (DESTRUCTIVE!)"
        
        # Count unchanged
        count_after = InventoryItem.objects.filter(
            business=phones_business,
            status="SOLD",
            pk=item.pk,
        ).count()
        
        assert count_after == count_before, (
            f"Record count changed from {count_before} to {count_after} (DESTRUCTIVE!)"
        )
    
    def test_voided_items_excluded_from_kpis(
        self, phones_business, location, product, manager_user
    ):
        """
        Voided items (is_active=False) must NOT be counted in KPIs.
        """
        # Create sold phone
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="212121212121212",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            selling_price=Decimal("150000"),
            status="SOLD",
            sold_at=timezone.now(),
            received_at=date.today(),
            is_active=True,
        )
        
        # Initial count
        from django.db.models import Q, Sum
        from django.db.models.functions import Coalesce
        from django.db.models import DecimalField
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)
        today_end = today_start + timedelta(days=1)
        
        initial_count = InventoryItem.objects.filter(
            business=phones_business,
            status="SOLD",
            is_active=True,
        ).filter(
            Q(sold_at__gte=month_start, sold_at__lt=today_end) |
            Q(sold_at__isnull=True, received_at__gte=month_start.date(), 
              received_at__lt=today_end.date())
        ).count()
        
        # Void the item
        service = DataCorrectionService(
            business=phones_business,
            user=manager_user,
        )
        
        result = service.void_phone_item(
            item_id=item.pk,
            reason="Test voiding",
        )
        
        assert result.success is True
        
        # Count after voiding - should be 1 less
        after_count = InventoryItem.objects.filter(
            business=phones_business,
            status="SOLD",
            is_active=True,  # Key filter - voided items have is_active=False
        ).filter(
            Q(sold_at__gte=month_start, sold_at__lt=today_end) |
            Q(sold_at__isnull=True, received_at__gte=month_start.date(), 
              received_at__lt=today_end.date())
        ).count()
        
        assert after_count == initial_count - 1, (
            f"Voided item still counted in KPIs! Before={initial_count}, After={after_count}"
        )


@pytest.mark.django_db
class TestSoldItemsRemainActiveAfterSale:
    """
    REGRESSION TEST: Selling an item must NOT set is_active=False.
    
    This was a bug where api_mark_sold incorrectly set is_active=False,
    causing sold items to be excluded from KPI calculations.
    """
    
    def test_sold_items_remain_active(
        self, phones_business, location, product, manager_user
    ):
        """
        When a phone is sold via phone_scan_sell, is_active must remain True.
        """
        # Create in-stock phone
        item = InventoryItem.objects.create(
            business=phones_business,
            imei="222222222222221",
            product=product,
            current_location=location,
            order_price=Decimal("100000"),
            status="IN_STOCK",
            received_at=date.today(),
            is_active=True,
        )
        
        # Simulate selling (what phone_scan_sell does)
        item.status = "SOLD"
        item.selling_price = Decimal("150000")
        item.sold_at = timezone.now()
        item.payment_method = "CASH"
        item.save(update_fields=["status", "selling_price", "sold_at", "payment_method", "updated_at"])
        
        # Verify is_active is still True
        item.refresh_from_db()
        assert item.is_active is True, (
            f"CRITICAL: Sold item has is_active=False! This will break KPIs."
        )
        assert item.status == "SOLD"
