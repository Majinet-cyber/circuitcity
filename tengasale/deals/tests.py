from decimal import Decimal
from importlib import import_module

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import DeviceBrand, DeviceDeal


class DealUrlTests(TestCase):
    def test_all_deals_url_name_resolves(self):
        self.assertEqual(reverse("all_deals"), "/deals/")


class DealAdminImportTests(TestCase):
    def test_importing_deals_admin_does_not_create_model_conflicts(self):
        admin_module = import_module("deals.admin")

        self.assertIs(admin_module.DeviceBrand, DeviceBrand)
        self.assertIs(admin_module.DeviceDeal, DeviceDeal)

    def test_device_models_are_registered_in_admin(self):
        self.assertIn(DeviceBrand, admin.site._registry)
        self.assertIn(DeviceDeal, admin.site._registry)


class DeviceDealModelTests(TestCase):
    def make_deal(self, **overrides):
        brand = overrides.pop("brand", None) or DeviceBrand.objects.filter(name="TECNO").first()
        if brand is None:
            brand = DeviceBrand.objects.create(name="TECNO")
        data = {
            "brand": brand,
            "model_name": "Pop 10C",
            "specs": "2+64",
            "min_cash_price": Decimal("320000.00"),
            "max_cash_price": Decimal("380000.00"),
            "default_cash_price": Decimal("350000.00"),
            "cash_price": Decimal("350000.00"),
            "deposit_percent": Decimal("13.00"),
            "loan_multiplier": Decimal("2.50"),
            "term_months": 12,
            "total_12_month_price": Decimal("875000.00"),
        }
        data.update(overrides)
        return DeviceDeal(**data)

    def test_device_brand_can_be_created(self):
        brand = DeviceBrand.objects.create(name="Tenga")

        self.assertEqual(str(brand), "Tenga")

    def test_deposit_percent_below_13_is_invalid(self):
        deal = self.make_deal(deposit_percent=Decimal("12.99"))

        with self.assertRaises(ValidationError):
            deal.full_clean()

    def test_deposit_percent_above_16_is_invalid(self):
        deal = self.make_deal(deposit_percent=Decimal("16.01"))

        with self.assertRaises(ValidationError):
            deal.full_clean()

    def test_deposit_percent_13_and_16_are_valid(self):
        for percent in [Decimal("13.00"), Decimal("16.00")]:
            deal = self.make_deal(deposit_percent=percent)
            deal.full_clean()

    def test_default_cash_price_must_be_between_min_and_max(self):
        deal = self.make_deal(default_cash_price=Decimal("390000.00"))

        with self.assertRaises(ValidationError):
            deal.full_clean()

    def test_device_deal_calculates_prices_from_selected_cash_price(self):
        deal = self.make_deal()

        selected_cash_price = Decimal("400000.00")

        self.assertEqual(deal.calculated_total_loan(selected_cash_price), Decimal("1000000.00"))
        self.assertEqual(deal.calculated_deposit(selected_cash_price), Decimal("130000.00"))
        self.assertEqual(deal.calculated_monthly_payment(selected_cash_price), Decimal("83333.33"))
        self.assertEqual(deal.calculated_daily_payment(selected_cash_price), Decimal("2777.78"))
        self.assertEqual(deal.calculated_6_month_total(selected_cash_price), Decimal("850000.00"))
        self.assertEqual(deal.calculated_6_month_monthly(selected_cash_price), Decimal("141666.67"))
        self.assertEqual(deal.calculated_6_month_daily(selected_cash_price), Decimal("4722.22"))
        self.assertEqual(deal.calculated_3_month_total(selected_cash_price), Decimal("750000.00"))
        self.assertEqual(deal.calculated_3_month_monthly(selected_cash_price), Decimal("250000.00"))
        self.assertEqual(deal.calculated_3_month_daily(selected_cash_price), Decimal("8333.33"))


class SeedTengaSaleCommandTests(TestCase):
    def test_seed_tengasale_creates_required_brands_and_deals(self):
        call_command("seed_tengasale")

        for brand_name in ["TECNO", "itel", "Redmi"]:
            brand = DeviceBrand.objects.get(name=brand_name)
            self.assertTrue(DeviceDeal.objects.filter(brand=brand).exists())

    def test_seed_tengasale_is_idempotent(self):
        call_command("seed_tengasale")
        first_brand_count = DeviceBrand.objects.count()
        first_deal_count = DeviceDeal.objects.count()

        call_command("seed_tengasale")

        self.assertEqual(DeviceBrand.objects.count(), first_brand_count)
        self.assertEqual(DeviceDeal.objects.count(), first_deal_count)
