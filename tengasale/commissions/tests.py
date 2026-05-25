from decimal import Decimal
from importlib import import_module

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from applications.models import FinancingApplication
from core.models import BusinessSetting
from rewards.models import SpinWallet

from .models import Commission
from .services import process_application_approval


class CommissionApprovalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.merchant = User.objects.create_user(username="merchant", password="test-pass-123")
        self.manager = User.objects.create_user(username="manager", password="test-pass-123")

    def create_application(self, **overrides):
        data = {
            "created_by": self.merchant,
            "status": "under_review",
            "claimed_by": self.manager,
            "calculated_total_loan": Decimal("1000000.00"),
        }
        data.update(overrides)
        return FinancingApplication.objects.create(**data)

    def test_approving_application_creates_default_commissions_and_spin(self):
        app = self.create_application()

        result = process_application_approval(app, approved_by=self.manager)

        merchant_commission = Commission.objects.get(application=app, role=Commission.ROLE_MERCHANT)
        manager_commission = Commission.objects.get(application=app, role=Commission.ROLE_MANAGER)
        wallet = SpinWallet.objects.get(user=self.merchant)

        self.assertEqual(result["sale_amount"], Decimal("1000000.00"))
        self.assertEqual(merchant_commission.commission_percent, Decimal("1.00"))
        self.assertEqual(merchant_commission.amount, Decimal("10000.00"))
        self.assertEqual(manager_commission.commission_percent, Decimal("3.00"))
        self.assertEqual(manager_commission.amount, Decimal("30000.00"))
        self.assertEqual(wallet.available_spins, 1)
        self.assertEqual(wallet.total_spins_earned, 1)

    def test_changed_business_settings_affect_new_commissions(self):
        BusinessSetting.objects.update_or_create(
            pk=1,
            defaults={
                "merchant_commission_percent": Decimal("2.50"),
                "manager_commission_percent": Decimal("4.00"),
            },
        )
        app = self.create_application()

        process_application_approval(app, approved_by=self.manager)

        self.assertEqual(
            Commission.objects.get(application=app, role=Commission.ROLE_MERCHANT).amount,
            Decimal("25000.00"),
        )
        self.assertEqual(
            Commission.objects.get(application=app, role=Commission.ROLE_MANAGER).amount,
            Decimal("40000.00"),
        )

    def test_duplicate_approval_does_not_duplicate_commissions_or_spin(self):
        app = self.create_application()

        process_application_approval(app, approved_by=self.manager)
        process_application_approval(app, approved_by=self.manager)

        self.assertEqual(Commission.objects.filter(application=app).count(), 2)
        wallet = SpinWallet.objects.get(user=self.merchant)
        self.assertEqual(wallet.available_spins, 1)
        self.assertEqual(wallet.total_spins_earned, 1)

    def test_approval_view_creates_commissions(self):
        app = self.create_application()
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.post(reverse("review_application", args=[app.id]), {"decision": "approve"})

        app.refresh_from_db()
        self.assertRedirects(response, reverse("manager_home"))
        self.assertEqual(app.status, "approved")
        self.assertEqual(Commission.objects.filter(application=app).count(), 2)


class CommissionAdminImportTests(TestCase):
    def test_admin_imports_do_not_crash(self):
        admin_module = import_module("commissions.admin")

        self.assertIs(admin_module.Commission, Commission)
        self.assertIn(Commission, admin.site._registry)
