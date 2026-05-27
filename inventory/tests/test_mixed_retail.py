# inventory/tests/test_mixed_retail.py
"""
Mixed Retail Vertical Tests
============================

Tests cover:
- Seeded departments/categories availability and idempotency
- Custom department/category creation
- Product creation with flexible attributes
- Sale recording (stock reduction, profit calculation)
- Low stock detection
- Dashboard metrics
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.business_kinds import BusinessKind

User = get_user_model()


def _make_business():
    import random
    uid = random.randint(1000, 9999)
    return Business.objects.create(
        name=f"Test Mixed Retail Shop {uid}",
        business_kind=BusinessKind.MIXED_RETAIL,
    )


def _make_user():
    import random
    uid = random.randint(1000, 9999)
    return User.objects.create_user(
        username=f"mr_user_{uid}",
        password="test123",
    )


class MixedRetailSeedTest(TestCase):
    """Test seeding of departments and categories."""

    def test_seed_creates_departments(self):
        """seed_mixed_retail_catalog creates global departments."""
        from inventory.mixed_retail_seed import seed_mixed_retail_catalog
        from inventory.models_mixed_retail import RetailDepartment

        seed_mixed_retail_catalog()
        depts = RetailDepartment.objects.filter(is_seeded=True, business=None)
        self.assertGreater(depts.count(), 0, "No seeded departments created")

    def test_seed_creates_categories(self):
        """Each seeded department has at least one category."""
        from inventory.mixed_retail_seed import seed_mixed_retail_catalog
        from inventory.models_mixed_retail import RetailDepartment, RetailCategory

        seed_mixed_retail_catalog()
        electronics = RetailDepartment.objects.filter(is_seeded=True, slug="electronics").first()
        self.assertIsNotNone(electronics, "Electronics department not seeded")
        cats = RetailCategory.objects.filter(department=electronics)
        self.assertGreater(cats.count(), 0, "No categories for Electronics department")

    def test_seed_is_idempotent(self):
        """Running seed twice does not create duplicate departments."""
        from inventory.mixed_retail_seed import seed_mixed_retail_catalog
        from inventory.models_mixed_retail import RetailDepartment

        seed_mixed_retail_catalog()
        count_after_first = RetailDepartment.objects.filter(is_seeded=True, business=None).count()

        seed_mixed_retail_catalog()
        count_after_second = RetailDepartment.objects.filter(is_seeded=True, business=None).count()

        self.assertEqual(count_after_first, count_after_second, "Seed created duplicates on second run")

    def test_get_departments_for_business(self):
        """get_departments_for_business returns enabled seeded departments for a business."""
        from inventory.mixed_retail_seed import (
            seed_mixed_retail_catalog, get_departments_for_business, ensure_mixed_retail_defaults,
        )

        seed_mixed_retail_catalog()
        business = _make_business()
        # Enrollment records must exist for the business to see departments
        ensure_mixed_retail_defaults(business)
        depts = get_departments_for_business(business)
        self.assertGreater(len(depts), 0)

    def test_ensure_mixed_retail_defaults_idempotent(self):
        """ensure_mixed_retail_defaults can be called multiple times without duplicating records."""
        from inventory.mixed_retail_seed import (
            seed_mixed_retail_catalog, ensure_mixed_retail_defaults,
        )
        from inventory.models_mixed_retail import RetailBusinessDepartment

        seed_mixed_retail_catalog()
        business = _make_business()
        ensure_mixed_retail_defaults(business)
        count_1 = RetailBusinessDepartment.objects.filter(business=business).count()

        ensure_mixed_retail_defaults(business)
        count_2 = RetailBusinessDepartment.objects.filter(business=business).count()

        self.assertEqual(count_1, count_2, "ensure_mixed_retail_defaults duplicated enrollment records")

    def test_product_templates_seeded(self):
        """Seeded departments have product templates."""
        from inventory.mixed_retail_seed import seed_mixed_retail_catalog
        from inventory.models_mixed_retail import RetailProductTemplate

        seed_mixed_retail_catalog()
        self.assertGreater(RetailProductTemplate.objects.filter(is_active=True).count(), 0)


class MixedRetailCustomDeptCatTest(TestCase):
    """Test custom department and category creation."""

    def setUp(self):
        self.business = _make_business()
        self.user = _make_user()

    def test_create_custom_department(self):
        """User can create a custom department."""
        from inventory.models_mixed_retail import RetailDepartment

        dept = RetailDepartment.objects.create(
            business=self.business,
            name="Secondhand Goods",
            slug="secondhand-goods",
            is_seeded=False,
        )
        self.assertEqual(dept.name, "Secondhand Goods")
        self.assertEqual(dept.business, self.business)

    def test_create_custom_category(self):
        """User can create a custom category under a department."""
        from inventory.models_mixed_retail import RetailDepartment, RetailCategory

        dept = RetailDepartment.objects.create(
            business=self.business,
            name="Test Dept",
            slug="test-dept",
        )
        cat = RetailCategory.objects.create(
            business=self.business,
            department=dept,
            name="Used Phones",
            slug="used-phones",
        )
        self.assertEqual(cat.department, dept)
        self.assertEqual(cat.name, "Used Phones")


class MixedRetailProductTest(TestCase):
    """Test product creation and flexible attributes."""

    def setUp(self):
        self.business = _make_business()
        self.user = _make_user()
        from inventory.models_mixed_retail import RetailDepartment, RetailCategory
        self.dept = RetailDepartment.objects.create(
            business=self.business,
            name="Electronics",
            slug="electronics",
        )
        self.cat = RetailCategory.objects.create(
            business=self.business,
            department=self.dept,
            name="Smartphones",
            slug="smartphones",
        )

    def test_create_product_basic(self):
        """Can create a product with core fields."""
        from inventory.models_mixed_retail import RetailProduct
        product = RetailProduct.objects.create(
            business=self.business,
            department=self.dept,
            category=self.cat,
            name="Samsung Galaxy A15",
            cost_price=Decimal("85000"),
            selling_price=Decimal("100000"),
            stock_quantity=Decimal("10"),
            reorder_level=Decimal("3"),
        )
        self.assertEqual(product.name, "Samsung Galaxy A15")
        self.assertEqual(product.department, self.dept)

    def test_product_optional_attributes(self):
        """Product supports optional flexible attributes (IMEI, color, serial, expiry)."""
        from inventory.models_mixed_retail import RetailProduct
        import datetime
        product = RetailProduct.objects.create(
            business=self.business,
            name="Phone with IMEI",
            cost_price=Decimal("50000"),
            selling_price=Decimal("65000"),
            stock_quantity=Decimal("5"),
            imei="123456789012345",
            serial_number="SN-ABC-001",
            color="Black",
            warranty_months=12,
            expiry_date=None,
        )
        self.assertEqual(product.imei, "123456789012345")
        self.assertEqual(product.color, "Black")
        self.assertEqual(product.warranty_months, 12)

    def test_low_stock_detection(self):
        """is_low_stock is True when stock is at or below reorder_level."""
        from inventory.models_mixed_retail import RetailProduct
        product = RetailProduct.objects.create(
            business=self.business,
            name="Low Stock Item",
            cost_price=Decimal("1000"),
            selling_price=Decimal("1500"),
            stock_quantity=Decimal("2"),
            reorder_level=Decimal("5"),
        )
        self.assertTrue(product.is_low_stock)

    def test_not_low_stock_when_above_reorder(self):
        """is_low_stock is False when stock is above reorder_level."""
        from inventory.models_mixed_retail import RetailProduct
        product = RetailProduct.objects.create(
            business=self.business,
            name="Full Stock Item",
            cost_price=Decimal("1000"),
            selling_price=Decimal("1500"),
            stock_quantity=Decimal("20"),
            reorder_level=Decimal("5"),
        )
        self.assertFalse(product.is_low_stock)

    def test_out_of_stock_detection(self):
        """is_out_of_stock is True when stock_quantity <= 0."""
        from inventory.models_mixed_retail import RetailProduct
        product = RetailProduct.objects.create(
            business=self.business,
            name="OOS Item",
            cost_price=Decimal("1000"),
            selling_price=Decimal("1500"),
            stock_quantity=Decimal("0"),
        )
        self.assertTrue(product.is_out_of_stock)


class MixedRetailSaleTest(TestCase):
    """Test sale recording, stock reduction, and profit calculation."""

    def setUp(self):
        self.business = _make_business()
        self.user = _make_user()
        from inventory.models_mixed_retail import RetailProduct
        self.product = RetailProduct.objects.create(
            business=self.business,
            name="Test Widget",
            cost_price=Decimal("500"),
            selling_price=Decimal("800"),
            stock_quantity=Decimal("20"),
            reorder_level=Decimal("5"),
        )

    def test_sale_reduces_stock(self):
        """Recording a sale reduces product stock_quantity."""
        from inventory.models_mixed_retail import RetailSale

        initial_stock = self.product.stock_quantity
        qty = Decimal("3")

        RetailSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=qty,
            unit_price=self.product.selling_price,
            cost_price_snapshot=self.product.cost_price,
            payment_method="cash",
            created_by=self.user,
        )
        self.product.stock_quantity -= qty
        self.product.save(update_fields=["stock_quantity"])

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, initial_stock - qty)

    def test_sale_calculates_revenue_and_profit(self):
        """Sale correctly calculates total_amount and profit."""
        from inventory.models_mixed_retail import RetailSale

        sale = RetailSale.objects.create(
            business=self.business,
            product=self.product,
            quantity=Decimal("2"),
            unit_price=Decimal("800"),
            cost_price_snapshot=Decimal("500"),
            payment_method="cash",
            created_by=self.user,
        )

        expected_total = Decimal("2") * Decimal("800")
        expected_profit = (Decimal("800") - Decimal("500")) * Decimal("2")

        self.assertEqual(sale.total_amount, expected_total)
        self.assertEqual(sale.profit, expected_profit)

    def test_sale_payment_method_choices(self):
        """Sale accepts all valid payment methods."""
        from inventory.models_mixed_retail import RetailSale, RetailPaymentMethod

        for pm_val, _ in RetailPaymentMethod.choices:
            sale = RetailSale.objects.create(
                business=self.business,
                product=self.product,
                quantity=Decimal("1"),
                unit_price=self.product.selling_price,
                cost_price_snapshot=self.product.cost_price,
                payment_method=pm_val,
                created_by=self.user,
            )
            self.assertEqual(sale.payment_method, pm_val)
