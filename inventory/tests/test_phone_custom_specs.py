"""
Tests for custom Storage + RAM spec support on the Add Phone Product form.

Covers:
1. Preset spec 128+4 can be saved.
2. Custom spec 128+6 can be saved.
3. Custom spec 512+12 can be saved.
4. Custom spec 256+12 can be saved.
5. Custom spec 64+4 can be saved.
6. Spec with GB suffix (128GB+6GB) normalises to 128+6.
7. Spec with TB notation (1TB+16) is accepted.
8. Blank spec is rejected with a friendly error.
9. POST with valid spec creates a PhoneProductCatalog entry.
10. Existing products with old preset specs still load the page without error.
11. _parse_phone_specs helper: valid inputs.
12. _parse_phone_specs helper: invalid input raises ValueError.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tenants.models import Business, Membership
from inventory.models_phone_products import PhoneProductCatalog, ElectronicsCategory
from inventory.views_phone_products import _parse_phone_specs

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_phones_business(slug="test-custom-specs"):
    return Business.objects.create(
        name="Custom Specs Phone Shop",
        slug=slug,
        status="ACTIVE",
        business_kind="phones",
    )


def _make_manager(business, username="mgr_custom"):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        password="TestPass123!@#",
        is_staff=True,
    )
    Membership.objects.create(user=user, business=business, role="MANAGER", status="ACTIVE")
    return user


# ---------------------------------------------------------------------------
# Unit tests for _parse_phone_specs helper
# ---------------------------------------------------------------------------

class ParsePhoneSpecsTest(TestCase):
    """Unit tests for the _parse_phone_specs parsing helper."""

    def _parse(self, s):
        return _parse_phone_specs(s)

    # --- valid formats ---

    def test_simple_128_4(self):
        rom, ram, label = self._parse("128+4")
        self.assertEqual(rom, 128)
        self.assertEqual(ram, 4)
        self.assertEqual(label, "128+4")

    def test_custom_128_6(self):
        rom, ram, label = self._parse("128+6")
        self.assertEqual(rom, 128)
        self.assertEqual(ram, 6)
        self.assertEqual(label, "128+6")

    def test_custom_256_12(self):
        rom, ram, label = self._parse("256+12")
        self.assertEqual(rom, 256)
        self.assertEqual(ram, 12)
        self.assertEqual(label, "256+12")

    def test_custom_512_12(self):
        rom, ram, label = self._parse("512+12")
        self.assertEqual(rom, 512)
        self.assertEqual(ram, 12)
        self.assertEqual(label, "512+12")

    def test_custom_64_4(self):
        rom, ram, label = self._parse("64+4")
        self.assertEqual(rom, 64)
        self.assertEqual(ram, 4)
        self.assertEqual(label, "64+4")

    def test_gb_suffix_stripped(self):
        rom, ram, label = self._parse("128GB+6GB")
        self.assertEqual(rom, 128)
        self.assertEqual(ram, 6)
        self.assertEqual(label, "128+6")

    def test_gb_suffix_mixed_case(self):
        rom, ram, label = self._parse("256gb+8gb")
        self.assertEqual(rom, 256)
        self.assertEqual(ram, 8)

    def test_spaces_around_plus(self):
        rom, ram, label = self._parse("128 + 4")
        self.assertEqual(rom, 128)
        self.assertEqual(ram, 4)

    def test_tb_notation(self):
        rom, ram, label = self._parse("1TB+16")
        self.assertEqual(rom, 1000)
        self.assertEqual(ram, 16)
        self.assertEqual(label, "1000+16")

    def test_slash_separator(self):
        """Slash separator (ROM/RAM) should also work."""
        rom, ram, label = self._parse("128/4")
        self.assertEqual(rom, 128)
        self.assertEqual(ram, 4)

    def test_preset_32_2(self):
        rom, ram, label = self._parse("32+2")
        self.assertEqual(rom, 32)
        self.assertEqual(ram, 2)

    def test_preset_512_8(self):
        rom, ram, label = self._parse("512+8")
        self.assertEqual(rom, 512)
        self.assertEqual(ram, 8)

    # --- invalid formats ---

    def test_blank_raises(self):
        with self.assertRaises(ValueError):
            self._parse("")

    def test_whitespace_only_raises(self):
        with self.assertRaises(ValueError):
            self._parse("   ")

    def test_no_plus_raises(self):
        with self.assertRaises(ValueError):
            self._parse("128")

    def test_alpha_garbage_raises(self):
        with self.assertRaises(ValueError):
            self._parse("abc+xyz")

    def test_zero_rom_raises(self):
        with self.assertRaises(ValueError):
            self._parse("0+4")

    def test_zero_ram_raises(self):
        with self.assertRaises(ValueError):
            self._parse("128+0")


# ---------------------------------------------------------------------------
# Integration tests: POST to /inventory/phone-products/
# ---------------------------------------------------------------------------

class AddPhoneProductCustomSpecsTest(TestCase):
    """Tests that POSTing to add_phone_products saves custom specs correctly."""

    def setUp(self):
        self.business = _make_phones_business()
        self.user = _make_manager(self.business)
        self.client.login(username="mgr_custom", password="TestPass123!@#")
        session = self.client.session
        session["active_business_id"] = self.business.id
        session.save()
        self.url = reverse("inventory:phone_products")

    def _post(self, specs, model_name="Test Model", brand="tecno"):
        return self.client.post(self.url, {
            "brand": brand,
            "model_name": model_name,
            "model_number": "",
            "specs": specs,
            "order_price": "",
        })

    # --- preset specs still work ---

    def test_preset_128_4_saved(self):
        resp = self._post("128+4", model_name="Tecno Spark Preset")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            PhoneProductCatalog.objects.filter(
                business=self.business, rom_gb=128, ram_gb=4
            ).exists()
        )

    def test_preset_256_8_saved(self):
        resp = self._post("256+8", model_name="Tecno Spark 256")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            PhoneProductCatalog.objects.filter(
                business=self.business, rom_gb=256, ram_gb=8
            ).exists()
        )

    # --- new presets ---

    def test_custom_128_6_saved(self):
        resp = self._post("128+6", model_name="Samsung A15 128-6")
        self.assertEqual(resp.status_code, 302)
        product = PhoneProductCatalog.objects.get(
            business=self.business, rom_gb=128, ram_gb=6
        )
        self.assertEqual(product.variant_label, "128+6")

    def test_custom_64_4_saved(self):
        resp = self._post("64+4", model_name="Itel Budget 64-4")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            PhoneProductCatalog.objects.filter(
                business=self.business, rom_gb=64, ram_gb=4
            ).exists()
        )

    def test_custom_256_12_saved(self):
        resp = self._post("256+12", model_name="Samsung A35 256-12", brand="samsung")
        self.assertEqual(resp.status_code, 302)
        product = PhoneProductCatalog.objects.get(
            business=self.business, rom_gb=256, ram_gb=12
        )
        self.assertEqual(product.variant_label, "256+12")

    def test_custom_512_12_saved(self):
        resp = self._post("512+12", model_name="Flagship 512-12", brand="samsung")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            PhoneProductCatalog.objects.filter(
                business=self.business, rom_gb=512, ram_gb=12
            ).exists()
        )

    def test_gb_suffix_normalised(self):
        """128GB+6GB should save as rom=128, ram=6."""
        resp = self._post("128GB+6GB", model_name="GB Suffix Model")
        self.assertEqual(resp.status_code, 302)
        product = PhoneProductCatalog.objects.get(
            business=self.business, rom_gb=128, ram_gb=6,
            model_name="GB Suffix Model",
        )
        self.assertEqual(product.variant_label, "128+6")

    # --- blank spec rejected ---

    def test_blank_spec_rejected(self):
        resp = self._post("", model_name="No Spec Model")
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            PhoneProductCatalog.objects.filter(
                business=self.business, model_name="No Spec Model"
            ).exists()
        )

    def test_invalid_spec_rejected(self):
        resp = self._post("badformat", model_name="Bad Spec Model")
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            PhoneProductCatalog.objects.filter(
                business=self.business, model_name="Bad Spec Model"
            ).exists()
        )

    # --- existing product loads page without error ---

    def test_page_loads_with_existing_preset_products(self):
        """Existing products with preset specs must not break the add page."""
        PhoneProductCatalog.objects.create(
            business=self.business,
            category=ElectronicsCategory.PHONE,
            brand="TECNO",
            model_name="Spark 10C",
            ram_gb=4,
            rom_gb=128,
            variant_label="128+4",
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_variant_label_stored_for_custom_spec(self):
        """variant_label should store the normalised custom spec string."""
        self._post("512+12", model_name="Flagship X", brand="samsung")
        product = PhoneProductCatalog.objects.get(
            business=self.business, model_name="Flagship X"
        )
        self.assertEqual(product.variant_label, "512+12")
