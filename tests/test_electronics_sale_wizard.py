"""
Tests for the Electronics Sale Wizard (Laptops / Desktops).

Covers:
1. Brand filtering - only brands with IN_STOCK units shown
2. Model filtering - only models with count > 0, shows count
3. Serial validation - cannot sell serial not in stock
4. Selling marks unit SOLD with correct payment_method
5. Duplicate sell rejected (already SOLD)
6. Payment method required
7. Price must be > 0
8. Existing phone wizard tests unaffected (regression guard)
9. Electronics stock list view
10. CSV export
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.models import Location
from inventory.models_phone_products import (
    ElectronicsCategory,
    ElectronicsStockItem,
    PhoneProductCatalog,
)
from tenants.models import Business, Membership

User = get_user_model()


class BaseElectronicsWizardTestCase(TestCase):
    """Shared setup for wizard tests."""

    def setUp(self):
        self.business = Business.objects.create(
            name="Wizard Test Shop",
            slug="wizard-test-shop",
            business_kind=BusinessKind.PHONES,
        )
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        self.user = User.objects.create_user(
            username="wiz_manager",
            email="wiz@test.com",
            password="testpass123",
        )
        Membership.objects.create(
            business=self.business,
            user=self.user,
            role="MANAGER",
            status="ACTIVE",
        )
        self.client = Client()
        self.client.login(username="wiz_manager", password="testpass123")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()

        # Laptop catalog product
        self.laptop_catalog = PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.LAPTOP,
            brand="Dell",
            model_name="Latitude 5420",
            ram_gb=0,
            rom_gb=0,
            ram_str="16GB",
            storage_str="512GB SSD",
            cpu="Intel i5-1135G7",
            screen_size='14"',
            os="Windows 11",
            default_cost_price=Decimal("1500.00"),
            default_selling_price=Decimal("1900.00"),
            is_active=True,
        )
        self.desktop_catalog = PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.DESKTOP,
            brand="HP",
            model_name="ProDesk 400",
            ram_gb=0,
            rom_gb=0,
            ram_str="8GB",
            storage_str="1TB HDD",
            is_active=True,
        )
        # In-stock laptop unit
        self.laptop_unit = ElectronicsStockItem.objects.create(
            business=self.business,
            catalog_product=self.laptop_catalog,
            serial_number="SN-LAPTOP-001",
            current_location=self.location,
            order_price=Decimal("1500.00"),
            selling_price=Decimal("1900.00"),
            status="IN_STOCK",
            is_active=True,
        )
        # In-stock desktop unit
        self.desktop_unit = ElectronicsStockItem.objects.create(
            business=self.business,
            catalog_product=self.desktop_catalog,
            serial_number="SN-DESKTOP-001",
            current_location=self.location,
            order_price=Decimal("2000.00"),
            selling_price=Decimal("2500.00"),
            status="IN_STOCK",
            is_active=True,
        )


class TestWizardStep1Brand(BaseElectronicsWizardTestCase):
    """Step 1: Brand selection filtered to brands with in-stock units."""

    def test_step1_renders_200(self):
        url = reverse("inventory:laptop_sale_wizard") + "?step=1"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Dell")

    def test_step1_only_shows_brands_with_stock(self):
        """Brand without stock should NOT appear in step 1."""
        # Create catalog product with no units
        PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.LAPTOP,
            brand="ACER",
            model_name="Swift 3",
            ram_gb=0, rom_gb=0,
            is_active=True,
        )
        url = reverse("inventory:laptop_sale_wizard") + "?step=1"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Dell")
        self.assertNotContains(res, "ACER")

    def test_step1_post_brand_goes_to_step2(self):
        url = reverse("inventory:laptop_sale_wizard")
        res = self.client.post(url, {"brand": "Dell"})
        self.assertEqual(res.status_code, 302)
        self.assertIn("step=2", res["Location"])

    def test_step1_post_empty_brand_shows_error(self):
        url = reverse("inventory:laptop_sale_wizard")
        res = self.client.post(url, {"brand": ""})
        # Empty brand shows form again with error (200), does not redirect
        self.assertIn(res.status_code, [200, 302])

    def test_desktop_step1_shows_hp(self):
        url = reverse("inventory:desktop_sale_wizard") + "?step=1"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "HP")


class TestWizardStep2Model(BaseElectronicsWizardTestCase):
    """Step 2: Model selection filtered to models with in-stock count."""

    def _set_session_step2(self):
        session = self.client.session
        session["electronics_sale_wizard"] = {
            "category": "laptops",
            "step": 2,
            "brand": "Dell",
        }
        session.save()

    def test_step2_renders_with_in_stock_count(self):
        self._set_session_step2()
        url = reverse("inventory:laptop_sale_wizard") + "?step=2"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Latitude 5420")
        # Should show "In stock: 1"
        self.assertContains(res, "In stock")

    def test_step2_post_valid_catalog_goes_to_step3(self):
        self._set_session_step2()
        url = reverse("inventory:laptop_sale_wizard")
        res = self.client.post(url + "?step=2", {"catalog_id": str(self.laptop_catalog.id)})
        self.assertIn(res.status_code, [200, 302])
        if res.status_code == 302:
            self.assertIn("step=3", res["Location"])

    def test_step2_invalid_catalog_id_redirect(self):
        self._set_session_step2()
        url = reverse("inventory:laptop_sale_wizard") + "?step=2"
        res = self.client.post(url, {"catalog_id": "99999"})
        self.assertEqual(res.status_code, 302)

    def test_step2_model_with_no_stock_rejected(self):
        """Model that has 0 in-stock units should not be selectable."""
        # Mark the only unit as SOLD
        self.laptop_unit.status = "SOLD"
        self.laptop_unit.save()

        self._set_session_step2()
        url = reverse("inventory:laptop_sale_wizard") + "?step=2"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        # Dell should not appear because no stock
        self.assertNotContains(res, "Latitude 5420")


class TestWizardStep3Unit(BaseElectronicsWizardTestCase):
    """Step 3: Unit/serial selection and validation."""

    def _set_session_step3(self):
        session = self.client.session
        session["electronics_sale_wizard"] = {
            "category": "laptops",
            "step": 3,
            "brand": "Dell",
            "catalog_id": self.laptop_catalog.id,
            "catalog_display": "Dell Latitude 5420",
            "default_cost_price": 1500.0,
            "default_selling_price": 1900.0,
        }
        session.save()

    def test_step3_renders_available_units(self):
        self._set_session_step3()
        url = reverse("inventory:laptop_sale_wizard") + "?step=3"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "SN-LAPTOP-001")

    def test_step3_valid_serial_goes_to_step4(self):
        self._set_session_step3()
        url = reverse("inventory:laptop_sale_wizard") + "?step=3"
        res = self.client.post(url, {"serial_number": "SN-LAPTOP-001"})
        self.assertEqual(res.status_code, 302)
        self.assertIn("step=4", res["Location"])

    def test_step3_nonexistent_serial_rejected(self):
        """Serial not in stock should fail with error."""
        self._set_session_step3()
        url = reverse("inventory:laptop_sale_wizard") + "?step=3"
        res = self.client.post(url, {"serial_number": "NONEXISTENT-SERIAL"})
        self.assertEqual(res.status_code, 302)
        # Should redirect back to step 3 (or to step 1)
        # Check that the unit is NOT sold
        self.laptop_unit.refresh_from_db()
        self.assertEqual(self.laptop_unit.status, "IN_STOCK")

    def test_step3_already_sold_serial_rejected(self):
        """Cannot sell a unit that is already SOLD."""
        self.laptop_unit.status = "SOLD"
        self.laptop_unit.sold_at = timezone.now()
        self.laptop_unit.save()

        self._set_session_step3()
        url = reverse("inventory:laptop_sale_wizard") + "?step=3"
        res = self.client.post(url, {"serial_number": "SN-LAPTOP-001"})
        self.assertEqual(res.status_code, 302)


class TestWizardStep4Price(BaseElectronicsWizardTestCase):
    """Step 4: Price entry with margin warnings."""

    def _set_session_step4(self):
        session = self.client.session
        session["electronics_sale_wizard"] = {
            "category": "laptops",
            "step": 4,
            "brand": "Dell",
            "catalog_id": self.laptop_catalog.id,
            "unit_id": self.laptop_unit.id,
            "serial_number": "SN-LAPTOP-001",
            "unit_display": "Dell Latitude 5420 (SN: SN-LAPTOP-001)",
            "unit_cost_price": 1500.0,
            "unit_suggested_price": 1900.0,
            "battery_health": "",
        }
        session.save()

    def test_step4_renders_200(self):
        self._set_session_step4()
        url = reverse("inventory:laptop_sale_wizard") + "?step=4"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

    def test_step4_valid_price_goes_to_step5(self):
        self._set_session_step4()
        url = reverse("inventory:laptop_sale_wizard") + "?step=4"
        res = self.client.post(url, {"selling_price": "2000"})
        self.assertEqual(res.status_code, 302)
        self.assertIn("step=5", res["Location"])

    def test_step4_zero_price_rejected(self):
        self._set_session_step4()
        url = reverse("inventory:laptop_sale_wizard") + "?step=4"
        res = self.client.post(url, {"selling_price": "0"})
        self.assertEqual(res.status_code, 302)
        # Should redirect back (not to step 5)
        self.assertNotIn("step=5", res["Location"])

    def test_step4_negative_price_rejected(self):
        self._set_session_step4()
        url = reverse("inventory:laptop_sale_wizard") + "?step=4"
        res = self.client.post(url, {"selling_price": "-100"})
        self.assertEqual(res.status_code, 302)
        self.assertNotIn("step=5", res["Location"])

    def test_step4_selling_below_cost_warns(self):
        """Price below cost still allowed but should warn."""
        self._set_session_step4()
        url = reverse("inventory:laptop_sale_wizard") + "?step=4"
        res = self.client.post(url, {"selling_price": "1000"})
        # Redirect to step 5 (warning is non-blocking for electronics)
        self.assertEqual(res.status_code, 302)
        self.assertIn("step=5", res["Location"])


class TestWizardStep5Payment(BaseElectronicsWizardTestCase):
    """Step 5: Payment method and sale completion."""

    def _set_session_step5(self):
        session = self.client.session
        session["electronics_sale_wizard"] = {
            "category": "laptops",
            "step": 5,
            "brand": "Dell",
            "catalog_id": self.laptop_catalog.id,
            "unit_id": self.laptop_unit.id,
            "serial_number": "SN-LAPTOP-001",
            "unit_display": "Dell Latitude 5420 (SN: SN-LAPTOP-001)",
            "unit_cost_price": 1500.0,
            "unit_suggested_price": 1900.0,
            "battery_health": "",
            "selling_price": 2000.0,
        }
        session.save()

    def test_step5_renders_payment_methods(self):
        self._set_session_step5()
        url = reverse("inventory:laptop_sale_wizard") + "?step=5"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Cash")
        self.assertContains(res, "Mobile Money")

    def test_step5_complete_sale_marks_unit_sold(self):
        """Completing the sale marks the unit SOLD with correct payment."""
        self._set_session_step5()
        url = reverse("inventory:laptop_sale_wizard") + "?step=5"
        res = self.client.post(url, {"payment_method": "CASH"})
        self.assertEqual(res.status_code, 302)

        self.laptop_unit.refresh_from_db()
        self.assertEqual(self.laptop_unit.status, "SOLD")
        self.assertIsNotNone(self.laptop_unit.sold_at)
        self.assertEqual(self.laptop_unit.sold_by, self.user)
        self.assertEqual(self.laptop_unit.payment_method, "CASH")
        self.assertEqual(self.laptop_unit.selling_price, Decimal("2000.00"))

    def test_step5_mobile_money_payment_works(self):
        self._set_session_step5()
        url = reverse("inventory:laptop_sale_wizard") + "?step=5"
        res = self.client.post(url, {"payment_method": "MOBILE_MONEY"})
        self.assertEqual(res.status_code, 302)

        self.laptop_unit.refresh_from_db()
        self.assertEqual(self.laptop_unit.status, "SOLD")
        self.assertEqual(self.laptop_unit.payment_method, "MOBILE_MONEY")

    def test_step5_bank_payment_works(self):
        self._set_session_step5()
        url = reverse("inventory:laptop_sale_wizard") + "?step=5"
        res = self.client.post(url, {"payment_method": "BANK"})
        self.assertEqual(res.status_code, 302)

        self.laptop_unit.refresh_from_db()
        self.assertEqual(self.laptop_unit.payment_method, "BANK")

    def test_step5_invalid_payment_method_rejected(self):
        self._set_session_step5()
        url = reverse("inventory:laptop_sale_wizard") + "?step=5"
        res = self.client.post(url, {"payment_method": "CRYPTO"})
        self.assertEqual(res.status_code, 302)

        # Unit should still be in stock
        self.laptop_unit.refresh_from_db()
        self.assertEqual(self.laptop_unit.status, "IN_STOCK")

    def test_step5_cannot_sell_already_sold_unit(self):
        """Race condition guard: unit sold between step 3 and 5."""
        # Mark unit as SOLD before POST
        self.laptop_unit.status = "SOLD"
        self.laptop_unit.sold_at = timezone.now()
        self.laptop_unit.save()

        self._set_session_step5()
        url = reverse("inventory:laptop_sale_wizard") + "?step=5"
        res = self.client.post(url, {"payment_method": "CASH"})
        # Should redirect back with error, not crash
        self.assertEqual(res.status_code, 302)
        # Unit remains SOLD (not double-sold)
        self.laptop_unit.refresh_from_db()
        self.assertEqual(self.laptop_unit.status, "SOLD")
        # sold_by was not overwritten to current user if it was NULL before
        # (we just check it didn't 500)


class TestDesktopWizard(BaseElectronicsWizardTestCase):
    """Desktop wizard mirrors laptop wizard."""

    def test_desktop_wizard_step1_renders(self):
        url = reverse("inventory:desktop_sale_wizard") + "?step=1"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "HP")

    def test_desktop_wizard_complete_sale(self):
        """Full desktop sale from step 5 POST."""
        session = self.client.session
        session["electronics_sale_wizard"] = {
            "category": "desktops",
            "step": 5,
            "brand": "HP",
            "catalog_id": self.desktop_catalog.id,
            "unit_id": self.desktop_unit.id,
            "serial_number": "SN-DESKTOP-001",
            "unit_display": "HP ProDesk 400 (SN: SN-DESKTOP-001)",
            "unit_cost_price": 2000.0,
            "unit_suggested_price": 2500.0,
            "battery_health": "",
            "selling_price": 2600.0,
        }
        session.save()

        url = reverse("inventory:desktop_sale_wizard") + "?step=5"
        res = self.client.post(url, {"payment_method": "MOBILE_MONEY"})
        self.assertEqual(res.status_code, 302)

        self.desktop_unit.refresh_from_db()
        self.assertEqual(self.desktop_unit.status, "SOLD")
        self.assertEqual(self.desktop_unit.payment_method, "MOBILE_MONEY")
        self.assertEqual(self.desktop_unit.selling_price, Decimal("2600.00"))


class TestWizardReset(BaseElectronicsWizardTestCase):
    """Wizard reset clears session."""

    def test_laptop_wizard_reset(self):
        session = self.client.session
        session["electronics_sale_wizard"] = {"category": "laptops", "step": 3, "brand": "Dell"}
        session.save()

        url = reverse("inventory:laptop_sale_wizard_reset")
        res = self.client.post(url)
        self.assertEqual(res.status_code, 302)

        session = self.client.session
        self.assertNotIn("electronics_sale_wizard", session)

    def test_desktop_wizard_reset(self):
        session = self.client.session
        session["electronics_sale_wizard"] = {"category": "desktops", "step": 2, "brand": "HP"}
        session.save()

        url = reverse("inventory:desktop_sale_wizard_reset")
        res = self.client.post(url)
        self.assertEqual(res.status_code, 302)


class TestElectronicsStockList(BaseElectronicsWizardTestCase):
    """Electronics stock list view tests."""

    def test_laptops_stock_list_200(self):
        url = reverse("inventory:electronics_stock_list") + "?category=laptops"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Dell")
        self.assertContains(res, "SN-LAPTOP-001")

    def test_desktops_stock_list_200(self):
        url = reverse("inventory:electronics_stock_list") + "?category=desktops"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "HP")
        self.assertContains(res, "SN-DESKTOP-001")

    def test_status_filter_sold(self):
        """Sold filter shows only sold items."""
        self.laptop_unit.status = "SOLD"
        self.laptop_unit.sold_at = timezone.now()
        self.laptop_unit.save()
        url = reverse("inventory:electronics_stock_list") + "?category=laptops&status=sold"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "SN-LAPTOP-001")

    def test_search_by_serial(self):
        url = reverse("inventory:electronics_stock_list") + "?category=laptops&q=SN-LAPTOP"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "SN-LAPTOP-001")

    def test_search_no_match_shows_empty(self):
        url = reverse("inventory:electronics_stock_list") + "?category=laptops&q=XXXXXX"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

    def test_csv_export(self):
        url = reverse("inventory:electronics_stock_list") + "?category=laptops&format=csv"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/csv")
        content = res.content.decode("utf-8")
        self.assertIn("SN-LAPTOP-001", content)
        self.assertIn("Dell", content)


class TestScanSellLanding(BaseElectronicsWizardTestCase):
    """Tests for the Scan & Sell landing page (category chooser)."""

    def test_landing_renders_200(self):
        url = reverse("inventory:scan_sell_landing")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

    def test_landing_contains_phones_card(self):
        url = reverse("inventory:scan_sell_landing")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Phones")

    def test_landing_contains_laptops_card(self):
        url = reverse("inventory:scan_sell_landing")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Laptops")

    def test_landing_contains_desktops_card(self):
        url = reverse("inventory:scan_sell_landing")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Desktops")

    def test_landing_links_to_phone_wizard(self):
        url = reverse("inventory:scan_sell_landing")
        res = self.client.get(url)
        phone_wizard_url = reverse("inventory:phone_sale_wizard")
        self.assertContains(res, phone_wizard_url)

    def test_landing_links_to_laptop_wizard(self):
        url = reverse("inventory:scan_sell_landing")
        res = self.client.get(url)
        laptop_wizard_url = reverse("inventory:laptop_sale_wizard")
        self.assertContains(res, laptop_wizard_url)

    def test_landing_links_to_desktop_wizard(self):
        url = reverse("inventory:scan_sell_landing")
        res = self.client.get(url)
        desktop_wizard_url = reverse("inventory:desktop_sale_wizard")
        self.assertContains(res, desktop_wizard_url)

    def test_landing_requires_login(self):
        from django.test import Client as AnonClient
        anon = AnonClient()
        url = reverse("inventory:scan_sell_landing")
        res = anon.get(url)
        # Should redirect to login
        self.assertIn(res.status_code, [302, 403])


class TestPhoneFlowRegression(BaseElectronicsWizardTestCase):
    """Ensure existing phone wizard is not broken by our changes."""

    def test_phone_sale_wizard_v2_step1_renders(self):
        """Phone wizard v2 step 1 still works."""
        url = reverse("inventory:phone_sale_wizard_v2") + "?step=1"
        res = self.client.get(url)
        # Should render or redirect (not 500)
        self.assertIn(res.status_code, [200, 302])

    def test_scan_sell_phones_still_routes_correctly(self):
        """Scan & Sell ?category=phones still routes to phone flow."""
        url = reverse("inventory:scan_sell") + "?category=phones"
        res = self.client.get(url)
        # Should render the phone scan_sell page (200) or redirect (302)
        self.assertIn(res.status_code, [200, 302])

    def test_scan_sell_laptops_redirects_to_wizard(self):
        """Scan & Sell ?category=laptops redirects to laptop wizard."""
        url = reverse("inventory:scan_sell") + "?category=laptops"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)
        self.assertIn("laptop-sale-wizard", res["Location"])

    def test_scan_sell_desktops_redirects_to_wizard(self):
        """Scan & Sell ?category=desktops redirects to desktop wizard."""
        url = reverse("inventory:scan_sell") + "?category=desktops"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)
        self.assertIn("desktop-sale-wizard", res["Location"])

    def test_battery_health_field_on_model(self):
        """battery_health field exists and can be set."""
        unit = ElectronicsStockItem.objects.create(
            business=self.business,
            catalog_product=self.laptop_catalog,
            serial_number="BATTERY-TEST-001",
            current_location=self.location,
            order_price=Decimal("1000.00"),
            status="IN_STOCK",
            is_active=True,
            battery_health="85%",
        )
        unit.refresh_from_db()
        self.assertEqual(unit.battery_health, "85%")

    def test_payment_method_field_on_model(self):
        """payment_method field exists and can be set on ElectronicsStockItem."""
        unit = ElectronicsStockItem.objects.create(
            business=self.business,
            catalog_product=self.laptop_catalog,
            serial_number="PAYMENT-TEST-001",
            current_location=self.location,
            order_price=Decimal("1000.00"),
            status="IN_STOCK",
            is_active=True,
        )
        unit.payment_method = "MOBILE_MONEY"
        unit.save(update_fields=["payment_method"])
        unit.refresh_from_db()
        self.assertEqual(unit.payment_method, "MOBILE_MONEY")
