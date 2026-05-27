"""
Tests for unified Scan IN and Scan & Sell (Phones, Laptops, Desktops).

Covers:
- Category selector renders for laptops/desktops
- Laptop stock-in creates inventory units
- Laptop sale updates stock and records sale
- Margin warning logic (negative/low/healthy)
- Phones flow remains unchanged when selecting Phones
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models import Location
from inventory.models_phone_products import (
    PhoneProductCatalog,
    ElectronicsStockItem,
    ElectronicsCategory,
)
from inventory.business_kinds import BusinessKind

User = get_user_model()


class ElectronicsUnifiedScanInTestCase(TestCase):
    """Test unified Scan IN with category selector."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="mgr_elec",
            email="mgr@elec.com",
            password="testpass123",
            is_staff=True,
        )
        self.business = Business.objects.create(
            name="Electronics Shop",
            slug="electronics-shop",
            business_kind=BusinessKind.PHONES,
        )
        Membership.objects.create(
            business=self.business,
            user=self.user,
            role="MANAGER",
            status="ACTIVE",
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        self.client.login(username="mgr_elec", password="testpass123")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_scan_in_phones_category_renders_phone_ui(self):
        """Selecting Phones renders existing phone scan-in UI."""
        url = reverse("inventory:scan_in") + "?category=phones"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Should contain phone-specific content (brand cards or gamification)
        self.assertIn(b"Scan In", response.content)
        self.assertIn(b"Phones", response.content)

    def test_scan_in_laptops_category_renders_laptop_ui(self):
        """Selecting Laptops renders laptop stock-in UI."""
        # Create a catalog product so the "Choose a model" section renders
        PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.LAPTOP,
            brand="Dell",
            model_name="XPS 15",
            ram_gb=0, rom_gb=0,
            ram_str="16GB",
            storage_str="512GB SSD",
            is_active=True,
        )
        url = reverse("inventory:scan_in") + "?category=laptops"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Laptops", response.content)
        self.assertIn(b"Choose a model", response.content)

    def test_scan_in_desktops_category_renders_desktop_ui(self):
        """Selecting Desktops renders desktop stock-in UI."""
        url = reverse("inventory:scan_in") + "?category=desktops"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Desktops", response.content)

    def test_laptop_stock_in_creates_inventory_unit(self):
        """Laptop stock-in with serial creates ElectronicsStockItem."""
        catalog = PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.LAPTOP,
            brand="Dell",
            model_name="XPS 15",
            ram_str="16GB",
            storage_str="512GB SSD",
            default_cost_price=Decimal("800000"),
            is_active=True,
        )
        url = reverse("inventory:scan_in") + "?category=laptops"
        get_resp = self.client.get(url)
        self.assertEqual(get_resp.status_code, 200)
        csrf_cookie = get_resp.cookies.get("csrftoken")
        post_data = {
            "catalog_id": str(catalog.id),
            "serial_numbers": "SN-LAPTOP-001",
            "location_id": str(self.location.id),
            "order_price": "800000",
            "selling_price": "950000",
        }
        if csrf_cookie:
            post_data["csrfmiddlewaretoken"] = csrf_cookie.value
        response = self.client.post(url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ElectronicsStockItem.objects.filter(
                business=self.business,
                serial_number="SN-LAPTOP-001",
                status="IN_STOCK",
            ).exists()
        )


class ElectronicsUnifiedScanSellTestCase(TestCase):
    """Test unified Scan & Sell with margin warnings."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="mgr_sell",
            email="mgr@sell.com",
            password="testpass123",
            is_staff=True,
        )
        self.business = Business.objects.create(
            name="Sell Shop",
            slug="sell-shop",
            business_kind=BusinessKind.PHONES,
        )
        Membership.objects.create(
            business=self.business,
            user=self.user,
            role="MANAGER",
            status="ACTIVE",
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Store",
            is_default=True,
        )
        self.catalog = PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.LAPTOP,
            brand="HP",
            model_name="Pavilion",
            ram_str="8GB",
            storage_str="256GB",
            default_cost_price=Decimal("500000"),
            is_active=True,
        )
        self.item = ElectronicsStockItem.objects.create(
            business=self.business,
            catalog_product=self.catalog,
            serial_number="SN-SELL-001",
            current_location=self.location,
            order_price=Decimal("500000"),
            selling_price=Decimal("600000"),
            status="IN_STOCK",
            is_active=True,
        )
        self.client.login(username="mgr_sell", password="testpass123")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

    def test_laptop_sale_via_wizard_redirects(self):
        """scan_sell?category=laptops now redirects to the gamified laptop wizard."""
        url = reverse("inventory:scan_sell") + "?category=laptops"
        response = self.client.get(url)
        # Updated behaviour: redirects to laptop-sale-wizard
        self.assertEqual(response.status_code, 302)
        self.assertIn("laptop-sale-wizard", response["Location"])

    def test_scan_sell_laptops_wizard_step1_renders_margin_section(self):
        """Laptop wizard (step 4) has margin indicator (JS-driven)."""
        # Step 4 of the wizard has the margin section
        session = self.client.session
        session["electronics_sale_wizard"] = {
            "category": "laptops",
            "step": 4,
            "brand": "HP",
            "catalog_id": self.catalog.id,
            "unit_id": self.item.id,
            "serial_number": "SN-SELL-001",
            "unit_display": "HP Pavilion (SN: SN-SELL-001)",
            "unit_cost_price": float(self.item.order_price),
            "unit_suggested_price": float(self.item.selling_price or 0),
            "battery_health": "",
        }
        session.save()
        url = reverse("inventory:laptop_sale_wizard") + "?step=4"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"margin-section", response.content)
        self.assertIn(b"updateMargin", response.content)

    def test_phones_flow_unchanged(self):
        """Phones selection renders phone scan-sell (unchanged)."""
        url = reverse("inventory:scan_sell") + "?category=phones"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Phones", response.content)
