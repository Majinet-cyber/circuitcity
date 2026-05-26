from decimal import Decimal
from datetime import datetime
from importlib import import_module
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.test import TestCase

from .models import BusinessSetting
from .business_hours import is_business_hours
from .services import get_business_settings


class BusinessSettingTests(TestCase):
    def test_get_business_settings_creates_defaults(self):
        settings = get_business_settings()

        self.assertEqual(settings.merchant_commission_percent, Decimal("1.00"))
        self.assertEqual(settings.manager_commission_percent, Decimal("3.00"))
        self.assertEqual(settings.loan_multiplier, Decimal("2.50"))
        self.assertTrue(settings.spin_enabled)

    def test_admin_imports_do_not_crash(self):
        admin_module = import_module("core.admin")

        self.assertIs(admin_module.BusinessSetting, BusinessSetting)
        self.assertIn(BusinessSetting, admin.site._registry)


class BusinessHoursTests(TestCase):
    zone = ZoneInfo("Africa/Blantyre")

    def test_weekday_10_is_business_hours(self):
        self.assertTrue(is_business_hours(datetime(2026, 5, 25, 10, 0, tzinfo=self.zone)))

    def test_weekday_20_is_outside_business_hours(self):
        self.assertFalse(is_business_hours(datetime(2026, 5, 25, 20, 0, tzinfo=self.zone)))

    def test_saturday_10_is_business_hours(self):
        self.assertTrue(is_business_hours(datetime(2026, 5, 23, 10, 0, tzinfo=self.zone)))

    def test_saturday_18_is_outside_business_hours(self):
        self.assertFalse(is_business_hours(datetime(2026, 5, 23, 18, 0, tzinfo=self.zone)))

    def test_sunday_is_outside_business_hours(self):
        self.assertFalse(is_business_hours(datetime(2026, 5, 24, 10, 0, tzinfo=self.zone)))
