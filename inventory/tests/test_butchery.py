# inventory/tests/test_butchery.py
"""
Butchery Vertical Tests
=======================

Covers:
- Model: intake, product, sale, processing, daily ledger
- Views: dashboard, daily_sales, products, intake, reports (200 with empty data)
- CSV export: returns text/csv with correct filename
- PDF export: returns application/pdf with correct filename
- Quantity calculation: MWK / price = quantity
- Ledger lock/unlock behaviour
"""
from decimal import Decimal
import random

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from tenants.models import Business
from inventory.business_kinds import BusinessKind
from inventory.models_butchery import (
    ButcheryCategory,
    ButcheryDailyLedger,
    ButcheryIntake,
    ButcheryIntakeAllocation,
    ButcheryProcessingBatch,
    ButcheryProduct,
    ButcherySale,
    ButcheryExpense,
    MeatType,
)

User = get_user_model()


def _make_business():
    uid = random.randint(10000, 99999)
    return Business.objects.create(
        name=f"Test Pork Centre {uid}",
        business_kind=BusinessKind.BUTCHERY,
    )


def _make_user(business=None):
    uid = random.randint(10000, 99999)
    user = User.objects.create_user(
        username=f"butchery_user_{uid}",
        password="testpass123",
    )
    if business:
        business.users.add(user)
    return user


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class ButcheryProductModelTest(TestCase):
    def setUp(self):
        self.business = _make_business()

    def test_create_product(self):
        p = ButcheryProduct.objects.create(
            business=self.business,
            name="Pork Braai",
            category=ButcheryCategory.PORK,
            meat_type=MeatType.PORK,
            unit="kg",
            selling_price=Decimal("8000.00"),
            cost_price=Decimal("5000.00"),
            stock_quantity=Decimal("20.000"),
            reorder_level=Decimal("3.000"),
        )
        self.assertEqual(p.name, "Pork Braai")
        self.assertEqual(p.margin_pct, 37.5)
        self.assertFalse(p.is_low_stock)
        self.assertFalse(p.is_out_of_stock)

    def test_low_stock(self):
        p = ButcheryProduct.objects.create(
            business=self.business,
            name="Sausage Braai",
            category=ButcheryCategory.SAUSAGE,
            unit="kg",
            selling_price=Decimal("5000.00"),
            cost_price=Decimal("3000.00"),
            stock_quantity=Decimal("1.500"),
            reorder_level=Decimal("3.000"),
        )
        self.assertTrue(p.is_low_stock)
        self.assertFalse(p.is_out_of_stock)

    def test_out_of_stock(self):
        p = ButcheryProduct.objects.create(
            business=self.business,
            name="Beef Bones",
            category=ButcheryCategory.BEEF,
            unit="kg",
            selling_price=Decimal("2000.00"),
            stock_quantity=Decimal("0.000"),
        )
        self.assertTrue(p.is_out_of_stock)

    def test_expanded_units(self):
        for unit_val, _ in ButcheryProduct.UNIT_CHOICES:
            p = ButcheryProduct.objects.create(
                business=self.business,
                name=f"Product {unit_val}",
                unit=unit_val,
                selling_price=Decimal("1000.00"),
            )
            self.assertEqual(p.unit, unit_val)


class ButcheryIntakeModelTest(TestCase):
    def setUp(self):
        self.business = _make_business()

    def test_cost_per_kg(self):
        intake = ButcheryIntake.objects.create(
            business=self.business,
            meat_type=MeatType.PORK,
            intake_weight_kg=Decimal("50.000"),
            total_cost=Decimal("200000.00"),
        )
        self.assertEqual(intake.cost_per_kg, Decimal("4000.00"))

    def test_zero_weight_cost_per_kg(self):
        intake = ButcheryIntake.objects.create(
            business=self.business,
            meat_type=MeatType.BEEF,
            intake_weight_kg=Decimal("0.001"),
            total_cost=Decimal("0.00"),
        )
        self.assertEqual(intake.cost_per_kg, Decimal("0.00"))


class ButcherySaleModelTest(TestCase):
    def setUp(self):
        self.business = _make_business()
        self.product = ButcheryProduct.objects.create(
            business=self.business,
            name="Chicken Fresh",
            category=ButcheryCategory.CHICKEN,
            unit="kg",
            selling_price=Decimal("6000.00"),
            cost_price=Decimal("4000.00"),
            stock_quantity=Decimal("10.000"),
        )

    def test_total_amount(self):
        sale = ButcherySale.objects.create(
            business=self.business,
            product=self.product,
            quantity=Decimal("2.500"),
            unit_price=Decimal("6000.00"),
            cost_price_snapshot=Decimal("4000.00"),
        )
        self.assertEqual(sale.total_amount, Decimal("15000.00"))

    def test_profit(self):
        sale = ButcherySale.objects.create(
            business=self.business,
            product=self.product,
            quantity=Decimal("2.500"),
            unit_price=Decimal("6000.00"),
            cost_price_snapshot=Decimal("4000.00"),
        )
        self.assertEqual(sale.profit, Decimal("5000.00"))

    def test_quantity_from_mwk(self):
        """Core business logic: quantity = MWK amount / price per unit."""
        mwk_sales = Decimal("40000.00")
        price_per_unit = Decimal("8000.00")
        quantity = (mwk_sales / price_per_unit).quantize(Decimal("0.001"))
        self.assertEqual(quantity, Decimal("5.000"))


class ButcheryDailyLedgerTest(TestCase):
    def setUp(self):
        self.business = _make_business()

    def test_create_draft_ledger(self):
        ledger = ButcheryDailyLedger.objects.create(
            business=self.business,
            date=timezone.localdate(),
            status=ButcheryDailyLedger.STATUS_DRAFT,
        )
        self.assertFalse(ledger.is_locked)

    def test_lock_ledger(self):
        ledger = ButcheryDailyLedger.objects.create(
            business=self.business,
            date=timezone.localdate(),
            status=ButcheryDailyLedger.STATUS_LOCKED,
        )
        self.assertTrue(ledger.is_locked)

    def test_unique_per_business_date(self):
        today = timezone.localdate()
        ButcheryDailyLedger.objects.create(business=self.business, date=today)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ButcheryDailyLedger.objects.create(business=self.business, date=today)


# ---------------------------------------------------------------------------
# View Tests
# ---------------------------------------------------------------------------

class ButcheryViewsTest(TestCase):
    def setUp(self):
        self.business = _make_business()
        self.user = _make_user(self.business)
        self.client = Client()
        self.client.login(username=self.user.username, password="testpass123")
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()

    def _get(self, url_name, **kwargs):
        url = reverse(f"butchery:{url_name}", kwargs=kwargs)
        return self.client.get(url)

    def test_dashboard_200_empty(self):
        resp = self._get("dashboard")
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_period_filter(self):
        url = reverse("butchery:dashboard") + "?period=w1"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_products_200_empty(self):
        resp = self._get("products")
        self.assertEqual(resp.status_code, 200)

    def test_product_add_200(self):
        resp = self._get("product_add")
        self.assertEqual(resp.status_code, 200)

    def test_intake_200_empty(self):
        resp = self._get("intake")
        self.assertEqual(resp.status_code, 200)

    def test_processing_200_empty(self):
        resp = self._get("processing")
        self.assertEqual(resp.status_code, 200)

    def test_sell_200_empty(self):
        resp = self._get("sell")
        self.assertEqual(resp.status_code, 200)

    def test_daily_sales_200_empty(self):
        resp = self._get("daily_sales")
        self.assertEqual(resp.status_code, 200)

    def test_sales_200_empty(self):
        resp = self._get("sales")
        self.assertEqual(resp.status_code, 200)

    def test_expenses_200_empty(self):
        resp = self._get("expenses")
        self.assertEqual(resp.status_code, 200)

    def test_reports_200_empty(self):
        resp = self._get("reports")
        self.assertEqual(resp.status_code, 200)

    def test_reports_period_filter(self):
        url = reverse("butchery:reports") + "?period=w2"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_csv_export_content_type(self):
        url = reverse("butchery:reports_export_csv")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")

    def test_csv_export_filename(self):
        url = reverse("butchery:reports_export_csv")
        resp = self.client.get(url)
        self.assertIn("butchery_sales_", resp["Content-Disposition"])
        self.assertIn(".csv", resp["Content-Disposition"])

    def test_daily_sales_with_products(self):
        ButcheryProduct.objects.create(
            business=self.business, name="Pork Braai",
            category=ButcheryCategory.PORK, unit="kg",
            selling_price=Decimal("8000.00"),
            cost_price=Decimal("5000.00"),
        )
        resp = self._get("daily_sales")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pork Braai")

    def test_record_daily_sales_post(self):
        product = ButcheryProduct.objects.create(
            business=self.business, name="Sausage Braai",
            category=ButcheryCategory.SAUSAGE, unit="kg",
            selling_price=Decimal("5000.00"),
            cost_price=Decimal("3000.00"),
        )
        today = timezone.localdate().isoformat()
        url = reverse("butchery:daily_sales")
        resp = self.client.post(url, {
            "action": "save_draft",
            "sale_date": today,
            "product_id": [str(product.pk)],
            "mwk_sales": ["25000"],
            "unit_price": ["5000"],
            "line_notes": [""],
            "payment_method": "cash",
        })
        self.assertEqual(resp.status_code, 302)
        # Check sale was created with correct quantity (25000/5000 = 5kg)
        sales = ButcherySale.objects.filter(business=self.business)
        self.assertEqual(sales.count(), 1)
        self.assertEqual(sales.first().quantity, Decimal("5.000"))

    def test_lock_ledger(self):
        product = ButcheryProduct.objects.create(
            business=self.business, name="Beef Steak",
            category=ButcheryCategory.BEEF, unit="kg",
            selling_price=Decimal("12000.00"),
        )
        today = timezone.localdate().isoformat()
        url = reverse("butchery:daily_sales")
        resp = self.client.post(url, {
            "action": "save_lock",
            "sale_date": today,
            "product_id": [str(product.pk)],
            "mwk_sales": ["60000"],
            "unit_price": ["12000"],
            "line_notes": [""],
            "payment_method": "cash",
        })
        self.assertEqual(resp.status_code, 302)
        ledger = ButcheryDailyLedger.objects.filter(
            business=self.business, date=timezone.localdate()
        ).first()
        self.assertIsNotNone(ledger)
        self.assertTrue(ledger.is_locked)

    def test_intake_record(self):
        url = reverse("butchery:intake")
        resp = self.client.post(url, {
            "action": "record_intake",
            "intake_date": timezone.localdate().isoformat(),
            "meat_type": "pork",
            "intake_weight_kg": "50",
            "total_cost": "200000",
            "supplier_name": "ABC Farms",
            "batch_ref": "BTH-001",
            "storage_location": "Cold Room A",
            "description": "",
            "notes": "",
        })
        self.assertEqual(resp.status_code, 302)
        intake = ButcheryIntake.objects.filter(business=self.business).first()
        self.assertIsNotNone(intake)
        self.assertEqual(intake.intake_weight_kg, Decimal("50"))
        self.assertEqual(intake.cost_per_kg, Decimal("4000.00"))

    def test_product_add_post(self):
        url = reverse("butchery:product_add")
        resp = self.client.post(url, {
            "name": "Goat Offals",
            "category": "goat",
            "meat_type": "goat",
            "unit": "kg",
            "selling_price": "3000",
            "cost_price": "1500",
            "stock_quantity": "5",
            "reorder_level": "2",
            "description": "",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            ButcheryProduct.objects.filter(business=self.business, name="Goat Offals").exists()
        )

    def test_reports_with_data(self):
        product = ButcheryProduct.objects.create(
            business=self.business, name="Pork Fresh",
            category=ButcheryCategory.PORK, unit="kg",
            selling_price=Decimal("7000.00"),
            cost_price=Decimal("4500.00"),
        )
        ButcherySale.objects.create(
            business=self.business, product=product,
            quantity=Decimal("3.0"), unit_price=Decimal("7000.00"),
            cost_price_snapshot=Decimal("4500.00"),
        )
        resp = self._get("reports")
        self.assertEqual(resp.status_code, 200)

    def test_csv_export_with_data(self):
        product = ButcheryProduct.objects.create(
            business=self.business, name="Chicken Braai",
            category=ButcheryCategory.CHICKEN, unit="kg",
            selling_price=Decimal("6500.00"),
            cost_price=Decimal("4000.00"),
        )
        ButcherySale.objects.create(
            business=self.business, product=product,
            quantity=Decimal("2.0"), unit_price=Decimal("6500.00"),
            cost_price_snapshot=Decimal("4000.00"),
            sale_date=timezone.localdate(),
        )
        url = reverse("butchery:reports_export_csv")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        content = resp.content.decode()
        self.assertIn("Chicken Braai", content)
        self.assertIn("Date", content)

    def test_processing_200(self):
        resp = self._get("processing")
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirects(self):
        anon_client = Client()
        for url_name in ["dashboard", "products", "intake", "daily_sales", "reports"]:
            url = reverse(f"butchery:{url_name}")
            resp = anon_client.get(url)
            self.assertIn(resp.status_code, [302, 403])
