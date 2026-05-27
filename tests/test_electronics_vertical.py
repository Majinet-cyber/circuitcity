"""
Tests for Electronics vertical expansion: Laptops and Desktops.

- Creating laptop/desktop catalog product with specs
- Stock in by serial number
- Sell flow
- Legacy phone flows unchanged
- Dashboard includes electronics
"""
import pytest
from decimal import Decimal
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Location
from inventory.models_phone_products import (
    PhoneProductCatalog,
    ElectronicsCategory,
    ElectronicsStockItem,
)
from tenants.models import Business
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestElectronicsLaptopDesktop(TestCase):
    """Laptop/Desktop catalog, stock-in, and sell."""

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Electronics",
            business_kind="phones",
            slug="test-electronics",
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main",
            is_default=True,
        )
        self.user = User.objects.create_user(
            username="electronics_manager",
            password="testpass123",
            email="em@test.com",
        )
        from tenants.models import Membership
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
        self.client = Client()
        self.client.login(username="electronics_manager", password="testpass123")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_create_laptop_catalog_product(self):
        """Add a laptop model to catalog with specs."""
        catalog = PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.LAPTOP,
            brand="Dell",
            model_name="Latitude 5420",
            ram_gb=0,
            rom_gb=0,
            ram_str="16GB",
            storage_str="512GB SSD",
            cpu="Intel i5-1135G7",
            screen_size="14\"",
            os="Windows 11",
            is_active=True,
        )
        self.assertEqual(catalog.category, ElectronicsCategory.LAPTOP)
        self.assertEqual(catalog.display_name, "Dell Latitude 5420 16GB / 512GB SSD")
        self.assertTrue(catalog.is_laptop)

    def test_stock_in_laptop_and_sell(self):
        """Stock in a laptop by serial then sell it."""
        catalog = PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.LAPTOP,
            brand="Lenovo",
            model_name="ThinkPad E14",
            ram_gb=0,
            rom_gb=0,
            ram_str="16GB",
            storage_str="512GB SSD",
            is_active=True,
        )
        item = ElectronicsStockItem.objects.create(
            business=self.business,
            catalog_product=catalog,
            serial_number="SN123456789012345",
            current_location=self.location,
            order_price=Decimal("1500.00"),
            selling_price=Decimal("1800.00"),
            status="IN_STOCK",
            is_active=True,
        )
        self.assertEqual(item.status, "IN_STOCK")

        # Sell via view
        url = reverse("inventory:electronics_sell")
        res = self.client.post(url, {"item_id": str(item.id)})
        self.assertEqual(res.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, "SOLD")
        self.assertIsNotNone(item.sold_at)
        self.assertEqual(item.sold_by, self.user)

    def test_electronics_stock_in_creates_item(self):
        """POST to electronics_stock_in creates ElectronicsStockItem."""
        catalog = PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.LAPTOP,
            brand="Dell",
            model_name="XPS 15",
            ram_gb=0,
            rom_gb=0,
            ram_str="32GB",
            storage_str="1TB SSD",
            is_active=True,
        )
        url = reverse("inventory:electronics_stock_in")
        res = self.client.post(url, {
            "catalog_id": str(catalog.id),
            "serial_number": "UNIQUESERIAL999",
            "location_id": str(self.location.id),
            "order_price": "2000",
            "selling_price": "2400",
        })
        self.assertEqual(res.status_code, 302)
        self.assertTrue(
            ElectronicsStockItem.objects.filter(
                business=self.business,
                serial_number="UNIQUESERIAL999",
                status="IN_STOCK",
                is_active=True,
            ).exists()
        )

    def test_serial_number_unique_per_business(self):
        """Duplicate serial in same business is rejected."""
        catalog = PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.LAPTOP,
            brand="Dell",
            model_name="Vostro",
            ram_gb=0,
            rom_gb=0,
            ram_str="8GB",
            storage_str="256GB",
            is_active=True,
        )
        ElectronicsStockItem.objects.create(
            business=self.business,
            catalog_product=catalog,
            serial_number="DUP123",
            current_location=self.location,
            status="IN_STOCK",
            is_active=True,
        )
        url = reverse("inventory:electronics_stock_in")
        res = self.client.post(url, {
            "catalog_id": str(catalog.id),
            "serial_number": "DUP123",
            "location_id": str(self.location.id),
            "order_price": "0",
        })
        self.assertEqual(res.status_code, 302)
        self.assertEqual(ElectronicsStockItem.objects.filter(serial_number="DUP123", is_active=True).count(), 1)


@pytest.mark.django_db
class TestLegacyPhoneFlowsUnchanged(TestCase):
    """Ensure existing phone catalog and flows still work."""

    def setUp(self):
        self.business = Business.objects.create(
            name="Test Phones",
            business_kind="phones",
            slug="test-phones-legacy",
        )
        Location.objects.create(business=self.business, name="Store", is_default=True)
        self.user = User.objects.create_user(username="phoneuser", password="testpass123", email="p@test.com")
        from tenants.models import Membership
        Membership.objects.create(user=self.user, business=self.business, role="MANAGER", status="ACTIVE")
        self.client = Client()
        self.client.login(username="phoneuser", password="testpass123")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_phone_products_page_returns_200(self):
        """Legacy phone products URL still works."""
        res = self.client.get(reverse("inventory:phone_products"))
        self.assertEqual(res.status_code, 200)

    def test_phone_catalog_category_phone_default(self):
        """New phone catalog entries get category=PHONE."""
        from inventory.phone_catalog_seed import seed_phone_catalog
        created = seed_phone_catalog(self.business, created_by=self.user)
        self.assertGreater(created, 0)
        for p in PhoneProductCatalog.objects.filter(business=self.business):
            self.assertEqual(p.category, ElectronicsCategory.PHONE)

    def test_laptop_and_desktop_routes_require_phones_business(self):
        """Laptop/desktop product routes exist and require PHONES business."""
        res = self.client.get(reverse("inventory:laptop_products"))
        self.assertEqual(res.status_code, 200)
        res = self.client.get(reverse("inventory:desktop_products"))
        self.assertEqual(res.status_code, 200)


@pytest.mark.django_db
def test_dashboard_includes_electronics_stock():
    """Phones adapter stock overview includes electronics (laptop/desktop) value."""
    from django.db.models import Sum
    from django.db.models.functions import Coalesce
    from inventory.analytics.adapters.phones import PhonesAdapter, _get_electronics_stock_qs

    business = Business.objects.create(name="Biz", business_kind="phones", slug="biz-dash")
    loc = Location.objects.create(business=business, name="L1", is_default=True)
    catalog = PhoneProductCatalog.objects.create(
        business=business,
        category=ElectronicsCategory.LAPTOP,
        brand="Dell",
        model_name="X",
        ram_gb=0,
        rom_gb=0,
        ram_str="8GB",
        storage_str="256GB",
        is_active=True,
    )
    ElectronicsStockItem.objects.create(
        business=business,
        catalog_product=catalog,
        serial_number="DASH1",
        current_location=loc,
        order_price=Decimal("1000"),
        status="IN_STOCK",
        is_active=True,
    )

    stock_qs = _get_electronics_stock_qs(business)
    assert stock_qs is not None
    total = stock_qs.aggregate(s=Coalesce(Sum("order_price"), Decimal("0")))["s"]
    assert total == Decimal("1000")

    adapter = PhonesAdapter()
    overview = adapter.charts(
        business,
        timezone.localdate() - timezone.timedelta(days=30),
        timezone.localdate(),
    )
    assert overview["stock_overview"]["stock_value"] >= 1000.0
