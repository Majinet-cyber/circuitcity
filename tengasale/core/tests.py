from decimal import Decimal
from importlib import import_module

from django.contrib import admin
from django.test import TestCase

from .models import BusinessSetting
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
